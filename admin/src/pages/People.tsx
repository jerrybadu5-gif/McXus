import { useEffect, useState } from "react";
import { Link, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { PageHead } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Empty, ErrorLine, Loading } from "@/components/ui/states";
import { api, qs } from "@/lib/api";
import { ROLE_NAMES, useSession } from "@/lib/session";
import type { Order, Profile, Role, User } from "@/lib/types";
import { useDebounced, useLoad } from "@/lib/use";
import { cn, kina, when } from "@/lib/utils";

const TIERS = ["T0 Chat only", "T1 Basic (buy)", "T2 Verified (buy, sell, withdraw)", "T3 Registered seller"];

export function PeoplePage() {
  return (
    <Routes>
      <Route path="" element={<Search />} />
      <Route path=":userId" element={<Search />} />
    </Routes>
  );
}

function Search() {
  const { userId } = useParams();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const staffOnly = params.get("role") === "staff";
  const [text, setText] = useState(q);
  const typed = useDebounced(text.trim(), 250);
  // Search as you type (any case, words in any order); the address keeps the search for back/forward.
  useEffect(() => {
    if (typed === q) return;
    if (typed) params.set("q", typed); else params.delete("q");
    setParams(params, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed]);
  const list = useLoad(() => api.get<User[]>(`/v1/admin/users${qs({ q, role: staffOnly ? "staff" : undefined })}`), [q, staffOnly]);

  return (
    <>
      <PageHead title="People" />
      <div className="grid lg:grid-cols-[360px_1fr]">
        <section className="border-r border-line bg-white">
          <form className="border-b border-line p-4" onSubmit={(e) => e.preventDefault()} role="search">
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a name, phone or id" aria-label="Search people" autoFocus />
            <p className="mt-1 text-2xs text-muted">Suggestions appear as you type. Not case-sensitive.</p>
          </form>
          <label className="flex items-center gap-2 px-4 py-2 text-xs">
            <input type="checkbox" checked={staffOnly} onChange={(e) => { if (e.target.checked) params.set("role", "staff"); else params.delete("role"); setParams(params); }} />
            Staff only
          </label>
          {list.error ? <div className="p-4"><ErrorLine error={list.error} /></div> : !list.data ? <Loading /> : list.data.length === 0 ? <Empty title="Nobody found" /> : (
            <ul className="divide-y divide-line">
              {list.data.map((u) => (
                <li key={u.id}>
                  <Link to={`/people/${u.id}${params.toString() ? `?${params}` : ""}`} className={cn("block px-4 py-3 hover:bg-tint", u.id === userId && "bg-tint")}>
                    <p className="font-semibold text-ink">{u.display_name || "No name"}{u.status === "frozen" && <Badge tone="late" className="ml-2">Frozen</Badge>}</p>
                    <p className="text-xs text-muted">{u.phone} · T{u.kyc_tier}{u.role !== "user" && ` · ${ROLE_NAMES[u.role]}`}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>{userId ? <Person id={userId} onChanged={list.reload} /> : <div className="hidden lg:block"><Empty title="Find someone">Search by phone number, name or account id.</Empty></div>}</section>
      </div>
    </>
  );
}

function Person({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { me, notify } = useSession();
  const p = useLoad(() => api.get<Profile>(`/v1/admin/users/${id}`), [id]);
  const orders = useLoad(() => api.get<Order[]>(`/v1/admin/orders${qs({ user_id: id, limit: 20 })}`), [id]);
  const [dialog, setDialog] = useState<"tier" | "role" | "status" | null>(null);
  if (p.error) return <div className="p-6"><ErrorLine error={p.error} /></div>;
  if (!p.data) return <Loading />;
  const u = p.data.user;
  const isAdmin = me.role === "admin";
  const done = (text: string) => { notify(text); setDialog(null); p.reload(); onChanged(); };

  return (
    <article className="max-w-3xl space-y-6 px-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold">{u.display_name || "No name"}</h2>
          <p className="text-xs text-muted">{u.phone} · joined {when(p.data.created_at)} · id {u.id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(isAdmin || me.role === "kyc") && <Button size="sm" variant="outline" onClick={() => setDialog("tier")}>Change verification</Button>}
          {isAdmin && <Button size="sm" variant="outline" onClick={() => setDialog("role")}>Change staff role</Button>}
          {(isAdmin || me.role === "compliance") && u.id !== me.id && (
            <Button size="sm" variant={u.status === "frozen" ? "gold" : "danger"} onClick={() => setDialog("status")}>{u.status === "frozen" ? "Unfreeze" : "Freeze account"}</Button>
          )}
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
        {[
          ["Wallet", kina(p.data.wallet)], ["Owes in penalties", kina(p.data.penalties_owed)],
          ["Verification", `T${u.kyc_tier}`], ["Status", u.status === "frozen" ? "Frozen" : "Active"],
          ["Bought", String(p.data.orders_as_buyer)], ["Sold", `${p.data.orders_as_seller} (${p.data.completed_sales} completed)`],
          ["Disputes", String(p.data.disputes)], ["Trust", `${p.data.trust_badge} (score ${p.data.trust_score})`],
        ].map(([k, v]) => (
          <div key={k} className="bg-white px-4 py-3"><dt className="text-2xs text-muted">{k}</dt><dd className="num mt-0.5 font-semibold text-ink">{v}</dd></div>
        ))}
      </dl>
      <section>
        <h3 className="mb-2 font-bold">Recent orders</h3>
        {orders.error ? <ErrorLine error={orders.error} /> : !orders.data ? <Loading /> : orders.data.length === 0 ? <p className="text-muted">No orders yet.</p> : (
          <ul className="divide-y divide-line rounded-xl border border-line bg-white">
            {orders.data.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span><b className="text-ink">{o.title}</b> <span className="text-xs text-muted">{o.buyer_id === u.id ? "bought" : "sold"} · {when(o.created_at)}</span></span>
                <span className="flex items-center gap-2">
                  <span className="num font-semibold text-ink">{kina(o.amount)}</span>
                  {o.status === "DISPUTED" ? <Link to={`/disputes/${o.id}`}><Badge tone="gold">Disputed</Badge></Link> : <Badge>{o.status.toLowerCase().replace("_", " ")}</Badge>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <TierDialog open={dialog === "tier"} user={u} onClose={() => setDialog(null)} onDone={done} />
      <RoleDialog open={dialog === "role"} user={u} onClose={() => setDialog(null)} onDone={done} />
      <StatusDialog open={dialog === "status"} user={u} onClose={() => setDialog(null)} onDone={done} />
    </article>
  );
}

type DialogProps = { open: boolean; user: User; onClose: () => void; onDone: (text: string) => void };

function TierDialog({ open, user, onClose, onDone }: DialogProps) {
  const [tier, setTier] = useState(user.kyc_tier);
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>();
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title="Change verification level" description="Record what you checked. It is kept in the staff activity log.">
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        try { await api.post(`/v1/admin/users/${user.id}/kyc-tier`, { kyc_tier: tier, note }); onDone(`Verification set to T${tier}`); } catch (err) { setError(err); }
      }}>
        <Field label="Level"><Select value={tier} onChange={(e) => setTier(Number(e.target.value))}>{TIERS.map((t, i) => <option key={t} value={i}>{t}</option>)}</Select></Field>
        <Field label="What you checked"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="NID matches selfie; ward councillor letter" /></Field>
        {!!error && <ErrorLine error={error} />}
        <div className="flex justify-end"><Button disabled={note.trim().length < 3 || tier === user.kyc_tier}>Set T{tier}</Button></div>
      </form>
    </Dialog>
  );
}

function RoleDialog({ open, user, onClose, onDone }: DialogProps) {
  const [role, setRole] = useState<Role>(user.role);
  const [error, setError] = useState<unknown>();
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title="Change staff role" description="Staff roles open parts of this console. Customer means no staff access.">
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        try { await api.post(`/v1/admin/users/${user.id}/role`, { role }); onDone(`Role set to ${ROLE_NAMES[role]}`); } catch (err) { setError(err); }
      }}>
        <Field label="Role"><Select value={role} onChange={(e) => setRole(e.target.value as Role)}>{(Object.keys(ROLE_NAMES) as Role[]).map((r) => <option key={r} value={r}>{ROLE_NAMES[r]}</option>)}</Select></Field>
        {!!error && <ErrorLine error={error} />}
        <div className="flex justify-end"><Button disabled={role === user.role}>Make {ROLE_NAMES[role]}</Button></div>
      </form>
    </Dialog>
  );
}

function StatusDialog({ open, user, onClose, onDone }: DialogProps) {
  const freezing = user.status !== "frozen";
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>();
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} title={freezing ? "Freeze this account" : "Unfreeze this account"}
      description={freezing ? "They can't sign in or move Stars until it is unfrozen. Their Stars stay where they are." : "They can sign in and use their wallet again."}>
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        try { await api.post(`/v1/admin/users/${user.id}/status`, { status: freezing ? "frozen" : "active", reason }); onDone(freezing ? "Account frozen" : "Account unfrozen"); } catch (err) { setError(err); }
      }}>
        <Field label="Reason" hint="Kept in the staff activity log."><Textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {!!error && <ErrorLine error={error} />}
        <div className="flex justify-end"><Button variant={freezing ? "danger" : "gold"} disabled={reason.trim().length < 5}>{freezing ? "Freeze account" : "Unfreeze account"}</Button></div>
      </form>
    </Dialog>
  );
}
