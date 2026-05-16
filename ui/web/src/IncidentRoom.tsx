import { useEffect, useState } from "react";
import { api, IncidentDetail } from "./api";

const SEVERITY_COLOR: Record<string, string> = {
  low: "#7be0a4",
  medium: "#f0c860",
  high: "#ff8a4a",
  critical: "#ff5a5a",
};

const ROLE_LABEL: Record<string, string> = {
  dispatcher: "Dispatcher",
  supervisor: "Supervisor",
  on_call_manager: "On-Call Manager",
  command_centre: "Command Centre",
  tech: "Tech",
  manager: "Manager",
  system: "System",
};

function shortId(id: string): string {
  return id.slice(0, 8);
}

function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function Ladder({ incident }: { incident: IncidentDetail }) {
  const filled: Record<number, string> = {};
  for (const r of incident.responders) {
    if (r.left_at === null) filled[r.level] = r.role;
  }
  return (
    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
      {Array.from({ length: incident.max_level }, (_, i) => i + 1).map((lvl) => {
        const active = lvl <= incident.current_level;
        const role = filled[lvl];
        return (
          <div
            key={lvl}
            style={{
              flex: 1,
              padding: "0.5rem 0.6rem",
              borderRadius: "0.3rem",
              backgroundColor: active ? "#1f2933" : "#13151a",
              border: `1px solid ${active ? SEVERITY_COLOR[incident.severity] : "#22262e"}`,
              fontSize: "0.75rem",
            }}
          >
            <div style={{ color: "#9aa0aa", fontSize: "0.7rem" }}>L{lvl}</div>
            <div style={{ color: active ? "#dcdfe6" : "#5d6168", fontWeight: 600 }}>
              {ROLE_LABEL[role] ?? role ?? "—"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Timeline({ incident }: { incident: IncidentDetail }) {
  return (
    <div
      style={{
        marginTop: "0.75rem",
        backgroundColor: "#13151a",
        borderRadius: "0.3rem",
        padding: "0.5rem 0.75rem",
        maxHeight: "320px",
        overflowY: "auto",
        fontFamily: "ui-monospace, SFMono-Regular, monospace",
        fontSize: "0.78rem",
      }}
    >
      {incident.messages.length === 0 && (
        <div style={{ color: "#5d6168" }}>no messages yet</div>
      )}
      {incident.messages.map((m) => (
        <div key={m.id} style={{ padding: "0.3rem 0", borderBottom: "1px solid #1c1f25" }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#9aa0aa" }}>
            <span
              style={{
                color: m.kind === "system" ? "#7aa0c2" : "#dcdfe6",
                fontWeight: 600,
              }}
            >
              {m.kind === "system"
                ? "● system"
                : `${m.actor_name} (${ROLE_LABEL[m.actor_role] ?? m.actor_role})`}
            </span>
            <span style={{ color: "#5d6168" }}>{timeOnly(m.posted_at)}</span>
          </div>
          <div style={{ color: m.kind === "system" ? "#9aa0aa" : "#dcdfe6", marginTop: "0.15rem" }}>
            {m.body}
          </div>
        </div>
      ))}
    </div>
  );
}

export function IncidentRoom({ incidentId, pollMs }: { incidentId: string; pollMs: number }) {
  const [detail, setDetail] = useState<IncidentDetail | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const v = await api.incident(incidentId);
        if (alive) setDetail(v);
      } catch {
        /* ignore */
      }
    };
    tick();
    const h = setInterval(tick, pollMs);
    return () => {
      alive = false;
      clearInterval(h);
    };
  }, [incidentId, pollMs]);

  if (detail === null) {
    return <div style={{ color: "#9aa0aa" }}>loading incident...</div>;
  }

  const sevColor = SEVERITY_COLOR[detail.severity] ?? "#dcdfe6";
  return (
    <div
      style={{
        backgroundColor: "#15171c",
        borderRadius: "0.4rem",
        padding: "1rem 1.1rem",
        borderTop: `3px solid ${sevColor}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <div>
          <div style={{ color: sevColor, fontWeight: 700, fontSize: "0.95rem" }}>
            INCIDENT {detail.severity.toUpperCase()}
          </div>
          <div style={{ color: "#9aa0aa", fontSize: "0.78rem" }}>
            Job {shortId(detail.job_id)} · opened {timeOnly(detail.opened_at)} ·
            reason {detail.opened_reason}
          </div>
        </div>
        <div style={{ color: "#9aa0aa", fontSize: "0.78rem" }}>
          {detail.status === "open"
            ? `Level ${detail.current_level} / ${detail.max_level}`
            : "RESOLVED"}
        </div>
      </div>

      <Ladder incident={detail} />
      <Timeline incident={detail} />
    </div>
  );
}
