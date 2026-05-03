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
    <div className="max-w-md mx-auto relative mt-20">
      <div className="glass-card p-6 sm:p-8 space-y-6 rounded-2xl relative z-10 border-[#333333]">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-2xl font-bold text-white tracking-tight">Sign In</h2>
            <span className="badge-teal text-[10px] tracking-widest">MockTalk</span>
          </div>
          <p className="text-sm font-medium text-[#A0A0A5]">Welcome back. Sign in to continue.</p>
        </div>
        {!isConfigured && (
          <p className="rounded-xl border border-red-900/50 bg-red-900/20 px-4 py-3 text-red-200 text-sm font-medium">
            Firebase not configured.
          </p>
        )}
        {error && (
          <p className="rounded-xl border border-red-900/50 bg-red-900/20 px-4 py-3 text-red-200 text-sm font-medium">
            {error}
          </p>
        )}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-xs font-bold text-[#888890] uppercase tracking-wide mb-1.5" htmlFor="email">
              Email
            </label>
            <input
              className="input-field mt-0 font-medium"
              id="email"
              type="email"
              placeholder="you@domain.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-[#888890] uppercase tracking-wide mb-1.5" htmlFor="password">
              Password
            </label>
            <input
              className="input-field mt-0 font-medium"
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div className="pt-2">
            <button
              className="btn-primary w-full py-3.5"
              type="submit"
              disabled={busy || !isConfigured}
            >
              {busy ? 'Signing in...' : 'Sign In'}
            </button>
          </div>
        </form>
        <p className="text-[#888890] text-sm text-center pt-2">
          No account?{' '}
          <Link className="text-[#2A9D8F] hover:text-white font-semibold transition" to="/signup">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
