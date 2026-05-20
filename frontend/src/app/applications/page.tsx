"use client";

import { useEffect, useState } from "react";
import { getApplications, updateAppStatus } from "@/lib/api";

const STATUSES = ["all", "saved", "applied", "screen", "interview", "offer", "rejected"];
const STAGE_MAP: Record<string, number> = { saved: 0, applied: 1, screen: 2, interview: 3, offer: 4, rejected: 5 };
const STAGE_COLORS: Record<string, string> = {
  saved: "var(--jp-dim)", applied: "var(--jp-primary)", screen: "var(--jp-amber)",
  interview: "var(--jp-emerald)", offer: "#27ae60", rejected: "var(--jp-rose)",
};

export default function ApplicationsPage() {
  const [apps, setApps] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({});
  const [activeTab, setActiveTab] = useState("all");

  const fetchApps = async () => {
    const filter = activeTab === "all" ? "" : activeTab;
    const res = await getApplications(filter);
    setApps(res.applications);
    setStats(res.stats);
  };

  useEffect(() => { fetchApps(); }, [activeTab]);

  const handleStatusChange = async (appId: number, newStatus: string) => {
    await updateAppStatus(appId, newStatus);
    fetchApps();
  };

  return (
    <div style={{ padding: "28px 36px 60px" }}>
      <h1 className="jp-display" style={{ marginBottom: 24 }}>Applications</h1>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16, marginBottom: 28 }}>
        {[
          ["Total", stats.total || 0],
          ["Sent", stats.sent || 0],
          ["Reply Rate", `${stats.reply_rate || 0}%`],
          ["Interviews", stats.interviews || 0],
          ["Offers", stats.offers || 0],
        ].map(([label, val]) => (
          <div key={String(label)} className="jp-card" style={{ padding: "18px 20px", textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 600, fontFamily: "var(--jp-mono)", color: "var(--jp-ink)" }}>{val}</div>
            <div style={{ fontSize: 12, color: "var(--jp-dim)", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.5px" }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Status tabs */}
      <div className="jp-seg" style={{ marginBottom: 22 }}>
        {STATUSES.map((s) => (
          <button key={s} className={activeTab === s ? "on" : ""} onClick={() => setActiveTab(s)}>
            {s.charAt(0).toUpperCase() + s.slice(1)}
            {stats.by_status && s !== "all" ? ` (${stats.by_status[s] || 0})` : ""}
          </button>
        ))}
      </div>

      {/* Applications table */}
      <div style={{ overflowX: "auto" }}>
        <table className="jp-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Company</th>
              <th>Role</th>
              <th>Location</th>
              <th>Pipeline</th>
              <th>Status</th>
              <th>Applied</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((a) => (
              <tr key={a.id}>
                <td><strong>{a.company}</strong></td>
                <td>
                  {a.url ? (
                    <a href={a.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--jp-primary)" }}>{a.title}</a>
                  ) : a.title}
                </td>
                <td style={{ color: "var(--jp-dim)" }}>{a.location}</td>
                <td>
                  <div style={{ display: "flex", gap: 3 }}>
                    {[0, 1, 2, 3, 4].map((seg) => (
                      <div
                        key={seg}
                        style={{
                          width: 24, height: 6, borderRadius: 3,
                          background: seg <= (a.stage || 0) ? STAGE_COLORS[a.status] || "var(--jp-dim)" : "var(--neu-bg-2)",
                          boxShadow: seg <= (a.stage || 0) ? "none" : "var(--neu-pressed-sm)",
                        }}
                      />
                    ))}
                  </div>
                </td>
                <td>
                  <select
                    value={a.status}
                    onChange={(e) => handleStatusChange(a.id, e.target.value)}
                    className="jp-input"
                    style={{ fontSize: 13, padding: "4px 10px", width: "auto" }}
                  >
                    {STATUSES.filter((s) => s !== "all").map((s) => (
                      <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                    ))}
                  </select>
                </td>
                <td style={{ color: "var(--jp-dim)", fontSize: 13 }}>
                  {a.applied_at ? new Date(a.applied_at).toLocaleDateString() : ""}
                </td>
              </tr>
            ))}
            {apps.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", padding: 40, color: "var(--jp-dim)" }}>
                  No applications yet. Start applying from the Jobs page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
