"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getSignals,
  getSignalStats,
  triggerSignalScan,
  getContacts,
  generateOutreach,
  batchGenerateOutreach,
  type Signal,
  type SignalStats,
  type Contact,
} from "@/lib/api";

type Tab = "signals" | "contacts";

export default function SignalsPage() {
  const [tab, setTab] = useState<Tab>("signals");
  const [stats, setStats] = useState<SignalStats | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState("");

  useEffect(() => {
    getSignalStats().then(setStats).catch(() => {});
  }, []);

  const handleScan = async () => {
    setScanning(true);
    setScanMsg("Scanning LinkedIn...");
    try {
      const res = await triggerSignalScan();
      setScanMsg(res.message || "Scan complete");
      // Refresh stats
      getSignalStats().then(setStats).catch(() => {});
    } catch (e: any) {
      setScanMsg(`Error: ${e.message}`);
    } finally {
      setTimeout(() => setScanning(false), 2000);
    }
  };

  return (
    <div style={{ padding: "28px 36px 60px", overflowY: "auto", height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 className="jp-display">
            <span style={{ fontFamily: "var(--jp-mono)", fontSize: 44, fontWeight: 500 }}>
              {stats?.total_signals ?? "..."}
            </span>{" "}
            <span style={{ color: "var(--jp-dim)", fontStyle: "italic" }}>hiring signals</span>
          </h1>
          <p style={{ color: "var(--jp-mute)", fontSize: 14, marginTop: 4 }}>
            AI-classified LinkedIn posts with hiring intent
          </p>
        </div>
        <button className="jp-btn primary" onClick={handleScan} disabled={scanning}>
          {scanning ? scanMsg : "Scan LinkedIn"}
        </button>
      </div>

      {/* Stat cards */}
      {stats && (
        <div className="jp-grid-3" style={{ marginBottom: 24, gridTemplateColumns: "repeat(4, 1fr)" }}>
          <StatCard label="Total Signals" value={stats.total_signals} color="var(--jp-primary)" />
          <StatCard label="High Intent" value={stats.high_intent} color="var(--jp-emerald)" />
          <StatCard label="Actionable" value={stats.actionable} color="var(--jp-amber)" />
          <StatCard label="Contacts" value={stats.contacts} color="var(--jp-violet)" />
        </div>
      )}

      {/* Tab toggle */}
      <div style={{ marginBottom: 20 }}>
        <div className="jp-seg">
          <button className={tab === "signals" ? "on" : ""} onClick={() => setTab("signals")}>
            Signals
          </button>
          <button className={tab === "contacts" ? "on" : ""} onClick={() => setTab("contacts")}>
            Contacts
          </button>
        </div>
      </div>

      {tab === "signals" ? <SignalsList /> : <ContactsList />}
    </div>
  );
}

/* ── Stat Card ─────────────────────────────────────────────────────────── */

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="jp-card" style={{ padding: "18px 20px" }}>
      <div className="jp-eyebrow" style={{ marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: "var(--jp-mono)", fontSize: 28, fontWeight: 600, color }}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}

/* ── Signals List ──────────────────────────────────────────────────────── */

function SignalsList() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [filter, setFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { page: String(page) };
      if (filter) params.action = filter;
      const res = await getSignals(params);
      setSignals(res.signals);
      setTotal(res.total);
      setTotalPages(res.pages);
    } catch {
      /* empty */
    }
    setLoading(false);
  }, [page, filter]);

  useEffect(() => { fetch(); }, [fetch]);

  return (
    <>
      {/* Action filter */}
      <div style={{ marginBottom: 16 }}>
        <div className="jp-seg">
          {[
            ["", "All"],
            ["apply", "Apply"],
            ["message", "Message"],
            ["connect", "Connect"],
          ].map(([val, label]) => (
            <button
              key={val}
              className={filter === val ? "on" : ""}
              onClick={() => { setFilter(val); setPage(1); }}
            >
              {label}
            </button>
          ))}
        </div>
        <span style={{ marginLeft: 12, fontSize: 13, color: "var(--jp-mute)" }}>
          {total} signals
        </span>
      </div>

      {/* Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {loading ? (
          <div className="jp-card" style={{ padding: 48, textAlign: "center", color: "var(--jp-mute)" }}>
            Loading signals...
          </div>
        ) : signals.length === 0 ? (
          <div className="jp-card" style={{ padding: 48, textAlign: "center", color: "var(--jp-dim)" }}>
            No signals yet. Click &quot;Scan LinkedIn&quot; to find hiring posts.
          </div>
        ) : (
          signals.map((s) => <SignalCard key={s.id} signal={s} />)
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 24 }}>
          <button className="jp-btn sm ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span style={{ padding: "8px 16px", fontFamily: "var(--jp-mono)" }}>
            {page} / {totalPages}
          </span>
          <button className="jp-btn sm ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </>
  );
}

/* ── Signal Card ───────────────────────────────────────────────────────── */

function SignalCard({ signal }: { signal: Signal }) {
  const [outreach, setOutreach] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const actionColor: Record<string, string> = {
    apply: "emerald",
    message: "primary",
    connect: "amber",
    skip: "ghost",
  };

  const handleOutreach = async () => {
    setGenerating(true);
    try {
      const res = await generateOutreach({
        post_content: signal.content,
        author_name: signal.author_name,
        author_title: signal.author_title,
        role_mentioned: signal.role_mentioned,
      });
      setOutreach(res.outreach_message);
    } catch {
      setOutreach("Failed to generate — is your profile set up?");
    }
    setGenerating(false);
  };

  return (
    <div className="jp-card" style={{ padding: "18px 22px" }}>
      <div style={{ display: "flex", gap: 16 }}>
        {/* Intent score */}
        <div style={{
          width: 52, height: 52, borderRadius: 14, display: "grid", placeItems: "center",
          background: "var(--neu-bg)", boxShadow: "var(--neu-raised-sm)", flexShrink: 0,
        }}>
          <div style={{
            fontFamily: "var(--jp-mono)", fontSize: 18, fontWeight: 700,
            color: signal.hiring_intent >= 70 ? "var(--jp-emerald)" :
                   signal.hiring_intent >= 50 ? "var(--jp-amber)" : "var(--jp-dim)",
          }}>
            {signal.hiring_intent}
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <strong style={{ fontSize: 15 }}>{signal.author_name}</strong>
            {signal.is_recruiter && (
              <span className="jp-chip violet" style={{ fontSize: 10, height: 20, padding: "0 8px" }}>Recruiter</span>
            )}
            <span className={`jp-chip ${actionColor[signal.suggested_action] || "ghost"}`}
              style={{ fontSize: 10, height: 20, padding: "0 8px", marginLeft: "auto" }}>
              {signal.suggested_action}
            </span>
          </div>

          <div style={{ fontSize: 13, color: "var(--jp-dim)", marginBottom: 6 }}>
            {signal.author_title}
            {signal.author_company && ` at ${signal.author_company}`}
          </div>

          {/* Post content preview */}
          <div style={{
            fontSize: 14, color: "var(--jp-ink-2)", lineHeight: 1.5,
            maxHeight: 60, overflow: "hidden", marginBottom: 8,
          }}>
            {signal.content}
          </div>

          {/* Metadata row */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            {signal.role_mentioned && (
              <span className="jp-chip primary" style={{ fontSize: 11, height: 22 }}>
                {signal.role_mentioned}
              </span>
            )}
            {signal.seniority_level && (
              <span className="jp-chip ghost" style={{ fontSize: 11, height: 22 }}>
                {signal.seniority_level}
              </span>
            )}
            <span style={{ fontSize: 12, color: "var(--jp-mute)", fontFamily: "var(--jp-mono)" }}>
              Urgency {signal.urgency_score}
            </span>
            <span style={{ fontSize: 12, color: "var(--jp-mute)", fontFamily: "var(--jp-mono)" }}>
              Outreach {signal.outreach_viability}%
            </span>
            {signal.likes > 0 && (
              <span style={{ fontSize: 12, color: "var(--jp-mute)" }}>
                {signal.likes} likes
              </span>
            )}
          </div>

          {/* AI reason */}
          {signal.ai_reason && (
            <div style={{ fontSize: 13, color: "var(--jp-dim)", marginTop: 6, fontStyle: "italic" }}>
              {signal.ai_reason}
            </div>
          )}

          {/* Outreach */}
          {outreach && (
            <div className="neu-well" style={{ marginTop: 12, fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              {outreach}
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8, flexShrink: 0 }}>
          {signal.post_url && (
            <a href={signal.post_url} target="_blank" rel="noopener noreferrer" className="jp-btn sm ghost">
              View
            </a>
          )}
          {signal.author_url && (
            <a href={signal.author_url} target="_blank" rel="noopener noreferrer" className="jp-btn sm ghost">
              Profile
            </a>
          )}
          {!outreach && (
            <button className="jp-btn sm primary" onClick={handleOutreach} disabled={generating}>
              {generating ? "..." : "Draft"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Contacts List ─────────────────────────────────────────────────────── */

type FilterMode = "relevant" | "all" | "recruiters";

function ContactsList() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterMode, setFilterMode] = useState<FilterMode>("relevant");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState("");

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { page: String(page) };
      if (filterMode === "recruiters") params.recruiter_only = "true";
      if (filterMode === "relevant") params.relevant_only = "true";
      const res = await getContacts(params);
      setContacts(res.contacts);
      setTotal(res.total);
    } catch {
      /* empty */
    }
    setLoading(false);
  }, [page, filterMode]);

  const setMode = (m: FilterMode) => { setFilterMode(m); setPage(1); };

  const handleBatchGenerate = async () => {
    setGenerating(true);
    setGenMsg("Generating outreach messages...");
    try {
      const params: Record<string, any> = {};
      if (filterMode === "recruiters") params.recruiter_only = true;
      if (filterMode === "relevant") params.relevant_only = true;
      const res = await batchGenerateOutreach(params);
      setGenMsg(`Generated ${res.generated}/${res.total} messages (${res.failed} failed)`);
      // Refresh contacts to show newly generated messages
      fetch();
      setTimeout(() => setGenMsg(""), 3000);
    } catch (e: any) {
      setGenMsg(`Error: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  };

  useEffect(() => { fetch(); }, [fetch]);

  return (
    <>
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="jp-seg">
            <button className={filterMode === "relevant" ? "on" : ""} onClick={() => setMode("relevant")}>
              Relevant US
            </button>
            <button className={filterMode === "all" ? "on" : ""} onClick={() => setMode("all")}>
              All
            </button>
            <button className={filterMode === "recruiters" ? "on" : ""} onClick={() => setMode("recruiters")}>
              Recruiters
            </button>
          </div>
          <span style={{ fontSize: 13, color: "var(--jp-mute)" }}>{total} contacts</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {genMsg && <span style={{ fontSize: 13, color: "var(--jp-dim)" }}>{genMsg}</span>}
          <button className="jp-btn primary" onClick={handleBatchGenerate} disabled={generating || total === 0}>
            {generating ? "Generating..." : "Generate All"}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {loading ? (
          <div className="jp-card" style={{ padding: 48, textAlign: "center", color: "var(--jp-mute)" }}>
            Loading contacts...
          </div>
        ) : contacts.length === 0 ? (
          <div className="jp-card" style={{ padding: 48, textAlign: "center", color: "var(--jp-dim)" }}>
            No contacts discovered yet. Signals with high hiring intent automatically create contacts.
          </div>
        ) : (
          contacts.map((c) => <ContactCard key={c.id} contact={c} />)
        )}
      </div>

      {total > 30 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 24 }}>
          <button className="jp-btn sm ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span style={{ padding: "8px 16px", fontFamily: "var(--jp-mono)" }}>
            Page {page}
          </span>
          <button className="jp-btn sm ghost" onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </>
  );
}

/* ── Contact Card ──────────────────────────────────────────────────────── */

function ContactCard({ contact }: { contact: Contact }) {
  const initials = contact.name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const statusColor: Record<string, string> = {
    none: "ghost",
    drafted: "amber",
    sent: "primary",
    replied: "emerald",
    meeting: "violet",
  };

  return (
    <div className="jp-card" style={{ padding: "16px 20px" }}>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <div className="jp-co">{initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
            <strong style={{ fontSize: 15 }}>{contact.name}</strong>
            {contact.is_recruiter && (
              <span className="jp-chip violet" style={{ fontSize: 10, height: 20, padding: "0 8px" }}>Recruiter</span>
            )}
          </div>
          <div style={{ fontSize: 13, color: "var(--jp-dim)" }}>
            {contact.title}{contact.company && ` at ${contact.company}`}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
            {contact.latest_role_mentioned && (
              <span className="jp-chip primary" style={{ fontSize: 10, height: 20, padding: "0 8px" }}>
                {contact.latest_role_mentioned}
              </span>
            )}
            <span style={{ fontSize: 12, color: "var(--jp-mute)", fontFamily: "var(--jp-mono)" }}>
              Seen {contact.interaction_count}x
            </span>
          </div>

          {/* Relevance reason */}
          {contact.is_relevant && contact.relevance_reason && (
            <div style={{ fontSize: 12, color: "var(--jp-emerald)", marginTop: 6 }}>
              ✓ {contact.relevance_reason}
            </div>
          )}

          {/* Outreach message */}
          {contact.outreach_message && (
            <div className="neu-well" style={{ marginTop: 12, fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              {contact.outreach_message}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
          <span className={`jp-chip ${statusColor[contact.outreach_status] || "ghost"}`}
            style={{ fontSize: 11, height: 24 }}>
            {contact.outreach_status}
          </span>
          {contact.linkedin_url && (
            <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="jp-btn sm ghost">
              LinkedIn
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
