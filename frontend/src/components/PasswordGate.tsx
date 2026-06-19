"use client";

import { useEffect, useState } from "react";

// Simple console gate. The password lives ONLY in the Vercel env var
// NEXT_PUBLIC_APP_PASSWORD (never committed). Client-side by design — this
// keeps casual visitors out of the console; it is not bank-grade auth.
const EXPECTED = process.env.NEXT_PUBLIC_APP_PASSWORD || "";
const KEY = "jp_authed_v1";

export function PasswordGate({ children }: { children: React.ReactNode }) {
  const [ok, setOk] = useState<boolean | null>(null);
  const [pw, setPw] = useState("");
  const [err, setErr] = useState(false);

  useEffect(() => {
    // If no password is configured, don't lock the owner out.
    if (!EXPECTED) { setOk(true); return; }
    setOk(typeof window !== "undefined" && localStorage.getItem(KEY) === "1");
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (pw === EXPECTED) {
      localStorage.setItem(KEY, "1");
      setOk(true);
    } else {
      setErr(true);
      setPw("");
    }
  };

  if (ok === null) return null; // avoid flash before localStorage check
  if (ok) return <>{children}</>;

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--jp-app-bg, #0f0f12)",
    }}>
      <form onSubmit={submit} style={{
        width: 320, padding: 28, borderRadius: 16, background: "var(--jp-card, #1a1a1f)",
        border: "1px solid var(--jp-line, #2a2a30)", display: "flex", flexDirection: "column", gap: 14,
        boxShadow: "0 8px 40px rgba(0,0,0,.4)",
      }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>JobPilot</div>
        <div className="jp-mute" style={{ fontSize: 13, marginTop: -8 }}>Enter password to continue</div>
        <input
          type="password"
          autoFocus
          value={pw}
          onChange={(e) => { setPw(e.target.value); setErr(false); }}
          placeholder="Password"
          style={{
            padding: "10px 12px", borderRadius: 10, fontSize: 14,
            background: "var(--jp-bg2, #111114)", color: "inherit",
            border: `1px solid ${err ? "#e5484d" : "var(--jp-line, #2a2a30)"}`,
          }}
        />
        {err && <div style={{ color: "#e5484d", fontSize: 12 }}>Wrong password.</div>}
        <button type="submit" className="jp-btn jp-primary" style={{ padding: 10 }}>Enter</button>
      </form>
    </div>
  );
}
