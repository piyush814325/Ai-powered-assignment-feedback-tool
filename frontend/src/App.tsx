import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
import { ROLE_MISMATCH_CLEARED_EVENT, ROLE_MISMATCH_EVENT } from './services/api';
import { Alert, Button } from './ui/components';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import StudentDashboard from './pages/StudentDashboard';
import TeacherDashboard from './pages/TeacherDashboard';

function RoleMismatchNotice() {
  const [visible, setVisible] = useState(false);
  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);

  useEffect(() => {
    const showNotice = () => setVisible(true);
    const clearNotice = () => setVisible(false);
    window.addEventListener(ROLE_MISMATCH_EVENT, showNotice);
    window.addEventListener(ROLE_MISMATCH_CLEARED_EVENT, clearNotice);
    return () => {
      window.removeEventListener(ROLE_MISMATCH_EVENT, showNotice);
      window.removeEventListener(ROLE_MISMATCH_CLEARED_EVENT, clearNotice);
    };
  }, []);

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 top-3 z-[100] px-4">
      <Alert variant="error" className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 shadow-lg">
        <span>You are signed in with a different account in another tab. Please sign in again.</span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            logout();
            navigate('/login');
          }}
        >
          Sign in again
        </Button>
      </Alert>
    </div>
  );
}

function App() {
  const { user } = useAuthStore();

  return (
    <BrowserRouter>
      <RoleMismatchNotice />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {user ? (
          <>
            {user.role === 'student' && <Route path="/dashboard" element={<StudentDashboard />} />}
            {(user.role === 'teacher' || user.role === 'admin') && (
              <Route path="/dashboard" element={<TeacherDashboard />} />
            )}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </>
        ) : (
          <>
            <Route path="*" element={<Navigate to="/login" replace />} />
          </>
        )}
      </Routes>
    </BrowserRouter>
  );
}

export default App;
