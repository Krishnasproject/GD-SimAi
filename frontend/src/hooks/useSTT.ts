import { useEffect, useRef, useState, useCallback } from 'react';

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  0: { transcript: string };
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
};

/**
 * Hook for Web Speech API Speech-to-Text (STT)
 * MVP: Zero latency, runs client-side in browser.
 */
export function useSTT(onTranscriptComplete?: (text: string) => void) {
  const [isListening, setIsListening] = useState(false);
  const [interimText, setInterimText] = useState("");
  const [finalText, setFinalText] = useState("");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldRestartRef = useRef(false);
  const finalBufferRef = useRef("");
  const lastSubmittedRef = useRef<{ text: string; at: number }>({ text: "", at: 0 });

  useEffect(() => {
    // Initialize Web Speech API
    const speechWindow = window as SpeechWindow;
    const RecognitionCtor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!RecognitionCtor) {
      console.error("Web Speech API is not supported in this browser.");
      return;
    }

    const recognition = new RecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-IN'; // Indian English optimization

    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      let currentInterim = "";
      let currentFinal = "";

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          currentFinal += event.results[i][0].transcript;
        } else {
          currentInterim += event.results[i][0].transcript;
        }
      }

      setInterimText(currentInterim);
      if (currentFinal) {
        const newText = `${finalBufferRef.current} ${currentFinal}`.trim();
        finalBufferRef.current = newText;
        setFinalText(newText);
      }
    };

    recognition.onend = () => {
      // If we are supposed to be listening but it ended, restart
      if (shouldRestartRef.current) {
        try {
          recognition.start();
        } catch {
          // Browser may throw if start is called while already active.
        }
      } else {
        setIsListening(false);
      }
    };

    recognitionRef.current = recognition;

    return () => {
      shouldRestartRef.current = false;
      recognition.stop();
    };
  }, []);

  const submitIfValid = useCallback((rawText: string) => {
    const text = rawText.trim();
    if (!text || !onTranscriptComplete) return;

    const now = Date.now();
    const previous = lastSubmittedRef.current;
    if (previous.text === text && now - previous.at < 2500) {
      return;
    }

    lastSubmittedRef.current = { text, at: now };
    onTranscriptComplete(text);
  }, [onTranscriptComplete]);

  const startListening = useCallback(() => {
    if (!recognitionRef.current) return;
    try {
      shouldRestartRef.current = true;
      if (!isListening) {
        recognitionRef.current.start();
      }
      setIsListening(true);
      setInterimText("");
      setFinalText("");
      finalBufferRef.current = "";
    } catch (e) {
      console.warn("Speech recognition already started", e);
    }
  }, [isListening]);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current) return;
    shouldRestartRef.current = false;
    recognitionRef.current.stop();
    setIsListening(false);

    const captured = finalBufferRef.current || finalText || interimText;
    submitIfValid(captured);

    setInterimText("");
    setFinalText("");
    finalBufferRef.current = "";
  }, [finalText, interimText, submitIfValid]);

  return {
    isListening,
    interimText,
    finalText,
    startListening,
    stopListening
  };
}
