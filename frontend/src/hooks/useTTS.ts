import { useEffect, useRef, useState } from 'react';

/**
 * Hook for Web Speech API Text-to-Speech (TTS)
 * Manages a queue of sentences received from the backend (sentence-boundary flush).
 *
 * TTS TIMING FIX:
 * Edge TTS generates audio per sentence chunk. Between chunks there can be a
 * brief gap during which the queue momentarily appears empty. Without a settle
 * delay this would fire onQueueEmpty prematurely, causing the backend to start
 * the next AI turn while audio is still playing.
 *
 * Solution: after the queue drains, wait SETTLE_DELAY_MS before firing the
 * callback. If a new chunk arrives during that window the timer is cancelled.
 */
export function useTTS() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const queue = useRef<string[]>([]);
  const isPlayingRef = useRef(false);

  // Track current utterance so we can cancel it
  const currentUtterance = useRef<SpeechSynthesisUtterance | null>(null);

  // Callback fired when the entire playback queue drains to empty
  const onQueueEmptyRef = useRef<(() => void) | null>(null);

  // Settling timer — prevents premature onQueueEmpty during inter-chunk gaps
  const settleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** How long to wait (ms) after the last chunk ends before firing onQueueEmpty. */
  const SETTLE_DELAY_MS = 1500;

  function buildUtterance(text: string): SpeechSynthesisUtterance {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;  // Slightly faster — still natural, reduces dead air
    utterance.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const indianVoice = voices.find(v => v.lang.includes('en-IN') || v.name.includes('India'));
    if (indianVoice) utterance.voice = indianVoice;
    return utterance;
  }

  function processQueue() {
    if (queue.current.length === 0) {
      isPlayingRef.current = false;
      setIsSpeaking(false);

      // Wait SETTLE_DELAY_MS before firing onQueueEmpty — gives time for the
      // next chunk to arrive in case of inter-sentence gaps in Edge TTS output.
      if (onQueueEmptyRef.current) {
        // Clear any previously scheduled settle timer
        if (settleTimer.current) {
          clearTimeout(settleTimer.current);
        }
        settleTimer.current = setTimeout(() => {
          // Double-check: still empty and not playing before firing
          if (queue.current.length === 0 && !isPlayingRef.current) {
            settleTimer.current = null;
            onQueueEmptyRef.current?.();
          }
        }, SETTLE_DELAY_MS);
      }
      return;
    }

    if (isPlayingRef.current) return; // Already speaking

    isPlayingRef.current = true;
    setIsSpeaking(true);

    const text = queue.current.shift()!;
    const utterance = buildUtterance(text);

    utterance.onend = () => {
      isPlayingRef.current = false;
      currentUtterance.current = null;
      // Pre-warm the next utterance (if any) immediately — avoids ~100ms init lag
      if (queue.current.length > 0) {
        const nextText = queue.current[0];
        // Build and speak immediately — don't wait for next processQueue() call
        isPlayingRef.current = true;
        const nextUtterance = buildUtterance(nextText);
        queue.current.shift(); // Remove the item we're about to speak
        nextUtterance.onend = utterance.onend; // Reuse same handler chain
        nextUtterance.onerror = utterance.onerror;
        currentUtterance.current = nextUtterance;
        window.speechSynthesis.speak(nextUtterance);
      } else {
        processQueue();
      }
    };

    utterance.onerror = (e) => {
      // "interrupted" and "canceled" are expected when stopAndClear() is called mid-speech.
      const expectedErrors = ['interrupted', 'canceled', 'cancel'];
      if (!expectedErrors.includes(e.error)) {
        console.error('TTS Error:', e);
      }
      isPlayingRef.current = false;
      processQueue();
    };

    currentUtterance.current = utterance;
    window.speechSynthesis.speak(utterance);
  }

  /**
   * Add a new chunk (sentence) to the playback queue.
   * IMPORTANT: Also cancels any active settle timer — a new chunk means
   * the TTS stream is still live, so onQueueEmpty must NOT fire yet.
   */
  const speakChunk = (text: string) => {
    if (!window.speechSynthesis) return;

    // Cancel settle timer — more audio arriving
    if (settleTimer.current) {
      clearTimeout(settleTimer.current);
      settleTimer.current = null;
    }

    // Chrome TTS bug: utterances > ~15s get silently cut off.
    // Split into ≤100-char word-boundary chunks to avoid this.
    const chunks = splitIntoSafeChunks(text, 100);
    chunks.forEach(chunk => queue.current.push(chunk));
    processQueue();
  };

  /**
   * Splits long text into ≤maxLen-char chunks at word boundaries.
   * This is the fix for the Chrome TTS bug where utterances > ~15s are silently cut off.
   */
  function splitIntoSafeChunks(text: string, maxLen: number): string[] {
    if (text.length <= maxLen) return [text];
    const chunks: string[] = [];
    let remaining = text.trim();
    while (remaining.length > maxLen) {
      let splitAt = remaining.lastIndexOf(' ', maxLen);
      if (splitAt === -1) splitAt = maxLen;
      chunks.push(remaining.slice(0, splitAt).trim());
      remaining = remaining.slice(splitAt).trim();
    }
    if (remaining) chunks.push(remaining);
    return chunks;
  }

  /**
   * Stop all playback immediately and clear the queue.
   * Called when "hush_ai" arrives (user interrupted).
   * Does NOT fire onQueueEmpty — the queue was forcefully cleared, not naturally drained.
   */
  const stopAndClear = () => {
    if (!window.speechSynthesis) return;

    // Cancel any pending settle timer so onQueueEmpty doesn't fire after a forced stop
    if (settleTimer.current) {
      clearTimeout(settleTimer.current);
      settleTimer.current = null;
    }

    queue.current = [];
    window.speechSynthesis.cancel();
    isPlayingRef.current = false;
    setIsSpeaking(false);
    currentUtterance.current = null;
  };

  /**
   * Register a callback that is invoked once after the audio queue fully drains
   * (with an 800ms settle delay to account for inter-chunk gaps).
   * Used by Room.tsx to send `tts_done` to the backend, opening the user's speaking window.
   */
  const setOnQueueEmpty = (cb: () => void) => {
    onQueueEmptyRef.current = cb;
  };

  // Ensure voices are loaded (Chrome sometimes loads them async)
  useEffect(() => {
    if (window.speechSynthesis) {
      window.speechSynthesis.onvoiceschanged = () => {
        // Voices are ready — no-op, next speakChunk call will pick the right voice
      };
    }

    return () => {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      // Clean up any pending settle timer on unmount
      if (settleTimer.current) {
        clearTimeout(settleTimer.current);
      }
    };
  }, []);

  return { speakChunk, stopAndClear, isSpeaking, setOnQueueEmpty };
}
