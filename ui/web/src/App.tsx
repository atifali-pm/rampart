import { useEffect, useMemo, useState } from "react";
import { api, EventRow, IncidentListRow, JobBoardRow, SlaStatus } from "./api";
import { AuditChat } from "./AuditChat";
import { IncidentRoom } from "./IncidentRoom";

const POLL_MS = 3000;

const STATUS_STYLE: Record<SlaStatus, { bg: string; fg: string; label: string }> = {
  ok: { bg: "#0e3a23", fg: "#7be0a4", label: "OK" },
  warning: { bg: "#3a2e0e", fg: "#f0c860", label: "WARN" },
  breach: { bg: "#3a0e0e", fg: "#ff7a7a", label: "BREACH" },
  closed: { bg: "#23262d", fg: "#9aa0aa", label: "CLOSED" },
};

const EVENT_COLOR: Record<string, string> = {
  "transition.applied": "#7be0a4",
  "transition.denied": "#ff7a7a",
  "sla.warning": "#f0c860",
  "sla.breach": "#ff5a5a",
};

function useApiState<T>(loader: () => Promise<T>, intervalMs: number): T | null {
  const [value, setValue] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const v = await loader();
        if (alive) setValue(v);
      } catch {
        /* swallow; polling will retry */
      }
    };
    tick();
    const h = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(h);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return value;
}

