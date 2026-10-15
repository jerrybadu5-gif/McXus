import { LockOpen, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHead } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";
import { Empty, ErrorLine, Loading } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { FreezeCase } from "@/lib/types";
import { useLoad } from "@/lib/use";
import { cn, when } from "@/lib/utils";

const STATUS: Record<FreezeCase["status"], string> = {
  frozen: "Frozen, no appeal", appealed: "Appeal waiting", unfrozen: "Unfrozen", upheld: "Appeal refused",
};

/**
 * Frozen accounts to verify: appeals first. Unfreezing, or refusing an appeal, must be done by someone other
 * than the person who froze the account (the API enforces it too).
 */
export function FreezesPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("show") === "closed" ? "closed" : "open";
  const list = useLoad(() => api.get<FreezeCase[]>(`/v1/admin/freezes?status=${tab}`), [tab]);
  const [deciding, setDeciding] = useState<{ c: FreezeCase; unfreeze: boolean } | null>(null);

  return (
    <>
      <PageHead title="Frozen accounts" />
      <div className="flex gap-1 border-b border-line bg-white px-6" role="tablist">
        {(["open", "closed"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => { params.set("show", t); setParams(params); }}
            className={cn("border-b-2 px-3 py-2.5 text-sm font-medium", tab === t ? "border-gold text-ink" : "border-transparent text-muted hover:text-ink")}>
            {t === "open" ? "Still frozen" : "Decided"}
          </button>
        ))}
      </div>
      <section className="max-w-4xl space-y-3 px-6 py-5">
        <p className="text-xs text-muted">
          A frozen person can sign in only to read why and send one appeal. Someone other than the staff member who froze the
          account decides: unfreeze it, or keep it frozen with a reason they will read.
        </p>
        {list.error ? <ErrorLine error={list.error} /> : !list.data ? <Loading /> :
          list.data.length === 0 ? <Empty title={tab === "open" ? "No frozen accounts" : "Nothing decided yet"}>Freeze an account from People.</Empty> : (
            <ul className="space-y-3">
              {list.data.map((c) => <CaseCard key={c.id} c={c} onDecide={(unfreeze) => setDeciding({ c, unfreeze })} />)}
            </ul>
          )}
      </section>
      <DecideDialog value={deciding} onClose={() => setDeciding(null)} onDone={() => { setDeciding(null); list.reload(); }} />
    </>
  );
}

function CaseCard({ c, onDecide }: { c: FreezeCase; onDecide: (unfreeze: boolean) => void }) {
  const { me } = useSession();
  const mine = c.frozen_by_id === me.id;
  const open = c.status === "frozen" || c.status === "appealed";
  return (
    <li className={cn("rounded-xl border bg-white p-4", c.status === "appealed" ? "border-gold" : "border-line")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/people/${c.user.id}`} className="font-semibold text-ink underline-offset-2 hover:underline">{c.user.name}</Link>
          <span className="ml-2 text-xs text-muted">{c.user.phone}</span>
          <p className="text-2xs text-muted">Frozen {when(c.frozen_at)}{c.frozen_by ? ` by ${c.frozen_by}` : ""}</p>
        </div>
        <Badge tone={c.status === "appealed" ? "gold" : c.status === "unfrozen" ? "ok" : c.status === "upheld" ? "late" : "plain"}>{STATUS[c.status]}</Badge>
      </div>
      <p className="mt-3 text-sm text-ink"><span className="text-muted">Why: </span>{c.reason}</p>
      {c.appeal_text && (
        <div className="mt-3 rounded-lg bg-gold-soft px-3 py-2">
          <p className="text-2xs font-semibold text-gold-ink">Their appeal · {when(c.appealed_at)}</p>
          <p className="text-sm text-ink">{c.appeal_text}</p>
        </div>
      )}
      {c.decision_note && (
        <p className="mt-3 text-sm"><span className="text-muted">Decision{c.decided_by ? ` by ${c.decided_by}` : ""} · {when(c.decided_at)}: </span>{c.decision_note}</p>
      )}
      {open && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {mine ? (
            <p className="flex items-center gap-1.5 text-xs text-muted"><ShieldAlert size={14} />You froze this account, so another compliance officer or admin decides.</p>
          ) : (
            <>
              <Button size="sm" variant="gold" onClick={() => onDecide(true)}><LockOpen size={14} />Unfreeze</Button>
              {c.status === "appealed" && <Button size="sm" variant="outline" onClick={() => onDecide(false)}>Keep frozen</Button>}
            </>
          )}
        </div>
      )}
    </li>
  );
}

function DecideDialog({ value, onClose, onDone }: { value: { c: FreezeCase; unfreeze: boolean } | null; onClose: () => void; onDone: () => void }) {
  const { notify } = useSession();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const unfreeze = value?.unfreeze ?? true;
  return (
    <Dialog open={!!value} onOpenChange={(o) => { if (!o) { onClose(); setNote(""); setError(undefined); } }}
      title={unfreeze ? `Unfreeze ${value?.c.user.name ?? ""}` : "Keep the account frozen"}
      description={unfreeze ? "They can sign in and use their wallet again." : "They will read your reason. They cannot appeal again."}>
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        if (!value) return;
        setBusy(true); setError(undefined);
        try {
          await api.post(`/v1/admin/freezes/${value.c.id}/decide`, { unfreeze, note: note.trim() });
          notify(unfreeze ? "Account unfrozen" : "Kept frozen; they can read your reason");
          setNote(""); onDone();
        } catch (err) { setError(err); } finally { setBusy(false); }
      }}>
        <Field label={unfreeze ? "What you checked" : "Why it stays frozen"} hint="Shown to the person and kept in the staff activity log.">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
        </Field>
        {!!error && <ErrorLine error={error} />}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant={unfreeze ? "gold" : "danger"} disabled={busy || note.trim().length < 5}>{unfreeze ? "Unfreeze" : "Keep frozen"}</Button>
        </div>
      </form>
    </Dialog>
  );
}
