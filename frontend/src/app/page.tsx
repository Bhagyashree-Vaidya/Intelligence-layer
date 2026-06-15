"use client";

import { useEffect, useState, useCallback } from "react";
import { getJobs, rescoreAll, startScrape, getScrapeStatus, generateMessage, generateCoverLetter, trackApplication, getApplications, type Job, type JobsResponse } from "@/lib/api";
import { MatchRing } from "@/components/MatchRing";

export default function Dashboard() {
  const [data, setData] = useState<JobsResponse | null>(null);
  const [filters, setFilters] = useState({ q: "", company: "", location: "", role: "", freshness: "", sort: "relevancy", targets_only: "", pm_program_only: "" });
  const [page, setPage] = useState(1);
  const [scraping, setScraping] = useState(false);
  const [scrapeMsg, setScrapeMsg] = useState("");
  const [appliedIds, setAppliedIds] = useState<Set<number>>(new Set());
  const [appStats, setAppStats] = useState<{ total: number; sent: number; interviews: number; offers: number }>({ total: 0, sent: 0, interviews: 0, offers: 0 });

  const fetchJobs = useCallback(async () => {
    const params: Record<string, string> = { page: String(page) };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const res = await getJobs(params);
    setData(res);
  }, [page, filters]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // Fetch applied IDs + stats on mount
  useEffect(() => {
    getApplications().then((res) => {
      setAppliedIds(new Set(res.applications.map((a: any) => a.job_id)));
      setAppStats(res.stats);
    }).catch(() => {});
  }, []);

  // Poll scrape status while running
  useEffect(() => {
    if (!scraping) return;
    const id = setInterval(async () => {
      const s = await getScrapeStatus();
      setScrapeMsg(s.progress || s.last_result || "");
      if (!s.running) { setScraping(false); fetchJobs(); }
    }, 2000);
    return () => clearInterval(id);
  }, [scraping, fetchJobs]);

  const handleFilter = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setFilters({
      q: fd.get("q") as string || "",
      company: fd.get("company") as string || "",
      location: fd.get("location") as string || "",
      role: fd.get("role") as string || "",
      freshness: filters.freshness,
      sort: filters.sort,
      targets_only: filters.targets_only,
      pm_program_only: filters.pm_program_only,
    });
    setPage(1);
  };

  const handleScrape = async () => {
    setScraping(true);
    setScrapeMsg("Starting...");
    await startScrape("all", { hours: "24" });
  };

  const handleRescore = async () => {
    await rescoreAll();
    fetchJobs();
  };

  return (
    <div style={{ padding: "28px 36px 60px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 className="jp-display">
            <span style={{ fontFamily: "var(--jp-mono)", fontSize: 44, fontWeight: 500 }}>
              {data?.total?.toLocaleString() ?? "..."}
            </span>{" "}
            <span style={{ color: "var(--jp-dim)", fontStyle: "italic" }}>open roles</span>
          </h1>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {/* Application counter */}
          <div style={{ display: "flex", gap: 12, marginRight: 12 }}>
            {[
              ["Applied", appStats.sent, "var(--jp-primary)"],
              ["Interviews", appStats.interviews, "var(--jp-emerald)"],
              ["Offers", appStats.offers, "#27ae60"],
            ].map(([label, val, color]) => (
              <div key={String(label)} style={{ textAlign: "center", padding: "4px 10px" }}>
                <div style={{ fontSize: 20, fontWeight: 600, fontFamily: "var(--jp-mono)", color: String(color) }}>{val}</div>
                <div style={{ fontSize: 10, color: "var(--jp-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>{label}</div>
              </div>
            ))}
          </div>
          <button className="jp-btn sm ghost" onClick={handleRescore}>Rescore</button>
          <button className="jp-btn primary" onClick={handleScrape} disabled={scraping}>
            {scraping ? scrapeMsg : "Fetch new jobs"}
          </button>
        </div>
      </div>

      {/* Filter card */}
      <form onSubmit={handleFilter} className="jp-card" style={{ padding: 22, marginBottom: 22 }}>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 14, alignItems: "end" }}>
          <div className="jp-field">
            <label className="label">Search</label>
            <input className="jp-input" name="q" defaultValue={filters.q} placeholder="Title or keyword..." />
          </div>
          <div className="jp-field">
            <label className="label">Company</label>
            <input className="jp-input" name="company" defaultValue={filters.company} placeholder="e.g. Stripe" />
          </div>
          <div className="jp-field">
            <label className="label">Location</label>
            <input className="jp-input" name="location" defaultValue={filters.location} placeholder="e.g. Remote" />
          </div>
          <div className="jp-field">
            <label className="label">Role</label>
            <input className="jp-input" name="role" defaultValue={filters.role} placeholder="e.g. PM" />
          </div>
          <button type="submit" className="jp-btn dark" style={{ height: 46 }}>Filter</button>
        </div>

        {/* Freshness + Sort toggles */}
        <div style={{ display: "flex", gap: 18, marginTop: 18, paddingTop: 18, borderTop: "1px solid rgba(163,177,198,0.3)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span className="jp-eyebrow">Posted</span>
            <div className="jp-seg">
              {[["24h", "24h"], ["48h", "48h"], ["7d", "7 days"], ["30d", "30 days"], ["", "All"]].map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  className={filters.freshness === val ? "on" : ""}
                  onClick={() => { setFilters((f) => ({ ...f, freshness: val })); setPage(1); }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span className="jp-eyebrow">Sort</span>
            <div className="jp-seg">
              {[["relevancy", "Match"], ["date", "Date"], ["company", "Company"]].map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  className={filters.sort === val ? "on" : ""}
                  onClick={() => { setFilters((f) => ({ ...f, sort: val })); setPage(1); }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginLeft: "auto" }}>
            <span className="jp-eyebrow">Scope</span>
            <div className="jp-seg">
              {([
                { key: "all", label: "All jobs", targets: "", pm: "" },
                { key: "targets", label: "★ My Targets", targets: "true", pm: "" },
                { key: "top70", label: "🎯 Top 70 (PM/Program)", targets: "true", pm: "true" },
              ] as const).map((opt) => {
                const active = filters.targets_only === opt.targets && filters.pm_program_only === opt.pm;
                return (
                  <button
                    key={opt.key}
                    type="button"
                    className={active ? "on" : ""}
                    onClick={() => { setFilters((f) => ({ ...f, targets_only: opt.targets, pm_program_only: opt.pm })); setPage(1); }}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </form>

      {/* Job list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {data?.jobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            isApplied={appliedIds.has(job.id)}
            onApply={async () => {
              await trackApplication(job.id, "applied");
              setAppliedIds((prev) => new Set([...prev, job.id]));
              setAppStats((s) => ({ ...s, total: s.total + 1, sent: s.sent + 1 }));
            }}
            onSave={async () => {
              await trackApplication(job.id, "saved");
              setAppliedIds((prev) => new Set([...prev, job.id]));
              setAppStats((s) => ({ ...s, total: s.total + 1 }));
            }}
          />
        ))}
        {data && data.jobs.length === 0 && (
          <div className="jp-card" style={{ padding: 48, textAlign: "center", color: "var(--jp-dim)" }}>
            No jobs match your filters.
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 24 }}>
          <button className="jp-btn sm ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span style={{ padding: "8px 16px", fontFamily: "var(--jp-mono)" }}>
            {page} / {data.total_pages}
          </span>
          <button className="jp-btn sm ghost" disabled={page >= data.total_pages} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}

function JobCard({ job, isApplied, onApply, onSave }: {
  job: Job;
  isApplied: boolean;
  onApply: () => Promise<void>;
  onSave: () => Promise<void>;
}) {
  const [applying, setApplying] = useState(false);
  const [coverLetter, setCoverLetter] = useState("");
  const [clLoading, setClLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCoverLetter = async () => {
    setClLoading(true);
    try {
      const res = await generateCoverLetter(job.id);
      setCoverLetter(res.cover_letter);
    } catch {
      setCoverLetter("Failed to generate — is your profile set up?");
    }
    setClLoading(false);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(coverLetter);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  const handlePdf = () => {
    const w = window.open("", "_blank");
    if (!w) { alert("Pop-up blocked — allow pop-ups to download the PDF."); return; }
    const safe = coverLetter
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    w.document.write(
      `<!doctype html><html><head><title>Cover Letter - ${job.company}</title>` +
      `<style>@page{margin:1in;}body{font-family:Georgia,'Times New Roman',serif;` +
      `font-size:12pt;line-height:1.6;color:#111;white-space:pre-wrap;}</style></head>` +
      `<body>${safe}</body></html>`
    );
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  };

  const handleApply = async () => {
    if (isApplied) return;
    setApplying(true);
    try {
      // Open the job URL in a new tab (Chrome extension will auto-fill)
      window.open(job.url, "_blank");
      // Track the application
      await onApply();
    } catch (e) {
      console.error("Failed to track application:", e);
    }
    setApplying(false);
  };

  const handleSave = async () => {
    if (isApplied) return;
    try {
      await onSave();
    } catch (e) {
      console.error("Failed to save job:", e);
    }
  };

  return (
    <div className="jp-card" style={{
      padding: "18px 22px",
      borderLeft: isApplied ? "3px solid var(--jp-primary)" : "3px solid transparent",
    }}>
    <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
      <MatchRing score={job.relevancy_score || 0} color={job.color} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <strong style={{ fontSize: 16, color: "var(--jp-ink)" }}>{job.title}</strong>
          {isApplied && (
            <span className="jp-badge" style={{ fontSize: 12, padding: "4px 10px", background: "var(--jp-primary)", color: "#fff", borderRadius: 6 }}>
              Applied
            </span>
          )}
          {job.freshness && (
            <span
              className="jp-badge"
              style={{
                fontSize: 12,
                padding: "4px 10px",
                borderRadius: 6,
                background: job.freshness.badge_color === "red" ? "var(--jp-rose-50)" :
                  job.freshness.badge_color === "orange" ? "var(--jp-amber-50)" :
                  "var(--neu-bg-2)",
                color: job.freshness.badge_color === "red" ? "var(--jp-rose)" :
                  job.freshness.badge_color === "orange" ? "var(--jp-amber)" :
                  "var(--jp-dim)",
              }}
            >
              {job.freshness.label}
            </span>
          )}
        </div>
        <div style={{ fontSize: 14, color: "var(--jp-dim)", marginBottom: 6 }}>
          {job.company} &middot; {job.location}
        </div>
        {job.keywords_list && job.keywords_list.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {job.keywords_list.slice(0, 6).map((kw) => (
              <span key={kw} className="jp-badge" style={{ fontSize: 12, padding: "3px 8px" }}>{kw}</span>
            ))}
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
        {!isApplied && (
          <button className="jp-btn sm ghost" onClick={handleSave} title="Save for later">
            Save
          </button>
        )}
        <button className="jp-btn sm ghost" onClick={handleCoverLetter} disabled={clLoading} title="Generate a tailored cover letter">
          {clLoading ? "..." : "Cover Letter"}
        </button>
        {job.url && (
          <button
            className={`jp-btn sm ${isApplied ? "ghost" : "primary"}`}
            onClick={isApplied ? () => window.open(job.url, "_blank") : handleApply}
            disabled={applying}
          >
            {applying ? "..." : isApplied ? "View" : "Apply"}
          </button>
        )}
      </div>
    </div>

    {/* Cover letter — editable */}
    {coverLetter && (
      <div style={{ marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <span className="jp-eyebrow">Cover letter — edit before exporting</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="jp-btn sm ghost" onClick={handleCopy}>{copied ? "Copied ✓" : "Copy"}</button>
            <button className="jp-btn sm ghost" onClick={handlePdf}>Download PDF</button>
            <button className="jp-btn sm ghost" onClick={() => setCoverLetter("")}>Dismiss</button>
          </div>
        </div>
        <textarea
          className="jp-input"
          value={coverLetter}
          onChange={(e) => setCoverLetter(e.target.value)}
          rows={16}
          style={{ width: "100%", resize: "vertical", fontSize: 14, lineHeight: 1.7 }}
        />
      </div>
    )}
    </div>
  );
}
