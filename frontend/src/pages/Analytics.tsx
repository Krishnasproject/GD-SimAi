import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { apiUrl } from '../config/api';

// ── Types ────────────────────────────────────────────────────────────────────

type AirtimeData = {
  userSeconds: number;
  totalSeconds: number;
  userPercent: number;
  benchmark: string;
};

type InterruptionData = {
  userInitiated: number;
  userReceived: number;
  recoveryRate: number;
};

type ScoreBreakdown = {
  score: number;
  pointsWithReasoning?: number;
  pointsWithExample?: number;
  acknowledgements?: number;
  buildOnOthers?: number;
};

type AnalyticsData = {
  session_id: string;
  topic: string;
  target_company: string;
  started_at: string;

  duration_seconds: number;
  turn_count: number;
  user_turn_count: number;
  score: number | null;
  avg_words_per_turn: number;
  speaking_pace_wpm: number;
  communication_archetype: string;

  placement_score: number;
  airtime_score: number;
  interruption_score: number;

  airtime: AirtimeData;
  interruptions: InterruptionData;
  logic_score: ScoreBreakdown;
  diplomacy_score: ScoreBreakdown;

  gemini_verdict: string;
  gemini_strengths: string[];
  gemini_weaknesses: string[];
  gemini_next_steps: string[];

  confidence_level: string;
  confidence_rationale: string;
  communication_style: string;
  topic_mastery: string;
  key_moments: string[];
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s}s`;
}

function scoreColor(score: number): string {
  if (score >= 75) return '#1e9b8a';
  if (score >= 50) return '#c9a84c';
  return '#e05a6b';
}

function confidenceBadgeColor(level: string): { bg: string; text: string; border: string } {
  if (level === 'High') return { bg: 'rgba(30,155,138,0.15)', text: '#1e9b8a', border: '#1e9b8a' };
  if (level === 'Low') return { bg: 'rgba(224,90,107,0.15)', text: '#e05a6b', border: '#e05a6b' };
  return { bg: 'rgba(201,168,76,0.15)', text: '#c9a84c', border: '#c9a84c' };
}

// ── Sub-components ───────────────────────────────────────────────────────────

function ScoreRing({ score, size = 160 }: { score: number; size?: number }) {
  const [displayed, setDisplayed] = useState(0);
  const radius = (size - 20) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (displayed / 100) * circumference;
  const color = scoreColor(score);

  useEffect(() => {
    let frame: number;
    let current = 0;
    const step = score / 60;
    function animate() {
      current = Math.min(current + step, score);
      setDisplayed(Math.round(current));
      if (current < score) frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [score]);

  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="var(--bg-hover)" strokeWidth={12}
      />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke={color} strokeWidth={12}
        strokeDasharray={circumference}
        strokeDashoffset={circumference - progress}
        strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 0.05s linear' }}
      />
      <text
        x={size / 2} y={size / 2 + 2}
        textAnchor="middle" dominantBaseline="middle"
        style={{
          transform: 'rotate(90deg)',
          transformOrigin: `${size / 2}px ${size / 2}px`,
          fill: color,
          fontSize: size * 0.22,
          fontFamily: 'var(--font-display)',
          fontWeight: 800,
        }}
      >
        {displayed}
      </text>
      <text
        x={size / 2} y={size / 2 + size * 0.16}
        textAnchor="middle" dominantBaseline="middle"
        style={{
          transform: 'rotate(90deg)',
          transformOrigin: `${size / 2}px ${size / 2}px`,
          fill: 'var(--text-muted)',
          fontSize: size * 0.1,
          fontFamily: 'var(--font-body)',
        }}
      >
        /100
      </text>
    </svg>
  );
}

function AnimatedBar({ score, label, sublabel }: { score: number; label: string; sublabel?: string }) {
  const [width, setWidth] = useState(0);
  const color = scoreColor(score);

  useEffect(() => {
    const t = setTimeout(() => setWidth(score), 120);
    return () => clearTimeout(t);
  }, [score]);

  return (
    <div style={{ marginBottom: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <div>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</span>
          {sublabel && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '8px' }}>{sublabel}</span>
          )}
        </div>
        <span style={{ fontSize: '14px', fontWeight: 700, color, fontFamily: 'var(--font-display)' }}>
          {score}/100
        </span>
      </div>
      <div style={{
        height: '8px', background: 'var(--bg-hover)', borderRadius: '4px', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${width}%`,
          background: `linear-gradient(90deg, ${color}99, ${color})`,
          borderRadius: '4px',
          transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)',
        }} />
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, accent }: {
  label: string; value: string | number; sub?: string; accent?: string;
}) {
  return (
    <div className="card" style={{ textAlign: 'center', padding: '20px 16px' }}>
      <div style={{
        fontSize: '10px', fontWeight: 700, color: 'var(--text-muted)',
        textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '8px',
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '28px', fontFamily: 'var(--font-display)', fontWeight: 800,
        color: accent || 'white', lineHeight: 1,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{sub}</div>
      )}
    </div>
  );
}

