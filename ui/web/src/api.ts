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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  board: (includeClosed = true) =>
    get<JobBoardRow[]>(`/board?include_closed=${includeClosed}`),
  events: (count = 50) => get<EventRow[]>(`/events?count=${count}`),
};
