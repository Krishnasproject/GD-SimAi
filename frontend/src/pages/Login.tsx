import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';

export default function Login() {
  const { login, isConfigured } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || '/dashboard';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to login');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', position: 'relative' }}>
      <div style={{ width: '100%', maxWidth: '420px', position: 'relative', zIndex: 1 }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div className="navbar-brand" style={{ fontSize: '22px', marginBottom: '8px', display: 'block' }}>
            Mock<span style={{ color: 'var(--ember)' }}>Talk</span>
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '24px', marginBottom: '8px' }}>
            Welcome back
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
            Sign in to continue your GD preparation
          </p>
        </div>

        <div className="card" style={{ padding: '32px' }}>
          {!isConfigured && (
            <div style={{ padding: '12px 16px', background: 'var(--rose-dim)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: 'var(--r-sm)', fontSize: '13px', color: 'var(--rose)', marginBottom: '20px' }}>
              Firebase not configured.
            </div>
          )}
          {error && (
            <div style={{ padding: '12px 16px', background: 'var(--rose-dim)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: 'var(--r-sm)', fontSize: '13px', color: 'var(--rose)', marginBottom: '20px' }}>
              {error}
            </div>
          )}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                Email address
              </label>
              <input className="input" type="email" placeholder="you@college.edu"
                value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                Password
              </label>
              <input className="input" type="password" placeholder="••••••••"
                value={password} onChange={e => setPassword(e.target.value)} required />
            </div>
            <button type="submit" disabled={busy || !isConfigured} className="btn-primary"
              style={{ marginTop: '8px', padding: '13px', fontSize: '15px' }}>
              {busy ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
          <p style={{ textAlign: 'center', fontSize: '14px', color: 'var(--text-muted)', marginTop: '24px' }}>
            New here?{' '}
            <Link to="/signup" style={{ color: 'var(--ember)', fontWeight: 600, textDecoration: 'none' }}>
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
