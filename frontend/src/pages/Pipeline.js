import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { GitBranch, Building2, Phone, MessageSquare, Save } from "lucide-react";

const STAGES = [
  { key: "new", label: "New" },
  { key: "contacted", label: "Contacted" },
  { key: "replied", label: "Replied" },
  { key: "meeting", label: "Meeting" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
];

const INTENT_STYLE = {
  interested: "bg-emerald-500/10 text-emerald-400",
  not_interested: "bg-red-500/10 text-red-400",
  referral: "bg-cyan-500/10 text-cyan-300",
  out_of_office: "bg-zinc-700/40 text-zinc-400",
  question: "bg-amber-500/10 text-amber-400",
};

function LeadCard({ lead, onDragStart, onSaved }) {
  const [notes, setNotes] = useState(lead.notes || "");
  const [saving, setSaving] = useState(false);
  const dirty = notes !== (lead.notes || "");

  const saveNotes = async () => {
    setSaving(true);
    try {
      await api.put(`/leads/${lead.id}`, { notes });
      onSaved();
    } catch (e) {
      toast.error("Could not save notes.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, lead.id)}
      data-testid={`pipeline-card-${lead.id}`}
      className="bg-[#18181B] border border-zinc-800 rounded-md p-3 cursor-grab active:cursor-grabbing hover:border-cyan-500/40 transition-colors"
    >
      <p className="font-display font-semibold text-sm truncate">{lead.contact_name || "—"}</p>
      <p className="text-xs text-zinc-500 flex items-center gap-1.5 mt-0.5 truncate">
        <Building2 className="w-3 h-3 shrink-0" /> {lead.company}
      </p>
      {lead.phone && (
        <p className="text-xs text-zinc-500 flex items-center gap-1.5 mt-0.5 font-mono truncate">
          <Phone className="w-3 h-3 shrink-0" /> {lead.phone}
        </p>
      )}
      {lead.reply_intent && lead.reply_intent !== "unknown" && (
        <span className={`inline-block mt-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm ${INTENT_STYLE[lead.reply_intent] || "bg-zinc-700/40 text-zinc-400"}`}>
          {lead.reply_intent.replace("_", " ")}
        </span>
      )}
      <div className="mt-2 flex items-start gap-1.5">
        <MessageSquare className="w-3 h-3 text-zinc-600 mt-1.5 shrink-0" />
        <textarea
          data-testid={`pipeline-notes-${lead.id}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes…"
          rows={2}
          className="flex-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-2 py-1 text-xs resize-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
        />
      </div>
      {dirty && (
        <button
          onClick={saveNotes}
          disabled={saving}
          data-testid={`pipeline-save-notes-${lead.id}`}
          className="mt-1.5 flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300"
        >
          <Save className="w-3 h-3" /> Save note
        </button>
      )}
    </div>
  );
}

export default function Pipeline() {
  const [leads, setLeads] = useState(null);

  const load = () => api.get("/leads").then((r) => setLeads(r.data)).catch(() => setLeads([]));

  useEffect(() => {
    load();
  }, []);

  const onDragStart = (e, leadId) => {
    e.dataTransfer.setData("text/lead-id", leadId);
  };

  const onDrop = async (e, stage) => {
    e.preventDefault();
    const leadId = e.dataTransfer.getData("text/lead-id");
    if (!leadId) return;
    const current = leads.find((l) => l.id === leadId);
    if (!current || current.stage === stage) return;
    setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, stage } : l)));
    try {
      await api.put(`/leads/${leadId}`, { stage });
    } catch (err) {
      toast.error("Could not move lead — reverting.");
      setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, stage: current.stage } : l)));
    }
  };

  return (
    <div className="p-8 max-w-[1600px]">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5" /> Deal flow
        </p>
        <h1 className="font-display text-4xl font-black tracking-tight">Pipeline</h1>
        <p className="text-zinc-400 text-sm mt-2">
          Drag leads across stages as deals progress. The agent auto-advances New → Contacted →
          Replied — you take it from there.
        </p>
      </div>

      {leads === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading pipeline…</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {STAGES.map((stage) => {
            const stageLeads = leads.filter((l) => l.stage === stage.key);
            return (
              <div
                key={stage.key}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => onDrop(e, stage.key)}
                data-testid={`pipeline-column-${stage.key}`}
                className="bg-[#0f0f11] border border-zinc-800/80 rounded-md p-3 min-h-[200px]"
              >
                <div className="flex items-center justify-between mb-3 px-1">
                  <h3 className="text-xs uppercase tracking-wider text-zinc-400 font-semibold">{stage.label}</h3>
                  <span className="text-xs font-mono text-zinc-500">{stageLeads.length}</span>
                </div>
                <div className="space-y-2">
                  {stageLeads.map((lead) => (
                    <LeadCard key={lead.id} lead={lead} onDragStart={onDragStart} onSaved={load} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
