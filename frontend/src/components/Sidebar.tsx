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
        <div className="jp-nav-section">Daily Drive</div>

        <Link href="/daily" className={`jp-nav-item ${pathname === "/daily" ? "active" : ""}`}>
          <span className="ic">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
          </span>
          <span>Today</span>
        </Link>

        <Link href="/weekly" className={`jp-nav-item ${pathname === "/weekly" ? "active" : ""}`}>
          <span className="ic">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" />
              <path d="M16 2v4M8 2v4M3 10h18" />
            </svg>
          </span>
          <span>This Week</span>
        </Link>

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


        <Link href="/referrals" className={`jp-nav-item ${pathname === "/referrals" ? "active" : ""}`}>
          <span className="ic">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </span>
          <span>Referrals</span>
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
