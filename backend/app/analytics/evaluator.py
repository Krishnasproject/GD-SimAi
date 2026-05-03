from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Iterable

from app.models.transcript import Turn
from app.services.llm import GeminiService

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


async def evaluate_transcript(
    llm: GeminiService,
    topic: str,
    transcript: Iterable[Turn | dict],
    metrics: dict,
) -> dict:
    turns: list[Turn] = [turn if isinstance(turn, Turn) else Turn(**turn) for turn in transcript]

    condensed = "\n".join(
        f"- {turn.speaker_id}: {turn.text[:240]}" for turn in turns[-20:]
    )

    # Build a compact metrics summary for the prompt
    logic = metrics.get("logicScore", {}).get("score", 0)
    diplomacy = metrics.get("diplomacyScore", {}).get("score", 0)
    airtime_pct = metrics.get("airtime", {}).get("userPercent", 0.0)
    placement = metrics.get("placementScore", 0)
    archetype = metrics.get("communicationArchetype", "")

    prompt = (
        "You are an expert GD (Group Discussion) evaluator for campus placements. "
        "Return STRICT JSON only — no markdown, no code fences — with EXACTLY these keys:\n"
        "  geminiVerdict      (string, 2-3 sentences overall assessment)\n"
        "  geminiStrengths    (string[], exactly 3 concise strengths)\n"
        "  geminiWeaknesses   (string[], exactly 3 areas to improve)\n"
        "  geminiNextSteps    (string[], exactly 3 actionable next steps)\n"
        "  confidenceLevel    (string: 'High' | 'Medium' | 'Low')\n"
        "  confidenceRationale (string, 1 sentence explaining why)\n"
        "  communicationStyle (string, one of: 'Analytical' | 'Diplomatic' | 'Assertive' | 'Collaborative' | 'Reserved')\n"
        "  topicMastery       (string, 1 sentence on domain knowledge shown)\n"
        "  keyMoments         (string[], exactly 2 notable moments from the transcript)\n\n"
        f"Topic: {topic}\n"
        f"Computed metrics — Placement Score: {placement}/100 | Logic: {logic}/100 | "
        f"Diplomacy: {diplomacy}/100 | Airtime: {airtime_pct:.1f}% (benchmark 15-35%) | "
        f"Rule-based archetype: {archetype}\n"
        "Transcript (latest turns):\n"
        f"{condensed}\n"
        "Be specific, honest, and practical. Focus on placement GD best practices."
    )

    try:
        raw = await llm.generate(
            prompt=prompt,
            system_instruction=(
                "You are strict, concise, and practical in GD feedback. "
                "Return ONLY valid JSON with the exact keys requested."
            ),
            max_tokens=600,
        )
        data = _extract_json(raw)
        if data:
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Evaluator fallback used due to error: %s", exc)

    return _fallback_from_metrics(metrics)


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None

    candidate = raw.strip()
    # Strip markdown code fences if present
    candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.MULTILINE)
    candidate = re.sub(r"\s*```$", "", candidate, flags=re.MULTILINE)

    match = _JSON_BLOCK.search(candidate)
    if match:
        candidate = match.group(0)

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    required = {
        "geminiVerdict",
        "geminiStrengths",
        "geminiWeaknesses",
        "geminiNextSteps",
    }
    if not required.issubset(parsed.keys()):
        return None

    return {
        "geminiVerdict": str(parsed.get("geminiVerdict", "")),
        "geminiStrengths": [str(x) for x in parsed.get("geminiStrengths", [])][:3],
        "geminiWeaknesses": [str(x) for x in parsed.get("geminiWeaknesses", [])][:3],
        "geminiNextSteps": [str(x) for x in parsed.get("geminiNextSteps", [])][:3],
        "confidenceLevel": str(parsed.get("confidenceLevel", "Medium")),
        "confidenceRationale": str(parsed.get("confidenceRationale", "")),
        "communicationStyle": str(parsed.get("communicationStyle", "")),
        "topicMastery": str(parsed.get("topicMastery", "")),
        "keyMoments": [str(x) for x in parsed.get("keyMoments", [])][:2],
    }


def _fallback_from_metrics(metrics: dict) -> dict:
    logic = int(metrics.get("logicScore", {}).get("score", 0))
    diplomacy = int(metrics.get("diplomacyScore", {}).get("score", 0))
    airtime = float(metrics.get("airtime", {}).get("userPercent", 0.0))
    placement = int(metrics.get("placementScore", 0))
    archetype = metrics.get("communicationArchetype", "Balanced")

    verdict = (
        f"You showed {('strong' if logic >= 70 else 'developing')} structure and "
        f"{('good' if diplomacy >= 65 else 'limited')} collaboration. "
        f"Your airtime was {airtime:.1f}% which should stay near 15-35%."
    )

    confidence = "High" if placement >= 70 else ("Medium" if placement >= 45 else "Low")

    return {
        "geminiVerdict": verdict,
        "geminiStrengths": [
            "Clear opinion framing in multiple turns",
            "Maintained relevance to the given topic",
            "Participated consistently without long silence",
        ],
        "geminiWeaknesses": [
            "Use more data-backed reasoning",
            "Add concrete examples to strengthen arguments",
            "Acknowledge peers before countering points",
        ],
        "geminiNextSteps": [
            "Use the point-reason-example structure in each key turn",
            "Balance speaking time within the 15-35% target band",
            "Use one bridge phrase before disagreement",
        ],
        "confidenceLevel": confidence,
        "confidenceRationale": f"Based on a placement score of {placement}/100 and {archetype.lower()} communication style.",
        "communicationStyle": archetype,
        "topicMastery": "Showed basic familiarity with the topic; deeper domain examples would strengthen your case.",
        "keyMoments": [
            "Raised a valid point early in the discussion",
            "Maintained composure when challenged by other participants",
        ],
    }
