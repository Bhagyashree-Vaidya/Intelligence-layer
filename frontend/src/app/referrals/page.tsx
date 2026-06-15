"use client";

import { useEffect, useState, useCallback } from "react";
import { getReferrals, generateReferralOutreach, type ReferralGroup } from "@/lib/api";

const REL_LABEL: Record<string, string> = {
  hiring_manager: "Hiring Manager",
  alum: "UW Alum",
  team_senior: "Team Senior",
  referrer: "Referrer",
  recruiter: "Recruiter",
  peer: "Peer",
};

export default function ReferralsPage() {
  const [groups, setGroups] = useState<ReferralGroup[]>([]);
  const [meta, setMeta] = useState({ companies: 0, total_people: 0 });
  const [loading, setLoading] = useState(true);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);

  const refresh = useCallback(() => {
    getReferrals()
      .then((d) => { setGroups(d.groups); setMeta({ companies: d.companies, total_people: d.total_people }); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const draft = async (id: number) => {
    setBusy(id);
    try {
      const r = await generateReferralOutreach(id);
      setDrafts((d) => ({ ...d, [id]: r.outreach_message }));
    } catch (e: any) {
      setDrafts((d) => ({ ...d, [id]: `Error: ${e.message}` }));
    } finally { setBusy(null); }
  };

  return (
    <div style={{ padding: "28px 36px 60px", overflowY: "auto", height: "100%" }}>
      <div style={{ marginBottom: 8 }}>
        <h1 className="jp-display" style={{ margin: 0 }}>Referrals</h1>
        <p className="jp-mute" style={{ marginTop: 6, maxWidth: 560 }}>
          Warm paths into your Top 70. Ranked: hiring managers, UW alumni, then seniors on the
          team. A warm intro beats 100 cold applications — especially for the Workday giants
          (Adobe, Capital One, Salesforce, NVIDIA…) whose roles never show up via API.
        </p>
      </div>

      <div className="jp-mute" style={{ fontSize: 13, marginBottom: 20 }}>
        {loading ? "Loading…" : `${meta.total_people} contacts across ${meta.companies} target companies`}
      </div>

      {!loading && meta.total_people === 0 && (
        <div className="jp-card" style={{ padding: 20, fontSize: 14, lineHeight: 1.7 }}>
          No Top-70 contacts yet. Your existing contacts came from LinkedIn hiring posts and
          mostly aren’t at your target companies. <strong>People-discovery (Apify) fills this tab</strong> —
          it finds hiring managers, UW alumni, and team seniors at each of your 70 targets.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {groups.map((g) => (
          <div key={g.company} className="jp-card" style={{ padding: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontWeight: 600, fontSize: 15 }}>{g.company}</span>
              <span className="jp-chip">{g.count} contacts</span>
              {g.warm > 0 && <span className="jp-chip jp-emerald">{g.warm} warm</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {g.people.map((p) => (
                <div key={p.id} style={{ borderTop: "1px solid var(--jp-line,#2a2a30)", paddingTop: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontWeight: 500 }}>{p.name}</span>
                    {p.relationship_type && (
                      <span className="jp-chip">{REL_LABEL[p.relationship_type] || p.relationship_type}</span>
                    )}
                    <span className="jp-mute" style={{ flex: 1, fontSize: 13 }}>{p.title}</span>
                    {p.linkedin_url && (
                      <a href={p.linkedin_url} target="_blank" rel="noreferrer" className="jp-btn" style={{ fontSize: 12, padding: "4px 10px" }}>LinkedIn</a>
                    )}
                    <button className="jp-btn jp-primary" style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={() => draft(p.id)} disabled={busy === p.id}>
                      {busy === p.id ? "Writing…" : "Draft outreach"}
                    </button>
                  </div>
                  {(drafts[p.id] || p.outreach_message) && (
                    <textarea
                      readOnly
                      value={drafts[p.id] || p.outreach_message}
                      style={{ width: "100%", marginTop: 8, minHeight: 90, fontSize: 13, padding: 10,
                        background: "var(--jp-bg2,#1a1a1f)", color: "inherit", border: "1px solid var(--jp-line,#2a2a30)", borderRadius: 8 }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
