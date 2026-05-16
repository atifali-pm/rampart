import { useEffect, useState } from "react";
import { api, Recommendation } from "./api";

const SEVERITY_COLOR: Record<string, string> = {
  low: "#7be0a4",
  medium: "#f0c860",
  high: "#ff8a4a",
  critical: "#ff5a5a",
};

const ACTION_COLOR: Record<string, string> = {
  escalate: "#ff8a4a",
  hold: "#9aa0aa",
  resolve: "#7be0a4",
};

export function TriageCard({ incidentId, pollMs }: { incidentId: string; pollMs: number }) {
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [running, setRunning] = useState(false);

  const refresh = async () => {
    try {
      const list = await api.recommendationsByTarget("incident", incidentId);
      const latest = list.find((r) => r.agent === "triage") ?? null;
      setRec(latest);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refresh();
    const h = setInterval(refresh, pollMs);
    return () => clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId, pollMs]);

  const onRun = async () => {
    setRunning(true);
    try {
      await api.runTriage(incidentId);
      await refresh();
    } finally {
      setRunning(false);
    }
  };

  const out = rec?.output_payload ?? {};
  const sev = (out.recommended_severity as string) ?? null;
  const act = (out.recommended_action as string) ?? null;
  const conf = (out.confidence as number) ?? null;
  const rationale = (out.rationale as string) ?? null;

  return (
    <div
      style={{
        marginTop: "0.9rem",
        backgroundColor: "#13151a",
        borderRadius: "0.4rem",
        padding: "0.75rem 0.9rem",
        border: "1px solid #22262e",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.45rem",
        }}
      >
        <div style={{ color: "#9aa0aa", fontSize: "0.78rem", fontWeight: 600 }}>
          TRIAGE AGENT {rec && (
            <span style={{ fontWeight: 400, color: "#5d6168" }}>
              · {rec.provider}/{rec.model}
            </span>
          )}
        </div>
        <button
          onClick={onRun}
          disabled={running}
          style={{
            backgroundColor: running ? "#22262e" : "#1f2933",
            color: "#dcdfe6",
            border: "1px solid #2a3441",
            padding: "0.3rem 0.7rem",
            borderRadius: "0.3rem",
            fontSize: "0.75rem",
            cursor: running ? "default" : "pointer",
          }}
        >
          {running ? "running..." : rec ? "Re-run" : "Run triage"}
        </button>
      </div>

      {rec === null ? (
        <div style={{ color: "#5d6168", fontSize: "0.8rem" }}>
          no triage recommendation yet
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
            {sev && (
              <span
                style={{
                  backgroundColor: SEVERITY_COLOR[sev] ?? "#1f2933",
                  color: "#0f1115",
                  padding: "0.15rem 0.5rem",
                  borderRadius: "0.25rem",
                  fontWeight: 700,
                  fontSize: "0.75rem",
                }}
              >
                {sev.toUpperCase()}
              </span>
            )}
            {act && (
              <span
                style={{
                  borderColor: ACTION_COLOR[act] ?? "#5d6168",
                  borderStyle: "solid",
                  borderWidth: "1px",
                  color: ACTION_COLOR[act] ?? "#dcdfe6",
                  padding: "0.15rem 0.5rem",
                  borderRadius: "0.25rem",
                  fontWeight: 600,
                  fontSize: "0.75rem",
                }}
              >
                ACTION: {act.toUpperCase()}
              </span>
            )}
            {conf !== null && (
              <span style={{ color: "#5d6168", fontSize: "0.75rem", alignSelf: "center" }}>
                confidence {(conf * 100).toFixed(0)}%
              </span>
            )}
          </div>
          {rationale && (
            <div
              style={{
                color: "#dcdfe6",
                fontSize: "0.82rem",
                lineHeight: 1.45,
              }}
            >
              {rationale}
            </div>
          )}
          <div
            style={{
              color: "#5d6168",
              fontSize: "0.7rem",
              marginTop: "0.4rem",
              fontStyle: "italic",
            }}
          >
            Recommendation only. A dispatcher must commit any state change.
          </div>
        </>
      )}
    </div>
  );
}
