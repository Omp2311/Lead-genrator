import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Send, MessageCircle, ExternalLink, Mail } from "lucide-react";

export default function Outbox() {
  const [tab, setTab] = useState("email");
  const [emails, setEmails] = useState(null);

  const load = (channel) => {
    setEmails(null);
    api.get(`/emails?channel=${channel}`).then((r) => setEmails(r.data)).catch(() => setEmails([]));
  };

  useEffect(() => {
    load(tab);
  }, [tab]);

  return (
    <div className="p-8 max-w-6xl">
      <div className="mb-6">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Dispatch log</p>
        <h1 className="font-display text-4xl font-black tracking-tight">Outbox</h1>
        <p className="text-zinc-400 text-sm mt-2">
          Every AI-personalized message the agent generated and dispatched.
        </p>
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
              tab === t.k
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
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
                  <div className="flex items-center gap-2 flex-wrap">
                    {e.channel === "email" && (
                      <span className="text-[10px] uppercase tracking-wider bg-cyan-400/10 text-cyan-300 px-1.5 py-0.5 rounded-sm">
                        {e.type === "follow_up" ? `Follow-up ${e.step - 1}` : "Initial"}
                      </span>
                    )}
                    <p className="font-display font-semibold">{e.subject}</p>
                  </div>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    To {e.contact_name} · {e.company} ·{" "}
                    <span className="font-mono">{e.to_email}</span>
                    {e.status === "scheduled" && e.scheduled_for && (
                      <span className="text-amber-400/80"> · scheduled {new Date(e.scheduled_for).toLocaleDateString()}</span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {e.simulated && e.status === "sent" && (
                    <span className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm bg-zinc-700/50 text-zinc-400">
                      simulated
                    </span>
                  )}
                  <span
                    className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm ${
                      e.status === "sent"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : e.status === "scheduled"
                        ? "bg-amber-500/10 text-amber-400"
                        : e.status === "failed"
                        ? "bg-red-500/10 text-red-400"
                        : e.status === "cancelled"
                        ? "bg-zinc-700/40 text-zinc-500"
                        : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {e.status}
                  </span>
                </div>
              </div>
              {e.channel === "email" ? (
                <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed mt-3 border-t border-zinc-800 pt-3">
                  {e.body}
                </pre>
              ) : (
                <a
                  href={e.whatsapp_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid={`outbox-whatsapp-${i}`}
                  className="mt-2 inline-flex items-center gap-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-sm px-4 py-2 text-sm hover:bg-emerald-500/20 transition-colors"
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
