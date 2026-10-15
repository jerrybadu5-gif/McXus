import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ErrorLine } from "@/components/ui/states";
import { api, token } from "@/lib/api";
import type { User } from "@/lib/types";

/** Staff sign in with their phone and a 6-digit code, like the app. Customer accounts are turned away. */
export function SignIn({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(undefined);
    try {
      const r = await api.post<{ dev_code?: string }>("/v1/auth/otp/request", { phone });
      setSent(true); setDevCode(r.dev_code ?? null);
      if (r.dev_code) setCode(r.dev_code);
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(undefined);
    try {
      const t = await api.post<{ access_token: string }>("/v1/auth/otp/verify", { phone, code });
      token.set(t.access_token);
      const me = await api.get<User>("/v1/me");
      if (me.role === "user") {
        token.set(null);
        throw new Error("This number is a customer account. Ask an admin to give you a staff role.");
      }
      onSignedIn(me);
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-navy px-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-7">
        <img src="/icon.svg" alt="" className="h-10 w-10" />
        <h1 className="mt-4 text-xl font-bold">Sign in to McXus staff</h1>
        <p className="mt-1 text-xs text-muted">For mediators, finance, KYC, moderators and compliance.</p>
        {!sent ? (
          <form onSubmit={send} className="mt-6 space-y-4">
            <Field label="Phone number"><Input autoFocus inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="7000 9999" required /></Field>
            <Button className="w-full" size="lg" disabled={busy || phone.trim().length < 7}>Send code</Button>
          </form>
        ) : (
          <form onSubmit={verify} className="mt-6 space-y-4">
            <Field label="6-digit code" hint={devCode ? `Sandbox: the code is filled in (${devCode}); no SMS is sent yet.` : `Sent to ${phone}.`}>
              <Input autoFocus inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />
            </Field>
            <Button className="w-full" size="lg" disabled={busy || code.length !== 6}>Sign in</Button>
            <button type="button" className="w-full text-xs text-muted hover:text-ink" onClick={() => { setSent(false); setCode(""); }}>Use another number</button>
          </form>
        )}
        {!!error && <div className="mt-4"><ErrorLine error={error} /></div>}
      </div>
    </div>
  );
}