function ItemList({ items, variant }: {
  items: string[];
  variant: 'strength' | 'weakness' | 'step';
}) {
  const colors = {
    strength: { border: '#1e9b8a', bg: 'rgba(30,155,138,0.07)', icon: '✓', iconColor: '#1e9b8a' },
    weakness: { border: '#c9a84c', bg: 'rgba(201,168,76,0.07)', icon: '△', iconColor: '#c9a84c' },
    step:     { border: '#7c6bdc', bg: 'rgba(124,107,220,0.07)', icon: '→', iconColor: '#7c6bdc' },
  }[variant];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {items.map((item, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'flex-start', gap: '12px',
          padding: '14px 16px',
          background: colors.bg,
          border: `1px solid ${colors.border}33`,
          borderLeft: `3px solid ${colors.border}`,
          borderRadius: 'var(--radius-sm)',
        }}>
          <span style={{
            fontSize: '13px', fontWeight: 800, color: colors.iconColor,
            marginTop: '1px', flexShrink: 0, minWidth: '18px', textAlign: 'center',
          }}>
            {variant === 'step' ? `${i + 1}` : colors.icon}
          </span>
          <span style={{ fontSize: '14px', color: 'var(--text-primary)', lineHeight: 1.6 }}>{item}</span>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ marginBottom: '20px' }}>
      <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
        {title}
      </h2>
      {subtitle && <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function Skeleton({ w = '100%', h = '20px' }: { w?: string; h?: string }) {
  return (
    <div style={{
      width: w, height: h, borderRadius: '6px',
      background: 'linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.4s infinite',
    }} />
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function Analytics() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { user } = useAuth();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId || !user) return;
    (async () => {
      try {
        const idToken = await user.getIdToken();
        const res = await fetch(apiUrl(`/api/analytics/${sessionId}`), {
          headers: { Authorization: `Bearer ${idToken}` },
        });
        if (!res.ok) throw new Error(`Failed to load analytics (${res.status})`);
        setData(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load analytics.');
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId, user]);

  // ── Derived values ─────────────────────────────────────────────────────────

  const placementScore = data?.placement_score ?? data?.score ?? 0;
  const logicScore = data?.logic_score?.score ?? 0;
  const diplomacyScore = data?.diplomacy_score?.score ?? 0;
  const airtimeScore = data?.airtime_score ?? 0;
  const interruptionScore = data?.interruption_score ?? 0;

  const confColors = data ? confidenceBadgeColor(data.confidence_level) : confidenceBadgeColor('Medium');
  const archetypeLabel = data?.communication_archetype || data?.communication_style || '—';

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <style>{`
        @keyframes shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .analytics-section {
          animation: fadeUp 0.5s ease both;
        }
      `}</style>

      <div className="orb orb-teal" />
      <div className="orb orb-gold" />

      {/* Navbar */}
      <nav className="navbar">
        <Link to="/" className="navbar-brand">Mock<span>Talk</span></Link>
        <Link to="/dashboard" className="btn-ghost" style={{ fontSize: '13px', padding: '6px 14px' }}>
          Dashboard
        </Link>
      </nav>

      <div style={{
        flex: 1, maxWidth: '900px', margin: '0 auto',
        padding: '48px 24px 80px', width: '100%', position: 'relative', zIndex: 1,
      }}>

        {/* ── Loading state ── */}
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <Skeleton h="36px" w="60%" />
            <Skeleton h="20px" w="40%" />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
              {[1,2,3].map(i => <Skeleton key={i} h="100px" />)}
            </div>
            <Skeleton h="200px" />
            <Skeleton h="180px" />
          </div>
        )}

        {/* ── Error state ── */}
        {error && (
          <div style={{
            padding: '20px', marginTop: '24px',
            background: 'var(--accent-rose-dim)', border: '1px solid var(--accent-rose)',
            borderRadius: 'var(--radius-md)', color: 'var(--accent-rose)',
          }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* ── Main content ── */}
        {data && (
          <>
            {/* ── Hero ── */}
            <div className="analytics-section" style={{ marginBottom: '40px', animationDelay: '0s' }}>
              <div style={{
                display: 'inline-block', fontSize: '11px', fontWeight: 700,
                color: 'var(--accent-gold)', textTransform: 'uppercase',
                letterSpacing: '0.12em', marginBottom: '10px',
                padding: '4px 12px', background: 'var(--accent-gold-dim)',
                borderRadius: '20px', border: '1px solid rgba(201,168,76,0.25)',
              }}>
                {data.target_company || 'General'}
              </div>
              <h1 style={{ fontSize: '30px', marginBottom: '8px', lineHeight: 1.2 }}>
                Session Analytics
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '16px', maxWidth: '600px' }}>
                {data.topic}
              </p>
            </div>

            {/* ── Score + Stats Row ── */}
            <div className="analytics-section card" style={{
              marginBottom: '24px', animationDelay: '0.08s',
              display: 'flex', alignItems: 'center', gap: '32px', flexWrap: 'wrap',
            }}>
              {/* Ring */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
                <ScoreRing score={placementScore} size={140} />
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Placement Score
                </span>
              </div>

              {/* Key stats */}
              <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px' }}>
                <StatCard label="Duration" value={fmtDuration(data.duration_seconds)} />
                <StatCard label="Total Turns" value={data.turn_count} />
                <StatCard label="Your Turns" value={data.user_turn_count} />
                <StatCard
                  label="Airtime"
                  value={`${data.airtime?.userPercent ?? 0}%`}
                  sub="Target: 15-35%"
                  accent={
                    data.airtime?.userPercent >= 15 && data.airtime?.userPercent <= 35
                      ? '#1e9b8a' : '#c9a84c'
                  }
                />
                <StatCard label="Avg Words/Turn" value={data.avg_words_per_turn} />
                <StatCard label="Speaking Pace" value={`${data.speaking_pace_wpm}`} sub="words/min" />
              </div>
            </div>

            {/* ── Score Breakdown Bars ── */}
            <div className="analytics-section card" style={{ marginBottom: '24px', animationDelay: '0.16s' }}>
              <SectionHeader title="Performance Breakdown" subtitle="How you scored across key competencies" />
              <AnimatedBar score={logicScore}       label="Logic & Reasoning"  sublabel="Point-Reason-Example structure" />
              <AnimatedBar score={diplomacyScore}   label="Diplomacy & Collaboration" sublabel="Acknowledgements + building on others" />
              <AnimatedBar score={airtimeScore}     label="Airtime Balance"    sublabel="15-35% is the target band" />
              <AnimatedBar score={interruptionScore} label="Flow & Recovery"   sublabel="Interruptions handled" />
            </div>

            {/* ── Strengths / Weaknesses / Next Steps ── */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: '20px', marginBottom: '24px',
            }}>
              <div className="analytics-section card" style={{ animationDelay: '0.22s' }}>
                <SectionHeader title="✦ Strengths" />
                <ItemList items={data.gemini_strengths?.length ? data.gemini_strengths : ['—']} variant="strength" />
              </div>
              <div className="analytics-section card" style={{ animationDelay: '0.28s' }}>
                <SectionHeader title="△ Areas to Improve" />
                <ItemList items={data.gemini_weaknesses?.length ? data.gemini_weaknesses : ['—']} variant="weakness" />
              </div>
            </div>

            <div className="analytics-section card" style={{ marginBottom: '24px', animationDelay: '0.34s' }}>
              <SectionHeader title="→ Your Action Plan" subtitle="Concrete steps to level up before your next GD" />
              <ItemList items={data.gemini_next_steps?.length ? data.gemini_next_steps : ['—']} variant="step" />
            </div>

            {/* ── Gemini Verdict ── */}
            <div className="analytics-section card" style={{ marginBottom: '24px', animationDelay: '0.40s' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }}>
                <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  🤖 AI Verdict
                </h2>
                {data.communication_style && (
                  <span style={{
                    fontSize: '11px', fontWeight: 700, padding: '3px 10px',
                    borderRadius: '20px', background: 'rgba(124,107,220,0.15)',
                    color: '#9d8ef0', border: '1px solid rgba(124,107,220,0.3)',
                    letterSpacing: '0.06em', textTransform: 'uppercase',
                  }}>
                    {data.communication_style}
                  </span>
                )}
                {archetypeLabel && archetypeLabel !== data.communication_style && (
                  <span style={{
                    fontSize: '11px', fontWeight: 700, padding: '3px 10px',
                    borderRadius: '20px', background: 'rgba(201,168,76,0.12)',
                    color: 'var(--accent-gold)', border: '1px solid rgba(201,168,76,0.25)',
                    letterSpacing: '0.06em', textTransform: 'uppercase',
                  }}>
                    {archetypeLabel}
                  </span>
                )}
              </div>
              <p style={{
                color: 'var(--text-secondary)', lineHeight: 1.8,
                fontSize: '15px', whiteSpace: 'pre-wrap',
              }}>
                {data.gemini_verdict || 'No verdict available.'}
              </p>
            </div>

            {/* ── ML Insights ── */}
            <div className="analytics-section card" style={{ marginBottom: '32px', animationDelay: '0.46s' }}>
              <SectionHeader title="🧠 ML Insights" subtitle="Gemini-powered deeper analysis" />

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '20px' }}>
                {/* Confidence Level */}
                <div style={{
                  padding: '16px', borderRadius: 'var(--radius-sm)',
                  background: confColors.bg,
                  border: `1px solid ${confColors.border}33`,
                }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '8px' }}>
                    Confidence Level
                  </div>
                  <div style={{ fontSize: '22px', fontFamily: 'var(--font-display)', fontWeight: 800, color: confColors.text, marginBottom: '6px' }}>
                    {data.confidence_level}
                  </div>
                  {data.confidence_rationale && (
                    <p style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                      {data.confidence_rationale}
                    </p>
                  )}
                </div>

                {/* Topic Mastery */}
                <div style={{
                  padding: '16px', borderRadius: 'var(--radius-sm)',
                  background: 'rgba(124,107,220,0.08)',
                  border: '1px solid rgba(124,107,220,0.2)',
                }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '8px' }}>
                    Topic Mastery
                  </div>
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {data.topic_mastery || '—'}
                  </p>
                </div>
              </div>

              {/* Key Moments */}
              {data.key_moments?.length > 0 && (
                <>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    Key Moments
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {data.key_moments.map((moment, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                        <div style={{
                          width: '24px', height: '24px', borderRadius: '50%',
                          background: 'var(--accent-teal-dim)', border: '1px solid var(--accent-teal)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: '11px', fontWeight: 800, color: 'var(--accent-teal)',
                          flexShrink: 0,
                        }}>
                          {i + 1}
                        </div>
                        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.6, paddingTop: '2px' }}>
                          {moment}
                        </p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* ── Detailed Breakdown (collapsible feel via grid) ── */}
            <div className="analytics-section card" style={{ marginBottom: '32px', animationDelay: '0.52s' }}>
              <SectionHeader title="📊 Detailed Stats" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                {[
                  { label: 'Points with Reasoning', value: data.logic_score?.pointsWithReasoning ?? '—' },
                  { label: 'Points with Examples', value: data.logic_score?.pointsWithExample ?? '—' },
                  { label: 'Acknowledgements', value: data.diplomacy_score?.acknowledgements ?? '—' },
                  { label: 'Built on Others', value: data.diplomacy_score?.buildOnOthers ?? '—' },
                  { label: 'Interruptions Made', value: data.interruptions?.userInitiated ?? 0 },
                  { label: 'Interruptions Received', value: data.interruptions?.userReceived ?? 0 },
                  { label: 'Recovery Rate', value: data.interruptions?.recoveryRate !== undefined ? `${Math.round((data.interruptions.recoveryRate) * 100)}%` : '—' },
                  { label: 'Your Speaking Time', value: data.airtime?.userSeconds !== undefined ? `${data.airtime.userSeconds}s` : '—' },
                ].map(row => (
                  <div key={row.label} style={{
                    padding: '12px 14px', borderRadius: 'var(--radius-sm)',
                    background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
                  }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{row.label}</div>
                    <div style={{ fontSize: '20px', fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {row.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Action Buttons ── */}
            <div className="analytics-section" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', animationDelay: '0.58s' }}>
              <Link to="/" className="btn-primary" style={{ textDecoration: 'none' }}>
                Practice Again →
              </Link>
              <Link to="/dashboard" className="btn-ghost" style={{ textDecoration: 'none' }}>
                View Dashboard
              </Link>
              <button
                className="btn-ghost"
                onClick={() => window.print()}
                style={{ cursor: 'pointer' }}
              >
                🖨 Download Report
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
