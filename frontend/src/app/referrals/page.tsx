"use client";

import { useEffect, useState, useCallback } from "react";
import { getReferrals, generateReferralOutreach, discoverPeople, getNightShiftTiers, markReferralSent, type ReferralGroup } from "@/lib/api";

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
  const [discovering, setDiscovering] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState("");
  const [sentIds, setSentIds] = useState<Set<number>>(new Set());

  const toggleSent = async (id: number, next: boolean) => {
    setSentIds((s) => { const n = new Set(s); next ? n.add(id) : n.delete(id); return n; });
    try { await markReferralSent(id, next); }
    catch { setSentIds((s) => { const n = new Set(s); next ? n.delete(id) : n.add(id); return n; }); }
  };

  const discover = async () => {
    setDiscovering(true);
    setDiscoverMsg("Loading company list…");
    try {
      // Get all 70 targets, then discover in small batches so no single request
      // times out (all-70-at-once takes 10+ min and the gateway kills it).
      const tiers = await getNightShiftTiers();
      const companies = [...tiers.tier_1_never_apply, ...tiers.tier_2_eligible];
      const BATCH = 3;
      let found = 0, done = 0, failed = 0;
      for (let i = 0; i < companies.length; i += BATCH) {
        const batch = companies.slice(i, i + BATCH);
        try {
          const r = await discoverPeople(batch);
          if (r.success) found += r.discovered || 0;
          else failed += batch.length;
        } catch { failed += batch.length; }
        done = Math.min(i + BATCH, companies.length);
        setDiscoverMsg(`Discovering… ${done}/${companies.length} companies · ${found} people found so far${failed ? ` · ${failed} failed` : ""}`);
        refresh();   // live-fill the tab as batches complete
      }
      setDiscoverMsg(`Done — found ${found} people across ${companies.length} companies${failed ? ` (${failed} companies failed; retry to fill gaps)` : ""}.`);
      refresh();
    } catch (e: any) {
      setDiscoverMsg(`Error: ${e.message}. (Check Apify credit, then retry.)`);
    } finally {
      setDiscovering(false);
    }
  };

  const refresh = useCallback(() => {
    getReferrals()
      .then((d) => {
        setGroups(d.groups);
        setMeta({ companies: d.companies, total_people: d.total_people });
        const sent = new Set<number>();
        d.groups.forEach((g) => g.people.forEach((p) => { if (p.outreach_status === "sent") sent.add(p.id); }));
        setSentIds(sent);
      })
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

      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 20 }}>
        <button className="jp-btn jp-primary" onClick={discover} disabled={discovering}>
          {discovering ? "Finding people…" : "🔎 Find people (all 70)"}
        </button>
        <span className="jp-mute" style={{ fontSize: 13 }}>
          {discoverMsg || (loading ? "Loading…" : `${meta.total_people} contacts across ${meta.companies} target companies`)}
        </span>
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
                    <label title="Mark as contacted" style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={sentIds.has(p.id)}
                        onChange={(e) => toggleSent(p.id, e.target.checked)}
                        style={{ width: 16, height: 16, cursor: "pointer", accentColor: "#7c3aed" }}
                      />
                    </label>
                    <span style={{ fontWeight: 500, textDecoration: sentIds.has(p.id) ? "line-through" : "none", opacity: sentIds.has(p.id) ? 0.55 : 1 }}>{p.name}</span>
                    {sentIds.has(p.id) && <span className="jp-chip jp-emerald" style={{ fontSize: 11 }}>sent</span>}
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
                        background: "#ffffff", color: "#111827", border: "1px solid #d1d5db",
                        borderRadius: 8, lineHeight: 1.5, fontFamily: "inherit" }}
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
