import { useEffect, useState } from "react";
import api from "@/lib/api";
import { BarChart3, TrendingDown, Reply } from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, LabelList,
} from "recharts";

const FUNNEL_STEPS = [
  { key: "sent", label: "Sent" },
  { key: "opened", label: "Opened" },
  { key: "clicked", label: "Clicked" },
  { key: "replied_stage", label: "Replied" },
  { key: "meeting", label: "Meeting booked" },
  { key: "won", label: "Won" },
];

const SOURCE_LABELS = {
  apollo: "Apollo",
  places_hunter: "Places+Hunter",
  foursquare_hunter: "Foursquare+Hunter",
  github: "GitHub",
  osm_hunter: "OSM+Hunter",
  csv: "CSV import",
};

const sourceLabel = (source) => SOURCE_LABELS[source] || source || "Unknown";
const rate = (n, d) => (d ? Math.round((n / d) * 100) : 0);

const CHART_TOOLTIP_STYLE = { background: "#09090B", border: "1px solid #27272A", borderRadius: 4, fontSize: 12 };

function ReplyRateChart({ rows, testid }) {
  if (!rows || rows.length === 0) {
    return <p className="text-xs text-zinc-500">No sent emails yet.</p>;
  }
  const chartData = rows.map((r) => ({ ...r, rate: rate(r.replied, r.sent) }));
  return (
    <ResponsiveContainer width="100%" height={200} data-testid={testid}>
      <BarChart data={chartData} margin={{ left: -20, right: 8, top: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
        <XAxis dataKey="label" stroke="#71717A" fontSize={11} tickLine={false} axisLine={false} />
        <YAxis stroke="#71717A" fontSize={11} tickLine={false} axisLine={false} unit="%" allowDecimals={false} />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          labelStyle={{ color: "#a1a1aa" }}
          formatter={(_value, _name, props) => [`${props.payload.replied} / ${props.payload.sent} replied`, "Reply rate"]}
        />
        <Bar dataKey="rate" fill="#34d399" radius={[4, 4, 0, 0]} maxBarSize={56}>
          <LabelList dataKey="rate" position="top" formatter={(v) => `${v}%`} fill="#a1a1aa" fontSize={11} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function Analytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/analytics/funnel").then((r) => setData(r.data)).catch(() => setData(null));
  }, []);

  if (!data) return <div className="p-8 text-zinc-500 font-mono text-sm">Loading analytics…</div>;

  const values = {
    sent: data.sent,
    opened: data.opened,
    clicked: data.clicked,
    replied_stage: (data.stages?.replied || 0) + (data.stages?.meeting || 0) + (data.stages?.won || 0),
    meeting: (data.stages?.meeting || 0) + (data.stages?.won || 0),
    won: data.stages?.won || 0,
  };
  const max = Math.max(1, values.sent);

  const replyByVariantRows = (data.reply_by_variant || []).map((v) => ({
    label: `Variant ${v.variant}`, sent: v.sent, replied: v.replied,
  }));
  const replyBySourceRows = (data.reply_by_source || []).map((s) => ({
    label: sourceLabel(s.lead_source), sent: s.sent, replied: s.replied,
  }));

  return (
    <div className="p-8 max-w-5xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
          <BarChart3 className="w-3.5 h-3.5" /> Performance
        </p>
        <h1 className="font-display text-4xl font-black tracking-tight">Analytics</h1>
        <p className="text-zinc-400 text-sm mt-2">Your outreach funnel, reply attribution, and subject-line performance.</p>
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 mb-6">
        <h3 className="font-display font-semibold text-lg mb-5 flex items-center gap-2">
          <TrendingDown className="w-4 h-4 text-cyan-400" /> Outreach funnel
        </h3>
        <div className="space-y-3">
          {FUNNEL_STEPS.map((step) => {
            const v = values[step.key] || 0;
            const pct = data.sent ? Math.round((v / data.sent) * 100) : 0;
            const widthPct = Math.max(2, Math.round((v / max) * 100));
            return (
              <div key={step.key} data-testid={`funnel-row-${step.key}`}>
                <div className="flex items-baseline justify-between text-sm mb-1">
                  <span className="text-zinc-300">{step.label}</span>
                  <span className="font-mono text-zinc-400">
                    {v} <span className="text-zinc-600">({pct}%)</span>
                  </span>
                </div>
                <div className="h-3 bg-[#0f0f11] rounded-sm overflow-hidden">
                  <div className="h-full bg-cyan-400/70 rounded-sm transition-all" style={{ width: `${widthPct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6" data-testid="reply-rate-by-variant-card">
          <h3 className="font-display font-semibold text-lg mb-1 flex items-center gap-2">
            <Reply className="w-4 h-4 text-emerald-400" /> Reply rate by variant
          </h3>
          <p className="text-sm text-zinc-400 mb-2">Which subject-line style actually gets a reply, not just an open.</p>
          <ReplyRateChart rows={replyByVariantRows} testid="reply-rate-by-variant-chart" />
        </div>
        <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6" data-testid="reply-rate-by-source-card">
          <h3 className="font-display font-semibold text-lg mb-1 flex items-center gap-2">
            <Reply className="w-4 h-4 text-emerald-400" /> Reply rate by lead source
          </h3>
          <p className="text-sm text-zinc-400 mb-2">Which source finds people who actually write back.</p>
          <ReplyRateChart rows={replyBySourceRows} testid="reply-rate-by-source-chart" />
        </div>
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
        <h3 className="font-display font-semibold text-lg mb-1">Subject line A/B test</h3>
        <p className="text-sm text-zinc-400 mb-4">
          Variant A uses curiosity-driven subjects, Variant B uses direct value statements —
          automatically alternated across every batch.
        </p>
        {(!data.ab_variants || data.ab_variants.length === 0) ? (
          <p className="text-xs text-zinc-500">No sent emails with A/B data yet.</p>
        ) : (
          <div className="grid sm:grid-cols-2 gap-4">
            {data.ab_variants.map((v) => {
              const openRate = v.sent ? Math.round((v.opened / v.sent) * 100) : 0;
              const replyRow = (data.reply_by_variant || []).find((r) => r.variant === v.variant);
              const replyRate = replyRow ? rate(replyRow.replied, replyRow.sent) : null;
              return (
                <div key={v.variant} data-testid={`ab-variant-${v.variant}`} className="bg-[#0f0f11] border border-zinc-800/80 rounded-sm p-4">
                  <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Variant {v.variant}</p>
                  <div className="flex items-baseline gap-2">
                    <span className="font-display text-3xl font-black text-cyan-400">{openRate}%</span>
                    <span className="text-zinc-500 text-sm">open rate</span>
                  </div>
                  <p className="text-xs text-zinc-500 mt-1">{v.opened} opened / {v.sent} sent</p>
                  {replyRate !== null && (
                    <p className="text-xs text-emerald-400 mt-2 border-t border-zinc-800 pt-2">
                      {replyRate}% reply rate · {replyRow.replied} replied
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
