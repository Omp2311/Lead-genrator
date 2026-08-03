import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  LayoutDashboard,
  Users,
  Send,
  Zap,
  Activity as ActivityIcon,
  LogOut,
  Radar,
  UserCog,
} from "lucide-react";

const nav = [
  { to: "/app", label: "Command", icon: LayoutDashboard, end: true, id: "nav-dashboard" },
  { to: "/app/profile", label: "Profile & Skills", icon: UserCog, id: "nav-profile" },
  { to: "/app/leads", label: "Leads", icon: Users, id: "nav-leads" },
  { to: "/app/outbox", label: "Outbox", icon: Send, id: "nav-outbox" },
  { to: "/app/automation", label: "Automation", icon: Zap, id: "nav-automation" },
  { to: "/app/activity", label: "Activity", icon: ActivityIcon, id: "nav-activity" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="min-h-screen flex bg-[#09090B] text-white">
      <aside className="w-60 shrink-0 border-r border-zinc-800 flex flex-col fixed h-screen bg-[#0c0c0e]">
        <div className="px-6 py-6 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Radar className="w-6 h-6 text-cyan-400" strokeWidth={2.2} />
            <span className="font-display font-extrabold text-lg tracking-tight">
              Outreach<span className="text-cyan-400">Pilot</span>
            </span>
          </div>
          <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-600 mt-2">
            Autonomous Cold Outreach
          </p>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              data-testid={item.id}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm transition-colors duration-200 ${
                  isActive
                    ? "bg-cyan-400/10 text-cyan-300 border-l-2 border-cyan-400"
                    : "text-zinc-400 hover:text-white hover:bg-zinc-800/60 border-l-2 border-transparent"
                }`
              }
            >
              <item.icon className="w-4 h-4" strokeWidth={2} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-zinc-800">
          <div className="px-3 mb-3">
            <p className="text-sm font-medium truncate" data-testid="sidebar-user-name">
              {user?.name || "Operator"}
            </p>
            <p className="text-xs text-zinc-500 truncate">{user?.email}</p>
          </div>
          <button
            onClick={handleLogout}
            data-testid="logout-button"
            className="w-full flex items-center gap-2 px-3 py-2 rounded-sm text-sm text-zinc-400 hover:text-red-400 hover:bg-red-500/10 transition-colors duration-200"
          >
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 ml-60 min-h-screen">
        <Outlet />
      </main>
    </div>
  );
}
