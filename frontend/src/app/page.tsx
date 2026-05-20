"use client";

import { useEffect, useState, useCallback } from "react";
import { getJobs, rescoreAll, startScrape, getScrapeStatus, generateMessage, type Job, type JobsResponse } from "@/lib/api";
import { MatchRing } from "@/components/MatchRing";

export default function Dashboard() {
  const [data, setData] = useState<JobsResponse | null>(null);
  const [filters, setFilters] = useState({ q: "", company: "", location: "", role: "", freshness: "", sort: "relevancy" });
  const [page, setPage] = useState(1);
  const [scraping, setScraping] = useState(false);
  const [scrapeMsg, setScrapeMsg] = useState("");

  const fetchJobs = useCallback(async () => {
    const params: Record<string, string> = { page: String(page) };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const res = await getJobs(params);
    setData(res);
  }, [page, filters]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

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
        <div style={{ display: "flex", gap: 10 }}>
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
        </div>
      </form>

      {/* Job list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {data?.jobs.map((job) => (
          <JobCard key={job.id} job={job} />
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

function JobCard({ job }: { job: Job }) {
  return (
    <div className="jp-card" style={{ padding: "18px 22px", display: "flex", gap: 18, alignItems: "center" }}>
      <MatchRing score={job.relevancy_score || 0} color={job.color} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <strong style={{ fontSize: 16, color: "var(--jp-ink)" }}>{job.title}</strong>
          {job.freshness && (
            <span
              className="jp-badge"
              style={{
                fontSize: 11,
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
              <span key={kw} className="jp-badge" style={{ fontSize: 11 }}>{kw}</span>
            ))}
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
        {job.url && (
          <a href={job.url} target="_blank" rel="noopener noreferrer" className="jp-btn sm ghost">
            Apply
          </a>
        )}
      </div>
    </div>
  );
}
