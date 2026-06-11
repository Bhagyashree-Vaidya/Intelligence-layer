/**
 * API client — all requests go to the FastAPI backend on Fly.io.
 * Never exposes secrets; uses only the public NEXT_PUBLIC_API_URL.
 */

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Jobs ───────────────────────────────────────────────────────────────────
export interface Job {
  id: number;
  greenhouse_id: string;
  company: string;
  title: string;
  location: string;
  department: string;
  url: string;
  description: string;
  relevancy_score: number;
  color: string;
  keywords_list: string[];
  freshness: { hours_ago: number; label: string; badge_color: string };
  updated_at: string;
}

export interface JobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  total_pages: number;
}

export function getJobs(params: Record<string, string> = {}): Promise<JobsResponse> {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/jobs${qs ? `?${qs}` : ""}`);
}

export function getStats(): Promise<{ stats: Record<string, number>; applied_ids: number[] }> {
  return request("/api/stats");
}

export function rescoreAll(): Promise<{ ok: boolean; rescored: number }> {
  return request("/api/rescore", { method: "POST" });
}

export function getRecruiter(jobId: number) {
  return request<Record<string, string>>(`/api/jobs/${jobId}/recruiter`);
}

export function generateMessage(jobId: number, contactName?: string) {
  return request<{ message: string }>(`/api/jobs/${jobId}/message`, {
    method: "POST",
    body: JSON.stringify({ contact_name: contactName || "[Name]" }),
  });
}

export function generateCoverLetter(jobId: number) {
  return request<{ cover_letter: string; job: { title: string; company: string } }>(
    `/api/jobs/${jobId}/cover-letter`,
    { method: "POST" },
  );
}

// ── Scraper ────────────────────────────────────────────────────────────────
export function startScrape(type: "all" | "" | "bigtech" | "apify", body?: Record<string, string>) {
  const path = type ? `/api/scrape/${type}` : "/api/scrape";
  return request(path, { method: "POST", body: JSON.stringify(body || {}) });
}

export function getScrapeStatus() {
  return request<{ running: boolean; progress: string; last_result: string }>("/api/scrape/status");
}

/** WebSocket for real-time scrape progress */
export function connectScrapeWS(onMessage: (data: any) => void): WebSocket {
  const wsUrl = API.replace(/^http/, "ws") + "/api/ws/scrape";
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
}

// ── Profile ────────────────────────────────────────────────────────────────
export function getProfile() {
  return request<{ profile: Record<string, any>; resumes: any[] }>("/api/profile");
}

export function updateProfile(data: Record<string, any>) {
  return request("/api/profile", { method: "PUT", body: JSON.stringify(data) });
}

export function uploadResume(file: File, roleTags: string, isDefault: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("role_tags", roleTags);
  form.append("is_default", String(isDefault));
  return fetch(`${API}/api/resumes/upload`, { method: "POST", body: form }).then((r) => r.json());
}

export function deleteResume(id: number) {
  return request(`/api/resumes/${id}`, { method: "DELETE" });
}

// ── Applications ───────────────────────────────────────────────────────────
export function getApplications(status?: string) {
  const qs = status ? `?status=${status}` : "";
  return request<{ applications: any[]; stats: any }>(`/api/applications${qs}`);
}

export function trackApplication(jobId: number, status = "applied") {
  return request(`/api/track/${jobId}`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function updateAppStatus(appId: number, status: string) {
  return request(`/api/applications/${appId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

// ── Answers ────────────────────────────────────────────────────────────────
export function generateAnswers(questions: string[], company: string, roleTitle: string) {
  return request<Record<string, string>>("/api/answers", {
    method: "POST",
    body: JSON.stringify({ questions, company, role_title: roleTitle }),
  });
}

// ── Signals ───────────────────────────────────────────────────────────────

export interface Signal {
  id: number;
  post_url: string;
  content: string;
  author_name: string;
  author_title: string;
  author_url: string;
  author_company: string;
  platform: string;
  likes: number;
  comments: number;
  reposts: number;
  posted_at: string;
  scraped_at: string;
  hiring_intent: number;
  role_mentioned: string;
  company_mentioned: string;
  seniority_level: string;
  is_recruiter: boolean;
  outreach_viability: number;
  urgency_score: number;
  suggested_action: string;
  ai_reason: string;
  outreach_sent: boolean;
}

export interface SignalsResponse {
  signals: Signal[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface SignalStats {
  total_signals: number;
  high_intent: number;
  actionable: number;
  contacts: number;
}

export interface Contact {
  id: number;
  name: string;
  title: string;
  company: string;
  linkedin_url: string;
  is_recruiter: boolean;
  first_seen_at: string;
  last_seen_at: string;
  interaction_count: number;
  latest_role_mentioned: string;
  outreach_status: string;
  outreach_message?: string;
  is_relevant?: boolean;
  relevance_reason?: string;
}

export function getSignals(params: Record<string, string> = {}): Promise<SignalsResponse> {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/signals${qs ? `?${qs}` : ""}`);
}

export function getSignalStats(): Promise<SignalStats> {
  return request("/api/signals/stats");
}

export function triggerSignalScan(): Promise<{ status: string; message: string }> {
  return request("/api/signals/scan", { method: "POST" });
}

export function getContacts(params: Record<string, string> = {}): Promise<{ contacts: Contact[]; total: number }> {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/signals/contacts${qs ? `?${qs}` : ""}`);
}

export function generateOutreach(data: {
  post_content: string;
  author_name: string;
  author_title: string;
  role_mentioned?: string;
}): Promise<{ outreach_message: string }> {
  return request("/api/signals/outreach", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export interface OutreachResult {
  contact_id: number;
  name: string;
  title: string;
  company: string;
  linkedin_url: string;
  is_recruiter: boolean;
  message: string;
  status: string;
  error?: string;
}

export function batchGenerateOutreach(params: Record<string, any> = {}): Promise<{
  total: number;
  generated: number;
  failed: number;
  messages: OutreachResult[];
}> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  return request(`/api/signals/outreach/batch${qs ? `?${qs}` : ""}`, { method: "POST" });
}

// ── Night Shift ─────────────────────────────────────────────────────────────

export interface NightShiftSettings {
  id: number;
  enabled: boolean;
  max_per_night: number;
  min_fit_score: number;
  enabled_roles: string;
  last_run_at: string | null;
  updated_at: string;
}

export interface NightShiftQueueItem {
  id: number;
  job_id: number;
  company: string;
  title: string;
  url: string;
  role: string;
  resume_id: number | null;
  tier: string;
  status: string;
  error_message: string;
  queued_at: string;
  filled_at: string | null;
  ai_overall_fit?: number;
}

export function getNightShiftSettings(): Promise<{ settings: NightShiftSettings }> {
  return request("/api/night-shift/settings");
}

export function updateNightShiftSettings(
  body: Partial<NightShiftSettings>
): Promise<{ settings: NightShiftSettings }> {
  return request("/api/night-shift/settings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function selectNightShift(dryRun = false): Promise<any> {
  return request(`/api/night-shift/select?dry_run=${dryRun}`, { method: "POST" });
}

export function getNightShiftQueue(status?: string): Promise<{
  queue: NightShiftQueueItem[];
  total: number;
}> {
  const qs = status ? `?status=${status}` : "";
  return request(`/api/night-shift/queue${qs}`);
}

export function updateNightShiftItem(id: number, body: Record<string, any>) {
  return request(`/api/night-shift/queue/${id}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getNightShiftTiers(): Promise<{
  tier_1_never_apply: string[];
  tier_2_eligible: string[];
  tier_1_count: number;
  tier_2_count: number;
}> {
  return request("/api/night-shift/tiers");
}

// ── Daily / Weekly tasks ─────────────────────────────────────────────────────

export interface TaskItem {
  key: string;
  label: string;
  done: boolean;
  notes: string;
}

export interface Funnel {
  applications_sent: number;
  interviews: number;
  offers: number;
  interview_rate: number;
  offer_rate: number;
  responses: number;
  response_rate: number;
  rejections: number;
}

export function getToday(): Promise<{ date: string; tasks: TaskItem[]; funnel: Funnel }> {
  return request("/api/tasks/today");
}

export function getWeek(): Promise<{ week_start: string; tasks: TaskItem[] }> {
  return request("/api/tasks/week");
}

export function tickTask(taskKey: string, cadence: "daily" | "weekly", done: boolean, notes = "") {
  return request("/api/tasks/tick", {
    method: "POST",
    body: JSON.stringify({ task_key: taskKey, cadence, done, notes }),
  });
}

export function getMemoTarget(): Promise<{ target: any; candidates: any[] }> {
  return request("/api/tasks/memo-target");
}

export function generateMemo(body: {
  company: string; target_name?: string; target_title?: string; target_url?: string;
}): Promise<{ id: number; company: string; target_name: string; target_url: string; memo: string }> {
  return request("/api/tasks/generate/memo", { method: "POST", body: JSON.stringify(body) });
}

export function generatePmConcept(focus = ""): Promise<{ id: number; concept: string }> {
  return request("/api/tasks/generate/pm-concept", { method: "POST", body: JSON.stringify({ focus }) });
}

export function generateArticle(topic = ""): Promise<{ id: number; article: string }> {
  return request("/api/tasks/generate/article", { method: "POST", body: JSON.stringify({ topic }) });
}
