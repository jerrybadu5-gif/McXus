import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { PageHead } from "@/components/Layout";
import { useNames } from "@/components/Names";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Empty, ErrorLine, Loading } from "@/components/ui/states";
import { api, qs } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Deposit, User, Withdrawal } from "@/lib/types";
import { useLoad } from "@/lib/use";
import { cn, isMoney, kina, when } from "@/lib/utils";

export function MoneyPage() {
  const tab = (to: string, label: string) => (
    <NavLink to={to} end className={({ isActive }) => cn("border-b-2 px-3 py-2.5 text-sm font-medium", isActive ? "border-gold text-ink" : "border-transparent text-muted hover:text-ink")}>{label}</NavLink>
  );
  return (
    <>
      <PageHead title="Deposits & payouts" />
      <nav className="flex gap-1 border-b border-line bg-white px-6">{tab("/money", "Deposits to approve")}{tab("/money/payouts", "Withdrawals to pay")}</nav>
      <Routes>
        <Route path="" element={<Deposits />} />
        <Route path="payouts" element={<Payouts />} />
      </Routes>
    </>
  );
}

function Deposits() {
  const { me, notify } = useSession();
  const list = useLoad(() => api.get<Deposit[]>("/v1/admin/deposits?status=pending"), []);
  const names = useNames((list.data ?? []).flatMap((d) => [d.user_id, d.created_by]));
  const [recording, setRecording] = useState(false);

  async function decide(d: Deposit, approve: boolean) {
    try {
      await api.post(`/v1/admin/deposits/${d.id}/decision`, { approve });
      notify(approve ? `Approved: ${kina(d.amount)} added to ${names[d.user_id] ?? "the wallet"}` : "Deposit rejected");
      list.reload();
    } catch (e) { notify((e as Error).message, "error"); }
  }

  return (
    <section className="max-w-5xl px-6 py-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <p className="text-xs text-muted">A deposit adds Stars only when a second finance officer approves it. You can't approve one you recorded.</p>
        <Button onClick={() => setRecording(true)}>Record a bank deposit</Button>
      </div>
      {list.error ? <ErrorLine error={list.error} /> : !list.data ? <Loading /> : list.data.length === 0 ? <Empty title="No deposits waiting">Record one when money arrives in the trust account.</Empty> : (
        <table className="w-full overflow-hidden rounded-xl border border-line bg-white text-left">
          <thead className="bg-tint text-xs text-muted"><tr><th className="px-4 py-2 font-semibold">Customer</th><th className="px-4 py-2 font-semibold">Amount</th><th className="px-4 py-2 font-semibold">Reference</th><th className="px-4 py-2 font-semibold">Recorded by</th><th /></tr></thead>
          <tbody className="divide-y divide-line">
            {list.data.map((d) => (
              <tr key={d.id}>
                <td className="px-4 py-3 font-semibold text-ink">{names[d.user_id] ?? "…"}</td>
                <td className="num px-4 py-3 font-semibold text-ink">{kina(d.amount)}</td>
                <td className="px-4 py-3">{d.external_ref}<span className="block text-2xs text-muted">{d.method.replace("_", " ")} · {when(d.created_at)}</span></td>
                <td className="px-4 py-3">{d.created_by === me.id ? "You" : names[d.created_by] ?? "…"}</td>
                <td className="px-4 py-3 text-right">
                  {d.created_by === me.id ? <span className="text-2xs text-muted">Another officer approves</span> : (
                    <span className="inline-flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => decide(d, false)}>Reject</Button>
                      <Button size="sm" variant="gold" onClick={() => decide(d, true)}>Approve</Button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RecordDeposit open={recording} onClose={() => setRecording(false)} onDone={() => { setRecording(false); list.reload(); }} />
    </section>
  );
}

function RecordDeposit({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { notify } = useSession();
  const [q, setQ] = useState("");
  const [found, setFound] = useState<User[]>([]);
  const [who, setWho] = useState<User | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("bank_transfer");
  const [ref, setRef] = useState("");
  const [error, setError] = useState<unknown>();

  async function search() {
    try { setFound(await api.get<User[]>(`/v1/admin/users${qs({ q, limit: 8 })}`)); } catch (e) { setError(e); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!who) return;
    try {
      await api.post("/v1/admin/deposits", { user_id: who.id, amount: amount.trim(), method, external_ref: ref.trim() });
      notify(`Recorded ${kina(amount.trim())} for ${who.display_name || who.phone}. Another officer approves it.`);
      setWho(null); setAmount(""); setRef(""); setQ(""); setFound([]); onDone();
    } catch (err) { setError(err); }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title="Record a bank deposit" description="Use the bank statement line. Stars are added after a second officer approves.">
      <form className="space-y-4" onSubmit={save}>
        {!who ? (
          <Field label="Customer (phone or name)">
            <div className="flex gap-2">
              <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); search(); } }} />
              <Button type="button" variant="outline" onClick={search}>Find</Button>
            </div>
            <ul className="mt-2 divide-y divide-line rounded-lg border border-line empty:hidden">
              {found.map((u) => <li key={u.id}><button type="button" className="w-full px-3 py-2 text-left hover:bg-tint" onClick={() => setWho(u)}>{u.display_name || "No name"} <span className="text-muted">{u.phone}</span></button></li>)}
            </ul>
          </Field>
        ) : (
          <p className="rounded-lg bg-tint px-3 py-2">For <b className="text-ink">{who.display_name || "No name"}</b> {who.phone} <button type="button" className="ml-2 text-xs underline" onClick={() => setWho(null)}>change</button></p>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Amount (K)"><Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="150.00" /></Field>
          <Field label="How it arrived">
            <Select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="bank_transfer">Bank transfer</option><option value="cash_agent">Cash agent</option><option value="mobile_money">Mobile money</option>
            </Select>
          </Field>
        </div>
        <Field label="Bank reference"><Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="BSP 88812" /></Field>
        {!!error && <ErrorLine error={error} />}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={!who || !isMoney(amount) || ref.trim().length < 3}>Record deposit</Button>
        </div>
      </form>
    </Dialog>
  );
}

function Payouts() {
  const { notify } = useSession();
  const list = useLoad(() => api.get<Withdrawal[]>("/v1/admin/withdrawals?status=requested"), []);
  const names = useNames((list.data ?? []).map((w) => w.user_id));
  const [paying, setPaying] = useState<Withdrawal | null>(null);
  const [ref, setRef] = useState("");

  async function settle(w: Withdrawal, paid: boolean) {
    try {
      await api.post(`/v1/admin/withdrawals/${w.id}/settle`, { paid, bank_ref: paid ? ref.trim() : null });
      notify(paid ? `Marked paid: ${kina(w.amount)}` : "Marked failed; the Stars went back to the wallet");
      setPaying(null); setRef(""); list.reload();
    } catch (e) { notify((e as Error).message, "error"); }
  }

  return (
    <section className="max-w-5xl px-6 py-5">
      <p className="mb-4 text-xs text-muted">Pay each withdrawal from the trust account by bank transfer, then mark it paid with the bank reference.</p>
      {list.error ? <ErrorLine error={list.error} /> : !list.data ? <Loading /> : list.data.length === 0 ? <Empty title="No withdrawals waiting" /> : (
        <table className="w-full overflow-hidden rounded-xl border border-line bg-white text-left">
          <thead className="bg-tint text-xs text-muted"><tr><th className="px-4 py-2 font-semibold">Customer</th><th className="px-4 py-2 font-semibold">Pay</th><th className="px-4 py-2 font-semibold">To account</th><th /></tr></thead>
          <tbody className="divide-y divide-line">
            {list.data.map((w) => (
              <tr key={w.id}>
                <td className="px-4 py-3 font-semibold text-ink">{names[w.user_id] ?? "…"}<span className="block text-2xs font-normal text-muted">{when(w.created_at)}</span></td>
                <td className="num px-4 py-3 font-semibold text-ink">{kina(w.amount)}<span className="block text-2xs font-normal text-muted">fee {kina(w.fee)}</span></td>
                <td className="px-4 py-3">{w.bank_account}</td>
                <td className="px-4 py-3 text-right"><span className="inline-flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => settle(w, false)}>Failed</Button>
                  <Button size="sm" variant="gold" onClick={() => setPaying(w)}>Mark paid</Button>
                </span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Dialog open={!!paying} onOpenChange={(o) => !o && setPaying(null)} title="Mark as paid" description={paying ? `${kina(paying.amount)} to ${paying.bank_account}` : ""}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (paying) settle(paying, true); }}>
          <Field label="Bank reference of the transfer"><Input autoFocus value={ref} onChange={(e) => setRef(e.target.value)} /></Field>
          <div className="flex justify-end"><Button variant="gold" disabled={ref.trim().length < 3}>Mark paid</Button></div>
        </form>
      </Dialog>
    </section>
  );
}
