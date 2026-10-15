import { AlertTriangle, Loader2 } from "lucide-react";

export function Loading({ what = "Loading" }: { what?: string }) {
  return <div className="flex items-center gap-2 p-6 text-muted"><Loader2 className="animate-spin" size={16} />{what}…</div>;
}

export function ErrorLine({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg bg-late-soft px-3 py-2 text-sm text-late">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />{message}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="p-8 text-center">
      <p className="font-semibold text-ink">{title}</p>
      {children && <p className="mt-1 text-xs text-muted">{children}</p>}
    </div>
  );
}
