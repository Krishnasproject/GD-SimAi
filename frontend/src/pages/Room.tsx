import { useEffect, useState, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { wsUrl } from '../config/api';
import { useWebSocket } from '../hooks/useWebSocket';
import { useTTS } from '../hooks/useTTS';
import { useVAD } from '../hooks/useVAD';

type Speaker = 'aggressor' | 'logical' | 'diplomat' | 'user' | 'system';

type TranscriptEntry = {
  id: string;
  speaker: Speaker;
  text: string;
  timestamp: Date;
};

type RoomState = 'connecting' | 'waiting' | 'ai_speaking' | 'user_turn' | 'ended';

const SPEAKER_LABELS: Record<Speaker, string> = {
  aggressor: 'Ravi',
  logical: 'Sneha',
  diplomat: 'Arjun',
  user: 'You',
  system: 'System',
};



const AI_PERSONAS = [
  { id: 'aggressor', name: 'Ravi', role: 'Aggressor', initial: 'R', color: '#E8402A' },
  { id: 'logical', name: 'Sneha', role: 'Logical', initial: 'S', color: 'var(--teal)' },
  { id: 'diplomat', name: 'Arjun', role: 'Diplomat', initial: 'A', color: 'var(--gold)' },
];

export default function Room() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();

  const sessionId = location.state?.sessionId as string | undefined;
  const topic = location.state?.topic as string | undefined;
  const targetCompany = location.state?.targetCompany as string | undefined;

  const [roomState, setRoomState] = useState<RoomState>('connecting');
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [currentSpeaker, setCurrentSpeaker] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [userInputEnabled, setUserInputEnabled] = useState(false);
  const [timer, setTimer] = useState(0);
  const [micActive, setMicActive] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const streamBufferRef = useRef<string>('');
  const userInputEnabledRef = useRef(false);

  // Keep ref in sync so VAD callbacks (which close over initial state) see current value
  useEffect(() => {
    userInputEnabledRef.current = userInputEnabled;
  }, [userInputEnabled]);

  // Build WS URL only when sessionId is available
  const wsEndpoint = sessionId && user
    ? wsUrl(`/ws/${sessionId}`)
    : null;

  const { isConnected, addHandler, removeHandler, sendJson } = useWebSocket(wsEndpoint);
  const { speakChunk, stopAndClear, setOnQueueEmpty } = useTTS();

  // ── Helpers ────────────────────────────────────────────────────────────

  const addToTranscript = useCallback((speaker: Speaker, text: string) => {
    setTranscript(prev => [...prev, {
      id: `${Date.now()}-${Math.random()}`,
      speaker,
      text: text.trim(),
      timestamp: new Date(),
    }]);
  }, []);

  // ── VAD callbacks ──────────────────────────────────────────────────────

  // Called the INSTANT voice energy is detected — sends user_vad_start to backend
  // so it can cancel the current AI stream immediately (no waiting for STT).
  const handleSpeechStart = useCallback(() => {
    sendJson({ type: 'user_vad_start' });
    stopAndClear(); // Mute local TTS immediately
  }, [sendJson, stopAndClear]);

  // Called when VAD detects end-of-speech and hands us the raw audio base64.
  // We forward the audio to the backend for Groq Whisper transcription.
  // We do NOT add anything to the transcript here — the backend will echo it
  // back via user_turn_recorded once STT is complete.
  const handleSpeechEnd = useCallback((audioBase64: string) => {
    if (!userInputEnabledRef.current) return;
    sendJson({ type: 'user_vad_end', audio: audioBase64 });
  }, [sendJson]);

  const handleVADMisfire = useCallback(() => {
    // Too short to be real speech — ignore silently
  }, []);

  const { isListening, userSpeaking, start: startVAD, pause: pauseVAD } = useVAD({
    onSpeechStart: handleSpeechStart,
    onSpeechEnd: handleSpeechEnd,
    onVADMisfire: handleVADMisfire,
  });

  const toggleMic = useCallback(async () => {
    if (isListening) {
      await pauseVAD();
      setMicActive(false);
    } else {
      await startVAD();
      setMicActive(true);
    }
  }, [isListening, startVAD, pauseVAD]);

  // ── Send session_start as soon as WS opens ─────────────────────────────
  useEffect(() => {
    if (!isConnected || !user || !location.state?.targetCompany) return;
    user.getIdToken().then((idToken) => {
      sendJson({
        type: 'session_start',
        id_token: idToken,
        target_company: (location.state?.targetCompany as string) || 'General',
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected]); // Only fire once when connection is established

  // ── TTS done handshake ─────────────────────────────────────────────────
  // When the entire TTS queue drains (all AI audio has played), signal the
  // backend so it can open the user's speaking window.
  useEffect(() => {
    setOnQueueEmpty(() => {
      sendJson({ type: 'tts_done' });
    });
  }, [setOnQueueEmpty, sendJson]);

  // ── WebSocket message handlers ─────────────────────────────────────────
  useEffect(() => {
    // Backend confirmed session is ready (topic + initiator decided)
    addHandler('session_ready', () => {
      setRoomState('waiting');
    });

    // AI is about to speak
    addHandler('ai_turn_start', (data) => {
      const speaker = (data.speaker as string) || (data.speaker_name as string);
      setCurrentSpeaker(speaker);
      setStreamingText('');
      streamBufferRef.current = '';
      setRoomState('ai_speaking');
      setUserInputEnabled(false);
      // Pause VAD while AI speaks to avoid accidental interruptions from ambient noise
      if (isListening) void pauseVAD();
    });

    // Sentence chunk → feed to TTS queue; also build streaming display text
    addHandler('tts_chunk', (data) => {
      const chunk = data.text as string;
      if (chunk) {
        speakChunk(chunk);
        streamBufferRef.current += (streamBufferRef.current ? ' ' : '') + chunk;
        setStreamingText(streamBufferRef.current);
      }
    });

    // AI finished streaming all text — commit the full turn to the transcript
    addHandler('ai_turn_end', (data) => {
      const finalText = (data.text as string) || streamBufferRef.current;
      if (finalText.trim() && currentSpeaker) {
        addToTranscript(currentSpeaker as Speaker, finalText);
      }
      setStreamingText('');
      streamBufferRef.current = '';
      setCurrentSpeaker(null);
      setRoomState('waiting');
      // NOTE: We do NOT set userInputEnabled here.
      // The backend will send "your_turn" AFTER it receives "tts_done",
      // ensuring audio has actually finished playing before we open the mic.
    });

    // Backend acknowledged our tts_done signal
    addHandler('tts_done_ack', () => {
      // No-op — just confirms receipt
    });

    // Backend is ready for us to receive user input (fires after tts_done handshake)
    addHandler('ready_for_user_input', () => {
      // Backend is preparing the user window — user_turn will follow shortly
    });

    // Backend opens the user input window
    addHandler('your_turn', () => {
      setUserInputEnabled(true);
      setRoomState('user_turn');
      // Do NOT auto-start VAD — user must click mic button when ready.
      // This prevents ambient noise from being captured as speech.
    });

    // User was nudged (silent too long)
    addHandler('prod_user', (data) => {
      addToTranscript('system', (data.text as string) || 'Your turn to speak!');
      setUserInputEnabled(true);
      setRoomState('user_turn');
      // Do NOT auto-start VAD here either — user clicks mic when ready.
    });

    // AI interrupted by user — stop all audio immediately
    addHandler('ai_hushed', () => {
      stopAndClear();
      setStreamingText('');
      streamBufferRef.current = '';
    });

    // Backend confirmed it received and transcribed user's speech.
    // This is the ONE AND ONLY place we add the user's text to the transcript.
    addHandler('user_turn_recorded', (data) => {
      addToTranscript('user', data.text as string);
      setUserInputEnabled(false);
      setRoomState('waiting');
      void pauseVAD();
      setMicActive(false);
    });

    // Backend acknowledged STT receipt — frontend can accept next audio chunk
    addHandler('stt_ack', () => {
      // No-op — keeps pipeline flow
    });

    // Session ended
    addHandler('session_over', (data) => {
      setRoomState('ended');
      stopAndClear();
      void pauseVAD();
      setMicActive(false);
      if (timerRef.current) clearInterval(timerRef.current);
      const msg = (data.message as string) || 'Session complete. Generating analytics…';
      addToTranscript('system', msg);
      setTimeout(() => {
        navigate(`/analytics/${sessionId}`, { state: { sessionId } });
      }, 2000);
    });

    // Error from backend
    addHandler('error', (data) => {
      addToTranscript('system', `Error: ${data.message as string}`);
    });

    return () => {
      [
        'session_ready', 'ai_turn_start', 'tts_chunk', 'ai_turn_end',
        'tts_done_ack', 'ready_for_user_input', 'your_turn', 'prod_user',
        'ai_hushed', 'user_turn_recorded', 'stt_ack', 'session_over', 'error',
      ].forEach(removeHandler);
    };
  }, [
    addHandler, removeHandler, sendJson, speakChunk, stopAndClear,
    startVAD, pauseVAD, isListening, addToTranscript, currentSpeaker,
    navigate, sessionId,
  ]);

  // ── Timer ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (isConnected && roomState !== 'ended') {
      timerRef.current = setInterval(() => setTimer(t => t + 1), 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isConnected, roomState]);

  // ── Auto-scroll transcript ─────────────────────────────────────────────
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript, streamingText]);

  // ── No session redirect ────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) navigate('/');
  }, [sessionId, navigate]);

  const formatTime = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div style={{ height: '100vh', display: 'flex', background: 'var(--bg-base)', overflow: 'hidden' }}>
      <style>{`
        @keyframes waveBar {
          0%, 100% { height: 6px; }
          50% { height: 20px; }
        }
      `}</style>

      {/* LEFT PANEL */}
      <div style={{ width: '280px', height: '100%', background: 'var(--bg-surface)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '24px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '20px', color: 'white' }}>
            Mock<span style={{ color: 'var(--ember)' }}>Talk</span>
          </span>
          {targetCompany && (
            <div style={{ marginTop: '8px', fontSize: '11px', display: 'inline-block', padding: '3px 10px', background: 'var(--gold-dim)', color: 'var(--gold)', borderRadius: '20px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {targetCompany}
            </div>
          )}
        </div>
        
        <div style={{ padding: '24px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginLeft: '8px' }}>Participants</div>
          {AI_PERSONAS.map((p) => {
            const isSpeaking = currentSpeaker === p.id;
            return (
              <div key={p.id} style={{ 
                display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', 
                background: 'var(--bg-card)', borderRadius: '16px', border: `1px solid ${isSpeaking ? p.color : 'var(--border)'}`,
                boxShadow: isSpeaking ? `0 0 20px ${p.color}40` : 'none',
                transition: 'all 0.3s ease'
              }}>
                <div style={{ 
                  width: '44px', height: '44px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', 
                  fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '16px', color: 'white', flexShrink: 0,
                  background: p.color
                }}>
                  {p.initial}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '15px', color: 'var(--text-primary)' }}>{p.name}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: '2px' }}>{p.role}</div>
                </div>
                {/* Speaking Indicator */}
                <div style={{ width: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px', height: '24px' }}>
                  {isSpeaking ? (
                    <>
                      <div style={{ width: '3px', borderRadius: '2px', background: p.color, animation: 'waveBar 0.8s ease-in-out infinite 0s' }} />
                      <div style={{ width: '3px', borderRadius: '2px', background: p.color, animation: 'waveBar 0.8s ease-in-out infinite 0.15s' }} />
                      <div style={{ width: '3px', borderRadius: '2px', background: p.color, animation: 'waveBar 0.8s ease-in-out infinite 0.3s' }} />
                    </>
                  ) : (
                    <>
                      <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--text-muted)' }} />
                      <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--text-muted)' }} />
                      <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--text-muted)' }} />
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* CENTER PANEL */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {topic && (
          <div style={{ padding: '20px 32px', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ember)', textTransform: 'uppercase', letterSpacing: '0.1em', marginRight: '16px' }}>Discussion Topic</span>
            <span style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>{topic}</span>
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {transcript.length === 0 && roomState === 'connecting' && (
            <div style={{ textAlign: 'center', marginTop: '80px', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '32px', marginBottom: '12px' }}>⏳</div>
              <p>Connecting to simulation…</p>
            </div>
          )}

          {transcript.map(entry => {
            const isUser = entry.speaker === 'user';
            const isSystem = entry.speaker === 'system';
            const speakerConfig = AI_PERSONAS.find(p => p.id === entry.speaker);
            
            if (isSystem) {
              return (
                <div key={entry.id} className="fade-in" style={{ alignSelf: 'center', fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic', padding: '8px 16px', background: 'var(--bg-surface)', borderRadius: '20px', border: '1px solid var(--border)' }}>
                  {entry.text}
                </div>
              );
            }

            return (
              <div key={entry.id} className="fade-in" style={{ display: 'flex', gap: '16px', alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: '80%', flexDirection: isUser ? 'row-reverse' : 'row' }}>
                {!isUser && speakerConfig && (
                  <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: speakerConfig.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '14px', color: 'white', flexShrink: 0, marginTop: '24px' }}>
                    {speakerConfig.initial}
                  </div>
                )}
                {isUser && (
                  <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'var(--ember)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '14px', color: 'white', flexShrink: 0, marginTop: '24px' }}>
                    U
                  </div>
                )}
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: isUser ? 'var(--ember)' : speakerConfig?.color, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 4px' }}>
                    {SPEAKER_LABELS[entry.speaker]}
                  </div>
                  <div style={{
                    padding: '14px 18px', borderRadius: '16px', fontSize: '15px', lineHeight: 1.6,
                    background: isUser ? 'var(--ember-dim)' : 'var(--bg-card)',
                    border: `1px solid ${isUser ? 'var(--ember-border)' : 'var(--border)'}`,
                    color: 'var(--text-primary)',
                    borderTopLeftRadius: !isUser ? '4px' : '16px',
                    borderTopRightRadius: isUser ? '4px' : '16px',
                  }}>
                    {entry.text}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Streaming Bubble */}
          {streamingText && currentSpeaker && (
            <div style={{ display: 'flex', gap: '16px', alignSelf: 'flex-start', maxWidth: '80%' }}>
              {(() => {
                const speakerConfig = AI_PERSONAS.find(p => p.id === currentSpeaker);
                return speakerConfig && (
                  <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: speakerConfig.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '14px', color: 'white', flexShrink: 0, marginTop: '24px' }}>
                    {speakerConfig.initial}
                  </div>
                );
              })()}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: AI_PERSONAS.find(p => p.id === currentSpeaker)?.color || 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 4px' }}>
                  {SPEAKER_LABELS[currentSpeaker as Speaker] || currentSpeaker}
                </div>
                <div style={{ padding: '14px 18px', borderRadius: '16px', fontSize: '15px', lineHeight: 1.6, background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-primary)', borderTopLeftRadius: '4px' }}>
                  {streamingText}
                  <span style={{ display: 'inline-block', width: '6px', height: '14px', background: 'var(--ember)', marginLeft: '6px', borderRadius: '1px', animation: 'pulse-dot 1s ease-in-out infinite', verticalAlign: 'middle' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={transcriptEndRef} />
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div style={{ width: '200px', height: '100%', background: 'var(--bg-surface)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 16px', flexShrink: 0 }}>
        {/* Timer */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', marginBottom: '32px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>Session Time</div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '32px', color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
            {formatTime(timer)}
          </div>
        </div>

        {/* Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 16px', background: 'var(--bg-card)', borderRadius: '20px', border: '1px solid var(--border)', marginBottom: 'auto' }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: isConnected ? 'var(--ember)' : '#666', animation: isConnected ? 'pulse-dot 1.8s ease-in-out infinite' : 'none' }} />
          <span style={{ fontSize: '12px', fontWeight: 600, color: isConnected ? 'var(--ember)' : 'var(--text-muted)' }}>
            {isConnected ? 'Connected' : 'Connecting'}
          </span>
        </div>

        {/* Mic Button */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', marginBottom: 'auto' }}>
          <button
            onClick={toggleMic}
            style={{
              width: '72px', height: '72px', borderRadius: '50%',
              border: `2px solid ${micActive ? 'var(--ember)' : 'var(--border)'}`,
              cursor: 'pointer',
              background: micActive 
                ? userSpeaking ? 'var(--rose)' : 'var(--ember)'
                : 'var(--bg-card)',
              fontSize: '28px',
              boxShadow: micActive ? '0 0 30px var(--ember-dim)' : 'none',
              transition: 'all 0.2s',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}
          >
            🎙
          </button>
          
          <div style={{ textAlign: 'center', height: '40px' }}>
            {micActive ? (
              <div style={{ fontSize: '12px', fontWeight: 600, color: userSpeaking ? 'var(--rose)' : 'var(--ember)' }}>
                {userSpeaking ? 'Listening...' : 'Mic Active'}
              </div>
            ) : roomState === 'user_turn' ? (
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>Tap to speak</div>
            ) : (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>AI Speaking</div>
            )}
          </div>
        </div>

        {/* End Session Button */}
        <button
          onClick={() => sendJson({ type: 'end_session' })}
          style={{
            width: '100%', padding: '12px',
            background: 'rgba(224,90,107,0.15)',
            border: '1px solid rgba(224,90,107,0.4)',
            borderRadius: '10px', color: '#e05a6b',
            fontFamily: 'var(--font-display)',
            fontWeight: 700, fontSize: '13px',
            cursor: 'pointer', letterSpacing: '0.05em',
            textTransform: 'uppercase',
            transition: 'all 0.2s',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.background = 'rgba(224,90,107,0.25)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = 'rgba(224,90,107,0.15)';
          }}
        >
          End Session
        </button>
      </div>
    </div>
  );
}
