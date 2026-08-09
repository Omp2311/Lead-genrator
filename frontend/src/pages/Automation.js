import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";
import { Zap, Loader2, Save, Mail, Radar, MessageCircle, Send, Clock, Circle, Inbox, BellOff, Plus, X, GitBranch, ArrowRight } from "lucide-react";

function SequencePanel() {
  const [steps, setSteps] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/sequence").then((r) => setSteps(r.data.map((s) => ({ delay_days: s.delay_days, angle: s.angle })))).catch(() => setSteps([]));

  useEffect(() => {
    load();
  }, []);

  const update = (i, k, v) => setSteps((prev) => prev.map((s, idx) => (idx === i ? { ...s, [k]: v } : s)));
  const remove = (i) => setSteps((prev) => prev.filter((_, idx) => idx !== i));
  const add = () => setSteps((prev) => [...prev, { delay_days: (prev[prev.length - 1]?.delay_days || 0) + 3, angle: "" }]);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put("/sequence", steps);
      setSteps(r.data.map((s) => ({ delay_days: s.delay_days, angle: s.angle })));
      toast.success("Sequence saved — future runs will follow these steps.");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not save sequence.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
      <h3 className="font-display font-semibold text-lg mb-1 flex items-center gap-2">
        <GitBranch className="w-4 h-4 text-cyan-400" /> Follow-up sequence
      </h3>
      <p className="text-sm text-zinc-400 mb-4">
        Define how many follow-ups to send, how many days apart, and the strategic angle for each —
        the AI writes the copy per lead, matching your angle.
      </p>
      {steps === null ? (
        <p className="text-xs text-zinc-500 font-mono">Loading…</p>
      ) : (
        <div className="space-y-3">
          {steps.map((s, i) => (
            <div key={i} data-testid={`sequence-step-${i}`} className="flex items-start gap-3 bg-[#0f0f11] border border-zinc-800/80 rounded-sm p-3">
              <span className="text-xs font-mono text-cyan-400 mt-2 shrink-0 flex items-center gap-1">
                <ArrowRight className="w-3.5 h-3.5" /> #{i + 1}
              </span>
              <div className="shrink-0">
                <label className="text-[10px] uppercase tracking-wider text-zinc-500">Days after previous</label>
                <input
                  type="number"
                  min={1}
                  data-testid={`sequence-delay-${i}`}
                  value={s.delay_days}
                  onChange={(e) => update(i, "delay_days", parseInt(e.target.value || "1", 10))}
                  className="mt-1 w-20 bg-[#18181B] border border-zinc-800 rounded-sm px-2 py-1.5 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] uppercase tracking-wider text-zinc-500">Angle / strategy for this step</label>
                <input
                  data-testid={`sequence-angle-${i}`}
                  value={s.angle}
                  onChange={(e) => update(i, "angle", e.target.value)}
                  placeholder="e.g. Share a relevant case study, <=70 words"
                  className="mt-1 w-full bg-[#18181B] border border-zinc-800 rounded-sm px-3 py-1.5 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                />
              </div>
              <button onClick={() => remove(i)} data-testid={`sequence-remove-${i}`} className="text-zinc-500 hover:text-red-400 mt-6">
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={add}
              disabled={steps.length >= 10}
              data-testid="sequence-add-step-button"
              className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-3 py-1.5 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
            >
              <Plus className="w-3.5 h-3.5" /> Add step
            </button>
            <button
              onClick={save}
              disabled={saving}
              data-testid="sequence-save-button"
              className="flex items-center gap-2 text-sm bg-cyan-400 text-[#09090B] font-semibold px-3 py-1.5 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save sequence
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SuppressionPanel() {
  const [list, setList] = useState(null);
  const [email, setEmail] = useState("");
  const [adding, setAdding] = useState(false);

  const load = () => api.get("/suppressions").then((r) => setList(r.data)).catch(() => setList([]));

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    const v = email.trim();
    if (!v) return;
    setAdding(true);
    try {
      await api.post("/suppressions", { email: v, reason: "manual" });
      setEmail("");
      toast.success(`${v} added to suppression list.`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not add.");
    } finally {
      setAdding(false);
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/suppressions/${id}`);
      setList((prev) => prev.filter((s) => s.id !== id));
    } catch (e) {
      toast.error("Could not remove.");
    }
  };

  return (
    <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
      <h3 className="font-display font-semibold text-lg mb-1 flex items-center gap-2">
        <BellOff className="w-4 h-4 text-amber-400" /> Suppression list
      </h3>
      <p className="text-sm text-zinc-400 mb-4">
        Addresses here never receive outreach — recipients land here automatically when they click
        "unsubscribe", or add them manually below.
      </p>
      <div className="flex gap-2 mb-4">
        <input
          data-testid="suppression-email-input"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="someone@company.com"
          className="flex-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
        />
        <button
          onClick={add}
          disabled={adding}
          data-testid="suppression-add-button"
          className="flex items-center gap-2 bg-zinc-800 text-white text-sm font-medium px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
        >
          {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
        </button>
      </div>
      {list === null ? (
        <p className="text-xs text-zinc-500 font-mono">Loading…</p>
      ) : list.length === 0 ? (
        <p className="text-xs text-zinc-500">No suppressed addresses.</p>
      ) : (
        <div className="space-y-1.5">
          {list.map((s) => (
            <div key={s.id} data-testid={`suppression-row-${s.id}`} className="flex items-center justify-between text-xs bg-[#0f0f11] border border-zinc-800/80 rounded-sm px-3 py-2">
              <span className="font-mono text-zinc-300">{s.email}</span>
              <div className="flex items-center gap-3">
                <span className="text-zinc-500">{s.reason}</span>
                <button onClick={() => remove(s.id)} data-testid={`suppression-remove-${s.id}`} className="text-zinc-500 hover:text-red-400">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

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
  const [scanning, setScanning] = useState(false);

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

  const scanReplies = async () => {
    setScanning(true);
    toast.info("Reading inbox for replies…");
    try {
      const r = await api.post("/replies/scan");
      if (r.data.error) toast.error(`Scan failed: ${r.data.error}`);
      else toast.success(`${r.data.matched} reply(ies) detected — follow-ups auto-stopped.`);
    } catch (e) {
      toast.error("Could not scan inbox.");
    } finally {
      setScanning(false);
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
      const mode = r.data.email_live ? "delivered" : "drafted";
      toast.success(`${r.data.leads} leads · ${r.data.emails} emails ${mode}`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Run failed.");
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
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { label: "Email · SMTP", live: integ.email_live, icon: Mail, hint: integ.sender_email || "Add SMTP creds" },
                { label: "Leads · Apollo", live: integ.leads_live, icon: Radar, hint: integ.leads_live ? "Real leads live" : (integ.leads_blocked ? "Apollo Free plan — upgrade to enable API" : "Add APOLLO_API_KEY") },
                { label: "Leads · Places+Hunter", live: integ.places_hunter_live, icon: Radar, hint: integ.places_hunter_live ? "Real leads live" : (integ.places_hunter_blocked ? "Check Google Places billing" : "Add GOOGLE_PLACES_API_KEY") },
                { label: "Leads · Foursquare+Hunter", live: integ.foursquare_hunter_live, icon: Radar, hint: integ.foursquare_hunter_live ? "Real leads live — no billing needed" : (integ.foursquare_hunter_blocked ? "Check Foursquare API key" : "Add FOURSQUARE_API_KEY") },
                { label: "Leads · GitHub", live: integ.github_live, icon: Radar, hint: integ.github_live ? "Real leads live — tech companies" : (integ.github_blocked ? "Check GitHub token" : "Add GITHUB_API_KEY") },
                { label: "Leads · OSM+Hunter (free)", live: integ.osm_hunter_live, icon: Radar, hint: integ.osm_hunter_live ? "Real leads live — no billing needed" : "Add HUNTER_API_KEY" },
                { label: "WhatsApp · Twilio", live: integ.whatsapp_live, icon: MessageCircle, hint: integ.whatsapp_live ? "Auto-send live" : "Add Twilio creds" },
                { label: "Replies · IMAP", live: integ.reply_detection_live, icon: Inbox, hint: integ.reply_detection_live ? "Auto-stops follow-ups on reply" : "Uses your email login" },
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
              <button
                data-testid="scan-replies-button"
                onClick={scanReplies}
                disabled={scanning}
                className="flex items-center gap-2 bg-zinc-800 text-white text-sm font-medium px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
              >
                {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Inbox className="w-4 h-4" />}
                Scan inbox for replies
              </button>
            </div>
            {!integ.leads_live && !integ.places_hunter_live && !integ.foursquare_hunter_live &&
             !integ.github_live && !integ.osm_hunter_live && (
              <p className="text-xs text-amber-400/80 mt-3 leading-relaxed">
                Note: no real lead source is connected yet, so "Run outreach now" will error until you
                connect Apollo, Google Places + Hunter, Foursquare + Hunter, GitHub, or just a free
                Hunter.io key alone (OpenStreetMap sourcing needs no billing), or import a CSV of real
                contacts instead.
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

        <SequencePanel />

        <SuppressionPanel />

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
