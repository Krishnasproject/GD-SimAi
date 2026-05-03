import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { BrainCircuit, Zap, Activity, Users, Mic2, BarChart } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import { apiUrl } from '../config/api';
import { useScrollReveal } from '../hooks/useScrollReveal';

const METRICS = [
  { label: 'Max Session Turns', value: '40' },
  { label: 'Latency VAD/STT', value: '< 1s' },
  { label: 'Dynamic Personas', value: '3' },
];

const COMPANIES = [
  { id: 'TCS', name: 'TCS Ninja/Digital', span: 'col-span-12 sm:col-span-8', icon: BrainCircuit },
  { id: 'Infosys', name: 'Infosys SP', span: 'col-span-12 sm:col-span-4', icon: Zap },
  { id: 'Deloitte', name: 'Deloitte USI', span: 'col-span-12 sm:col-span-6', icon: Activity },
  { id: 'Accenture', name: 'Accenture', span: 'col-span-12 sm:col-span-6', icon: Users },
  { id: 'General', name: 'General Pool', span: 'col-span-12', icon: BarChart },
];

export default function Landing() {
  useScrollReveal();
  const [selectedCompany, setSelectedCompany] = useState('General');
  const [isInitializing, setIsInitializing] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { user, logout } = useAuth();

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
      <nav className="navbar">
        <div className="navbar-brand">Mock<span>Talk</span></div>
        <div className="flex items-center gap-4">
          {user ? (
            <>
              <Link to="/dashboard" className="btn-ghost" style={{ fontSize: '13px', padding: '6px 14px' }}>Dashboard</Link>
              <button 
                onClick={() => logout()} 
                className="btn-ghost" 
                style={{ fontSize: '13px', padding: '6px 14px', borderColor: 'var(--accent-rose-dim)', color: 'var(--accent-rose)' }}
              >
                Logout
              </button>
            </>
          ) : (
            <Link to="/login" className="btn-primary" style={{ padding: '8px 16px', fontSize: '13px' }}>Sign In</Link>
          )}
        </div>
      </nav>

      <div className="max-w-[1400px] mx-auto px-6 sm:px-10 mt-12 sm:mt-24 grid grid-cols-1 lg:grid-cols-12 gap-20 items-start relative z-10 w-full min-h-[calc(100vh-100px)]">

        {/* Left Col: Hero */}
        <div className="lg:col-span-7 space-y-12">
          <div className="space-y-6 reveal">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--accent-teal-dim)] bg-[var(--accent-teal-dim)] px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--accent-teal)]">
              <Mic2 className="w-3.5 h-3.5" />
              <span>MockTalk Engine v1.0</span>
            </div>

            <h1 className="text-[clamp(2.8rem,6vw,5rem)] font-['Syne'] font-[800] tracking-tight leading-[1.05] text-white">
              Practice GDs Like<br />You're Already in<br />the Room.
            </h1>

            <div className="pl-5 border-l-2 border-[var(--accent-gold)]">
              <p className="text-[var(--text-secondary)] text-[18px] max-w-xl leading-relaxed font-['DM_Sans']">
                Three AI personas. Real-time voice. Placement-grade pressure.
              </p>
            </div>
          </div>

          <div className="space-y-4 reveal reveal-delay-1">
            {startError && (
              <div className="rounded-[var(--radius-sm)] border border-[var(--accent-rose-dim)] bg-[var(--accent-rose-dim)] px-4 py-3 text-[var(--accent-rose)] text-[13px] font-medium">
                {startError}
              </div>
            )}
            <button
              onClick={handleStart}
              disabled={isInitializing}
              className="btn-primary px-8 py-4 sm:w-auto w-full text-[16px] font-['Syne'] font-bold shadow-[0_8px_32px_var(--accent-teal-dim)] hover:shadow-[0_12px_40px_rgba(30,155,138,0.4)] transition-all bg-[var(--accent-teal)]"
            >
              {isInitializing ? 'Initializing Pipeline...' : 'Begin Session →'}
            </button>
          </div>

          <div className="pt-8 border-t border-[var(--border)] grid grid-cols-3 gap-6 reveal reveal-delay-2">
            {METRICS.map((metric, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                <div className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider">{metric.label}</div>
                <div className="text-2xl font-['Syne'] font-bold text-white tabular-nums tracking-tight">{metric.value}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Col: Targets */}
        <div className="lg:col-span-5 w-full reveal reveal-delay-1">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-[11px] font-bold tracking-widest text-[var(--accent-gold)] uppercase">Training Environment</h3>
          </div>

          <div className="grid grid-cols-12 gap-4">
            {COMPANIES.map((company) => {
              const isSelected = selectedCompany === company.id;

              return (
                <button
                  key={company.id}
                  onClick={() => setSelectedCompany(company.id)}
                  className={`
                    text-left p-6 rounded-[var(--radius-md)] transition-all duration-200
                    ${company.span} 
                    ${isSelected
                      ? 'bg-[var(--bg-hover)] border-l-2 border-l-[var(--accent-gold)] shadow-xl relative'
                      : 'bg-[var(--bg-card)] border border-[var(--border)] hover:border-[#3A3A4A]'}
                  `}
                >
                  {isSelected && <div className="absolute top-4 right-4 w-2 h-2 rounded-full bg-[var(--accent-gold)]"></div>}
                  <div className="flex flex-col h-full gap-4">
                    <h4 className={`font-['Syne'] font-medium text-lg leading-tight tracking-tight ${isSelected ? 'text-white' : 'text-[var(--text-primary)]'}`}>
                      {company.name}
                    </h4>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

      </div>
    </>
  );
}
