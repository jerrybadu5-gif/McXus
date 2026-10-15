import { Check, Image as ImageIcon, MessageSquareText, UserCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PageHead } from "@/components/Layout";
import { StageTrack } from "@/components/StageTrack";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Empty, ErrorLine, Loading } from "@/components/ui/states";
import { api, qs } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Dispute, DisputeSummary, Stage } from "@/lib/types";
import { useLoad } from "@/lib/use";
import { cn, compareMoney, isMoney, kina, minus, until, when } from "@/lib/utils";

const TABS: { stage: Stage | ""; label: string }[] = [
  { stage: "", label: "Open" },
  { stage: "mediation", label: "Need a mediator" },
  { stage: "appeal", label: "Appeals" },
  { stage: "negotiation", label: "Negotiating" },
  { stage: "decided", label: "Decided, appeal window" },
  { stage: "resolved", label: "Resolved" },
];

export const STAGE_NAMES: Record<Stage, string> = {
  negotiation: "Negotiating", mediation: "With a mediator", decided: "Decided", appeal: "Appeal", resolved: "Resolved",
};

export function DisputesPage() {
  return (
    <Routes>
      <Route path="" element={<Queue />} />
      <Route path=":orderId" element={<Queue />} />
    </Routes>
  );
}

function Queue() {
  const { orderId } = useParams();
  const [params, setParams] = useSearchParams();
  const stage = (params.get("stage") ?? "") as Stage | "";
  const mine = params.get("mine") === "1";
  const list = useLoad(() => api.get<DisputeSummary[]>(`/v1/admin/disputes${qs({ stage, mine })}`), [stage, mine]);

  return (
    <>
      <PageHead title="Disputes">
        <label className="flex items-center gap-2 text-xs text-body">
          <input type="checkbox" checked={mine} onChange={(e) => { params.set("mine", e.target.checked ? "1" : "0"); setParams(params); }} />
          Only cases I took
        </label>
      </PageHead>
      <div className="flex gap-1 overflow-x-auto border-b border-line bg-white px-6" role="tablist">
        {TABS.map((t) => (
          <button key={t.label} role="tab" aria-selected={stage === t.stage}
            onClick={() => { if (t.stage) params.set("stage", t.stage); else params.delete("stage"); setParams(params); }}
            className={cn("whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium", stage === t.stage ? "border-gold text-ink" : "border-transparent text-muted hover:text-ink")}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="grid min-h-[calc(100vh-130px)] lg:grid-cols-[380px_1fr]">
        <section aria-label="Queue" className="border-r border-line bg-white">
          {list.error ? <div className="p-4"><ErrorLine error={list.error} /></div> : !list.data ? <Loading /> :
            list.data.length === 0 ? <Empty title="No disputes here">Buyers and sellers open disputes from an order in the app.</Empty> : (
              <ul className="divide-y divide-line">
                {list.data.map((d) => (
                  <li key={d.id}>
                    <Link to={`/disputes/${d.order_id}${params.toString() ? `?${params}` : ""}`}
                      className={cn("block px-5 py-3.5 hover:bg-tint", d.order_id === orderId && "bg-tint")}>
                      <div className="flex items-start justify-between gap-3">
                        <p className="font-semibold text-ink">{d.title}</p>
                        <span className="num font-semibold text-ink">{kina(d.amount)}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-1 text-xs text-muted">{d.reason}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Badge tone={d.stage === "appeal" || d.stage === "mediation" ? "gold" : d.stage === "resolved" ? "ok" : "plain"}>{STAGE_NAMES[d.stage]}</Badge>
                        {d.overdue && <Badge tone="late">Mediator deadline passed</Badge>}
                        {d.deadline && !d.overdue && <span className="text-2xs text-muted">{until(d.deadline)}</span>}
                        {d.mediator && <span className="text-2xs text-muted">· {d.mediator}</span>}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
        </section>
        <section aria-label="Case" className="min-w-0" id="case">
          {orderId ? <Case orderId={orderId} onChanged={list.reload} /> :
            <div className="hidden lg:block"><Empty title="Choose a dispute">Cases past the mediator deadline are at the top, then the nearest deadline.</Empty></div>}
        </section>
      </div>
    </>
  );
}

function Case({ orderId, onChanged }: { orderId: string; onChanged: () => void }) {
  const { notify } = useSession();
  const { data: d, error, setData } = useLoad(() => api.get<Dispute>(`/v1/admin/disputes/${orderId}`), [orderId]);
  const [deciding, setDeciding] = useState<"decide" | "final" | null>(null);
  const navigate = useNavigate();

  if (error) return <div className="p-6"><ErrorLine error={error} /></div>;
  if (!d) return <Loading />;

  const act = async (path: string, done: string, body?: unknown) => {
    try {
      setData(await api.post<Dispute>(`/v1/admin/disputes/${orderId}/${path}`, body));
      notify(done); onChanged();
    } catch (e) { notify((e as Error).message, "error"); throw e; }
  };

  return (
    <article className="mx-auto max-w-4xl space-y-6 px-6 py-6">
      <header className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold">{d.title}</h2>
            <p className="text-xs text-muted">
              Order {d.order_id.slice(0, 8)} · opened by the {d.opened_by} {when(d.opened_at)}
              {" · "}<button className="underline" onClick={() => navigate(`/people/${d.buyer.id}`)}>buyer {d.buyer.name}</button>
              {" · "}<button className="underline" onClick={() => navigate(`/people/${d.seller.id}`)}>seller {d.seller.name}</button>
            </p>
          </div>
          <p className="num text-2xl font-bold text-ink" title="Frozen in escrow">{kina(d.amount)}</p>
        </div>
        <StageTrack dispute={d} />
      </header>

      <Actions d={d} onTake={() => act("take", "You took the case")} onDecide={setDeciding} />

      {d.resolution && (
        <section className="rounded-xl border border-ok/30 bg-ok-soft px-4 py-3">
          <p className="font-semibold text-ok">Resolved ({d.resolution.outcome === "agreed" ? "buyer and seller agreed" : d.resolution.outcome === "senior" ? "appeal decision" : "mediator's decision"})</p>
          <p className="num mt-1 text-ink">Buyer got back {kina(d.resolution.buyer_refund)}; seller {kina(d.resolution.seller_gets)} before the escrow fee.</p>
          {d.resolution.note && <p className="mt-1 text-xs text-body">{d.resolution.note}</p>}
        </section>
      )}
      {d.decision && !d.resolution && (
        <section className="rounded-xl border border-line bg-white px-4 py-3">
          <p className="font-semibold text-ink">Mediator's decision: buyer gets back <span className="num">{kina(d.decision.buyer_refund)}</span></p>
          <p className="mt-1 text-xs text-body">{d.decision.note}</p>
          <p className="mt-2 text-2xs text-muted">
            Buyer {d.decision.buyer_accepted ? "accepted" : "has not accepted"} · seller {d.decision.seller_accepted ? "accepted" : "has not accepted"}
            {d.stage === "decided" && ` · final ${when(d.appeal_until)} unless someone appeals`}
          </p>
        </section>
      )}
      {d.appeal && (
        <section className="rounded-xl border border-gold/40 bg-gold-soft px-4 py-3">
          <p className="font-semibold text-gold-ink">The {d.appeal.by} appealed {when(d.appeal.at)}</p>
          <p className="mt-1 text-sm text-ink">{d.appeal.reason}</p>
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Evidence d={d} side="buyer" />
        <Evidence d={d} side="seller" />
      </div>

      {d.offers.length > 0 && (
        <section>
          <h3 className="mb-2 font-bold">Offers between them</h3>
          <ul className="divide-y divide-line rounded-xl border border-line bg-white">
            {d.offers.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span>The {o.by} offered: buyer gets back <span className="num font-semibold text-ink">{kina(o.buyer_refund)}</span>{o.note && <span className="text-muted"> — {o.note}</span>}</span>
                <Badge tone={o.status === "accepted" ? "ok" : o.status === "open" ? "gold" : "plain"}>{o.status}</Badge>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 font-bold">What happened</h3>
        <ol className="space-y-2 border-l-2 border-line pl-4">
          {d.timeline.map((t, i) => (
            <li key={i} className="text-xs">
              <span className="text-muted">{when(t.at)}</span> <span className="font-semibold text-ink">{t.by === "McXus" ? "McXus" : `The ${t.by}`}</span> {EVENT_TEXT[t.kind] ?? t.kind}
              {t.text && <span className="text-body">: {t.text}</span>}
            </li>
          ))}
        </ol>
      </section>

      <DecideDialog d={d} mode={deciding} onClose={() => setDeciding(null)}
        onSubmit={(refund, note) => act(deciding === "final" ? "final" : "decide", deciding === "final" ? "Final decision made; the money has moved" : "Decision sent to both parties", { buyer_refund: refund, note }).then(() => setDeciding(null))} />
    </article>
  );
}

const EVENT_TEXT: Record<string, string> = {
  opened: "opened the dispute", offer: "made an offer", offer_rejected: "rejected an offer", offer_withdrawn: "withdrew an offer",
  offer_accepted: "accepted an offer", escalated: "sent it to a mediator", assigned: "took the case", statement: "added a statement",
  photo: "added a photo", decided: "decided", accepted: "accepted the decision", appealed: "appealed", resolved: "closed it",
};

function Actions({ d, onTake, onDecide }: { d: Dispute; onTake: () => void; onDecide: (m: "decide" | "final") => void }) {
  const { me } = useSession();
  const a = new Set(d.actions);
  const tookIt = d.mediator_id === me.id;
  if (a.size === 0) {
    if (d.stage === "appeal") return <p className="text-xs text-muted">A compliance officer or admin who did not make the first decision decides this appeal.</p>;
    if (d.stage === "decided") return <p className="text-xs text-muted">Waiting for the appeal window to end. Nothing to do.</p>;
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-navy px-4 py-3 text-white">
      <p className="mr-auto text-sm">
        {d.stage === "appeal" ? "Make the final decision. It can't be appealed." :
          d.stage === "negotiation" ? "Buyer and seller are still negotiating. You can take the case now." :
          tookIt ? "Your case. Read both sides, then decide." : "Take the case so others know you're on it."}
      </p>
      {a.has("take_case") && !tookIt && <Button variant="outline" size="sm" onClick={onTake}><UserCheck size={14} />Take the case</Button>}
      {a.has("decide") && <Button variant="gold" size="sm" onClick={() => onDecide("decide")}>Decide the refund</Button>}
      {a.has("final_decision") && <Button variant="gold" size="sm" onClick={() => onDecide("final")}>Make the final decision</Button>}
    </div>
  );
}

function Evidence({ d, side }: { d: Dispute; side: "buyer" | "seller" }) {
  const items = d.evidence.filter((e) => e.by === side);
  const name = side === "buyer" ? d.buyer.name : d.seller.name;
  return (
    <section>
      <h3 className="mb-2 font-bold">{side === "buyer" ? "Buyer" : "Seller"}'s side <span className="font-normal text-muted">({name})</span></h3>
      {items.length === 0 ? <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-xs text-muted">Nothing added yet.</p> : (
        <ul className="space-y-2">
          {items.map((e) => (
            <li key={e.id} className="rounded-xl border border-line bg-white p-3">
              <p className="mb-1 flex items-center gap-1.5 text-2xs text-muted">
                {e.kind === "photo" ? <ImageIcon size={12} /> : <MessageSquareText size={12} />}{when(e.at)}
              </p>
              {e.kind === "photo" && e.file && <EvidencePhoto path={e.file} alt={e.text || `Photo from the ${side}`} />}
              {e.text && <p className="whitespace-pre-wrap text-sm text-ink">{e.text}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Evidence photos need the staff sign-in, so they are fetched with the token and shown from memory. */
function EvidencePhoto({ path, alt }: { path: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoke = "";
    api.blob(path).then((b) => { revoke = URL.createObjectURL(b); setUrl(revoke); }, () => setFailed(true));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [path]);
  if (failed) return <p className="text-xs text-late">The photo could not be loaded.</p>;
  if (!url) return <div className="h-40 animate-pulse rounded-lg bg-tint" />;
  return <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={alt} className="mb-2 max-h-72 rounded-lg object-contain" /></a>;
}

export function DecideDialog({ d, mode, onClose, onSubmit }: {
  d: Dispute; mode: "decide" | "final" | null; onClose: () => void; onSubmit: (refund: string, note: string) => Promise<void>;
}) {
  const [refund, setRefund] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (mode) { setRefund(d.decision?.buyer_refund ?? ""); setNote(""); } }, [mode, d.decision?.buyer_refund]);
  const valid = isMoney(refund) && compareMoney(refund, d.amount) <= 0 && note.trim().length >= 5;
  const presets = [{ label: "Full refund", value: d.amount }, { label: "Half", value: half(d.amount) }, { label: "Nothing back", value: "0.00" }];

  return (
    <Dialog open={mode !== null} onOpenChange={(o) => !o && onClose()}
      title={mode === "final" ? "Final decision on the appeal" : "Decide the refund"}
      description={mode === "final" ? "This is final and moves the money now." :
        "Both parties see this. It becomes final after 3 days unless one of them appeals, or sooner if both accept."}>
      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true);
        try { await onSubmit(refund.trim(), note.trim()); } catch { /* shown as a message */ } finally { setBusy(false); }
      }}>
        <Field label={`Buyer gets back (of ${kina(d.amount)})`}>
          <Input inputMode="decimal" value={refund} onChange={(e) => setRefund(e.target.value)} placeholder="0.00" autoFocus />
        </Field>
        <div className="flex gap-2">
          {presets.map((p) => <Button key={p.label} type="button" variant="outline" size="sm" onClick={() => setRefund(p.value)}>{p.label}</Button>)}
        </div>
        {isMoney(refund) && compareMoney(refund, d.amount) <= 0 && (
          <p className="num rounded-lg bg-tint px-3 py-2 text-xs text-ink">Buyer {kina(refund)} · seller {kina(minus(d.amount, refund))} (less the 3% escrow fee)</p>
        )}
        {isMoney(refund) && compareMoney(refund, d.amount) > 0 && <p className="text-xs text-late">The refund can't be more than the order ({kina(d.amount)}).</p>}
        <Field label="Reason" hint="Shown to the buyer and the seller. At least 5 characters.">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What the evidence shows and why" />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="gold" disabled={!valid || busy}><Check size={14} />
            {valid ? `Decide: buyer gets ${kina(refund)} back` : "Decide"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function half(amount: string): string {
  const cents = Math.round(Number(amount.replace(".", "")) / 2);
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}
