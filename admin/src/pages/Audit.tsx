import { PageHead } from "@/components/Layout";
import { Empty, ErrorLine, Loading } from "@/components/ui/states";
import { api } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { useLoad } from "@/lib/use";
import { when } from "@/lib/utils";

const ACTIONS: Record<string, string> = {
  kyc_tier: "changed verification", role: "changed a staff role", user_frozen: "froze an account", user_active: "unfroze an account",
  deposit_recorded: "recorded a deposit", deposit_approved: "approved a deposit", deposit_rejected: "rejected a deposit",
  withdrawal_paid: "paid a withdrawal", withdrawal_failed: "marked a withdrawal failed", dispute_taken: "took a dispute",
  dispute_decided: "decided a dispute", appeal_decided: "decided an appeal", listing_remove: "removed a listing", listing_restore: "restored a listing",
};

export function AuditPage() {
  const { data, error } = useLoad(() => api.get<AuditEntry[]>("/v1/admin/audit?limit=200"), []);
  return (
    <>
      <PageHead title="Staff activity" />
      <section className="max-w-4xl px-6 py-5">
        {error ? <ErrorLine error={error} /> : !data ? <Loading /> : data.length === 0 ? <Empty title="No staff actions yet" /> : (
          <ol className="divide-y divide-line rounded-xl border border-line bg-white">
            {data.map((e) => (
              <li key={e.id} className="px-4 py-2.5">
                <p><b className="text-ink">{e.actor || "Staff"}</b> {ACTIONS[e.action] ?? e.action} <span className="text-xs text-muted">({e.target_type} {e.target_id.slice(0, 8)})</span></p>
                <p className="text-xs text-muted">{when(e.created_at)}{e.detail && ` · ${e.detail}`}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  );
}
