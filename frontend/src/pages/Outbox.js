import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Send, MessageCircle, ExternalLink, Mail, Loader2, Pencil, Check, Zap, MailOpen, MousePointerClick, BellOff, ShieldAlert, Mic } from "lucide-react";

const StatusBadge = ({ status, simulated }) => (
  <div className="flex items-center gap-1.5 shrink-0">
    {simulated && status === "sent" && (
      <span className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm bg-zinc-700/50 text-zinc-400">simulated</span>
    )}
    <span
      className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm ${
        status === "sent" ? "bg-emerald-500/10 text-emerald-400"
          : status === "scheduled" ? "bg-amber-500/10 text-amber-400"
          : status === "failed" ? "bg-red-500/10 text-red-400"
          : status === "cancelled" ? "bg-zinc-700/40 text-zinc-500"
          : status === "draft" ? "bg-cyan-500/10 text-cyan-300"
          : status === "suppressed" ? "bg-amber-500/10 text-amber-400"
          : "bg-amber-500/10 text-amber-400"
      }`}
    >
      {status}
    </span>
  </div>
);

const EngagementBadges = ({ e }) => {
  if (e.status !== "sent") return null;
  return (
    <div className="flex items-center gap-3 mt-2 text-xs">
      <span className={`flex items-center gap-1 ${e.open_count > 0 ? "text-cyan-400" : "text-zinc-600"}`}>
        <MailOpen className="w-3.5 h-3.5" /> {e.open_count > 0 ? `Opened${e.open_count > 1 ? ` ×${e.open_count}` : ""}` : "Not opened"}
      </span>
      {e.click_count > 0 && (
        <span className="flex items-center gap-1 text-emerald-400">
          <MousePointerClick className="w-3.5 h-3.5" /> Clicked ×{e.click_count}
        </span>
      )}
    </div>
  );
};

function EmailRow({ e, index, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [to, setTo] = useState(e.to_email || "");
  const [subject, setSubject] = useState(e.subject || "");
  const [body, setBody] = useState(e.body || "");
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checkingSpam, setCheckingSpam] = useState(false);
  // Seed with the score already computed at draft-creation time, if any — the user still sees
  // it without clicking anything, and the manual "Check" button below lets them re-check after
  // editing the draft.
  const [spamResult, setSpamResult] = useState(
    e.spam_score != null ? { score: e.spam_score, flags: e.spam_flags || [] } : null
  );
  const [generatingVoice, setGeneratingVoice] = useState(false);
  const [voiceNoteUrl, setVoiceNoteUrl] = useState(e.voice_note_url || null);

  const canEdit = e.status === "draft" || e.status === "failed";
  const stepLabel = e.type === "follow_up" ? `Follow-up ${e.step - 1}`
    : e.type === "reply_draft" ? "Suggested reply" : "Initial";

  const checkSpam = async () => {
    setCheckingSpam(true);
    try {
      const r = await api.post("/emails/spam-check", { subject, body });
      setSpamResult(r.data);
    } catch (err) {
      toast.error("Could not check deliverability.");
    } finally {
      setCheckingSpam(false);
    }
  };

  const generateVoiceNote = async () => {
    setGeneratingVoice(true);
    try {
      const r = await api.post(`/emails/${e.id}/voice-note`);
      setVoiceNoteUrl(r.data.voice_note_url);
      toast.success("Voice note ready.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Voice note generation failed.");
    } finally {
      setGeneratingVoice(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/emails/${e.id}`, { to_email: to, subject, body });
      toast.success("Draft updated.");
      setEditing(false);
      onChanged();
    } catch (err) {
      toast.error("Could not save draft.");
    } finally {
      setSaving(false);
    }
  };

  const send = async () => {
    setSending(true);
    try {
      const r = await api.post(`/emails/${e.id}/send`);
      if (r.data.status === "sent") toast.success(`Sent to ${to}`);
      else toast.error(`Failed: ${r.data.error || "unknown"}`);
      onChanged();
    } catch (err) {
      toast.error("Send failed.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      data-testid={`outbox-item-${index}`}
      className="op-fade-up bg-[#18181B] border border-zinc-800 rounded-md p-5 hover:border-zinc-700 transition-colors"
      style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] uppercase tracking-wider bg-cyan-400/10 text-cyan-300 px-1.5 py-0.5 rounded-sm">{stepLabel}</span>
            <p className="font-display font-semibold truncate">{e.subject}</p>
          </div>
          <p className="text-xs text-zinc-500 mt-0.5">
            To {e.contact_name} · {e.company} · <span className="font-mono">{e.to_email}</span>
            {e.status === "scheduled" && e.scheduled_for && (
              <span className="text-amber-400/80"> · scheduled {new Date(e.scheduled_for).toLocaleDateString()}</span>
            )}
          </p>
        </div>
        <StatusBadge status={e.status} simulated={e.simulated} />
      </div>

      {editing ? (
        <div className="mt-3 space-y-2 border-t border-zinc-800 pt-3">
          <input
            data-testid={`edit-to-${index}`}
            value={to}
            onChange={(ev) => setTo(ev.target.value)}
            placeholder="Recipient email"
            className="w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
          />
          <input
            data-testid={`edit-subject-${index}`}
            value={subject}
            onChange={(ev) => setSubject(ev.target.value)}
            placeholder="Subject"
            className="w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
          />
          <textarea
            data-testid={`edit-body-${index}`}
            value={body}
            onChange={(ev) => setBody(ev.target.value)}
            rows={7}
            className="w-full bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm leading-relaxed focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none resize-y"
          />
          <button
            onClick={save}
            disabled={saving}
            data-testid={`save-draft-${index}`}
            className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-3 py-1.5 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Save
          </button>
        </div>
      ) : (
        <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed mt-3 border-t border-zinc-800 pt-3">
          {e.body}
        </pre>
      )}

      <EngagementBadges e={e} />

      {spamResult && (
        <div
          data-testid={`spam-result-${index}`}
          className={`mt-3 text-xs rounded-sm border p-2.5 ${
            spamResult.score >= 80 ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : spamResult.score >= 50 ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
              : "border-red-500/30 bg-red-500/10 text-red-300"
          }`}
        >
          <p className="font-semibold flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5" /> Deliverability score: {spamResult.score}/100
          </p>
          {spamResult.flags.length > 0 && (
            <ul className="mt-1 list-disc list-inside space-y-0.5 text-[11px] opacity-90">
              {spamResult.flags.map((f) => <li key={f}>{f}</li>)}
            </ul>
          )}
        </div>
      )}

      {voiceNoteUrl && (
        <audio controls src={voiceNoteUrl} data-testid={`voice-note-player-${index}`} className="mt-3 w-full h-9" />
      )}

      {e.status === "failed" && e.error && (
        <p className="text-xs text-red-400 mt-2">Error: {e.error}</p>
      )}
      {e.status === "suppressed" && (
        <p className="text-xs text-amber-400/80 mt-2 flex items-center gap-1.5">
          <BellOff className="w-3.5 h-3.5" /> Recipient unsubscribed — not sent.
        </p>
      )}

      {canEdit && (
        <div className="flex flex-wrap gap-2 mt-4">
          <button
            onClick={send}
            disabled={sending}
            data-testid={`send-email-${index}`}
            className="flex items-center gap-2 text-sm bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Send email
          </button>
          <button
            onClick={() => setEditing((v) => !v)}
            data-testid={`edit-email-${index}`}
            className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors"
          >
            <Pencil className="w-4 h-4" /> {editing ? "Close" : "Edit"}
          </button>
          <button
            onClick={checkSpam}
            disabled={checkingSpam}
            data-testid={`check-spam-${index}`}
            className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
          >
            {checkingSpam ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4" />}
            {spamResult ? "Re-check deliverability" : "Check deliverability"}
          </button>
          <button
            onClick={generateVoiceNote}
            disabled={generatingVoice}
            data-testid={`generate-voice-note-${index}`}
            className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
          >
            {generatingVoice ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mic className="w-4 h-4" />}
            {voiceNoteUrl ? "Regenerate voice note" : "Generate voice note"}
          </button>
        </div>
      )}
    </div>
  );
}

export default function Outbox() {
  const [tab, setTab] = useState("email");
  const [emails, setEmails] = useState(null);
  const [sendingAll, setSendingAll] = useState(false);

  const load = (channel) => {
    setEmails(null);
    api.get(`/emails?channel=${channel}`).then((r) => setEmails(r.data)).catch(() => setEmails([]));
  };

  useEffect(() => {
    load(tab);
  }, [tab]);

  const draftCount = (emails || []).filter((e) => e.status === "draft" || e.status === "failed").length;

  const sendAll = async () => {
    setSendingAll(true);
    toast.info("Sending all drafts…");
    try {
      const r = await api.post("/emails/send-all");
      toast.success(`${r.data.sent} sent · ${r.data.failed} failed`);
      load(tab);
    } catch (e) {
      toast.error("Send all failed.");
    } finally {
      setSendingAll(false);
    }
  };

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Dispatch log</p>
          <h1 className="font-display text-4xl font-black tracking-tight">Outbox</h1>
          <p className="text-zinc-400 text-sm mt-2">
            AI-drafted emails — review, edit the recipient, and hit send. Real delivery via your SMTP.
          </p>
        </div>
        {tab === "email" && draftCount > 0 && (
          <button
            onClick={sendAll}
            disabled={sendingAll}
            data-testid="send-all-button"
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-5 py-3 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {sendingAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Send all drafts ({draftCount})
          </button>
        )}
      </div>

      <div className="flex gap-2 mb-6 border-b border-zinc-800">
        {[
          { k: "email", label: "Cold Emails", icon: Mail },
          { k: "whatsapp", label: "WhatsApp Proposals", icon: MessageCircle },
        ].map((t) => (
          <button
            key={t.k}
            data-testid={`outbox-tab-${t.k}`}
            onClick={() => setTab(t.k)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
              tab === t.k ? "border-cyan-400 text-cyan-300" : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {emails === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading messages…</div>
      ) : emails.length === 0 ? (
        <div className="border border-dashed border-zinc-800 rounded-md p-16 text-center">
          <Send className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
          <p className="text-zinc-400">Nothing here yet. Run the agent to generate messages.</p>
        </div>
      ) : tab === "email" ? (
        <div className="space-y-3">
          {emails.map((e, i) => (
            <EmailRow key={e.id} e={e} index={i} onChanged={() => load("email")} />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {emails.map((e, i) => (
            <div
              key={e.id}
              data-testid={`outbox-item-${i}`}
              className="op-fade-up bg-[#18181B] border border-zinc-800 rounded-md p-5 hover:border-zinc-700 transition-colors"
              style={{ animationDelay: `${Math.min(i * 30, 300)}ms` }}
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                  <p className="font-display font-semibold">{e.subject}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    To {e.contact_name} · {e.company} · <span className="font-mono">{e.to_email}</span>
                  </p>
                </div>
                <StatusBadge status={e.status} simulated={e.simulated} />
              </div>
              <p className="text-sm text-zinc-300 mt-3 border-t border-zinc-800 pt-3">{e.body}</p>
              {e.whatsapp_link && (
                <a
                  href={e.whatsapp_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid={`outbox-whatsapp-${i}`}
                  className="mt-3 inline-flex items-center gap-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-sm px-4 py-2 text-sm hover:bg-emerald-500/20 transition-colors"
                >
                  <MessageCircle className="w-4 h-4" /> Open WhatsApp proposal
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
