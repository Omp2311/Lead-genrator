import { useEffect, useState } from "react";
import api, { API } from "@/lib/api";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/lib/api";

const BACKEND_ORIGIN = API.replace(/\/api$/, "");
import { BookOpen, Key, Plus, Trash2, Loader2, Copy, ExternalLink } from "lucide-react";

const CHANGELOG = [
  { tier: "Tier 4", items: [
    "Live-signal personalization from a lead's own website",
    "Deliverability / spam-score checker for drafts",
    "AI-drafted replies to interested/question responses",
    "Voice-note personalization (OpenAI TTS)",
  ]},
  { tier: "Tier 3", items: [
    "Team seats — invite teammates to share a workspace",
    "Stripe billing — Starter / Pro / Agency plans",
  ]},
  { tier: "Tier 2", items: [
    "Editable multi-step follow-up sequences",
    "CRM pipeline (Kanban) with reply-intent tagging",
    "A/B subject-line testing",
    "Meeting-booking link CTA",
  ]},
  { tier: "Tier 1", items: [
    "Unsubscribe list + compliance footer",
    "Multi-inbox rotation with warm-up ramp",
    "Open/click tracking",
    "CSV lead import",
  ]},
];

function CodeBlock({ children }) {
  return (
    <pre className="bg-[#0f0f11] border border-zinc-800 rounded-sm p-3 text-xs font-mono text-zinc-300 overflow-x-auto">
      {children}
    </pre>
  );
}

export default function Docs() {
  const [keys, setKeys] = useState(null);
  const [label, setLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState(null);

  const load = () => api.get("/api-keys").then((r) => setKeys(r.data)).catch(() => setKeys([]));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    setCreating(true);
    try {
      const r = await api.post("/api-keys", { label: label || "API key" });
      setNewKey(r.data.key);
      setLabel("");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not create key.");
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/api-keys/${id}`);
      load();
    } catch (e) {
      toast.error("Could not remove key.");
    }
  };

  const copy = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied.");
  };

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5" /> Reference
        </p>
        <h1 className="font-display text-4xl font-black tracking-tight">Docs & API</h1>
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 mb-6">
        <h3 className="font-display font-semibold text-lg mb-1 flex items-center gap-2">
          <Key className="w-4 h-4 text-cyan-400" /> API keys
        </h3>
        <p className="text-sm text-zinc-400 mb-4">
          Use a key to pull or push leads programmatically — this is what Zapier's or Make's generic
          "Webhooks" / "HTTP" actions connect to.
        </p>

        {newKey && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-sm p-3 mb-4">
            <p className="text-xs text-amber-300 mb-2">
              Copy this now — it won't be shown again.
            </p>
            <div className="flex gap-2">
              <code className="flex-1 text-xs font-mono text-zinc-200 bg-[#0f0f11] rounded-sm px-2 py-1.5 overflow-x-auto" data-testid="new-api-key-value">
                {newKey}
              </code>
              <button onClick={() => copy(newKey)} className="text-amber-300 hover:text-amber-200">
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        <div className="flex gap-2 mb-4">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label, e.g. Zapier"
            data-testid="api-key-label-input"
            className="flex-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
          />
          <button
            onClick={create}
            disabled={creating}
            data-testid="create-api-key-button"
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Create key
          </button>
        </div>

        {keys === null ? (
          <p className="text-xs text-zinc-500">Loading…</p>
        ) : keys.length === 0 ? (
          <p className="text-xs text-zinc-500">No API keys yet.</p>
        ) : (
          <div className="space-y-1.5">
            {keys.map((k) => (
              <div key={k.id} data-testid={`api-key-row-${k.id}`} className="flex items-center justify-between text-xs bg-[#0f0f11] border border-zinc-800/80 rounded-sm px-3 py-2">
                <div>
                  <span className="text-zinc-300 font-medium">{k.label}</span>
                  <span className="text-zinc-500 font-mono ml-2">{k.key_preview}</span>
                </div>
                <button onClick={() => remove(k.id)} className="text-zinc-500 hover:text-red-400">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 mb-6 space-y-4">
        <h3 className="font-display font-semibold text-lg">Endpoints</h3>
        <div>
          <p className="text-xs text-zinc-400 mb-1.5">List leads</p>
          <CodeBlock>{`curl -H "Authorization: Bearer YOUR_KEY" \\\n  ${BACKEND_ORIGIN}/api/public/v1/leads`}</CodeBlock>
        </div>
        <div>
          <p className="text-xs text-zinc-400 mb-1.5">Create a lead (e.g. from a Zapier trigger)</p>
          <CodeBlock>{`curl -X POST -H "Authorization: Bearer YOUR_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"email":"lead@company.com","company":"Acme"}' \\\n  ${BACKEND_ORIGIN}/api/public/v1/leads`}</CodeBlock>
        </div>
        <div>
          <p className="text-xs text-zinc-400 mb-1.5">List sent/drafted emails</p>
          <CodeBlock>{`curl -H "Authorization: Bearer YOUR_KEY" \\\n  ${BACKEND_ORIGIN}/api/public/v1/emails`}</CodeBlock>
        </div>
        <a
          href={`${BACKEND_ORIGIN}/docs`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300"
        >
          Full interactive API reference (Swagger) <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
        <h3 className="font-display font-semibold text-lg mb-4">Changelog</h3>
        <div className="space-y-4">
          {CHANGELOG.map((group) => (
            <div key={group.tier}>
              <p className="text-xs uppercase tracking-wider text-cyan-400 mb-1.5">{group.tier}</p>
              <ul className="space-y-1">
                {group.items.map((item) => (
                  <li key={item} className="text-sm text-zinc-300 flex items-start gap-2">
                    <span className="text-zinc-600 mt-0.5">–</span> {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
