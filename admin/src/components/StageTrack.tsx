import type { Dispute } from "@/lib/types";
import { cn, until, when } from "@/lib/utils";

/**
 * The dispute's three stages and where it is now, with the live deadline. The one bold element of the console:
 * staff read a case's urgency from it at a glance.
 */
export function StageTrack({ dispute: d, now = new Date() }: { dispute: Dispute; now?: Date }) {
  const order = ["negotiation", "mediation", "decided", "appeal", "resolved"] as const;
  const at = order.indexOf(d.stage);
  const steps = [
    { key: "negotiation", label: "Buyer and seller negotiate", due: d.negotiate_until, rule: "3 days" },
    { key: "mediation", label: "Mediator decides", due: d.mediator_due, rule: "5 PNG working days" },
    { key: "appeal", label: d.stage === "appeal" ? "Senior decides the appeal" : "Appeal window", due: d.stage === "decided" ? d.appeal_until : null, rule: "3 days to appeal" },
  ];
  const stepIndex = d.stage === "negotiation" ? 0 : d.stage === "mediation" ? 1 : d.stage === "resolved" ? 3 : 2;

  return (
    <ol className="grid grid-cols-3 overflow-hidden rounded-xl border border-line bg-white" aria-label="Dispute stages">
      {steps.map((s, i) => {
        const done = i < stepIndex || at === 4;
        const current = i === stepIndex && at !== 4;
        const late = current && s.due !== null && new Date(s.due) <= now && d.stage === "mediation";
        return (
          <li key={s.key} aria-current={current ? "step" : undefined}
            className={cn("relative border-r border-line px-4 py-3 last:border-r-0",
              current && (late ? "bg-late-soft" : "bg-gold-soft"), done && "bg-white")}>
            <div className={cn("absolute inset-x-0 top-0 h-1", done ? "bg-ok" : current ? (late ? "bg-late" : "bg-gold") : "bg-line")} />
            <p className={cn("text-2xs", current ? "font-semibold text-ink" : "text-muted")}>{done ? "Done" : current ? "Now" : "Next"}: {s.rule}</p>
            <p className={cn("mt-0.5 font-semibold", current ? "text-ink" : done ? "text-body" : "text-muted")}>{s.label}</p>
            {current && s.due && (
              <p className={cn("num mt-1 text-xs", late ? "font-bold text-late" : "text-gold-ink")}>
                {until(s.due, now)} · {when(s.due)}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
