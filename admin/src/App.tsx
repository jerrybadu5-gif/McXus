import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Loading } from "@/components/ui/states";
import { api, token, whenSignedOut } from "@/lib/api";
import { can, SessionContext } from "@/lib/session";
import type { User } from "@/lib/types";
import { AuditPage } from "@/pages/Audit";
import { DisputesPage } from "@/pages/Disputes";
import { HomePage } from "@/pages/Home";
import { MoneyPage } from "@/pages/Money";
import { ModerationPage } from "@/pages/Moderation";
import { PeoplePage } from "@/pages/People";
import { ReportsPage } from "@/pages/Reports";
import { SignIn } from "@/pages/SignIn";

type Toast = { text: string; tone: "ok" | "error"; id: number };

export default function App() {
  const [me, setMe] = useState<User | null | undefined>(token.get() ? undefined : null);
  const [toast, setToast] = useState<Toast | null>(null);

  const signOut = useCallback(() => { token.set(null); setMe(null); }, []);
  useEffect(() => whenSignedOut(() => setMe(null)), []);
  useEffect(() => {
    if (me !== undefined) return;
    api.get<User>("/v1/me").then(setMe, () => signOut());
  }, [me, signOut]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.tone === "error" ? 7000 : 3500);
    return () => clearTimeout(t);
  }, [toast]);

  if (me === undefined) return <Loading what="Signing in" />;
  if (me === null) return <SignIn onSignedIn={setMe} />;

  const notify = (text: string, tone: "ok" | "error" = "ok") => setToast({ text, tone, id: Date.now() });

  return (
    <SessionContext.Provider value={{ me, signOut, notify }}>
      <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          {can(me, "disputes") && <Route path="/disputes/*" element={<DisputesPage />} />}
          {can(me, "money") && <Route path="/money/*" element={<MoneyPage />} />}
          {can(me, "reports") && <Route path="/reports" element={<ReportsPage />} />}
          {can(me, "moderation") && <Route path="/moderation" element={<ModerationPage />} />}
          {can(me, "people") && <Route path="/people/*" element={<PeoplePage />} />}
          {can(me, "audit") && <Route path="/audit" element={<AuditPage />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
      {toast && (
        <div key={toast.id} role="status"
          className={`fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm font-semibold shadow-lg ${toast.tone === "error" ? "bg-late text-white" : "bg-navy text-white"}`}>
          {toast.text}
        </div>
      )}
    </SessionContext.Provider>
  );
}
