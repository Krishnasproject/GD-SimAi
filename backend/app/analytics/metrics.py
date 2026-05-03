from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.models.transcript import Turn


@dataclass
class _Counts:
    points: int = 0
    reasons: int = 0
    examples: int = 0
    acknowledgements: int = 0
    build_on_others: int = 0


def _ensure_turn(turn: Turn | dict) -> Turn:
    if isinstance(turn, Turn):
        return turn
    return Turn(**turn)


def _safe_duration_ms(turn: Turn) -> int:
    if turn.duration_ms and turn.duration_ms > 0:
        return int(turn.duration_ms)
    # Fallback estimate: ~130 wpm average => ~462ms/word
    words = max(1, len(turn.text.split()))
    return int(words * 462)


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def compute_metrics(transcript: Iterable[Turn | dict]) -> dict:
    turns = [_ensure_turn(turn) for turn in transcript]

    total_ms = sum(_safe_duration_ms(turn) for turn in turns)
    user_turns = [turn for turn in turns if turn.speaker_id == "user"]
    user_ms = sum(_safe_duration_ms(turn) for turn in user_turns)

    user_percent = round((user_ms / total_ms * 100.0), 1) if total_ms else 0.0

    # ── Turn counts ──────────────────────────────────────────────────────────
    turn_count = len(turns)
    user_turn_count = len(user_turns)

    # ── Speaking pace ────────────────────────────────────────────────────────
    user_word_counts = [len(t.text.split()) for t in user_turns]
    total_user_words = sum(user_word_counts)
    avg_words_per_turn = round(total_user_words / max(1, user_turn_count), 1)

    # wpm: total words / time in minutes
    user_minutes = user_ms / 60_000.0
    speaking_pace_wpm = round(total_user_words / max(0.01, user_minutes))

    # ── Interruption tracking ────────────────────────────────────────────────
    user_initiated_interruptions = sum(
        1 for turn in turns if turn.interrupted_by == "user"
    )
    user_received_interruptions = sum(
        1 for turn in user_turns if turn.was_interrupted
    )
    recovery_rate = (
        round(
            sum(1 for turn in user_turns if not turn.was_interrupted) / len(user_turns),
            2,
        )
        if user_turns
        else 0.0
    )

    counts = _Counts()
    for turn in user_turns:
        text = turn.text.lower()
        has_point = any(token in text for token in [
            "i think", "i believe", "in my view", "my point",
            "i feel", "in my opinion", "i would say", "i'd say",
            "i want to", "i'd like to", "we should", "we need to",
            "the point is", "basically", "fundamentally",
        ])
        has_reason = any(token in text for token in [
            "because", "since", "therefore", "as a result",
            "due to", "this means", "which means", "so",
            "that's why", "the reason", "this is why",
            "leads to", "results in", "hence",
        ])
        has_example = any(token in text for token in [
            "for example", "for instance", "such as", "e.g.",
            "like", "consider", "take", "look at",
            "in case of", "studies show", "data shows",
            "research shows", "according to", "report",
        ])
        has_ack = any(token in text for token in [
            "i agree", "fair point", "valid point", "good point",
            "you're right", "that's right", "absolutely",
            "exactly", "correct", "true", "well said",
            "building on", "adding to what",
        ])
        has_build = any(token in text for token in [
            "building on", "adding to", "to extend", "also",
            "furthermore", "additionally", "moreover",
            "and also", "not just that", "beyond that",
            "to add to", "what's more",
        ])

        counts.points += 1 if has_point else 0
        counts.reasons += 1 if has_reason else 0
        counts.examples += 1 if has_example else 0
        counts.acknowledgements += 1 if has_ack else 0
        counts.build_on_others += 1 if has_build else 0

    turns_len = max(1, len(user_turns))
    logic_score = _clamp_score(
        (counts.points / turns_len) * 40
        + (counts.reasons / turns_len) * 35
        + (counts.examples / turns_len) * 25
    )

    diplomacy_score = _clamp_score(
        (counts.acknowledgements / turns_len) * 55
        + (counts.build_on_others / turns_len) * 45
    )

    airtime_score = 100 - min(100, int(abs(user_percent - 25) * 4))
    interruption_score = 100 - min(100, (user_received_interruptions * 20)) + min(20, user_initiated_interruptions * 5)
    placement_score = _clamp_score(
        0.35 * logic_score
        + 0.25 * diplomacy_score
        + 0.20 * airtime_score
        + 0.20 * interruption_score
    )

    # ── Communication archetype (rule-based ML classification) ───────────────
    if logic_score >= 65 and diplomacy_score >= 65:
        archetype = "Balanced"
    elif logic_score >= 65 and diplomacy_score < 50:
        archetype = "Analytical"
    elif diplomacy_score >= 65 and logic_score < 50:
        archetype = "Diplomatic"
    elif user_percent > 35:
        archetype = "Assertive"
    else:
        archetype = "Reserved"

    _interruption_score_clamped = _clamp_score(interruption_score)

    return {
        # ── camelCase keys (existing — for Firestore storage / legacy consumers) ─
        "turnCount": turn_count,
        "userTurnCount": user_turn_count,
        "placementScore": placement_score,
        "airtimeScore": airtime_score,
        "interruptionScore": _interruption_score_clamped,
        "avgWordsPerTurn": avg_words_per_turn,
        "speakingPaceWpm": speaking_pace_wpm,
        "communicationArchetype": archetype,
        "airtime": {
            "userSeconds": round(user_ms / 1000.0, 1),
            "totalSeconds": round(total_ms / 1000.0, 1),
            "userPercent": user_percent,
            "benchmark": "15-35%",
        },
        "interruptions": {
            "userInitiated": user_initiated_interruptions,
            "userReceived": user_received_interruptions,
            "recoveryRate": recovery_rate,
        },
        "logicScore": {
            "score": logic_score,
            "pointsWithReasoning": counts.reasons,
            "pointsWithExample": counts.examples,
        },
        "diplomacyScore": {
            "score": diplomacy_score,
            "acknowledgements": counts.acknowledgements,
            "buildOnOthers": counts.build_on_others,
        },

        # ── snake_case aliases (for frontend Analytics.tsx) ───────────────────
        "turn_count": turn_count,
        "user_turn_count": user_turn_count,
        "placement_score": placement_score,
        "airtime_score": airtime_score,
        "interruption_score": _interruption_score_clamped,
        "avg_words_per_turn": avg_words_per_turn,
        "speaking_pace_wpm": speaking_pace_wpm,
        "communication_archetype": archetype,
        "logic_score": {
            "score": logic_score,
            "pointsWithReasoning": counts.reasons,
            "pointsWithExample": counts.examples,
        },
        "diplomacy_score": {
            "score": diplomacy_score,
            "acknowledgements": counts.acknowledgements,
            "buildOnOthers": counts.build_on_others,
        },
    }
