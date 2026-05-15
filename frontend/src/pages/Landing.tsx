import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { apiUrl } from '../config/api';
import { useScrollReveal } from '../hooks/useScrollReveal';

const COMPANIES = [
  { id: 'TCS', name: 'TCS Ninja/Digital' },
  { id: 'Infosys', name: 'Infosys SP' },
  { id: 'Deloitte', name: 'Deloitte USI' },
  { id: 'Accenture', name: 'Accenture' },
  { id: 'General', name: 'General Pool' },
];

export default function Landing() {
  useScrollReveal();
  const [selectedCompany, setSelectedCompany] = useState('General');
  const [isInitializing, setIsInitializing] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { user } = useAuth();

  const handleStart = async () => {
    if (!user) {
      navigate('/login');
      return;
    }

    setIsInitializing(true);
    setStartError(null);
    try {
      const idToken = await user.getIdToken();

      const response = await fetch(apiUrl('/api/sessions/create'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${idToken}`,
        },
        body: JSON.stringify({
          user_id: user.uid,
          target_company: selectedCompany,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create session (${response.status})`);
      }

      const payload = await response.json();
      navigate(`/room/${payload.session_id}`, {
        state: {
          sessionId: payload.session_id,
          topic: payload.topic,
          targetCompany: selectedCompany,
        },
      });
    } catch (err) {
      console.error('Failed to start simulation', err);
      setStartError(
        err instanceof Error
          ? err.message
          : 'Could not start simulation. Ensure backend is running on port 8000.'
      );
    } finally {
      setIsInitializing(false);
    }
  };

  return (
    <>
      {/* ── HERO SECTION ── */}
      <section style={{
        minHeight: '92vh', display: 'flex', alignItems: 'center',
        maxWidth: '1200px', margin: '0 auto', padding: '80px 48px',
        position: 'relative', zIndex: 1,
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '80px', alignItems: 'center', width: '100%' }}>
          
          {/* Left: Copy */}
          <div>
            {/* Eyebrow badge */}
            <div className="badge badge-ember" style={{ marginBottom: '28px' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ember)', display: 'inline-block' }} />
              Now in Beta · Free for students
            </div>

            <h1 style={{
              fontFamily: 'var(--font-display)', fontWeight: 800,
              fontSize: 'clamp(2.6rem, 4.5vw, 3.8rem)',
              lineHeight: 1.08, letterSpacing: '-0.03em',
              color: 'var(--text-primary)', marginBottom: '24px',
            }}>
              The smartest way to<br />
              <span style={{ color: 'var(--ember)' }}>crack your GD round.</span>
            </h1>

            <p style={{
              fontSize: '17px', color: 'var(--text-secondary)',
              lineHeight: 1.75, maxWidth: '480px', marginBottom: '40px',
              fontWeight: 400,
            }}>
              Practice live group discussions with AI personas that challenge, 
              interrupt, and evaluate you — exactly like real placement rounds 
              at TCS, Infosys, Deloitte and more.
            </p>

            {/* CTA row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '48px' }}>
              <button onClick={handleStart} disabled={isInitializing} className="btn-primary"
                style={{ padding: '14px 32px', fontSize: '15px' }}>
                {isInitializing ? 'Starting...' : 'Start Free Session →'}
              </button>
              <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                No signup needed to try
              </span>
            </div>

            {/* Stats strip */}
            <div style={{
              display: 'flex', gap: '32px',
              paddingTop: '32px', borderTop: '1px solid var(--border)',
            }}>
              {[
                { value: '3', label: 'AI Personas' },
                { value: '<1s', label: 'Response Time' },
                { value: '50+', label: 'GD Topics' },
                { value: '100%', label: 'Free' },
              ].map(stat => (
                <div key={stat.label}>
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '22px', color: 'var(--text-primary)' }}>
                    {stat.value}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Environment selector */}
          <div>
            <div style={{ marginBottom: '20px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ember)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: '6px' }}>
                Training Environment
              </div>
              <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
                Select your target company to get relevant GD topics
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              {COMPANIES.map(company => {
                const isSelected = selectedCompany === company.id;
                return (
                  <button
                    key={company.id}
                    onClick={() => setSelectedCompany(company.id)}
                    style={{
                      gridColumn: company.id === 'General' ? '1 / -1' : undefined,
                      padding: '16px 20px', borderRadius: 'var(--r-md)',
                      background: isSelected ? 'rgba(232,108,58,0.08)' : 'var(--bg-card)',
                      border: isSelected ? '1px solid var(--ember-border)' : '1px solid var(--border)',
                      cursor: 'pointer', textAlign: 'left',
                      transition: 'all 0.2s',
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    }}
                  >
                    <span style={{
                      fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '14px',
                      color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
                    }}>
                      {company.name}
                    </span>
                    {isSelected && (
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--ember)' }} />
                    )}
                  </button>
                );
              })}
            </div>

            {startError && (
              <div style={{ marginTop: '16px', padding: '12px 16px', background: 'var(--rose-dim)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: 'var(--r-md)', fontSize: '13px', color: 'var(--rose)' }}>
                {startError}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section style={{ maxWidth: '1200px', margin: '0 auto', padding: '80px 48px', position: 'relative', zIndex: 1 }}>
        <div style={{ textAlign: 'center', marginBottom: '56px' }}>
          <div className="badge badge-neutral" style={{ marginBottom: '16px' }}>How it works</div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 'clamp(1.8rem, 3vw, 2.6rem)', letterSpacing: '-0.02em' }}>
            Three steps to GD mastery
          </h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
          {[
            { step: '01', title: 'Pick your arena', desc: 'Choose your target company. We load relevant topics and calibrate AI difficulty to match their actual GD style.' },
            { step: '02', title: 'Discuss in real-time', desc: 'Speak naturally. Three AI personas — an Aggressor, a Logical thinker, and a Diplomat — respond instantly with voice.' },
            { step: '03', title: 'Get brutally honest feedback', desc: 'After every session, receive a performance report covering logic, diplomacy, airtime, and actionable next steps.' },
          ].map(item => (
            <div key={item.step} className="card reveal" style={{ position: 'relative', overflow: 'hidden' }}>
              <div style={{
                fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '48px',
                color: 'var(--border-light)', lineHeight: 1, marginBottom: '20px',
                letterSpacing: '-0.04em',
              }}>
                {item.step}
              </div>
              <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '17px', marginBottom: '12px' }}>
                {item.title}
              </h3>
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── PERSONAS SECTION ── */}
      <section style={{ maxWidth: '1200px', margin: '0 auto', padding: '80px 48px', position: 'relative', zIndex: 1 }}>
        <div style={{ textAlign: 'center', marginBottom: '56px' }}>
          <div className="badge badge-neutral" style={{ marginBottom: '16px' }}>Meet the panel</div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 'clamp(1.8rem, 3vw, 2.6rem)', letterSpacing: '-0.02em' }}>
            Three AI minds. Zero mercy.
          </h2>
          <p style={{ fontSize: '16px', color: 'var(--text-secondary)', marginTop: '12px' }}>
            Each persona has a distinct personality, speaking style, and strategy.
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
          {[
            { initial: 'R', name: 'Ravi', role: 'The Aggressor', color: '#E8402A', desc: 'Challenges every point. Uses data to dismantle weak arguments. Interrupts when he disagrees. High pressure, zero patience.', traits: ['Interrupts often', 'Data-driven attacks', 'Challenges assumptions'] },
            { initial: 'S', name: 'Sneha', role: 'The Analyst', color: '#2DD4BF', desc: 'Methodical and precise. Cites studies and reports. Builds structured arguments point by point. Hard to counter without facts.', traits: ['Cites research', 'Structured reasoning', 'Fact-checks claims'] },
            { initial: 'A', name: 'Arjun', role: 'The Diplomat', color: '#FBBF24', desc: 'Bridges gaps and summarises. Invites you to speak when you\'re silent. Collaborative but firm when needed.', traits: ['Bridges viewpoints', 'Encourages participation', 'Summarises fairly'] },
          ].map(persona => (
            <div key={persona.name} className="card reveal" style={{ borderTop: `3px solid ${persona.color}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '16px' }}>
                <div style={{
                  width: 48, height: 48, borderRadius: '50%',
                  background: `${persona.color}20`, border: `2px solid ${persona.color}40`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '18px', color: persona.color,
                }}>
                  {persona.initial}
                </div>
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '16px' }}>{persona.name}</div>
                  <div style={{ fontSize: '12px', color: persona.color, fontWeight: 600 }}>{persona.role}</div>
                </div>
              </div>
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: '20px' }}>
                {persona.desc}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {persona.traits.map(trait => (
                  <div key={trait} style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ width: 4, height: 4, borderRadius: '50%', background: persona.color, flexShrink: 0 }} />
                    {trait}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section style={{ maxWidth: '1200px', margin: '0 auto', padding: '80px 48px 120px', position: 'relative', zIndex: 1 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(232,108,58,0.08) 0%, rgba(45,212,191,0.05) 100%)',
          border: '1px solid var(--ember-border)', borderRadius: 'var(--r-xl)',
          padding: '64px', textAlign: 'center',
        }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 'clamp(1.8rem, 3vw, 2.8rem)', letterSpacing: '-0.02em', marginBottom: '16px' }}>
            Your GD round is 3 weeks away.<br />
            <span style={{ color: 'var(--ember)' }}>Are you ready?</span>
          </h2>
          <p style={{ fontSize: '16px', color: 'var(--text-secondary)', marginBottom: '32px' }}>
            Join thousands of students practicing with MockTalk every day.
          </p>
          <button onClick={handleStart} disabled={isInitializing} className="btn-primary"
            style={{ padding: '15px 36px', fontSize: '16px' }}>
            {isInitializing ? 'Starting...' : 'Begin Your First Session →'}
          </button>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer style={{
        borderTop: '1px solid var(--border)', padding: '28px 48px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        position: 'relative', zIndex: 1,
      }}>
        <span className="navbar-brand">Mock<span>Talk</span></span>
        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          Built for placement warriors. Free forever.
        </span>
      </footer>
    </>
  );
}