function relativeMinutes(min: number): string {
  if (min < -60) return `${Math.round(min / 60)}h overdue`;
  if (min < 0) return `${-min}m overdue`;
  if (min < 60) return `in ${min}m`;
  return `in ${Math.round(min / 60)}h`;
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

function JobBoard({ rows }: { rows: JobBoardRow[] | null }) {
  if (rows === null) return <div style={{ color: "#888" }}>loading...</div>;
  if (rows.length === 0)
    return <div style={{ color: "#888" }}>no jobs in scope</div>;

  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: "ui-monospace, SFMono-Regular, monospace",
        fontSize: "0.85rem",
      }}
    >
      <thead>
        <tr style={{ color: "#9aa0aa", textAlign: "left" }}>
          <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #2a2d33" }}>JOB</th>
          <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #2a2d33" }}>SITE</th>
          <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #2a2d33" }}>STATE</th>
          <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #2a2d33" }}>SLA</th>
          <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #2a2d33" }}>DEADLINE</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const sty = STATUS_STYLE[r.sla_status];
          return (
            <tr key={r.id} style={{ borderBottom: "1px solid #1f2228" }}>
              <td style={{ padding: "0.5rem 0.75rem", color: "#dcdfe6" }}>{shortId(r.id)}</td>
              <td style={{ padding: "0.5rem 0.75rem", color: "#9aa0aa" }}>{shortId(r.site_id)}</td>
              <td style={{ padding: "0.5rem 0.75rem", color: "#dcdfe6" }}>{r.state}</td>
              <td style={{ padding: "0.5rem 0.75rem" }}>
                <span
                  style={{
                    backgroundColor: sty.bg,
                    color: sty.fg,
                    padding: "0.15rem 0.5rem",
                    borderRadius: "0.25rem",
                    fontWeight: 600,
                  }}
                >
                  {sty.label}
                </span>
              </td>
              <td style={{ padding: "0.5rem 0.75rem", color: "#9aa0aa" }}>
                {relativeMinutes(r.minutes_to_deadline)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function EventStream({ events }: { events: EventRow[] | null }) {
  if (events === null) return <div style={{ color: "#888" }}>loading...</div>;
  if (events.length === 0)
    return <div style={{ color: "#888" }}>no events yet</div>;

  return (
    <div style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace", fontSize: "0.8rem" }}>
      {events.map((e) => {
        const color = EVENT_COLOR[e.type] ?? "#dcdfe6";
        const reason = (e.payload.reason_code as string | undefined) ?? "";
        const jobId = (e.payload.job_id as string | undefined) ?? "";
        return (
          <div
            key={e.id}
            style={{
              padding: "0.4rem 0.75rem",
              borderLeft: `3px solid ${color}`,
              marginBottom: "0.4rem",
              backgroundColor: "#1a1c20",
            }}
          >
            <div style={{ color, fontWeight: 600 }}>{e.type}</div>
            <div style={{ color: "#9aa0aa", fontSize: "0.75rem" }}>
              {shortId(jobId)} {reason && `· ${reason}`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      style={{
        backgroundColor: "#1a1c20",
        padding: "0.75rem 1rem",
        borderRadius: "0.4rem",
        minWidth: "8rem",
        borderTop: `3px solid ${color}`,
      }}
    >
      <div style={{ color: "#9aa0aa", fontSize: "0.75rem", textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ color, fontSize: "1.6rem", fontWeight: 700 }}>{value}</div>
    </div>
  );
}

export function App() {
  const rows = useApiState(() => api.board(true), POLL_MS);
  const events = useApiState(() => api.events(20), POLL_MS);
  const incidents = useApiState<IncidentListRow[]>(() => api.incidents(), POLL_MS);

  const stats = useMemo(() => {
    if (!rows) return { ok: 0, warning: 0, breach: 0, closed: 0 };
    const out = { ok: 0, warning: 0, breach: 0, closed: 0 };
    for (const r of rows) out[r.sla_status]++;
    return out;
  }, [rows]);

  const activeIncident = incidents && incidents.length > 0 ? incidents[0] : null;

  return (
    <main
      style={{
        backgroundColor: "#0f1115",
        color: "#dcdfe6",
        minHeight: "100vh",
        fontFamily: "system-ui, sans-serif",
        padding: "2rem",
      }}
    >
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.6rem" }}>Rampart Command Centre</h1>
        <p style={{ color: "#9aa0aa", marginTop: "0.25rem", fontSize: "0.9rem" }}>
          Phase 4: live job board, SLA enforcement, override audit trail, incident command bridge, AI triage + audit chat.
        </p>
      </header>

      <section style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <Stat label="On SLA" value={stats.ok} color="#7be0a4" />
        <Stat label="Warning" value={stats.warning} color="#f0c860" />
        <Stat label="Breach" value={stats.breach} color="#ff5a5a" />
        <Stat label="Closed" value={stats.closed} color="#9aa0aa" />
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 2fr) minmax(280px, 1fr)",
          gap: "1.5rem",
        }}
      >
        <div>
          <h2 style={{ fontSize: "1rem", color: "#9aa0aa", margin: "0 0 0.5rem 0" }}>
            JOB BOARD
          </h2>
          <div
            style={{
              backgroundColor: "#15171c",
              borderRadius: "0.4rem",
              overflow: "hidden",
              marginBottom: "1.25rem",
            }}
          >
            <JobBoard rows={rows} />
          </div>

          <h2 style={{ fontSize: "1rem", color: "#9aa0aa", margin: "0 0 0.5rem 0" }}>
            COMMAND BRIDGE
          </h2>
          {activeIncident ? (
            <IncidentRoom incidentId={activeIncident.id} pollMs={POLL_MS} />
          ) : (
            <div
              style={{
                backgroundColor: "#15171c",
                borderRadius: "0.4rem",
                padding: "1rem",
                color: "#9aa0aa",
                fontSize: "0.85rem",
              }}
            >
              no open incidents
            </div>
          )}
        </div>
        <div>
          <h2 style={{ fontSize: "1rem", color: "#9aa0aa", margin: "0 0 0.5rem 0" }}>
            EVENT STREAM
          </h2>
          <EventStream events={events} />

          <h2 style={{ fontSize: "1rem", color: "#9aa0aa", margin: "1rem 0 0.5rem 0" }}>
            AI
          </h2>
          <AuditChat pollMs={POLL_MS} />
        </div>
      </section>
    </main>
  );
}
