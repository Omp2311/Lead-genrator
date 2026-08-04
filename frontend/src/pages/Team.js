import { useEffect, useState } from "react";
import api from "@/lib/api";
import { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Users, Plus, Trash2, Loader2, Crown } from "lucide-react";

const EMPTY_FORM = { name: "", email: "", password: "" };

export default function Team() {
  const { user } = useAuth();
  const isOwner = !user?.owner_id;
  const [members, setMembers] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/team/members").then((r) => setMembers(r.data)).catch(() => setMembers([]));

  useEffect(() => {
    load();
  }, []);

  const invite = async () => {
    setSaving(true);
    try {
      await api.post("/team/members", form);
      toast.success(`${form.name} added — share their login with them.`);
      setForm(EMPTY_FORM);
      setShowForm(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not add teammate.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/team/members/${id}`);
      toast.success("Removed.");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not remove.");
    }
  };

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
            <Users className="w-3.5 h-3.5" /> Workspace access
          </p>
          <h1 className="font-display text-4xl font-black tracking-tight">Team</h1>
          <p className="text-zinc-400 text-sm mt-2">
            Teammates share this entire workspace — same leads, emails, settings, and pipeline.
          </p>
        </div>
        {isOwner && (
          <button
            onClick={() => setShowForm((v) => !v)}
            data-testid="add-teammate-button"
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-5 py-2.5 rounded-sm hover:bg-cyan-300 transition-colors"
          >
            <Plus className="w-4 h-4" /> Add teammate
          </button>
        )}
      </div>

      {!isOwner && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-md p-4 mb-6 text-sm text-amber-300">
          Only the workspace owner can add or remove teammates.
        </div>
      )}

      {showForm && (
        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 mb-6 space-y-4">
          <p className="text-xs text-zinc-500">
            This creates a login for them directly — share the email/password you set here so they can sign in.
          </p>
          <div className="grid sm:grid-cols-2 gap-4">
            <input
              data-testid="teammate-name-input"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Name"
              className="bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            />
            <input
              data-testid="teammate-email-input"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="Email"
              className="bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
            />
            <input
              data-testid="teammate-password-input"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="Temporary password"
              className="bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none sm:col-span-2"
            />
          </div>
          <button
            onClick={invite}
            disabled={saving}
            data-testid="save-teammate-button"
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Add
          </button>
        </div>
      )}

      {members === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading team…</div>
      ) : (
        <div className="space-y-2">
          {members.map((m) => (
            <div
              key={m.id}
              data-testid={`team-member-${m.id}`}
              className="flex items-center justify-between bg-[#18181B] border border-zinc-800 rounded-md p-4"
            >
              <div>
                <p className="text-sm font-medium flex items-center gap-2">
                  {m.name}
                  {m.is_owner && (
                    <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider bg-amber-500/10 text-amber-400 px-1.5 py-0.5 rounded-sm">
                      <Crown className="w-3 h-3" /> Owner
                    </span>
                  )}
                </p>
                <p className="text-xs text-zinc-500 font-mono">{m.email}</p>
              </div>
              {isOwner && !m.is_owner && (
                <button
                  onClick={() => remove(m.id)}
                  data-testid={`remove-teammate-${m.id}`}
                  className="text-zinc-500 hover:text-red-400 p-2"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
