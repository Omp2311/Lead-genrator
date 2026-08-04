import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";
import {
  Inbox as InboxIcon,
  Plus,
  Loader2,
  Send,
  Trash2,
  Flame,
  Circle,
} from "lucide-react";

const EMPTY_FORM = {
  label: "",
  provider: "smtp",
  smtp_host: "",
  smtp_port: 587,
  smtp_user: "",
  smtp_password: "",
  resend_api_key: "",
  from_email: "",
  daily_cap: 30,
  warmup_enabled: true,
  is_active: true,
};

function InboxCard({ inbox, onChanged }) {
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [togglingActive, setTogglingActive] = useState(false);

  const test = async () => {
    setTesting(true);
    try {
      const r = await api.post(`/inboxes/${inbox.id}/test`);
      if (r.data.status === "sent" && !r.data.simulated) toast.success("Test email sent!");
      else if (r.data.status === "suppressed") toast.error("Your own address is on the suppression list.");
      else if (r.data.simulated) toast.info("Sending is simulated — check the inbox's credentials.");
      else toast.error(`Send failed: ${r.data.error || "unknown"}`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally {
      setTesting(false);
    }
  };

  const toggleActive = async () => {
    setTogglingActive(true);
    try {
      await api.put(`/inboxes/${inbox.id}`, { ...inbox, is_active: !inbox.is_active });
      onChanged();
    } catch (e) {
      toast.error("Could not update inbox.");
    } finally {
      setTogglingActive(false);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await api.delete(`/inboxes/${inbox.id}`);
      toast.success("Inbox removed.");
      onChanged();
    } catch (e) {
      toast.error("Could not remove inbox.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div
      data-testid={`inbox-card-${inbox.id}`}
      className="bg-[#18181B] border border-zinc-800 rounded-md p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <InboxIcon className="w-4 h-4 text-cyan-400" />
            <h3 className="font-display font-semibold">{inbox.label}</h3>
            <span className="text-[10px] uppercase tracking-wider bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded-sm">
              {inbox.provider}
            </span>
          </div>
          <p className="text-xs text-zinc-500 mt-1 font-mono">{inbox.from_email || "No from-address set"}</p>
        </div>
        <span
          className={`flex items-center gap-1 text-xs shrink-0 ${inbox.is_active ? "text-emerald-400" : "text-zinc-500"}`}
        >
          <Circle className={`w-2 h-2 ${inbox.is_active ? "fill-emerald-400 text-emerald-400" : "fill-zinc-600 text-zinc-600"}`} />
          {inbox.is_active ? "Active" : "Paused"}
        </span>
      </div>

      <div className="flex items-center gap-4 mt-4 text-xs text-zinc-400">
        <span>
          Sent today: <span className="text-zinc-200 font-mono">{inbox.sent_today || 0}</span> / {inbox.daily_cap}
        </span>
        {inbox.warmup_enabled && (
          <span className="flex items-center gap-1 text-amber-400/80">
            <Flame className="w-3.5 h-3.5" /> Warming up
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mt-4">
        <button
          onClick={test}
          disabled={testing}
          data-testid={`inbox-test-${inbox.id}`}
          className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-3 py-1.5 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
        >
          {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />} Send test
        </button>
        <button
          onClick={toggleActive}
          disabled={togglingActive}
          data-testid={`inbox-toggle-${inbox.id}`}
          className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-3 py-1.5 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
        >
          {inbox.is_active ? "Pause" : "Activate"}
        </button>
        <button
          onClick={remove}
          disabled={deleting}
          data-testid={`inbox-delete-${inbox.id}`}
          className="flex items-center gap-2 text-sm text-red-400 hover:bg-red-500/10 px-3 py-1.5 rounded-sm transition-colors disabled:opacity-60"
        >
          {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />} Remove
        </button>
      </div>
    </div>
  );
}

export default function Inboxes() {
  const [inboxes, setInboxes] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/inboxes").then((r) => setInboxes(r.data)).catch(() => setInboxes([]));

  useEffect(() => {
    load();
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const create = async () => {
    setSaving(true);
    try {
      await api.post("/inboxes", form);
      toast.success("Inbox added.");
      setForm(EMPTY_FORM);
      setShowForm(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Sending capacity</p>
          <h1 className="font-display text-4xl font-black tracking-tight">Inboxes</h1>
          <p className="text-zinc-400 text-sm mt-2">
            Add multiple sending accounts. The agent rotates across them and warms up new ones
            gradually to protect your deliverability.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          data-testid="add-inbox-button"
          className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-5 py-2.5 rounded-sm hover:bg-cyan-300 transition-colors"
        >
          <Plus className="w-4 h-4" /> Add inbox
        </button>
      </div>

      {showForm && (
        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 mb-6 space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Label</label>
              <input
                data-testid="inbox-label-input"
                value={form.label}
                onChange={(e) => set("label", e.target.value)}
                placeholder="e.g. Sales inbox #1"
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Provider</label>
              <select
                data-testid="inbox-provider-select"
                value={form.provider}
                onChange={(e) => set("provider", e.target.value)}
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              >
                <option value="smtp">SMTP</option>
                <option value="resend">Resend</option>
              </select>
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">From address</label>
              <input
                data-testid="inbox-from-email-input"
                value={form.from_email}
                onChange={(e) => set("from_email", e.target.value)}
                placeholder="you@yourdomain.com"
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Daily cap (once warmed up)</label>
              <input
                data-testid="inbox-daily-cap-input"
                type="number"
                value={form.daily_cap}
                onChange={(e) => set("daily_cap", parseInt(e.target.value || "0", 10))}
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          {form.provider === "smtp" ? (
            <div className="grid sm:grid-cols-2 gap-4 border-t border-zinc-800 pt-4">
              <div>
                <label className="text-xs uppercase tracking-wider text-zinc-500">SMTP host</label>
                <input
                  data-testid="inbox-smtp-host-input"
                  value={form.smtp_host}
                  onChange={(e) => set("smtp_host", e.target.value)}
                  placeholder="smtp.gmail.com"
                  className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-zinc-500">SMTP port</label>
                <input
                  data-testid="inbox-smtp-port-input"
                  type="number"
                  value={form.smtp_port}
                  onChange={(e) => set("smtp_port", parseInt(e.target.value || "0", 10))}
                  className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-zinc-500">SMTP username</label>
                <input
                  data-testid="inbox-smtp-user-input"
                  value={form.smtp_user}
                  onChange={(e) => set("smtp_user", e.target.value)}
                  className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-zinc-500">SMTP password / app password</label>
                <input
                  data-testid="inbox-smtp-password-input"
                  type="password"
                  value={form.smtp_password}
                  onChange={(e) => set("smtp_password", e.target.value)}
                  className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
                />
              </div>
            </div>
          ) : (
            <div className="border-t border-zinc-800 pt-4">
              <label className="text-xs uppercase tracking-wider text-zinc-500">Resend API key</label>
              <input
                data-testid="inbox-resend-key-input"
                type="password"
                value={form.resend_api_key}
                onChange={(e) => set("resend_api_key", e.target.value)}
                className="mt-1 w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              />
            </div>
          )}

          <div className="flex items-center justify-between border-t border-zinc-800 pt-4">
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input
                type="checkbox"
                data-testid="inbox-warmup-checkbox"
                checked={form.warmup_enabled}
                onChange={(e) => set("warmup_enabled", e.target.checked)}
                className="accent-cyan-400"
              />
              Ramp up sending gradually (recommended for new inboxes)
            </label>
            <button
              onClick={create}
              disabled={saving}
              data-testid="save-inbox-button"
              className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Add inbox
            </button>
          </div>
        </div>
      )}

      {inboxes === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading inboxes…</div>
      ) : inboxes.length === 0 ? (
        <div className="border border-dashed border-zinc-800 rounded-md p-16 text-center">
          <InboxIcon className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
          <p className="text-zinc-400">
            No inboxes configured yet. Without one, sending falls back to the single account set in
            the backend's environment.
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4">
          {inboxes.map((inbox) => (
            <InboxCard key={inbox.id} inbox={inbox} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
