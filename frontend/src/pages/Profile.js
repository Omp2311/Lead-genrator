import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Save, User, Sparkles, Briefcase } from "lucide-react";

const TagInput = ({ label, values, onChange, testid, placeholder }) => {
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
        placeholder={placeholder || "Type & press Enter"}
        className="w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
      />
    </div>
  );
};

export default function Profile() {
  const [s, setS] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/settings").then((r) => setS(r.data)).catch(() => {});
  }, []);

  const set = (k, v) => setS({ ...s, [k]: v });

  const save = async () => {
    setSaving(true);
    try {
      const { user_id, last_run, ...payload } = s;
      const r = await api.put("/settings", payload);
      setS(r.data);
      toast.success("Profile saved — the agent will tailor leads & pitches to your skills.");
    } catch (e) {
      toast.error("Could not save profile.");
    } finally {
      setSaving(false);
    }
  };

  if (!s) return <div className="p-8 text-zinc-500 font-mono text-sm">Loading profile…</div>;

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Your seller identity</p>
        <h1 className="font-display text-4xl font-black tracking-tight">Profile & Skills</h1>
        <p className="text-zinc-400 text-sm mt-2">
          The agent uses this to find clients who need <span className="text-cyan-400">your</span> skills and
          to pitch tailored project ideas in every email.
        </p>
      </div>

      <div className="space-y-4">
        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
          <h3 className="font-display font-semibold text-lg flex items-center gap-2 mb-4">
            <User className="w-4 h-4 text-cyan-400" /> Identity
          </h3>
          <div className="grid sm:grid-cols-2 gap-5">
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Your name (email sender)</label>
              <input
                data-testid="profile-name-input"
                value={s.sender_name}
                onChange={(e) => set("sender_name", e.target.value)}
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Email tone</label>
              <input
                data-testid="profile-tone-input"
                value={s.tone}
                onChange={(e) => set("tone", e.target.value)}
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs uppercase tracking-wider text-zinc-500">Headline / positioning</label>
              <input
                data-testid="profile-headline-input"
                value={s.headline || ""}
                onChange={(e) => set("headline", e.target.value)}
                placeholder="e.g. Full-stack & GenAI engineer for growing SaaS companies"
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs uppercase tracking-wider text-zinc-500">Experience</label>
              <textarea
                data-testid="profile-experience-input"
                value={s.experience || ""}
                onChange={(e) => set("experience", e.target.value)}
                rows={2}
                placeholder="e.g. 5+ years shipping full-stack and AI products for startups"
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors resize-none"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs uppercase tracking-wider text-zinc-500">Meeting booking link (optional)</label>
              <input
                data-testid="profile-meeting-link-input"
                value={s.meeting_link || ""}
                onChange={(e) => set("meeting_link", e.target.value)}
                placeholder="e.g. https://cal.com/you/15min"
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
              />
              <p className="text-xs text-zinc-500 mt-1">If set, the AI may offer it as a direct way to book time instead of proposing a call.</p>
            </div>
          </div>
        </div>

        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 space-y-5">
          <h3 className="font-display font-semibold text-lg flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" /> Skills & offer
          </h3>
          <TagInput label="Your skills" values={s.skills || []} onChange={(v) => set("skills", v)} testid="profile-skills-input" placeholder="e.g. Python, React, GenAI — Enter to add" />
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">What you offer / sell</label>
            <textarea
              data-testid="profile-offer-input"
              value={s.offer}
              onChange={(e) => set("offer", e.target.value)}
              rows={2}
              className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors resize-none"
            />
          </div>
        </div>

        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 space-y-5">
          <h3 className="font-display font-semibold text-lg flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-cyan-400" /> Ideal client targeting
          </h3>
          <TagInput label="Target regions" values={s.regions || []} onChange={(v) => set("regions", v)} testid="profile-regions-input" />
          <TagInput label="Target industries" values={s.industries || []} onChange={(v) => set("industries", v)} testid="profile-industries-input" />
        </div>

        <button
          data-testid="profile-save-button"
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-6 py-3 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save profile
        </button>
      </div>
    </div>
  );
}
