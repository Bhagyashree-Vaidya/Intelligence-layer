/**
 * API client — all requests go to the backend at jobs.shreevaidya.com.
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
