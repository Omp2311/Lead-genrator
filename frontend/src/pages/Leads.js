import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Users, MapPin, Building2, Mail, Phone, MessageCircle, ExternalLink } from "lucide-react";

export default function Leads() {
  const [leads, setLeads] = useState(null);

  useEffect(() => {
    api.get("/leads").then((res) => setLeads(res.data)).catch(() => setLeads([]));
  }, []);

  return (
    <div className="p-8 max-w-7xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Prospect database</p>
        <h1 className="font-display text-4xl font-black tracking-tight">Leads</h1>
        <p className="text-zinc-400 text-sm mt-2">
          Decision-makers discovered by the agent across Dubai, US & high-IT cities.
        </p>
      </div>

      {leads === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading leads…</div>
      ) : leads.length === 0 ? (
        <div className="border border-dashed border-zinc-800 rounded-md p-16 text-center">
          <Users className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
          <p className="text-zinc-400">No leads yet. Hit “Run outreach now” on the Command Center.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {leads.map((l, i) => (
            <div
              key={l.id}
              data-testid={`lead-card-${i}`}
              className="op-fade-up bg-[#18181B] border border-zinc-800 rounded-md p-5 hover:border-cyan-500/40 hover:-translate-y-px transition-all duration-200"
              style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="font-display font-semibold text-base leading-tight">{l.contact_name}</h3>
                  <p className="text-xs text-zinc-500 mt-0.5">{l.title}</p>
                </div>
                <span className="text-[10px] uppercase tracking-wider bg-zinc-800 text-zinc-300 px-2 py-1 rounded-sm shrink-0">
                  {l.industry}
                </span>
              </div>

              <div className="mt-4 space-y-2 text-sm">
                <p className="flex items-center gap-2 text-zinc-300">
                  <Building2 className="w-3.5 h-3.5 text-zinc-500" /> {l.company}
                </p>
                <p className="flex items-center gap-2 text-zinc-400">
                  <MapPin className="w-3.5 h-3.5 text-zinc-500" /> {l.location}
                </p>
                <p className="flex items-center gap-2 text-zinc-400 truncate">
                  <Mail className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                  <span className="truncate font-mono text-xs">{l.email}</span>
                </p>
                {l.phone ? (
                  <p className="flex items-center gap-2 text-zinc-400">
                    <Phone className="w-3.5 h-3.5 text-zinc-500" />
                    <span className="font-mono text-xs">{l.phone}</span>
                  </p>
                ) : (
                  <p className="flex items-center gap-2 text-zinc-600">
                    <Phone className="w-3.5 h-3.5" /> <span className="text-xs">No phone</span>
                  </p>
                )}
              </div>

              <p className="mt-4 text-xs text-zinc-400 bg-[#0f0f11] border border-zinc-800/80 rounded-sm p-2.5 leading-relaxed">
                <span className="text-cyan-400/80">Signal:</span> {l.pain_point}
              </p>

              {l.whatsapp_link && (
                <a
                  href={l.whatsapp_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid={`lead-whatsapp-${i}`}
                  className="mt-4 flex items-center justify-center gap-2 w-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-sm py-2 text-sm hover:bg-emerald-500/20 transition-colors"
                >
                  <MessageCircle className="w-4 h-4" /> Send WhatsApp proposal
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
