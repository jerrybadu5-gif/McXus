import { useState } from "react";
import { PageHead } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty, ErrorLine, Loading } from "@/components/ui/states";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Listing, Report } from "@/lib/types";
import { useLoad } from "@/lib/use";
import { cn, kina, when } from "@/lib/utils";

const REASONS: Record<string, string> = {
  prohibited: "Banned item", scam: "Looks like a scam", wrong_category: "Wrong category", offensive: "Offensive", other: "Other",
};

export function ModerationPage() {
  const list = useLoad(() => api.get<Report[]>("/v1/mod/reports"), []);
  const [open, setOpen] = useState<string | null>(null);
  const byListing = new Map<string, Report[]>();
  (list.data ?? []).forEach((r) => byListing.set(r.listing_id, [...(byListing.get(r.listing_id) ?? []), r]));

  return (
    <>
      <PageHead title="Reported listings" />
      <div className="grid lg:grid-cols-[360px_1fr]">
        <section className="border-r border-line bg-white">
          {list.error ? <div className="p-4"><ErrorLine error={list.error} /></div> : !list.data ? <Loading /> :
            byListing.size === 0 ? <Empty title="No reports">Three reports hide a listing until you decide.</Empty> : (
              <ul className="divide-y divide-line">
                {[...byListing.entries()].map(([id, reports]) => (
                  <li key={id}>
                    <button onClick={() => setOpen(id)} className={cn("w-full px-5 py-3 text-left hover:bg-tint", open === id && "bg-tint")}>
                      <p className="font-semibold text-ink">{reports.length} report{reports.length > 1 ? "s" : ""}{reports.length >= 3 && <Badge tone="late" className="ml-2">Hidden</Badge>}</p>
                      <p className="text-xs text-muted">{[...new Set(reports.map((r) => REASONS[r.reason] ?? r.reason))].join(", ")} · {when(reports[0].created_at)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
        </section>
        <section>{open ? <ListingCase id={open} reports={byListing.get(open) ?? []} onDone={() => { setOpen(null); list.reload(); }} /> : <div className="hidden lg:block"><Empty title="Choose a report" /></div>}</section>
      </div>
    </>
  );
}

function ListingCase({ id, reports, onDone }: { id: string; reports: Report[]; onDone: () => void }) {
  const { notify } = useSession();
  const { data: l, error } = useLoad(() => api.get<Listing>(`/v1/listings/${id}`), [id]);
  if (error) return <div className="p-6"><ErrorLine error={error} /></div>;
  if (!l) return <Loading />;
  async function decide(action: "remove" | "restore") {
    try {
      await api.post(`/v1/mod/listings/${id}/decision`, { action });
      notify(action === "remove" ? "Listing removed" : "Listing restored and reports closed");
      onDone();
    } catch (e) { notify((e as Error).message, "error"); }
  }
  return (
    <article className="max-w-3xl space-y-5 px-6 py-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold">{l.title}</h2>
          <p className="text-xs text-muted">{l.seller.name} · {l.province} · {l.status}</p>
        </div>
        <p className="num text-xl font-bold text-ink">{kina(l.price)}</p>
      </div>
      {l.photos.length > 0 && <div className="flex gap-2 overflow-x-auto">{l.photos.map((p) => <img key={p.id} src={p.thumb_url} alt="" className="h-28 rounded-lg" />)}</div>}
      <p className="whitespace-pre-wrap text-ink">{l.description}</p>
      <section>
        <h3 className="mb-2 font-bold">What people reported</h3>
        <ul className="space-y-2">{reports.map((r) => <li key={r.id} className="rounded-lg border border-line bg-white px-3 py-2"><b className="text-ink">{REASONS[r.reason] ?? r.reason}</b>{r.note && <span>: {r.note}</span>}</li>)}</ul>
      </section>
      <div className="flex gap-2">
        <Button variant="danger" onClick={() => decide("remove")}>Remove the listing</Button>
        <Button variant="outline" onClick={() => decide("restore")}>Keep it up</Button>
      </div>
    </article>
  );
}
