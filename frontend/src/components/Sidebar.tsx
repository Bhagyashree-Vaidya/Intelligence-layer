"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";

export function Sidebar() {
  const pathname = usePathname();
  const [stats, setStats] = useState({ jobs: 0, applications: 0, companies: 0 });

  useEffect(() => {
    getStats()
      .then((d) => setStats(d.stats as any))
      .catch(() => {});
  }, []);

  return (
    <aside className="jp-sidebar">
      <Link href="/" className="jp-brand">
        <span className="mark">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1L15 22v-1.5L13 19v-5.5z" />
          </svg>
        </span>
        <span>JobPilot</span>
        <span className="ver">v4.0</span>
      </Link>

      <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div className="jp-nav-section">Workspace</div>

        <Link href="/" className={`jp-nav-item ${pathname === "/" ? "active" : ""}`}>
          <span className="ic">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="7" width="18" height="13" rx="2" />
              <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <path d="M3 12h18" />
            </svg>
          </span>
          <span>Jobs</span>
          <span className="count">{stats.jobs.toLocaleString()}</span>
        </Link>

        <Link href="/applications" className={`jp-nav-item ${pathname === "/applications" ? "active" : ""}`}>
          <span className="ic">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2 11 13" />
              <path d="m22 2-7 20-4-9-9-4Z" />
            </svg>
          </span>
          <span>Applied</span>
          <span className="count">{stats.applications}</span>
        </Link>

        <div className="jp-nav-section">Account</div>

        <Link href="/profile" className={`jp-nav-item ${pathname === "/profile" ? "active" : ""}`}>
          <span className="ic">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21a8 8 0 1 0-16 0" />
              <circle cx="12" cy="8" r="5" />
            </svg>
          </span>
          <span>Profile & Resumes</span>
        </Link>
      </nav>

      <div className="jp-pilot-card" style={{ marginTop: "auto" }}>
        <div className="jp-pilot-row" style={{ marginBottom: 12 }}>
          <div className="jp-pilot-avatar">BV</div>
          <div className="jp-pilot-meta" style={{ flex: 1, minWidth: 0 }}>
            <div className="name">Bhagyashree Vaidya</div>
            <div className="role">Commander</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
