/* Minimal API client for the Rampart dashboard. */

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? "http://localhost:8040";

export type SlaStatus = "ok" | "warning" | "breach" | "closed";

export interface JobBoardRow {
  id: string;
  site_id: string;
  state: string;
  sla_deadline: string;
  sla_status: SlaStatus;
  minutes_to_deadline: number;
}

export interface EventRow {
  id: string;
  type: string;
  payload: Record<string, unknown>;
}

export interface IncidentListRow {
  id: string;
  job_id: string;
  severity: string;
  status: string;
  current_level: number;
  opened_reason: string;
  opened_at: string;
  resolved_at: string | null;
}

export interface Responder {
  actor_id: string;
  actor_name: string;
  role: string;
  level: number;
  joined_at: string;
  left_at: string | null;
}

export interface Message {
  id: string;
  actor_name: string;
  actor_role: string;
  kind: "chat" | "system";
  body: string;
  posted_at: string;
}

export interface IncidentDetail {
  id: string;
  job_id: string;
  severity: string;
  status: string;
  current_level: number;
  max_level: number;
  opened_reason: string;
  opened_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
  responders: Responder[];
  messages: Message[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

export interface Recommendation {
  id: string;
  agent: string;
  target_kind: string;
  target_id: string | null;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  provider: string;
  model: string;
  status: string;
  created_at: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  board: (includeClosed = true) =>
    get<JobBoardRow[]>(`/board?include_closed=${includeClosed}`),
  events: (count = 50) => get<EventRow[]>(`/events?count=${count}`),
  incidents: () => get<IncidentListRow[]>(`/incidents`),
  incident: (id: string) => get<IncidentDetail>(`/incidents/${id}`),

  recommendationsByTarget: (kind: string, id: string) =>
    get<Recommendation[]>(
      `/ai/recommendations/by-target?target_kind=${kind}&target_id=${id}`,
    ),
  recentRecommendations: (limit = 10) =>
    get<Recommendation[]>(`/ai/recommendations/recent?limit=${limit}`),

  runTriage: (incidentId: string) =>
    post<{ recommendation_id: string; output: Record<string, unknown>; provider: string }>(
      `/ai/triage/incidents/${incidentId}`,
      {},
    ),
  askAudit: (question: string) =>
    post<{ recommendation_id: string; output: Record<string, unknown>; provider: string }>(
      `/ai/audit-chat`,
      { question },
    ),
};
