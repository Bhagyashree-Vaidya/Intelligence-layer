"use client";

import { useEffect, useState } from "react";
import { getProfile, updateProfile, uploadResume, deleteResume } from "@/lib/api";

const FIELDS = [
  { section: "Personal Info", fields: [
    { key: "first_name", label: "First Name" }, { key: "last_name", label: "Last Name" },
    { key: "email", label: "Email", type: "email" }, { key: "phone", label: "Phone", type: "tel" },
  ]},
  { section: "Location", fields: [
    { key: "address", label: "Address" }, { key: "city", label: "City" },
    { key: "state", label: "State" }, { key: "zip_code", label: "ZIP" },
    { key: "country", label: "Country" },
  ]},
  { section: "Professional", fields: [
    { key: "current_company", label: "Current Company" }, { key: "current_title", label: "Current Title" },
    { key: "years_experience", label: "Years of Experience", type: "number" },
    { key: "skills", label: "Skills (comma-separated)", wide: true },
    { key: "linkedin", label: "LinkedIn URL" }, { key: "website", label: "Website" },
    { key: "github", label: "GitHub" },
  ]},
  { section: "EEO & Work Auth", fields: [
    { key: "work_auth", label: "Work Authorization" }, { key: "sponsorship", label: "Needs Sponsorship" },
    { key: "gender", label: "Gender" }, { key: "veteran", label: "Veteran Status" },
    { key: "disability", label: "Disability Status" },
  ]},
];

export default function ProfilePage() {
  const [profile, setProfile] = useState<Record<string, any>>({});
  const [resumes, setResumes] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const fetchProfile = async () => {
    const res = await getProfile();
    setProfile(res.profile || {});
    setResumes(res.resumes || []);
  };

  useEffect(() => { fetchProfile(); }, []);

  const handleSave = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    const fd = new FormData(e.currentTarget);
    const data: Record<string, any> = {};
    for (const [k, v] of fd.entries()) data[k] = v;
    await updateProfile(data);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadResume(file, "", resumes.length === 0);
    fetchProfile();
    e.target.value = "";
  };

  const handleDelete = async (id: number) => {
    await deleteResume(id);
    fetchProfile();
  };

  // Completeness meter
  const filledCount = ["first_name", "last_name", "email", "phone", "city", "state",
    "current_title", "current_company", "skills", "linkedin", "years_experience", "work_auth",
  ].filter((k) => profile[k] && String(profile[k]).trim()).length;
  const pct = Math.round((filledCount / 12) * 100);

  return (
    <div style={{ padding: "28px 36px 60px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
        <h1 className="jp-display">Profile & Resumes</h1>
        {/* Completeness ring */}
        <div className="jp-card" style={{ padding: 20, display: "flex", alignItems: "center", gap: 16 }}>
          <svg width="56" height="56" viewBox="0 0 56 56">
            <circle cx="28" cy="28" r="24" fill="none" stroke="var(--neu-bg-2)" strokeWidth="5" />
            <circle
              cx="28" cy="28" r="24" fill="none"
              stroke={pct >= 80 ? "var(--jp-emerald)" : pct >= 50 ? "var(--jp-amber)" : "var(--jp-rose)"}
              strokeWidth="5" strokeDasharray={2 * Math.PI * 24} strokeDashoffset={2 * Math.PI * 24 * (1 - pct / 100)}
              strokeLinecap="round" transform="rotate(-90 28 28)"
            />
            <text x="28" y="32" textAnchor="middle" fontSize="14" fontWeight="600" fontFamily="var(--jp-mono)" fill="var(--jp-ink)">
              {pct}%
            </text>
          </svg>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Profile</div>
            <div style={{ fontSize: 12, color: "var(--jp-dim)" }}>{filledCount}/12 fields</div>
          </div>
        </div>
      </div>

      {saved && (
        <div className="jp-card" style={{ padding: "12px 20px", marginBottom: 20, background: "var(--jp-emerald-50)", color: "var(--jp-emerald)" }}>
          Profile saved successfully.
        </div>
      )}

      <form onSubmit={handleSave}>
        {FIELDS.map(({ section, fields }) => (
          <div key={section} className="jp-card" style={{ padding: 24, marginBottom: 20 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: "var(--jp-ink)" }}>{section}</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {fields.map((f) => (
                <div key={f.key} className="jp-field" style={(f as any).wide ? { gridColumn: "span 2" } : {}}>
                  <label className="label">{f.label}</label>
                  <input
                    className="jp-input"
                    name={f.key}
                    type={(f as any).type || "text"}
                    defaultValue={profile[f.key] || ""}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}

        {/* My Voice — AI generation instructions */}
        <div className="jp-card" style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4, color: "var(--jp-ink)" }}>My Voice</h2>
          <p style={{ fontSize: 13, color: "var(--jp-mute)", marginBottom: 16 }}>
            Tone &amp; style instructions for AI-generated cover letters and outreach messages.
            Plain English — e.g. &ldquo;colloquial, hyper-personalized, weave in current trends.&rdquo;
          </p>
          <textarea
            className="jp-input"
            name="voice_instructions"
            defaultValue={profile.voice_instructions || ""}
            rows={7}
            style={{ width: "100%", resize: "vertical" }}
          />
        </div>

        {/* Cover letter */}
        <div className="jp-card" style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: "var(--jp-ink)" }}>Cover Letter</h2>
          <textarea
            className="jp-input"
            name="cover_letter_default"
            defaultValue={profile.cover_letter_default || ""}
            rows={6}
            style={{ width: "100%", resize: "vertical" }}
          />
        </div>

        <button type="submit" className="jp-btn primary" disabled={saving} style={{ marginBottom: 32 }}>
          {saving ? "Saving..." : "Save Profile"}
        </button>
      </form>

      {/* Resumes */}
      <div className="jp-card" style={{ padding: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--jp-ink)" }}>Resumes</h2>
          <label className="jp-btn sm ghost" style={{ cursor: "pointer" }}>
            Upload
            <input type="file" accept=".pdf,.docx" onChange={handleUpload} style={{ display: "none" }} />
          </label>
        </div>
        {resumes.length === 0 ? (
          <div style={{ color: "var(--jp-dim)", padding: 20, textAlign: "center" }}>No resumes uploaded yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {resumes.map((r) => (
              <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderRadius: 12, boxShadow: "var(--neu-raised-sm)" }}>
                <span style={{ fontSize: 14, flex: 1 }}>{r.original_name}</span>
                {r.is_default && <span className="jp-badge" style={{ background: "var(--jp-primary-50)", color: "var(--jp-primary)" }}>Default</span>}
                <button className="jp-btn sm ghost" style={{ color: "var(--jp-rose)" }} onClick={() => handleDelete(r.id)}>Delete</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
