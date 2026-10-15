import { PageHead } from "@/components/Layout";
import { ErrorLine, Loading } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/use";
import { kina } from "@/lib/utils";

const LABELS: Record<string, string> = {
  asset: "Assets", liability: "Liabilities", revenue: "Revenue", expense: "Expenses", equity: "Equity",
  trust_bank: "Trust bank account", customer_funds: "Customer Stars (wallets + escrow)", fee_revenue: "Fees earned",
  safeguarding_position: "Safeguarding position", difference: "Difference",
};

export function ReportsPage() {
  const tb = useLoad(() => api.get<Record<string, string>>("/v1/admin/reports/trial-balance"), []);
  const trust = useLoad(() => api.get<Record<string, string>>("/v1/admin/reports/trust-reconciliation"), []);
  const integrity = useLoad(() => api.get<{ ok: boolean } & Record<string, unknown>>("/v1/admin/reports/integrity"), []);

  const table = (data: Record<string, string> | undefined) => data && (
    <table className="w-full text-left">
      <tbody className="divide-y divide-line">
        {Object.entries(data).map(([k, v]) => (
          <tr key={k}><td className="py-2 pr-4">{LABELS[k] ?? k.replace(/_/g, " ")}</td><td className="num py-2 text-right font-semibold text-ink">{/^-?\d+(\.\d+)?$/.test(v) ? kina(v) : v}</td></tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <>
      <PageHead title="Money reports" />
      <div className="grid max-w-5xl gap-6 px-6 py-6 lg:grid-cols-2">
        <section className="rounded-xl border border-line bg-white p-5">
          <h2 className="font-bold">Ledger check</h2>
          {integrity.error ? <ErrorLine error={integrity.error} /> : !integrity.data ? <Loading /> : (
            <p className={`mt-2 font-semibold ${integrity.data.ok ? "text-ok" : "text-late"}`}>
              {integrity.data.ok ? "Every entry balances and every account matches its postings." : "Problem found: see the API report /v1/admin/reports/integrity."}
            </p>
          )}
          <h2 className="mt-6 font-bold">Trial balance</h2>
          {tb.error ? <ErrorLine error={tb.error} /> : !tb.data ? <Loading /> : table(tb.data)}
        </section>
        <section className="rounded-xl border border-line bg-white p-5">
          <h2 className="font-bold">Trust account reconciliation</h2>
          <p className="mt-1 text-xs text-muted">Monthly report for the Central Bank directive: the trust bank balance must cover every customer Star.</p>
          {trust.error ? <ErrorLine error={trust.error} /> : !trust.data ? <Loading /> : table(trust.data)}
        </section>
      </div>
    </>
  );
}
