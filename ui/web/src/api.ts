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

export const api = {
  board: (includeClosed = true) =>
    get<JobBoardRow[]>(`/board?include_closed=${includeClosed}`),
  events: (count = 50) => get<EventRow[]>(`/events?count=${count}`),
  incidents: () => get<IncidentListRow[]>(`/incidents`),
  incident: (id: string) => get<IncidentDetail>(`/incidents/${id}`),
};
