import { useEffect, useRef, useState, useCallback } from 'react';

interface VADOptions {
  onSpeechStart?: () => void;
  onSpeechEnd?: (audioBase64: string) => void;
  onVADMisfire?: () => void;
}

/**
 * Browser-native VAD using Web Audio RMS energy + MediaRecorder for audio capture.
 * - RMS loop: detects when the user starts/stops talking (fast, ~10ms resolution)
 * - MediaRecorder: records the actual audio bytes while the user talks
 * - onSpeechEnd receives a base64-encoded WAV/webm blob for Groq STT on the backend
 */
export function useVAD({ onSpeechStart, onSpeechEnd, onVADMisfire }: VADOptions = {}) {
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errored, setErrored] = useState<string | false>(false);

  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);

  // MediaRecorder refs for audio capture
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const speakingRef = useRef(false);
  const speechStartAtRef = useRef(0);
  const lastVoiceAtRef = useRef(0);

  const startThreshold = 0.055;  // was 0.035 — higher = needs louder speech to trigger
  const stopThreshold = 0.025;   // was 0.018
  const minSpeechMs = 600;       // was 300 — ignore anything under 600ms (clicks, noise)
  const silenceHoldMs = 600;     // was 280 — wait longer before ending capture

  const stopLoop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const computeRms = (samples: Uint8Array): number => {
    let sumSquares = 0;
    for (let i = 0; i < samples.length; i += 1) {
      const normalized = (samples[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    return Math.sqrt(sumSquares / samples.length);
  };

  // ── MediaRecorder helpers ────────────────────────────────────────────────

  const startRecording = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;

    // Pick supported MIME type
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : '';

    try {
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });
        audioChunksRef.current = [];

        // Convert Blob → ArrayBuffer → Base64 and fire callback
        blob.arrayBuffer().then((buffer) => {
          const bytes = new Uint8Array(buffer);
          let binary = '';
          bytes.forEach((b) => (binary += String.fromCharCode(b)));
          const base64 = btoa(binary);
          onSpeechEnd?.(base64);
        });
      };

      recorder.start();
      recorderRef.current = recorder;
    } catch (err) {
      console.warn('MediaRecorder failed to start:', err);
    }
  }, [onSpeechEnd]);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    recorderRef.current = null;
  }, []);

  // ── RMS VAD loop ─────────────────────────────────────────────────────────

  const loop = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      const rms = computeRms(data);
      const now = performance.now();

      if (rms >= startThreshold) {
        lastVoiceAtRef.current = now;
        if (!speakingRef.current) {
          speakingRef.current = true;
          speechStartAtRef.current = now;
          setUserSpeaking(true);
          startRecording();       // ← start capturing audio bytes
          onSpeechStart?.();
        }
      } else if (speakingRef.current && now - lastVoiceAtRef.current >= silenceHoldMs) {
        const speechDuration = now - speechStartAtRef.current;
        speakingRef.current = false;
        setUserSpeaking(false);

        if (speechDuration >= minSpeechMs) {
          stopRecording();        // ← stop recording; onstop fires onSpeechEnd(base64)
        } else {
          // Too short — discard the recording and fire misfire
          const recorder = recorderRef.current;
          if (recorder && recorder.state !== 'inactive') {
            // Override onstop to discard instead of forwarding
            recorder.onstop = () => { audioChunksRef.current = []; };
            recorder.stop();
          }
          recorderRef.current = null;
          onVADMisfire?.();
        }
      } else if (!speakingRef.current && rms > stopThreshold && rms < startThreshold) {
        // Low-level background noise around threshold — ignore
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
  }, [onSpeechStart, startRecording, stopRecording, onVADMisfire]);

  const listeningRef = useRef(false);

  const start = useCallback(async () => {
    if (listeningRef.current) return;
    try {
      setLoading(true);
      setErrored(false);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      const context = new AudioCtx();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      streamRef.current = stream;
      audioContextRef.current = context;
      analyserRef.current = analyser;

      listeningRef.current = true;
      setListening(true);
      setLoading(false);
      loop();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not initialize microphone VAD';
      setErrored(message);
      setLoading(false);
    }
  }, [loop]);

  const pause = useCallback(async () => {
    if (!listeningRef.current) return;   // ← guard: never close an already-closed context
    listeningRef.current = false;
    stopLoop();
    stopRecording();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        await audioContextRef.current.close();
      } catch (_) {
        // Already closed — safe to ignore
      }
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    speakingRef.current = false;
    setUserSpeaking(false);
    setListening(false);
  }, [stopLoop, stopRecording]);

  const toggle = useCallback(async () => {
    if (listeningRef.current) {
      await pause();
    } else {
      await start();
    }
  }, [pause, start]);

  // Stable refs so the mount-once effect can always call the latest version
  const startRef = useRef(start);
  const pauseRef = useRef(pause);
  useEffect(() => { startRef.current = start; }, [start]);
  useEffect(() => { pauseRef.current = pause; }, [pause]);

  // DO NOT auto-start mic on mount.
  // The mic is now controlled manually via the push-to-talk button in Room.tsx.
  // This prevents background noise / filler words from hushing AI unexpectedly.
  useEffect(() => {
    return () => {
      // Always clean up mic resources on unmount
      void pauseRef.current();
    };
  }, []);

  // Expose micEnabled state so Room.tsx can show button correctly
  const micEnabled = listening;

  return {
    userSpeaking,
    listening,
    loading,
    errored,
    start,
    pause,
    toggle,
    isListening: listening,
    micEnabled,
  };
}
