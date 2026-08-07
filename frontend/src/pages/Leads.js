import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";
import { Users, MapPin, Building2, Mail, Phone, MessageCircle, ExternalLink, CheckCircle2, Upload, Download, Loader2, BellOff, Linkedin, Copy } from "lucide-react";

const CSV_TEMPLATE_HEADER = ["company", "contact_name", "title", "email", "phone", "location",
  "industry", "website", "pain_point", "project_idea", "estimated_value"];

function downloadCsvTemplate() {
  const blob = new Blob([CSV_TEMPLATE_HEADER.join(",") + "\n"], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "outreachpilot_leads_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function copyText(text) {
  navigator.clipboard.writeText(text);
  toast.success("Copied.");
}

function LeadCard({ l, i, onMarkReplied }) {
  const [drafting, setDrafting] = useState(false);
  const [linkedin, setLinkedin] = useState(
    l.linkedin_note || l.linkedin_message ? { connection_note: l.linkedin_note, first_message: l.linkedin_message } : null
  );

  const draftLinkedIn = async () => {
    setDrafting(true);
    try {
      const r = await api.post(`/leads/${l.id}/linkedin-draft`);
      setLinkedin({ connection_note: r.data.linkedin_note, first_message: r.data.linkedin_message });
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Draft failed.");
    } finally {
      setDrafting(false);
    }
  };

  return (
    <div
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

      {l.project_idea && (
        <div className="mt-3 bg-cyan-400/5 border border-cyan-500/20 rounded-sm p-2.5" data-testid={`lead-project-${i}`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase tracking-wider text-cyan-400/90">Project idea</span>
            {l.estimated_value && (
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded-sm">
                {l.estimated_value}
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-300 leading-relaxed">{l.project_idea}</p>
        </div>
      )}

      {l.suppressed && (
        <div className="mt-3 flex items-center gap-2 text-xs text-amber-400" data-testid={`lead-suppressed-${i}`}>
          <BellOff className="w-4 h-4" /> Unsubscribed — no outreach sent
        </div>
      )}

      {l.replied ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-emerald-400" data-testid={`lead-replied-${i}`}>
          <CheckCircle2 className="w-4 h-4" /> Replied — follow-ups stopped
          {l.reply_intent && l.reply_intent !== "unknown" && (
            <span data-testid={`lead-intent-${i}`} className="ml-1 text-[10px] uppercase tracking-wider bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded-sm">
              {l.reply_intent.replace("_", " ")}
            </span>
          )}
        </div>
      ) : (
        <button
          onClick={() => onMarkReplied(l.id)}
          data-testid={`lead-mark-replied-${i}`}
          className="mt-3 flex items-center gap-2 text-xs text-zinc-400 hover:text-emerald-400 transition-colors"
        >
          <CheckCircle2 className="w-4 h-4" /> Mark as replied
        </button>
      )}

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

      <button
        onClick={draftLinkedIn}
        disabled={drafting}
        data-testid={`lead-linkedin-draft-${i}`}
        className="mt-2 flex items-center justify-center gap-2 w-full bg-zinc-800 text-white rounded-sm py-2 text-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
      >
        {drafting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Linkedin className="w-4 h-4" />}
        {linkedin ? "Redraft LinkedIn message" : "Draft LinkedIn message"}
      </button>

      {linkedin && (
        <div className="mt-3 space-y-2" data-testid={`lead-linkedin-drafts-${i}`}>
          <div className="bg-[#0f0f11] border border-zinc-800/80 rounded-sm p-2.5">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">Connection note</span>
              <button onClick={() => copyText(linkedin.connection_note)} className="text-zinc-500 hover:text-cyan-400">
                <Copy className="w-3 h-3" />
              </button>
            </div>
            <p className="text-xs text-zinc-300 leading-relaxed">{linkedin.connection_note}</p>
          </div>
          <div className="bg-[#0f0f11] border border-zinc-800/80 rounded-sm p-2.5">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">First message (after they accept)</span>
              <button onClick={() => copyText(linkedin.first_message)} className="text-zinc-500 hover:text-cyan-400">
                <Copy className="w-3 h-3" />
              </button>
            </div>
            <p className="text-xs text-zinc-300 leading-relaxed">{linkedin.first_message}</p>
          </div>
          <p className="text-[10px] text-zinc-600">Paste these on LinkedIn yourself — nothing is sent automatically.</p>
        </div>
      )}
    </div>
  );
}

export default function Leads() {
  const [leads, setLeads] = useState(null);
  const [importing, setImporting] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const fileInputRef = useRef(null);

  const load = () => api.get("/leads").then((res) => setLeads(res.data)).catch(() => setLeads([]));

  useEffect(() => {
    load();
  }, []);

  const markReplied = async (id) => {
    try {
      const r = await api.post(`/leads/${id}/replied`);
      toast.success(`Marked as replied · ${r.data.cancelled_followups} follow-up(s) cancelled`);
      setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, replied: true } : l)));
    } catch (e) {
      toast.error("Could not update lead.");
    }
  };

  const handleFileChange = async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const r = await api.post("/leads/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const hunterNote = r.data.enriched_via_hunter > 0 ? ` · ${r.data.enriched_via_hunter} email(s) found via Hunter` : "";
      toast.success(`Imported ${r.data.imported} lead(s) · ${r.data.skipped} skipped${hunterNote}`);
      load();
      if (r.data.imported > 0) await draftMissing();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Import failed.");
    } finally {
      setImporting(false);
    }
  };

  const draftMissing = async () => {
    setDrafting(true);
    try {
      const r = await api.post("/leads/draft-missing");
      if (r.data.drafted > 0) {
        toast.success(`Drafted emails for ${r.data.drafted} lead(s) — check the Outbox.`);
      } else {
        toast.info("Every lead already has a draft.");
      }
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not draft emails.");
    } finally {
      setDrafting(false);
    }
  };

  return (
    <div className="p-8 max-w-7xl">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Prospect database</p>
          <h1 className="font-display text-4xl font-black tracking-tight">Leads</h1>
          <p className="text-zinc-400 text-sm mt-2">
            Decision-makers discovered by the agent across Dubai, US & high-IT cities.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={downloadCsvTemplate}
            data-testid="download-csv-template-button"
            className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors"
          >
            <Download className="w-4 h-4" /> Template
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            data-testid="import-csv-button"
            className="flex items-center gap-2 text-sm bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            Import CSV
          </button>
          <input ref={fileInputRef} type="file" accept=".csv" onChange={handleFileChange} className="hidden" data-testid="import-csv-input" />
          <button
            onClick={draftMissing}
            disabled={drafting}
            data-testid="draft-missing-emails-button"
            className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
            title="Generate cold email + follow-ups + WhatsApp for any lead that doesn't have a draft yet"
          >
            {drafting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
            Draft emails for new leads
          </button>
        </div>
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
            <LeadCard key={l.id} l={l} i={i} onMarkReplied={markReplied} />
          ))}
        </div>
      )}
    </div>
  );
}
