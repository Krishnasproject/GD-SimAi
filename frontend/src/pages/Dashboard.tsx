import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { apiUrl } from '../config/api';
import { useScrollReveal } from '../hooks/useScrollReveal';

type SessionItem = {
  sessionId: string;
  topic: string;
  targetCompany: string;
  status: string;
  createdAt?: string;
};

export default function Dashboard() {
  useScrollReveal();
  const { user } = useAuth();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSessions() {
      if (!user) { setLoading(false); return; }
      try {
        const idToken = await user.getIdToken();
        const response = await fetch(apiUrl(`/api/sessions/user/${user.uid}`), {
          headers: { Authorization: `Bearer ${idToken}` },
        });
        if (!response.ok) throw new Error(`Failed to load sessions (${response.status})`);
        const payload = (await response.json()) as SessionItem[];
        setSessions(payload);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    }
    loadSessions();
  }, [user]);

  return (
    <div className="reveal" style={{ maxWidth: '1100px', margin: '0 auto', padding: '48px 32px', position: 'relative', zIndex: 1 }}>
      
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '40px' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '28px', letterSpacing: '-0.02em', marginBottom: '4px' }}>
            Your Sessions
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
            Track your GD progress over time
          </p>
        </div>
        <Link to="/" className="btn-primary">+ New Session</Link>
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '40px' }}>
        {[
          { label: 'Total Sessions', value: loading ? '—' : sessions.length },
          { label: 'This Week', value: '—' },
          { label: 'Best Score', value: '—' },
        ].map(stat => (
          <div key={stat.label} className="card" style={{ padding: '20px 24px' }}>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>
              {stat.label}
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '28px', color: 'var(--text-primary)' }}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Sessions list */}
      {loading && <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>Loading sessions...</p>}
      {error && <p style={{ color: 'var(--rose)', fontSize: '14px' }}>{error}</p>}

      {!loading && sessions.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '64px', borderStyle: 'dashed' }}>
          <div style={{ fontSize: '32px', marginBottom: '16px' }}>🎯</div>
          <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '18px', marginBottom: '8px' }}>
            No sessions yet
          </h3>
          <p style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '24px' }}>
            Start your first GD practice session now
          </p>
          <Link to="/" className="btn-primary">Start practicing →</Link>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {sessions.map(session => (
          <div key={session.sessionId} className="card" style={{
            display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', padding: '20px 24px',
            transition: 'border-color 0.2s', cursor: 'default',
          }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border-light)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '15px', marginBottom: '6px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {session.topic}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span className="badge badge-ember" style={{ fontSize: '10px' }}>{session.targetCompany}</span>
                <span className="badge badge-neutral" style={{ fontSize: '10px' }}>{session.status}</span>
                {session.createdAt && (
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {new Date(session.createdAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '10px', marginLeft: '24px' }}>
              <Link
                to={`/analytics/${session.sessionId}`}
                state={{ sessionId: session.sessionId }}
                className="btn-secondary" style={{ fontSize: '13px', padding: '8px 16px' }}
              >
                Analytics
              </Link>
              <Link
                to={`/room/${session.sessionId}`}
                state={{ sessionId: session.sessionId, topic: session.topic, targetCompany: session.targetCompany }}
                className="btn-primary" style={{ fontSize: '13px', padding: '8px 16px' }}
              >
                Rejoin
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
