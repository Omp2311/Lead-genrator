import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { Users, Send, MessageCircle, Phone, Zap, Loader2, TrendingUp } from "lucide-react";

const StatCard = ({ label, value, sub, icon: Icon, accent, testid }) => (
  <div
    data-testid={testid}
    className="relative bg-[#18181B] border border-zinc-800 rounded-md p-5 hover:border-zinc-700 hover:-translate-y-px transition-all duration-200 overflow-hidden"
  >
    {accent && (
      <div className="absolute -top-8 -right-8 w-24 h-24 bg-cyan-500/10 blur-2xl rounded-full" />
    )}
    <div className="flex items-center justify-between mb-3">
      <span className="text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</span>
      <Icon className={`w-4 h-4 ${accent ? "text-cyan-400" : "text-zinc-500"}`} />
    </div>
    <div className="font-display text-3xl font-black tracking-tight">{value}</div>
    {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
  </div>
);

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [running, setRunning] = useState(false);

  const load = async () => {
    try {
      const res = await api.get("/dashboard/stats");
      setStats(res.data);
    } catch (e) {}
  };

  useEffect(() => {
    load();
  }, []);

  const runNow = async () => {
    setRunning(true);
    toast.info("Agent deployed — discovering leads & drafting emails…");
    try {
      const res = await api.post("/automation/run", { count: 8 });
      toast.success(`${res.data.leads} leads found · ${res.data.emails} emails sent`);
      await load();
    } catch (e) {
      toast.error("Run failed. Check your LLM key balance and try again.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-8 max-w-7xl">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 op-live-dot inline-block" />
            System online
          </p>
          <h1 className="font-display text-4xl font-black tracking-tight">Command Center</h1>
          <p className="text-zinc-400 text-sm mt-2">
            Your autonomous outreach agent — pipeline running on autopilot.
          </p>
        </div>
        <button
          data-testid="run-now-button"
          onClick={runNow}
          disabled={running}
          className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-5 py-3 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          {running ? "Agent working…" : "Run outreach now"}
        </button>
      </div>

      {!stats ? (
        <div className="text-zinc-500 font-mono text-sm">Loading telemetry…</div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCard testid="stat-emails-sent" label="Emails sent" value={stats.emails_sent} sub="Cold emails dispatched" icon={Send} accent />
            <StatCard testid="stat-leads" label="Leads found" value={stats.total_leads} sub="Decision makers discovered" icon={Users} />
            <StatCard testid="stat-whatsapp" label="WhatsApp proposals" value={stats.whatsapp_ready} sub="Ready to fire" icon={MessageCircle} />
            <StatCard testid="stat-phone" label="With phone" value={stats.leads_with_phone} sub="Direct contact available" icon={Phone} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-[#18181B] border border-zinc-800 rounded-md p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-display text-lg font-semibold flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-cyan-400" /> Email volume · 7 days
                </h3>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={stats.volume} margin={{ left: -20, right: 8 }}>
                  <defs>
                    <linearGradient id="cyanFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00F0FF" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#00F0FF" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
                  <XAxis dataKey="day" stroke="#71717A" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="#71717A" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: "#09090B", border: "1px solid #27272A", borderRadius: 4, fontSize: 12 }}
                    labelStyle={{ color: "#a1a1aa" }}
                  />
                  <Area type="monotone" dataKey="emails" stroke="#00F0FF" strokeWidth={2} fill="url(#cyanFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 flex flex-col">
              <h3 className="font-display text-lg font-semibold mb-4">Daily autopilot</h3>
              <div className="flex items-baseline gap-2">
                <span className="font-display text-5xl font-black text-cyan-400">
                  {stats.daily_target}
                </span>
                <span className="text-zinc-500 text-sm">/ day target</span>
              </div>
              <p className="text-sm text-zinc-400 mt-3 leading-relaxed">
                {stats.auto_enabled
                  ? "Autopilot is ON. The agent discovers leads, writes personalized emails and queues WhatsApp proposals every day — automatically."
                  : "Autopilot is currently OFF. Turn it on in Automation to run hands-free daily."}
              </p>
              <div className="mt-auto pt-4">
                <span
                  className={`inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-sm ${
                    stats.auto_enabled
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-zinc-700/40 text-zinc-400"
                  }`}
                  data-testid="autopilot-status"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${stats.auto_enabled ? "bg-emerald-400 op-live-dot" : "bg-zinc-500"}`} />
                  {stats.auto_enabled ? "AUTOPILOT ACTIVE" : "AUTOPILOT PAUSED"}
                </span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
