import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Zap, Loader2, Save, Mail, Radar, MessageCircle, Send, Clock, Circle } from "lucide-react";

const TagInput = ({ label, values, onChange, testid }) => {
  const [text, setText] = useState("");
  const add = () => {
    const v = text.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setText("");
  };
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-zinc-500">{label}</label>
      <div className="mt-1 flex flex-wrap gap-2 mb-2">
        {values.map((v) => (
          <span key={v} className="flex items-center gap-1 bg-cyan-400/10 text-cyan-300 text-xs px-2 py-1 rounded-sm">
            {v}
            <button onClick={() => onChange(values.filter((x) => x !== v))} className="hover:text-white">×</button>
          </span>
        ))}
      </div>
      <input
        data-testid={testid}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
        placeholder="Type & press Enter"
        className="w-full bg-[#18181B] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
      />
    </div>
  );
};

export default function Automation() {
  const [s, setS] = useState(null);
  const [integ, setInteg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [testing, setTesting] = useState(false);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    api.get("/settings").then((r) => setS(r.data)).catch(() => {});
    api.get("/integrations/status").then((r) => setInteg(r.data)).catch(() => {});
  }, []);

  const sendTest = async () => {
    setTesting(true);
    try {
      const r = await api.post("/integrations/test-email");
      if (r.data.status === "sent" && !r.data.simulated)
        toast.success("Test email sent — check your inbox!");
      else if (r.data.simulated)
        toast.info("Email not configured — sending is simulated.");
      else toast.error(`Send failed: ${r.data.error || "unknown"}`);
    } catch (e) {
      toast.error("Test failed.");
    } finally {
      setTesting(false);
    }
  };

  const processFollowups = async () => {
    setProcessing(true);
    try {
      const r = await api.post("/followups/process");
      toast.success(`${r.data.sent} due follow-up(s) processed.`);
    } catch (e) {
      toast.error("Could not process follow-ups.");
    } finally {
      setProcessing(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const { user_id, last_run, ...payload } = s;
      const r = await api.put("/settings", payload);
      setS(r.data);
      toast.success("Automation settings saved.");
    } catch (e) {
      toast.error("Could not save settings.");
    } finally {
      setSaving(false);
    }
  };

  const runNow = async () => {
    setRunning(true);
    toast.info("Deploying agent with these settings…");
    try {
      const r = await api.post("/automation/run", {
        count: 8,
        offer: s.offer,
        tone: s.tone,
      });
      const mode = r.data.email_live && r.data.lead_source === "apollo" ? "delivered" : "drafted (demo)";
      toast.success(`${r.data.leads} leads · ${r.data.emails} emails ${mode}`);
    } catch (e) {
      toast.error("Run failed.");
    } finally {
      setRunning(false);
    }
  };

  if (!s) return <div className="p-8 text-zinc-500 font-mono text-sm">Loading settings…</div>;

  const set = (k, v) => setS({ ...s, [k]: v });

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Autopilot config</p>
        <h1 className="font-display text-4xl font-black tracking-tight">Automation</h1>
        <p className="text-zinc-400 text-sm mt-2">
          Define who to target and what to offer. The agent runs this daily — hands-free.
        </p>
      </div>

      <div className="space-y-4">
        {integ && (
          <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
            <h3 className="font-display font-semibold text-lg mb-4">Integrations</h3>
            <div className="grid sm:grid-cols-3 gap-3">
              {[
                { label: "Email · SMTP", live: integ.email_live, icon: Mail, hint: integ.sender_email || "Add SMTP creds" },
                { label: "Leads · Apollo", live: integ.leads_live, icon: Radar, hint: integ.leads_live ? "Real leads live" : "Add APOLLO_API_KEY" },
                { label: "WhatsApp · Twilio", live: integ.whatsapp_live, icon: MessageCircle, hint: integ.whatsapp_live ? "Auto-send live" : "Add Twilio creds" },
              ].map((it) => (
                <div key={it.label} className={`p-3 rounded-sm border ${it.live ? "border-emerald-500/30 bg-emerald-500/10" : "border-zinc-800 bg-[#0f0f11]"}`}>
                  <div className="flex items-center gap-2">
                    <it.icon className={`w-4 h-4 ${it.live ? "text-emerald-400" : "text-zinc-500"}`} />
                    <span className="text-sm font-medium">{it.label}</span>
                    <span className={`ml-auto flex items-center gap-1 text-xs ${it.live ? "text-emerald-400" : "text-zinc-500"}`}>
                      <Circle className={`w-2 h-2 ${it.live ? "fill-emerald-400 text-emerald-400" : "fill-zinc-600 text-zinc-600"}`} /> {it.live ? "LIVE" : "OFF"}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-500 mt-1.5 truncate">{it.hint}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-3 mt-4">
              <button
                data-testid="send-test-email-button"
                onClick={sendTest}
                disabled={testing}
                className="flex items-center gap-2 bg-zinc-800 text-white text-sm font-medium px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
              >
                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Send test email
              </button>
              <button
                data-testid="process-followups-button"
                onClick={processFollowups}
                disabled={processing}
                className="flex items-center gap-2 bg-zinc-800 text-white text-sm font-medium px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
              >
                {processing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Clock className="w-4 h-4" />}
                Process due follow-ups
              </button>
            </div>
            {!integ.leads_live && (
              <p className="text-xs text-amber-400/80 mt-3 leading-relaxed">
                Note: leads are AI-generated demo data until Apollo is connected. To protect your email
                reputation, real sending only fires for real (Apollo) leads — demo emails stay simulated.
              </p>
            )}
          </div>
        )}

        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 flex items-center justify-between">
          <div>
            <h3 className="font-display font-semibold text-lg">Daily autopilot</h3>
            <p className="text-sm text-zinc-400 mt-1">
              Auto-discover leads & send outreach every day without any manual action.
            </p>
          </div>
          <button
            data-testid="toggle-autopilot"
            onClick={() => set("auto_enabled", !s.auto_enabled)}
            className={`relative w-14 h-7 rounded-full transition-colors ${
              s.auto_enabled ? "bg-cyan-400" : "bg-zinc-700"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-6 h-6 bg-[#09090B] rounded-full transition-transform duration-200 ${
                s.auto_enabled ? "translate-x-7" : ""
              }`}
            />
          </button>
        </div>

        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 grid sm:grid-cols-2 gap-6">
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">Daily target (emails)</label>
            <input
              data-testid="daily-target-input"
              type="number"
              value={s.daily_target}
              onChange={(e) => set("daily_target", parseInt(e.target.value || "0", 10))}
              className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">Sender name</label>
            <input
              data-testid="sender-name-input"
              value={s.sender_name}
              onChange={(e) => set("sender_name", e.target.value)}
              className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
            />
          </div>
          <TagInput label="Target regions" values={s.regions} onChange={(v) => set("regions", v)} testid="regions-input" />
          <TagInput label="Target industries" values={s.industries} onChange={(v) => set("industries", v)} testid="industries-input" />
        </div>

        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 space-y-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">Your offer</label>
            <textarea
              data-testid="offer-input"
              value={s.offer}
              onChange={(e) => set("offer", e.target.value)}
              rows={2}
              className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors resize-none"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">Email tone</label>
            <input
              data-testid="tone-input"
              value={s.tone}
              onChange={(e) => set("tone", e.target.value)}
              className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            data-testid="save-settings-button"
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 bg-zinc-800 text-white font-medium px-5 py-2.5 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save settings
          </button>
          <button
            data-testid="automation-run-button"
            onClick={runNow}
            disabled={running}
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-5 py-2.5 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Test run now
          </button>
        </div>
      </div>
    </div>
  );
}
