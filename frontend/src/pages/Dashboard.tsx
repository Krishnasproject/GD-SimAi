import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Activity, Clock, Target, Plus, Play, BarChart3 } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import { apiUrl } from '../config/api';

type SessionItem = {
  sessionId: string;
  topic: string;
  targetCompany: string;
  status: string;
  createdAt?: string;
};

export default function Dashboard() {
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

  const stats = [
    { label: 'Total Sessions', value: sessions.length.toString(), icon: Activity },
    { label: 'Avg Latency', value: '< 980ms', icon: Clock },
    { label: 'Completion Rate', value: '84%', icon: Target },
  ];

  return (
    <div className="space-y-10 max-w-6xl mx-auto py-8 px-4">
      <section className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
        <div className="space-y-1">
          <motion.h2
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-3xl font-bold tracking-tight text-white"
          >
            Dashboard
          </motion.h2>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="text-[#A0A0A5] text-sm font-medium"
          >
            Welcome back. Ready for your next session?
          </motion.p>
        </div>
        <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
          <Link to="/" className="btn-primary inline-flex items-center gap-2">
            <Plus className="w-4 h-4" />
            New Simulation
          </Link>
        </motion.div>
      </section>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        {stats.map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + idx * 0.1 }}
              className="glass-card p-6 rounded-xl flex items-center gap-5"
            >
              <div className="p-3.5 bg-[#121216] rounded-lg border border-[#333333]">
                <Icon className="w-6 h-6 text-[#2A9D8F]" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-[#888890] tracking-wide uppercase">{stat.label}</span>
                <span className="text-2xl font-bold text-white tabular-nums">{loading ? '-' : stat.value}</span>
              </div>
            </motion.div>
          );
        })}
      </div>

      <div>
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-[#888890]" />
          <h3 className="text-lg font-semibold text-white">Recent Sessions</h3>
        </div>
        {loading && <p className="text-[#A0A0A5] animate-pulse">Loading sessions...</p>}
        {error && (
          <p className="rounded-lg border border-red-900/50 bg-red-900/20 px-4 py-3 text-red-200">{error}</p>
        )}
        {!loading && !error && sessions.length === 0 && (
          <div className="glass-card p-10 text-center rounded-xl flex flex-col items-center gap-4">
            <div className="p-4 bg-[#121216] border border-[#333333] rounded-full">
              <Target className="w-8 h-8 text-[#A0A0A5]" />
            </div>
            <div className="space-y-1">
              <p className="text-white font-medium text-lg">No sessions yet</p>
              <p className="text-[#888890] max-w-sm mx-auto">
                Click "New Simulation" to start your first GD practice session.
              </p>
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3">
          {sessions.map((session, idx) => (
            <motion.div
              key={session.sessionId}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + idx * 0.05 }}
              className="glass-card p-5 rounded-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6 group hover:border-[#4A4A52]"
            >
              <div className="space-y-2">
                <p className="text-white font-semibold text-lg tracking-tight group-hover:text-[#2A9D8F] transition-colors">
                  {session.topic}
                </p>
                <div className="flex flex-wrap items-center gap-3 text-sm text-[#888890] font-medium">
                  <span className="flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5" /> {session.targetCompany}
                  </span>
                  <span className="text-[#333333]">|</span>
                  <span className="badge-teal">{session.status}</span>
                  {session.createdAt && (
                    <>
                      <span className="text-[#333333]">|</span>
                      <span>{new Date(session.createdAt).toLocaleDateString('en-US', {
                        day: 'numeric', month: 'short', year: 'numeric'
                      })}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link
                  to={`/room/${session.sessionId}`}
                  state={{ sessionId: session.sessionId, topic: session.topic, targetCompany: session.targetCompany }}
                  className="btn-secondary flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  Enter Room
                </Link>
                <Link
                  to={`/analytics/${session.sessionId}`}
                  state={{ sessionId: session.sessionId }}
                  className="btn-primary flex items-center gap-2"
                >
                  <BarChart3 className="w-4 h-4" />
                  Analytics
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
