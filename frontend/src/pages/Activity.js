import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Zap, Clock } from "lucide-react";

export default function Activity() {
  const [acts, setActs] = useState(null);

  useEffect(() => {
    api.get("/activity").then((r) => setActs(r.data)).catch(() => setActs([]));
  }, []);

  const fmt = (iso) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Agent log</p>
        <h1 className="font-display text-4xl font-black tracking-tight">Activity</h1>
        <p className="text-zinc-400 text-sm mt-2">Every autonomous action the agent has taken.</p>
      </div>

      {acts === null ? (
        <div className="text-zinc-500 font-mono text-sm">Loading activity…</div>
      ) : acts.length === 0 ? (
        <div className="border border-dashed border-zinc-800 rounded-md p-16 text-center">
          <Clock className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
          <p className="text-zinc-400">No activity yet.</p>
        </div>
      ) : (
        <div className="relative border-l border-zinc-800 ml-3">
          {acts.map((a, i) => (
            <div
              key={a.id}
              data-testid={`activity-item-${i}`}
              className="op-fade-up relative pl-6 pb-6"
              style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}
            >
              <span
                className={`absolute -left-[7px] top-1 w-3.5 h-3.5 rounded-full border-2 border-[#09090B] ${
                  a.type === "auto" ? "bg-emerald-400" : "bg-cyan-400"
                }`}
              />
              <div className="bg-[#18181B] border border-zinc-800 rounded-md p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className={`w-3.5 h-3.5 ${a.type === "auto" ? "text-emerald-400" : "text-cyan-400"}`} />
                  <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                    {a.type === "auto" ? "Autopilot" : "Manual run"}
                  </span>
                </div>
                <p className="text-sm text-zinc-200">{a.message}</p>
                <p className="text-xs text-zinc-600 mt-1 font-mono">{fmt(a.created_at)}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
