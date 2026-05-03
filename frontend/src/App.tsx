import { BrowserRouter, Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Room from './pages/Room';
import Analytics from './pages/Analytics';
import Dashboard from './pages/Dashboard';
import ProtectedRoute from './components/ProtectedRoute';
import { useAuth } from './auth/useAuth';

function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isRoom = location.pathname.startsWith('/room/');
  const isAnalytics = location.pathname.startsWith('/analytics/');
  if (isRoom || isAnalytics) return null; // These pages have their own header

  return (
    <nav className="navbar">
      <Link to={user ? '/dashboard' : '/'} className="navbar-brand">
        Mock<span>Talk</span>
      </Link>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {user ? (
          <>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {user.email}
            </span>
            <button
              className="btn-ghost"
              style={{ padding: '8px 16px', fontSize: '13px' }}
              onClick={async () => { await logout(); navigate('/login'); }}
            >
              Logout
            </button>
          </>
        ) : (
          <>
            <Link to="/login" style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
              Sign In
            </Link>
            <Link to="/signup" className="btn-primary" style={{ padding: '8px 20px', fontSize: '14px' }}>
              Get Started
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}

function AppLayout() {
  return (
    <>
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route
            path="/room/:sessionId"
            element={
              <ProtectedRoute>
                <Room />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics/:sessionId"
            element={
              <ProtectedRoute>
                <Analytics />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
}
