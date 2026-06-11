"use client";

import { useEffect, useState, useCallback } from "react";
import { getWeek, tickTask, generateArticle, type TaskItem } from "@/lib/api";

export default function WeeklyPage() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [weekStart, setWeekStart] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [topic, setTopic] = useState("");
  const [article, setArticle] = useState("");
  const [articleBusy, setArticleBusy] = useState(false);

  const load = useCallback(() => {
    getWeek().then((d) => { setTasks(d.tasks); setWeekStart(d.week_start); }).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = async (t: TaskItem) => {
    setBusyKey(t.key);
    setTasks((prev) => prev.map((x) => x.key === t.key ? { ...x, done: !x.done } : x));
    try { await tickTask(t.key, "weekly", !t.done); } catch { load(); }
    finally { setBusyKey(""); }
  };

  const doArticle = async () => {
    setArticleBusy(true);
    try { const r = await generateArticle(topic); setArticle(r.article); }
    finally { setArticleBusy(false); }
  };

  const done = tasks.filter((t) => t.done).length;

  return (
    <div style={{ padding: "28px 36px 60px", overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 6 }}>
        <h1 className="jp-display" style={{ margin: 0 }}>This Week</h1>
        <span className="jp-mute" style={{ fontSize: 13 }}>{done}/{tasks.length} done · week of {weekStart}</span>
      </div>
      <p className="jp-mute" style={{ marginTop: 4, marginBottom: 20, maxWidth: 560 }}>
        The compounding work: brand, learning, and the CIOS review that tells you what's actually working.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 28 }}>
        {tasks.map((t) => (
          <label key={t.key} className="jp-card" style={{
            padding: 14, display: "flex", alignItems: "center", gap: 12, cursor: "pointer",
            opacity: t.done ? 0.6 : 1,
          }}>
            <input type="checkbox" checked={t.done} disabled={busyKey === t.key}
              onChange={() => toggle(t)} style={{ width: 18, height: 18, accentColor: "#7c5cff" }} />
            <span style={{ flex: 1, textDecoration: t.done ? "line-through" : "none" }}>{t.label}</span>
          </label>
        ))}
      </div>

      {/* LinkedIn article generator */}
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: "0 0 10px" }}>✍️ LinkedIn Post</h2>
      <div className="jp-card" style={{ padding: 16 }}>
        <input value={topic} onChange={(e) => setTopic(e.target.value)}
          placeholder="Optional topic (e.g. 'a lesson from my signal-processing work')"
          style={{ width: "100%", padding: 10, borderRadius: 8, marginBottom: 10, fontSize: 13 }} />
        <button className="jp-btn jp-primary" onClick={doArticle} disabled={articleBusy}>
          {articleBusy ? "Writing…" : "Draft my post"}
        </button>
        {article && (
          <textarea value={article} onChange={(e) => setArticle(e.target.value)}
            style={{ width: "100%", minHeight: 220, marginTop: 12, padding: 12, fontFamily: "inherit",
                     fontSize: 13, lineHeight: 1.6, borderRadius: 8 }} />
        )}
      </div>
    </div>
  );
}
