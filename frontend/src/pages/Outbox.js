import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Send, Mail, Loader2, Pencil, Trash2, Zap, ShieldAlert, Mic } from "lucide-react";

const StatusBadge = ({ status }) => {
  const colors = {
    draft: "bg-cyan-500/10 text-cyan-300",
    sent: "bg-emerald-500/10 text-emerald-400",
    scheduled: "bg-amber-500/10 text-amber-400",
    failed: "bg-red-500/10 text-red-400",
    suppressed: "bg-amber-500/10 text-amber-400",
  };
  return (
    <span className={`text-xs uppercase tracking-wider px-2 py-1 rounded-sm ${colors[status] || "bg-zinc-700/50 text-zinc-400"}`}>
      {status}
    </span>
  );
};

function EmailCard({ e, onSend, onDelete, onEdit, sending, checkingSpam, generatingVoice, onCheckSpam, onGenerateVoice, spamResult, voiceNoteUrl }) {
  const canEdit = e.status === "draft" || e.status === "failed";

  return (
    <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 hover:border-zinc-700 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="font-display font-semibold text-lg">{e.subject}</h3>
            {e.industry && (
              <span className="text-xs px-2 py-1 rounded bg-cyan-500/10 text-cyan-300">{e.industry}</span>
            )}
          </div>
          <StatusBadge status={e.status} />
        </div>
      </div>

      {/* Lead Details Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 bg-[#0f0f11] p-4 rounded border border-zinc-800 mb-4">
        {e.contact_name && (
          <div>
            <p className="text-xs uppercase text-zinc-500">Contact</p>
            <p className="text-sm text-white">{e.contact_name}</p>
          </div>
        )}
        {e.company && (
          <div>
            <p className="text-xs uppercase text-zinc-500">Company</p>
            <p className="text-sm text-white">{e.company}</p>
          </div>
        )}
        {e.to_email && (
          <div>
            <p className="text-xs uppercase text-zinc-500">Email</p>
            <p className="text-xs text-zinc-300 font-mono">{e.to_email}</p>
          </div>
        )}
        {e.phone && (
          <div>
            <p className="text-xs uppercase text-zinc-500">Phone</p>
            <p className="text-sm text-white">{e.phone}</p>
          </div>
        )}
        {e.location && (
          <div>
            <p className="text-xs uppercase text-zinc-500">Location</p>
            <p className="text-sm text-white">{e.location}</p>
          </div>
        )}
        {e.lead_source && (
          <div>
            <p className="text-xs uppercase text-zinc-500">Source</p>
            <p className="text-sm text-white">{e.lead_source}</p>
          </div>
        )}
      </div>

      {/* Email Body */}
      <div className="bg-[#0f0f11] p-4 rounded border border-zinc-800 mb-4">
        <p className="text-xs uppercase text-zinc-500 mb-2">Email body</p>
        <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
          {e.body}
        </pre>
      </div>

      {/* Spam Check Result */}
      {spamResult && (
        <div className={`text-xs rounded p-3 mb-4 border ${
          spamResult.score >= 80 ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : spamResult.score >= 50 ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
            : "border-red-500/30 bg-red-500/10 text-red-300"
        }`}>
          <p className="font-semibold flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5" /> Deliverability: {spamResult.score}/100
          </p>
          {spamResult.flags && spamResult.flags.length > 0 && (
            <ul className="mt-2 list-disc list-inside text-[11px] opacity-90">
              {spamResult.flags.map((f) => <li key={f}>{f}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* Voice Note */}
      {voiceNoteUrl && (
        <div className="mb-4">
          <p className="text-xs uppercase text-zinc-500 mb-2">Voice note</p>
          <audio controls src={voiceNoteUrl} className="w-full h-8 rounded" />
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-2">
        {canEdit && (
          <>
            <button
              onClick={() => onSend(e)}
              disabled={sending}
              className="flex items-center gap-2 bg-cyan-400 text-[#09090B] text-sm font-semibold px-4 py-2 rounded hover:bg-cyan-300 transition-colors disabled:opacity-60"
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Send
            </button>
            <button
              onClick={() => onEdit(e)}
              className="flex items-center gap-2 bg-zinc-800 text-white text-sm px-4 py-2 rounded hover:bg-zinc-700 transition-colors"
            >
              <Pencil className="w-4 h-4" /> Edit
            </button>
            <button
              onClick={() => onDelete(e.id)}
              className="flex items-center gap-2 bg-red-500/10 text-red-400 text-sm px-4 py-2 rounded hover:bg-red-500/20 transition-colors"
            >
              <Trash2 className="w-4 h-4" /> Delete
            </button>
          </>
        )}
        <button
          onClick={() => onCheckSpam(e)}
          disabled={checkingSpam}
          className="flex items-center gap-2 bg-zinc-800 text-white text-sm px-4 py-2 rounded hover:bg-zinc-700 transition-colors disabled:opacity-60"
        >
          {checkingSpam ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4" />}
          {spamResult ? "Re-check" : "Check deliverability"}
        </button>
        <button
          onClick={() => onGenerateVoice(e)}
          disabled={generatingVoice}
          className="flex items-center gap-2 bg-zinc-800 text-white text-sm px-4 py-2 rounded hover:bg-zinc-700 transition-colors disabled:opacity-60"
        >
          {generatingVoice ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mic className="w-4 h-4" />}
          {voiceNoteUrl ? "Regenerate voice" : "Generate voice note"}
        </button>
      </div>
    </div>
  );
}

export default function Outbox() {
  const [emails, setEmails] = useState(null);
  const [filter, setFilter] = useState("draft");
  const [sending, setSending] = useState(null);
  const [sendingAll, setSendingAll] = useState(false);
  const [checkingSpam, setCheckingSpam] = useState({});
  const [generatingVoice, setGeneratingVoice] = useState({});
  const [spamResults, setSpamResults] = useState({});
  const [voiceNotes, setVoiceNotes] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [editData, setEditData] = useState({ to_email: "", subject: "", body: "" });

  const load = () => {
    api.get("/emails?channel=email").then((r) => setEmails(r.data)).catch(() => setEmails([]));
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = (emails || []).filter((e) => {
    if (filter === "draft") return e.status === "draft" || e.status === "failed";
    return e.status === filter;
  });

  const draftCount = (emails || []).filter((e) => e.status === "draft" || e.status === "failed").length;

  const handleSend = async (e) => {
    setSending(e.id);
    try {
      const r = await api.post(`/emails/${e.id}/send`);
      if (r.data.status === "sent") {
        toast.success(`Sent to ${e.to_email}`);
      } else {
        toast.error(`Failed: ${r.data.error || "unknown"}`);
      }
      load();
    } catch (err) {
      toast.error("Send failed");
    } finally {
      setSending(null);
    }
  };

  const handleSendAll = async () => {
    setSendingAll(true);
    try {
      const r = await api.post("/emails/send-all");
      toast.success(`${r.data.sent} sent · ${r.data.failed} failed`);
      load();
    } catch (e) {
      toast.error("Send all failed");
    } finally {
      setSendingAll(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this email?")) return;
    try {
      await api.delete(`/emails/${id}`);
      toast.success("Email deleted");
      load();
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  const handleEdit = (e) => {
    setEditingId(e.id);
    setEditData({ to_email: e.to_email, subject: e.subject, body: e.body });
  };

  const handleSaveEdit = async () => {
    try {
      await api.put(`/emails/${editingId}`, editData);
      toast.success("Email updated");
      setEditingId(null);
      load();
    } catch (e) {
      toast.error("Save failed");
    }
  };

  const handleCheckSpam = async (e) => {
    setCheckingSpam({ ...checkingSpam, [e.id]: true });
    try {
      const r = await api.post("/emails/spam-check", { subject: e.subject, body: e.body });
      setSpamResults({ ...spamResults, [e.id]: r.data });
      toast.success("Deliverability checked");
    } catch (err) {
      toast.error("Could not check deliverability");
    } finally {
      setCheckingSpam({ ...checkingSpam, [e.id]: false });
    }
  };

  const handleGenerateVoice = async (e) => {
    setGeneratingVoice({ ...generatingVoice, [e.id]: true });
    try {
      const r = await api.post(`/emails/${e.id}/voice-note`);
      setVoiceNotes({ ...voiceNotes, [e.id]: r.data.voice_note_url });
      toast.success("Voice note ready");
    } catch (err) {
      toast.error("Voice note generation failed");
    } finally {
      setGeneratingVoice({ ...generatingVoice, [e.id]: false });
    }
  };

  return (
    <div className="p-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Dispatch</p>
          <h1 className="font-display text-4xl font-black tracking-tight">Outbox</h1>
          <p className="text-zinc-400 text-sm mt-2">Review and send AI-drafted emails</p>
        </div>
        {draftCount > 0 && (
          <button
            onClick={handleSendAll}
            disabled={sendingAll}
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-5 py-3 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {sendingAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Send all ({draftCount})
          </button>
        )}
      </div>

      {/* Status Filter */}
      <div className="flex gap-2 mb-6">
        {[
          { k: "draft", label: "Draft" },
          { k: "scheduled", label: "Scheduled" },
          { k: "sent", label: "Sent" },
          { k: "failed", label: "Failed" },
        ].map((f) => (
          <button
            key={f.k}
            onClick={() => setFilter(f.k)}
            className={`px-4 py-2 rounded-sm text-sm font-medium transition-colors ${
              filter === f.k ? "bg-cyan-400 text-[#09090B]" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Edit Modal */}
      {editingId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <h2 className="font-display text-xl font-bold mb-4">Edit Email</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase text-zinc-500">To</label>
                <input
                  value={editData.to_email}
                  onChange={(e) => setEditData({ ...editData, to_email: e.target.value })}
                  className="w-full mt-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-zinc-500">Subject</label>
                <input
                  value={editData.subject}
                  onChange={(e) => setEditData({ ...editData, subject: e.target.value })}
                  className="w-full mt-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs uppercase text-zinc-500">Body</label>
                <textarea
                  value={editData.body}
                  onChange={(e) => setEditData({ ...editData, body: e.target.value })}
                  rows={8}
                  className="w-full mt-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none resize-none"
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={handleSaveEdit}
                className="flex-1 bg-cyan-400 text-[#09090B] font-semibold py-2 rounded-sm hover:bg-cyan-300 transition-colors"
              >
                Save
              </button>
              <button
                onClick={() => setEditingId(null)}
                className="flex-1 bg-zinc-800 text-white py-2 rounded-sm hover:bg-zinc-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Email Cards */}
      {emails === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="border border-dashed border-zinc-800 rounded-md p-12 text-center">
          <Mail className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
          <p className="text-zinc-400">No {filter} emails</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((e) => (
            <EmailCard
              key={e.id}
              e={e}
              onSend={handleSend}
              onDelete={handleDelete}
              onEdit={handleEdit}
              sending={sending === e.id}
              checkingSpam={checkingSpam[e.id]}
              generatingVoice={generatingVoice[e.id]}
              onCheckSpam={handleCheckSpam}
              onGenerateVoice={handleGenerateVoice}
              spamResult={spamResults[e.id]}
              voiceNoteUrl={voiceNotes[e.id]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
