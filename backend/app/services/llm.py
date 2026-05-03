# =============================================================================
# backend/app/services/llm.py
#
# PURPOSE: Gemini Flash streaming wrapper — the "vocal cords" of every AI persona.
#
# HOW IT WORKS:
#   Every time an AI agent needs to speak, this service:
#     1. Sends the prompt to Gemini 2.0 Flash via the official SDK
#     2. Receives tokens STREAMING (not waiting for full response)
#     3. Buffers tokens until a SENTENCE BOUNDARY (. ? !)
#     4. Flushes the complete sentence to the WebSocket
#     5. Browser starts speaking sentence 1 while Gemini generates sentence 2
#
#   This is our biggest latency win:
#     Without streaming: Wait 2-3s for full response → then speak → 2-3s latency
#     With sentence flush: First sentence arrives in ~250ms → speak immediately
#
# CANCELLATION:
#   When the user interrupts (VAD fires), we need to STOP Gemini mid-stream.
#   The `cancel()` method sets a flag that the streaming loop checks every
#   iteration. The partial response is saved as an interrupted turn.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from typing import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Regex to detect sentence boundaries: period, question mark, or exclamation
# followed by a space or end-of-string.
SENTENCE_BOUNDARY = re.compile(r'[.?!](?:\s|$)')
TOPIC_RE = re.compile(r'Topic:\s*"([^"]+)"')
ABBREVIATIONS = {"Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Jr.", "Sr.", "vs.", "etc.", "Inc.", "Ltd."}


def _find_sentence_boundary(text: str) -> re.Match[str] | None:
    """Return the first sentence-ending punctuation match that is not a known abbreviation."""
    for match in SENTENCE_BOUNDARY.finditer(text):
        candidate = text[:match.end()].strip()
        if not candidate:
            continue
        last_token = candidate.split()[-1]
        if last_token in ABBREVIATIONS:
            continue
        return match
    return None


class KeyPool:
    def __init__(self, keys: list[str], name: str):
        self.name = name
        self.keys = [k for k in keys if k]
        self.exhausted_until_map = {k: 0.0 for k in self.keys}
        self.idx = 0

    def get_key(self) -> str | None:
        if not self.keys:
            return None
        # Try finding a key that isn't functionally exhausted
        for _ in range(len(self.keys)):
            k = self.keys[self.idx]
            self.idx = (self.idx + 1) % len(self.keys)
            if time.monotonic() > self.exhausted_until_map[k]:
                return k
        # If all are exhausted, just return the next one and hope for the best
        k = self.keys[self.idx]
        self.idx = (self.idx + 1) % len(self.keys)
        return k

    def mark_exhausted(self, key: str, duration: float = 30.0):
        if key in self.exhausted_until_map:
            logger.warning(f"⚠️ {self.name} Key **{key[-4:]} exhausted. Setting aside for {duration}s.")
            self.exhausted_until_map[key] = time.monotonic() + duration


