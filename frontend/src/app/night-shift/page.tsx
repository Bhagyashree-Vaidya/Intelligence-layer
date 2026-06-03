"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getNightShiftSettings,
  updateNightShiftSettings,
  selectNightShift,
  getNightShiftQueue,
  getNightShiftTiers,
  type NightShiftSettings,
  type NightShiftQueueItem,
} from "@/lib/api";

export default function NightShiftPage() {
  const [settings, setSettings] = useState<NightShiftSettings | null>(null);
  const [queue, setQueue] = useState<NightShiftQueueItem[]>([]);
  const [tiers, setTiers] = useState<{ tier_1_never_apply: string[]; tier_2_eligible: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [preview, setPreview] = useState<any | null>(null);

  const refresh = useCallback(() => {
    getNightShiftSettings().then((d) => setSettings(d.settings)).catch(() => {});
    getNightShiftQueue().then((d) => setQueue(d.queue)).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    getNightShiftTiers().then(setTiers).catch(() => {});
  }, [refresh]);

  const toggle = async () => {
    if (!settings) return;
    setBusy(true);
    try {
      const next = !settings.enabled;
      const d = await updateNightShiftSettings({ enabled: next });
      setSettings(d.settings);
      setMsg(next ? "Night Shift is ON — it will prep applications for your review." : "Night Shift is OFF.");
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const runPreview = async () => {
    setBusy(true);
    setMsg("Previewing eligible jobs...");
    try {
      const res = await selectNightShift(true);
      setPreview(res);
      setMsg(
        res.enabled === false
          ? "Night Shift is OFF — turn it on to preview."
          : `Preview: ${res.would_queue} jobs would be queued (${res.blocked_tier1} Tier-1 blocked).`
      );
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const runSelect = async () => {
    setBusy(true);
    setMsg("Queueing jobs for review...");
    try {
      const res = await selectNightShift(false);
      setMsg(
        res.enabled === false
          ? "Night Shift is OFF — turn it on first."
          : `Queued ${res.queued} jobs (${res.blocked_tier1} Tier-1 blocked).`
      );
      refresh();
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const on = settings?.enabled ?? false;

  return (
    <div style={{ padding: "28px 36px 60px", overflowY: "auto", height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 8 }}>
        <div>
          <h1 className="jp-display" style={{ margin: 0 }}>Night Shift</h1>
          <p className="jp-mute" style={{ marginTop: 6, maxWidth: 540 }}>
            Auto-prepares applications for Tier-2 companies while you sleep. It fills every field, then
            parks each one for your morning review — it never submits, and never touches your Top 20.
          </p>
        </div>
      </div>

      {/* The Toggle */}
      <div className="jp-card" style={{ padding: 24, marginBottom: 20, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 16 }}>
            {on ? "🌙 Night Shift is ON" : "☀️ Night Shift is OFF"}
          </div>
          <div className="jp-mute" style={{ marginTop: 4, fontSize: 13 }}>
            {on
              ? `Will prep up to ${settings?.max_per_night ?? 20} Tier-2 applications per night.`
              : "Flip the switch to start prepping applications for review."}
          </div>
        </div>
        <button
          onClick={toggle}
          disabled={busy || !settings}
          aria-label="Toggle Night Shift"
          style={{
            position: "relative",
            width: 64,
            height: 34,
            borderRadius: 999,
            border: "none",
            cursor: busy ? "wait" : "pointer",
            background: on ? "var(--jp-violet, #7c5cff)" : "#3a3a42",
            transition: "background 0.2s",
          }}
        >
          <span
            style={{
              position: "absolute",
              top: 3,
              left: on ? 33 : 3,
              width: 28,
              height: 28,
              borderRadius: "50%",
              background: "#fff",
              transition: "left 0.2s",
              boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
            }}
          />
        </button>
      </div>

      {msg && (
        <div className="jp-mute" style={{ marginBottom: 16, fontSize: 13 }}>{msg}</div>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
        <button className="jp-btn" onClick={runPreview} disabled={busy}>Preview eligible jobs</button>
        <button className="jp-btn jp-primary" onClick={runSelect} disabled={busy || !on}>
          Queue jobs for review
        </button>
      </div>

      {/* Preview result */}
      {preview && preview.would_queue !== undefined && (
        <div className="jp-card" style={{ padding: 20, marginBottom: 24 }}>
          <div style={{ fontWeight: 600, marginBottom: 12 }}>
            Preview — {preview.would_queue} would queue · {preview.blocked_tier1} Tier-1 blocked · {preview.skipped_not_tier2} non-target skipped
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(preview.selected || []).slice(0, 20).map((s: any) => (
              <div key={s.job_id} style={{ display: "flex", gap: 12, fontSize: 13 }}>
                <span className="jp-chip">{s.company}</span>
                <span style={{ flex: 1 }}>{s.title}</span>
                <span className="jp-mute">{s.role}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Review Queue */}
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: "0 0 12px" }}>
        Review Queue {queue.length > 0 && <span className="jp-mute">({queue.length})</span>}
      </h2>
      {queue.length === 0 ? (
        <div className="jp-mute" style={{ fontSize: 13, padding: "16px 0" }}>
          Nothing queued yet. Turn Night Shift on and click “Queue jobs for review”.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {queue.map((q) => (
            <div key={q.id} className="jp-card" style={{ padding: 14, display: "flex", alignItems: "center", gap: 12 }}>
              <span className="jp-chip">{q.company}</span>
              <span style={{ flex: 1 }}>{q.title}</span>
              <span className={`jp-chip ${q.status === "error" ? "jp-amber" : q.status === "filled" ? "jp-emerald" : ""}`}>
                {q.status}
              </span>
              {q.url && (
                <a href={q.url} target="_blank" rel="noreferrer" className="jp-btn" style={{ fontSize: 12, padding: "4px 10px" }}>
                  Open
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tier transparency */}
      {tiers && (
        <details style={{ marginTop: 32 }}>
          <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600 }}>
            🛡️ Guardrails — your Top 20 are never auto-applied
          </summary>
          <div className="jp-mute" style={{ fontSize: 12, marginTop: 10, lineHeight: 1.8 }}>
            <strong>Never touched (Tier 1):</strong> {tiers.tier_1_never_apply.join(", ")}
            <br />
            <strong>Eligible (Tier 2):</strong> {tiers.tier_2_eligible.join(", ")}
          </div>
        </details>
      )}
    </div>
  );
}
