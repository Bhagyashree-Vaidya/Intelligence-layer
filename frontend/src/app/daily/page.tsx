"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getToday, tickTask, getMemoTarget, generateMemo, generatePmConcept,
  type TaskItem, type Funnel,
} from "@/lib/api";

export default function DailyPage() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [today, setToday] = useState("");
  const [busyKey, setBusyKey] = useState("");

  // generators
  const [memoTarget, setMemoTarget] = useState<any>(null);
  const [memo, setMemo] = useState("");
  const [memoBusy, setMemoBusy] = useState(false);
  const [concept, setConcept] = useState("");
  const [conceptBusy, setConceptBusy] = useState(false);

  const load = useCallback(() => {
    getToday().then((d) => { setTasks(d.tasks); setFunnel(d.funnel); setToday(d.date); }).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    getMemoTarget().then((d) => setMemoTarget(d.target)).catch(() => {});
  }, [load]);

  const toggle = async (t: TaskItem) => {
    setBusyKey(t.key);
    // optimistic
    setTasks((prev) => prev.map((x) => x.key === t.key ? { ...x, done: !x.done } : x));
    try { await tickTask(t.key, "daily", !t.done); } catch { load(); }
    finally { setBusyKey(""); }
  };

  const doMemo = async () => {
    if (!memoTarget) return;
    setMemoBusy(true);
    try {
      const r = await generateMemo({
        company: memoTarget.company || "",
        target_name: memoTarget.name || "",
        target_title: memoTarget.title || "",
        target_url: memoTarget.linkedin_url || "",
      });
      setMemo(r.memo);
    } finally { setMemoBusy(false); }
  };

  const doConcept = async () => {
    setConceptBusy(true);
    try { const r = await generatePmConcept(); setConcept(r.concept); }
    finally { setConceptBusy(false); }
  };

  const done = tasks.filter((t) => t.done).length;

  return (
    <div style={{ padding: "28px 36px 60px", overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 6 }}>
        <h1 className="jp-display" style={{ margin: 0 }}>Today</h1>
        <span className="jp-mute" style={{ fontSize: 13 }}>{done}/{tasks.length} done · {today}</span>
      </div>
      <p className="jp-mute" style={{ marginTop: 4, marginBottom: 20, maxWidth: 560 }}>
        The job is talking to humans. This is the daily motion that actually gets interviews.
      </p>

      {/* North Star funnel */}
      {funnel && (
        <div className="jp-card" style={{ padding: 16, marginBottom: 24, display: "flex", gap: 28 }}>
          <Stat label="Apps sent" value={funnel.applications_sent} />
          <Stat label="Responses" value={`${funnel.responses} (${funnel.response_rate}%)`} />
          <Stat label="Interviews" value={`${funnel.interviews} (${funnel.interview_rate}%)`} />
          <Stat label="Offers" value={`${funnel.offers} (${funnel.offer_rate}%)`} highlight />
        </div>
      )}

      {/* Checklist */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 28 }}>
        {tasks.map((t) => (
          <label key={t.key} className="jp-card" style={{
            padding: 14, display: "flex", alignItems: "center", gap: 12, cursor: "pointer",
            opacity: t.done ? 0.6 : 1,
          }}>
            <input type="checkbox" checked={t.done} disabled={busyKey === t.key}
              onChange={() => toggle(t)} style={{ width: 18, height: 18, accentColor: "#7c5cff" }} />
            <span style={{ flex: 1, textDecoration: t.done ? "line-through" : "none" }}>{t.label}</span>
            {t.key === "apply_5" && <a href="/night-shift" className="jp-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Night Shift →</a>}
            {t.key === "outreach_5" && <a href="/signals" className="jp-btn" style={{ fontSize: 12, padding: "4px 10px" }}>Contacts →</a>}
          </label>
        ))}
      </div>

      {/* Strategy memo generator */}
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: "0 0 10px" }}>📄 Strategy Memo</h2>
      {memoTarget ? (
        <div className="jp-card" style={{ padding: 16, marginBottom: 24 }}>
          <div className="jp-mute" style={{ fontSize: 13, marginBottom: 10 }}>
            Suggested human to send it to:&nbsp;
            <strong style={{ color: "var(--jp-ink, #111)" }}>{memoTarget.name}</strong>
            {memoTarget.title ? ` — ${memoTarget.title}` : ""} {memoTarget.company ? `@ ${memoTarget.company}` : ""}
            {memoTarget.linkedin_url && (
              <> · <a href={memoTarget.linkedin_url} target="_blank" rel="noreferrer">LinkedIn ↗</a></>
            )}
          </div>
          <button className="jp-btn jp-primary" onClick={doMemo} disabled={memoBusy}>
            {memoBusy ? "Writing…" : "Generate memo for this person"}
          </button>
          {memo && (
            <textarea value={memo} onChange={(e) => setMemo(e.target.value)}
              style={{ width: "100%", minHeight: 280, marginTop: 12, padding: 12, fontFamily: "inherit",
                       fontSize: 13, lineHeight: 1.6, borderRadius: 8 }} />
          )}
        </div>
      ) : (
        <div className="jp-mute" style={{ fontSize: 13, marginBottom: 24 }}>
          No relevant contact found yet — run a signal scan on the Signals tab to discover people.
        </div>
      )}

      {/* PM concept of the day */}
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: "0 0 10px" }}>🧠 PM Concept of the Day</h2>
      <div className="jp-card" style={{ padding: 16 }}>
        <button className="jp-btn" onClick={doConcept} disabled={conceptBusy}>
          {conceptBusy ? "Thinking…" : "Teach me one"}
        </button>
        {concept && (
          <div style={{ marginTop: 12, fontSize: 13, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{concept}</div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--jp-mono)", fontSize: 22, fontWeight: 600,
                    color: highlight ? "#7c5cff" : undefined }}>{value}</div>
      <div className="jp-mute" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
    </div>
  );
}
