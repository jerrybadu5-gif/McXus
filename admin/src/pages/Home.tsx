import { Link } from "react-router-dom";
import { PageHead } from "@/components/Layout";
import { ErrorLine, Loading } from "@/components/ui/states";
import { api } from "@/lib/api";
import { can, ROLE_NAMES, useSession } from "@/lib/session";
import type { Overview } from "@/lib/types";
import { useLoad } from "@/lib/use";

export function HomePage() {
  const { me } = useSession();
  const { data, error } = useLoad(() => api.get<Overview>("/v1/admin/overview"), []);
  if (error) return <div className="p-6"><ErrorLine error={error} /></div>;
  if (!data) return <Loading />;

  const rows = [
    can(me, "disputes") && { to: "/disputes", n: data.disputes.mediation ?? 0, label: "disputes need a mediator", late: data.disputes_overdue },
    can(me, "disputes") && { to: "/disputes?stage=appeal", n: data.disputes.appeal ?? 0, label: "appeals need a senior decision" },
    can(me, "disputes") && { to: "/disputes?stage=negotiation", n: data.disputes.negotiation ?? 0, label: "disputes where buyer and seller are still negotiating", quiet: true },
    can(me, "money") && { to: "/money", n: data.deposits_pending, label: "deposits to approve (another finance officer recorded them)" },
    can(me, "money") && { to: "/money/payouts", n: data.withdrawals_requested, label: "withdrawals to pay" },
    can(me, "moderation") && { to: "/moderation", n: data.reports_open, label: "reported listings to review" },
    can(me, "moderation") && { to: "/moderation?show=content", n: data.content_reports_open, label: "reported posts, comments and channels" },
    can(me, "freezes") && { to: "/freezes", n: data.freeze_appeals, label: "appeals from frozen accounts" },
    can(me, "freezes") && { to: "/freezes", n: data.freezes_open, label: "accounts frozen now", quiet: true },
  ].filter(Boolean) as { to: string; n: number; label: string; late?: number; quiet?: boolean }[];

  return (
    <>
      <PageHead title={`Good to see you, ${me.display_name || ROLE_NAMES[me.role]}`} />
      <section className="max-w-3xl px-6 py-6">
        <h2 className="mb-3 font-bold">Waiting for you</h2>
        {rows.length === 0 && <p className="text-muted">Nothing is assigned to your role. Use People to look someone up.</p>}
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-white">
          {rows.map((r) => (
            <li key={r.to + r.label}>
              <Link to={r.to} className="flex items-center gap-4 px-4 py-3.5 hover:bg-tint">
                <span className={`num w-10 text-right text-2xl font-bold ${r.n && !r.quiet ? "text-gold-deep" : "text-muted"}`}>{r.n}</span>
                <span className="flex-1 text-ink">{r.label}</span>
                {!!r.late && <span className="rounded bg-late-soft px-2 py-0.5 text-xs font-semibold text-late">{r.late} past the deadline</span>}
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-6 text-xs text-muted">{data.users.toLocaleString()} accounts, {data.staff} staff. Every staff action you take is recorded in the staff activity log.</p>
      </section>
    </>
  );
}
