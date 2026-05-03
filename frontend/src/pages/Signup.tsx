import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';

export default function Signup() {
  const { signup, isConfigured } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await signup(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md mx-auto relative mt-20">
      <div className="glass-card p-6 sm:p-8 space-y-6 rounded-2xl relative z-10 border-[#333333]">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-2xl font-bold text-white tracking-tight">Create Account</h2>
            <span className="badge-ai text-[10px] tracking-widest">MockTalk</span>
          </div>
          <p className="text-sm font-medium text-[#A0A0A5]">Start your GD preparation journey.</p>
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
              minLength={6}
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-[#888890] uppercase tracking-wide mb-1.5" htmlFor="confirm">
              Confirm Password
            </label>
            <input
              className="input-field mt-0 font-medium"
              id="confirm"
              type="password"
              placeholder="••••••••"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={6}
            />
          </div>
          <div className="pt-2">
            <button
              className="btn-primary w-full py-3.5"
              type="submit"
              disabled={busy || !isConfigured}
            >
              {busy ? 'Creating account...' : 'Create Account'}
            </button>
          </div>
        </form>
        <p className="text-[#888890] text-sm text-center pt-2">
          Already have an account?{' '}
          <Link className="text-[#2A9D8F] hover:text-white font-semibold transition" to="/login">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
