import { Suspense, lazy } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Landing from "@/pages/Landing";

const Login = lazy(() => import("@/pages/Login"));
const Register = lazy(() => import("@/pages/Register"));
const Layout = lazy(() => import("@/components/Layout"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Leads = lazy(() => import("@/pages/Leads"));
const Outbox = lazy(() => import("@/pages/Outbox"));
const Automation = lazy(() => import("@/pages/Automation"));
const Activity = lazy(() => import("@/pages/Activity"));
const Profile = lazy(() => import("@/pages/Profile"));
const Inboxes = lazy(() => import("@/pages/Inboxes"));
const Pipeline = lazy(() => import("@/pages/Pipeline"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const Billing = lazy(() => import("@/pages/Billing"));
const Team = lazy(() => import("@/pages/Team"));
const Referrals = lazy(() => import("@/pages/Referrals"));
const Docs = lazy(() => import("@/pages/Docs"));

const RouteFallback = () => (
  <div className="min-h-screen flex items-center justify-center bg-[#09090B] text-zinc-500 font-mono text-sm">
    Loading…
  </div>
);

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null)
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090B] text-zinc-500 font-mono text-sm">
        Initializing OutreachPilot…
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user } = useAuth();
  if (user === null) return null;
  if (user) return <Navigate to="/app" replace />;
  return children;
}

function App() {
  return (
    <div className="App dark">
      <AuthProvider>
        <BrowserRouter>
          <Toaster theme="dark" position="top-right" richColors />
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
              <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
              <Route
                path="/app"
                element={
                  <Protected>
                    <Layout />
                  </Protected>
                }
              >
                <Route index element={<Dashboard />} />
                <Route path="profile" element={<Profile />} />
                <Route path="leads" element={<Leads />} />
                <Route path="pipeline" element={<Pipeline />} />
                <Route path="outbox" element={<Outbox />} />
                <Route path="inboxes" element={<Inboxes />} />
                <Route path="automation" element={<Automation />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="billing" element={<Billing />} />
                <Route path="team" element={<Team />} />
                <Route path="referrals" element={<Referrals />} />
                <Route path="docs" element={<Docs />} />
                <Route path="activity" element={<Activity />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
