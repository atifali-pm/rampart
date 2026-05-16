"""Echo provider: deterministic, no LLM, schema-aware.

Used by tests and by anyone running the project without a cloud API
key. Outputs are produced by a small set of heuristic rules so the
shape and rough sentiment of a real LLM response are preserved. Adding
a new agent means teaching `_handle_*` what a plausible output looks
like for its schema.

The portfolio framing is honest: this is a deterministic fallback. The
real value is the provider abstraction, which means the same agent
code calls Groq the moment GROQ_API_KEY appears in the environment.
"""

from __future__ import annotations

import json
from typing import Any

from src.ai.providers.base import Provider, ProviderInfo

_INFO = ProviderInfo(name="echo", model="echo-v1")


class EchoProvider(Provider):
    @property
    def info(self) -> ProviderInfo:
        return _INFO

    def generate_text(self, *, system: str, user: str) -> str:
        return (
            "ECHO PROVIDER (no LLM configured). "
            "Set GROQ_API_KEY in .env to switch to a real model.\n\n"
            f"You asked: {user.strip()[:240]}"
        )

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        # The user message carries the agent's structured context. Each
        # agent prefixes the JSON payload with a banner like
        # `[triage]\n{...}` so we can route here without parsing free
        # text. If the banner is missing we fall back to a generic shape.
        first_line, _, body = user.partition("\n")
        agent_tag = first_line.strip().strip("[]").lower()
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        if agent_tag == "triage":
            return _handle_triage(payload)
        if agent_tag == "dispatch":
            return _handle_dispatch(payload)
        if agent_tag == "closeout":
            return _handle_closeout(payload)
        if agent_tag == "audit_chat":
            return _handle_audit_chat(payload)

        return {"note": "echo provider: no handler matched", "tag": agent_tag}


# ---- per-agent deterministic handlers --------------------------------------

def _handle_triage(payload: dict[str, Any]) -> dict[str, Any]:
    minutes_overdue = float(payload.get("minutes_overdue", 0) or 0)
    denied_count = int(payload.get("denied_count", 0) or 0)
    current_level = int(payload.get("current_level", 1) or 1)
    max_level = int(payload.get("max_level", 1) or 1)
    severity_now = (payload.get("severity") or "high").lower()

    # Heuristic: longer breaches and stacked denials push severity up.
    score = minutes_overdue / 30 + denied_count * 1.5
    if score >= 6 or severity_now == "critical":
        recommended_severity = "critical"
    elif score >= 3 or severity_now == "high":
        recommended_severity = "high"
    elif score >= 1 or severity_now == "medium":
        recommended_severity = "medium"
    else:
        recommended_severity = "low"

    if recommended_severity == "critical" and current_level < max_level:
        action = "escalate"
    elif recommended_severity == "high" and current_level < max_level and minutes_overdue > 15:
        action = "escalate"
    else:
        action = "hold"

    rationale_bits = []
    if minutes_overdue > 0:
        rationale_bits.append(f"SLA is {int(minutes_overdue)} min past deadline.")
    if denied_count > 0:
        rationale_bits.append(
            f"{denied_count} closeout denial(s) on this job suggest evidence is missing."
        )
    rationale_bits.append(
        f"Ladder is at L{current_level}/L{max_level}; "
        f"{'recommend bumping' if action == 'escalate' else 'holding at current level'}."
    )

    return {
        "recommended_severity": recommended_severity,
        "recommended_action": action,
        "confidence": 0.55 if recommended_severity == severity_now else 0.7,
        "rationale": " ".join(rationale_bits),
        "tags": ["sla_breach"] if minutes_overdue > 0 else [],
    }


def _handle_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    techs = payload.get("technicians", []) or []
    job_skill_tags = set((payload.get("job_skills") or []))
    site_lat = float(payload.get("site_latitude", 0) or 0)
    site_lon = float(payload.get("site_longitude", 0) or 0)

    ranked = []
    for t in techs:
        skill_match = len(set(t.get("skills", [])) & job_skill_tags)
        # Cheap proxy for distance: degrees of separation. Good enough
        # for the echo shape.
        dlat = float(t.get("home_latitude", 0) or 0) - site_lat
        dlon = float(t.get("home_longitude", 0) or 0) - site_lon
        rough_km = ((dlat ** 2 + dlon ** 2) ** 0.5) * 111
        load = int(t.get("current_load", 0) or 0)
        sla_pct = float(t.get("historical_sla_pct", 1.0) or 1.0)

        score = skill_match * 5 - rough_km * 0.05 - load * 2 + sla_pct * 4
        ranked.append(
            {
                "technician_id": t.get("id"),
                "name": t.get("name"),
                "score": round(score, 2),
                "rationale": (
                    f"{skill_match} skill match(es), "
                    f"~{int(rough_km)} km from site, "
                    f"load {load}, historical SLA {int(sla_pct * 100)}%."
                ),
            }
        )
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {"ranking": ranked[:5], "method": "echo_heuristic"}


def _handle_closeout(payload: dict[str, Any]) -> dict[str, Any]:
    site_name = payload.get("site_name") or "the site"
    duration_min = int(payload.get("duration_minutes", 0) or 0)
    checklist = payload.get("checklist_completed", []) or []
    photos_count = int(payload.get("photos_count", 0) or 0)

    summary = (
        f"Work at {site_name} completed in {duration_min} minutes. "
        f"{photos_count} photo(s) on file. "
        f"{len(checklist)} checklist item(s) confirmed: "
        f"{', '.join(checklist) if checklist else 'none recorded'}."
    )
    return {
        "customer_summary": summary,
        "internal_note": "Echo draft. Re-run with a real LLM provider for richer phrasing.",
        "follow_up_required": photos_count == 0,
    }


def _handle_audit_chat(payload: dict[str, Any]) -> dict[str, Any]:
    question = (payload.get("question") or "").strip()
    citations = payload.get("relevant_transitions", []) or []
    incidents = payload.get("relevant_incidents", []) or []

    # Heuristic answer assembly: stitch the candidate transitions
    # into a short narrative the user can sanity-check.
    if not citations and not incidents:
        answer = (
            "No matching audit rows were found for that question. "
            "Try narrowing by job id, time window, or reason code."
        )
    else:
        lines = [f"Looking at the audit log for: {question or '(no question text)'}"]
        for c in citations[:5]:
            lines.append(
                f"- {c.get('occurred_at', '?')}  "
                f"{c.get('from_state', '?')} -> {c.get('to_state', '?')}  "
                f"{c.get('decision', '?')} ({c.get('reason_code') or '-'})"
            )
        for inc in incidents[:3]:
            lines.append(
                f"- incident {inc.get('severity', '?')} opened "
                f"{inc.get('opened_at', '?')} (reason {inc.get('opened_reason', '?')})"
            )
        answer = "\n".join(lines)

    return {
        "answer": answer,
        "citations": [
            {"kind": "transition", "id": c.get("id")} for c in citations[:5]
        ]
        + [{"kind": "incident", "id": i.get("id")} for i in incidents[:3]],
    }