class GeminiService:
    """
    Wrapper around Google's Gemini Flash API.
    Provides both one-shot and streaming generation.
    """

    def __init__(self):
        """
        Configure the Gemini and Groq key pools.
        Called once at startup via dependency injection.
        """
        # Load all available keys from config
        self.gemini_pool = KeyPool(settings.get_gemini_keys(), "Gemini")
        self.groq_pool = KeyPool(settings.get_groq_keys(), "Groq")

        # Cancellation flag — set to True to abort a running stream
        self._cancel_flag = False
        self._llm_primary = settings.LLM_PRIMARY_PROVIDER
        self._groq_enabled = len(self.groq_pool.keys) > 0

        logger.info(f"✅ GeminiService initialized (Gemini keys: {len(self.gemini_pool.keys)})")
        if self._groq_enabled:
            logger.info(f"✅ Groq fallback enabled (Groq keys: {len(self.groq_pool.keys)}, model: {settings.GROQ_LLM_MODEL})")
        else:
            logger.info("ℹ️ Groq LLM fallback disabled (missing GROQ keys)")
        logger.info(f"ℹ️ Primary LLM provider: {self._llm_primary}")

    def _is_retryable(self, error: Exception | int) -> bool:
        message = str(error).lower()
        return (
            "429" in message
            or "quota" in message
            or "rate limit" in message
            or "temporarily unavailable" in message
            or "timeout" in message
        )

    def _should_failover_provider() -> bool:
        return False

    async def _backoff(self, attempt: int):
        base = 0.35 * (2 ** attempt)
        await asyncio.sleep(base + random.uniform(0.0, 0.2))

    def _extract_topic(self, prompt: str) -> str:
        match = TOPIC_RE.search(prompt)
        return match.group(1).strip() if match else "the topic"

    def _dynamic_fallback_sentences(
        self,
        prompt: str,
        system_instruction: str,
        speaker_name: str | None,
        intent: str | None,
    ) -> list[str]:
        topic = self._extract_topic(prompt).strip()
        if topic:
            topic = topic[0].upper() + topic[1:]
        # Only check speaker_name to avoid triggering on other agents' names mentioned in the prompt
        persona_hint = (speaker_name or "").lower()
        intent_key = (intent or "ACKNOWLEDGE").upper()

        if "ravi" in persona_hint or "aggressor" in persona_hint:
            bank = {
                "OPEN": [
                    f"Let's get straight to the point regarding {topic}.",
                    f"I'll start. The reality of {topic} is that execution matters most.",
                ],
                "INTERRUPT": [
                    f"Hold on, we are missing the main point on {topic}.",
                    "If we keep circling, we lose the practical outcome recruiters care about.",
                ],
                "OPPOSE": [
                    f"I disagree with that framing on {topic}.",
                    "The stronger argument is impact and execution, not just theory.",
                ],
                "ACKNOWLEDGE": [
                    "Fair point, and I want to push it one step further.",
                    f"On {topic}, clarity of action matters more than broad statements.",
                ],
                "YIELD": [
                    "I have made my key point for now.",
                    "I will let others add before I jump back in.",
                ],
            }
        elif "sneha" in persona_hint or "logical" in persona_hint:
            bank = {
                "OPEN": [
                    f"To kick off the discussion on {topic}, let's look at the facts.",
                    f"I would like to initiate by framing {topic} around the data.",
                ],
                "INTERRUPT": [
                    "One quick correction before we move ahead.",
                    "The conclusion changes if we look at evidence instead of assumptions.",
                ],
                "OPPOSE": [
                    f"I see the argument, but the data trend for {topic} suggests otherwise.",
                    "A better way is point, evidence, and implication for the business case.",
                ],
                "ACKNOWLEDGE": [
                    "That is a valid point, and it fits with the broader pattern.",
                    f"For {topic}, we should compare short-term trade-offs with long-term outcomes.",
                ],
                "YIELD": [
                    "I am aligned with the direction so far.",
                    "I will pass this turn and add if a new angle appears.",
                ],
            }
        else:
            bank = {
                "OPEN": [
                    f"I will start us off. {topic} is nuanced, and both sides have valid concerns.",
                    "If we keep this practical and balanced, we can reach a stronger conclusion as a group.",
                ],
                "INTERRUPT": [
                    "Let me step in for a second and connect both viewpoints.",
                    "If we anchor on outcomes, this discussion stays constructive.",
                ],
                "OPPOSE": [
                    "I respect that view, but there is another practical angle we should consider.",
                    f"On {topic}, balance matters as much as confidence in the argument.",
                ],
                "ACKNOWLEDGE": [
                    "Both points have value, and we can combine them into a stronger position.",
                    f"For {topic}, a middle path with clear next steps will work best in real decisions.",
                ],
                "YIELD": [
                    "I am happy to hear another perspective first.",
                    "I can summarize the discussion after the next speaker if needed.",
                ],
            }

        options = bank.get(intent_key, bank["ACKNOWLEDGE"])
        return options

    def _split_into_sentences(self, text: str) -> list[str]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        out: list[str] = []
        buffer = cleaned
        while True:
            match = _find_sentence_boundary(buffer)
            if not match:
                break
            end_pos = match.end()
            sentence = buffer[:end_pos].strip()
            buffer = buffer[end_pos:].strip()
            if sentence:
                out.append(sentence)

        if buffer:
            out.append(buffer)
        return out

    async def _groq_generate_text(
        self,
        prompt: str,
        system_instruction: str,
        max_tokens: int,
        temperature: float,
    ) -> str | None:
        if not self._groq_enabled:
            return None

        key = self.groq_pool.get_key()
        if not key:
            return None

        payload = {
            "model": settings.GROQ_LLM_MODEL,
            "messages": [
                *([{"role": "system", "content": system_instruction}] if system_instruction else []),
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        timeout_seconds = max(settings.GROQ_TIMEOUT_MS / 1000.0, 1.0)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

            if response.status_code == 429:
                self.groq_pool.mark_exhausted(key)
                return None

            if response.status_code >= 400:
                logger.error("Groq fallback error (%s): %s", response.status_code, response.text[:300])
                return None

            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return content or None
        except Exception as e:
            logger.error("Groq fallback request failed: %s", e)
            return None

    # ── One-Shot Generation (for intent assessment) ──────────────────────

    async def generate(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 200,
        timeout: float = 10.0,
    ) -> str:
        """
        Generate a COMPLETE response (non-streaming).
        Used for quick tasks like intent assessment (JSON output).

        Args:
            timeout: HTTP request timeout in seconds. Use 5.0 for intent
                     assessment (fail-fast), 10.0 for topic context generation.
        """
        if self._llm_primary == "groq":
            for _ in range(max(1, len(self.groq_pool.keys))):
                groq_text = await self._groq_generate_text(
                    prompt=prompt, system_instruction=system_instruction, max_tokens=max_tokens, temperature=0.3
                )
                if groq_text: return groq_text
            logger.warning("Groq primary failed for generate(); falling back to Gemini")

        # Fall back or main provider: Gemini REST API
        for attempt in range(max(3, len(self.gemini_pool.keys))):
            gemini_key = self.gemini_pool.get_key()
            if not gemini_key:
                break

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
            }
            if system_instruction:
                payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_instruction}]}

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=payload)
                
                if response.status_code == 429:
                    self.gemini_pool.mark_exhausted(gemini_key)
                    await self._backoff(attempt)
                    continue
                
                if response.status_code >= 400:
                    logger.error(f"Gemini generate API error ({response.status_code}): {response.text}")
                    if attempt < len(self.gemini_pool.keys) - 1:
                        continue
                    break

                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"].strip()
                
            except Exception as e:
                logger.error(f"Gemini generate() error: {e}")
                if self._is_retryable(e) and attempt < len(self.gemini_pool.keys) - 1:
                    await self._backoff(attempt)
                    continue
                break

        if self._llm_primary != "groq":
            for _ in range(max(1, len(self.groq_pool.keys))):
                groq_text = await self._groq_generate_text(
                    prompt=prompt, system_instruction=system_instruction, max_tokens=max_tokens, temperature=0.3
                )
                if groq_text:
                    logger.warning("Using Groq fallback for generate()")
                    return groq_text

        return '{"intent": "YIELD", "confidence": 0.1, "reason": "LLM completely exhausted"}'

    # ── Streaming Generation (for AI turns) ──────────────────────────────

    async def stream_generate(
        self,
        prompt: str,
        system_instruction: str = "",
        speaker_name: str | None = None,
        intent: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response from Gemini, yielding COMPLETE SENTENCES via SSE REST endpoint.
        """
        self._cancel_flag = False
        if self._llm_primary == "groq":
            for _ in range(max(1, len(self.groq_pool.keys))):
                groq_text = await self._groq_generate_text(
                    prompt=prompt, system_instruction=system_instruction, max_tokens=120, temperature=0.85
                )
                if groq_text:
                    for sentence in self._split_into_sentences(groq_text):
                        if self._cancel_flag: return
                        yield sentence
                    return
            logger.warning("Groq primary failed for stream_generate(); falling back to Gemini")

        gemini_success = False
        for attempt in range(max(3, len(self.gemini_pool.keys))):
            buffer = ""
            gemini_key = self.gemini_pool.get_key()
            if not gemini_key:
                break

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?alt=sse&key={gemini_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.85, "topP": 0.92, "maxOutputTokens": 120},
            }
            if system_instruction:
                payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_instruction}]}

            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", url, json=payload, timeout=20.0) as response:
                        if response.status_code == 429:
                            self.gemini_pool.mark_exhausted(gemini_key)
                            await self._backoff(attempt)
                            continue

                        if response.status_code >= 400:
                            logger.error(f"Gemini Stream Error ({response.status_code}): try next key")
                            continue

                        gemini_success = True
                        async for line in response.aiter_lines():
                            if self._cancel_flag:
                                logger.info("🛑 Stream cancelled (user interrupted)")
                                if buffer.strip(): yield buffer.strip()
                                return
                            
                            if not line.startswith("data: "):
                                continue
                            
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            
                            try:
                                chunk_json = json.loads(data_str)
                                candidates = chunk_json.get("candidates", [])
                                if not candidates: continue
                                delta = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                if not delta: continue
                                buffer += delta
                            except json.JSONDecodeError:
                                continue

                            # Sentence Boundary Flush
                            while True:
                                match = _find_sentence_boundary(buffer)
                                if not match:
                                    break
                                end_pos = match.end()
                                sentence = buffer[:end_pos].strip()
                                buffer = buffer[end_pos:].strip()
                                if sentence:
                                    logger.debug(f"📤 Flushing sentence: '{sentence[:50]}...'")
                                    yield sentence
                                    await asyncio.sleep(0)
                        
                        if buffer.strip():
                            yield buffer.strip()
                        return  # Success, exit the loop completely
            except Exception as e:
                logger.error(f"Gemini stream error connecting: {e}")
                if attempt < len(self.gemini_pool.keys) - 1:
                    await self._backoff(attempt)
                    continue

        if not gemini_success and self._llm_primary != "groq":
            for _ in range(max(1, len(self.groq_pool.keys))):
                groq_text = await self._groq_generate_text(
                    prompt=prompt, system_instruction=system_instruction, max_tokens=120, temperature=0.85
                )
                if groq_text:
                    logger.warning("Using Groq fallback for stream_generate()")
                    for sentence in self._split_into_sentences(groq_text):
                        if self._cancel_flag: return
                        yield sentence
                    return

        # If ALL else fails, use dynamic hardcoded sentences to keep the conversation alive
        for sentence in self._dynamic_fallback_sentences(
            prompt=prompt, system_instruction=system_instruction, speaker_name=speaker_name, intent=intent
        ):
            yield sentence

    # ── Stream Control ───────────────────────────────────────────────────

    def cancel(self):
        """
        Cancel an in-progress stream. Called when:
            - User interrupts (VAD fires → hush_ai node)
            - Another AI interrupts (INTERRUPT intent wins)
            - Session ends

        The streaming loop checks _cancel_flag every iteration.
        """
        self._cancel_flag = True
        logger.info("🛑 Cancel flag set — stream will stop at next chunk")

    @property
    def is_cancelled(self) -> bool:
        """Check if the stream has been cancelled."""
        return self._cancel_flag
