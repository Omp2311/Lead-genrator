import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Leads from "@/pages/Leads";
import Outbox from "@/pages/Outbox";
import Automation from "@/pages/Automation";
import Activity from "@/pages/Activity";
import Profile from "@/pages/Profile";
import Inboxes from "@/pages/Inboxes";
import Pipeline from "@/pages/Pipeline";
import Analytics from "@/pages/Analytics";
import Billing from "@/pages/Billing";
import Team from "@/pages/Team";
import Landing from "@/pages/Landing";

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
              <Route path="activity" element={<Activity />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
