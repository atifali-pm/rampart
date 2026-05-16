import { useEffect, useState } from "react";
import { api, Recommendation } from "./api";

interface AnswerView {
  question: string;
  answer: string;
  citations: { kind: string; id: string }[];
  provider: string;
}

export function AuditChat({ pollMs }: { pollMs: number }) {
  const [question, setQuestion] = useState("");
  const [view, setView] = useState<AnswerView | null>(null);
  const [running, setRunning] = useState(false);

  const loadLatest = async () => {
    try {
      const recs = await api.recentRecommendations(50);
      const latest = recs.find((r) => r.agent === "audit_chat") ?? null;
      if (latest) setView(viewFromRec(latest));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    loadLatest();
    const h = setInterval(loadLatest, pollMs);
    return () => clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollMs]);

  const onAsk = async () => {
    if (!question.trim()) return;
    setRunning(true);
    try {
      const r = await api.askAudit(question.trim());
      const out = r.output as { answer?: string; citations?: { kind: string; id: string }[] };
      setView({
        question,
        answer: out.answer ?? "(no answer)",
        citations: out.citations ?? [],
        provider: r.provider,
      });
      setQuestion("");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div
      style={{
        backgroundColor: "#15171c",
        borderRadius: "0.4rem",
        padding: "0.85rem 0.95rem",
        borderTop: "3px solid #6f9dc6",
      }}
    >
      <div style={{ color: "#6f9dc6", fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.45rem" }}>
        AUDIT CHAT
      </div>
      <div style={{ display: "flex", gap: "0.4rem" }}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onAsk();
          }}
          placeholder='e.g. "Why was the closeout denied?"'
          style={{
            flex: 1,
            backgroundColor: "#0f1115",
            color: "#dcdfe6",
            border: "1px solid #2a2d33",
            borderRadius: "0.3rem",
            padding: "0.4rem 0.55rem",
            fontSize: "0.8rem",
            fontFamily: "inherit",
          }}
        />
        <button
          onClick={onAsk}
          disabled={running || !question.trim()}
          style={{
            backgroundColor: "#1f2933",
            color: "#dcdfe6",
            border: "1px solid #2a3441",
            padding: "0.4rem 0.8rem",
            borderRadius: "0.3rem",
            fontSize: "0.8rem",
            cursor: running ? "default" : "pointer",
          }}
        >
          {running ? "..." : "ask"}
        </button>
      </div>

      {view && (
        <div style={{ marginTop: "0.6rem" }}>
          <div style={{ color: "#9aa0aa", fontSize: "0.72rem", marginBottom: "0.25rem" }}>
            Q: {view.question} <span style={{ color: "#5d6168" }}>· {view.provider}</span>
          </div>
          <div
            style={{
              backgroundColor: "#0f1115",
              color: "#dcdfe6",
              padding: "0.55rem 0.7rem",
              borderRadius: "0.3rem",
              whiteSpace: "pre-wrap",
              fontSize: "0.8rem",
              lineHeight: 1.45,
              fontFamily: "ui-monospace, SFMono-Regular, monospace",
            }}
          >
            {view.answer}
          </div>
          {view.citations.length > 0 && (
            <div style={{ color: "#5d6168", fontSize: "0.7rem", marginTop: "0.3rem" }}>
              cites: {view.citations.map((c) => `${c.kind}:${shortId(c.id)}`).join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function viewFromRec(r: Recommendation): AnswerView {
  const out = r.output_payload as { answer?: string; citations?: { kind: string; id: string }[] };
  const input = r.input_payload as { question?: string };
  return {
    question: input.question ?? "",
    answer: out.answer ?? "",
    citations: out.citations ?? [],
    provider: r.provider,
  };
}

function shortId(id: string | undefined | null): string {
  return (id ?? "").slice(0, 8);
}
