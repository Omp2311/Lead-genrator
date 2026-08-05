import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Gift, Copy, Users } from "lucide-react";

export default function Referrals() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.get("/referrals/status").then((r) => setStatus(r.data)).catch(() => setStatus(null));
  }, []);

  const copyLink = () => {
    navigator.clipboard.writeText(status.referral_url);
    toast.success("Referral link copied.");
  };

  if (!status) return <div className="p-8 text-zinc-500 font-mono text-sm">Loading referrals…</div>;

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
          <Gift className="w-3.5 h-3.5" /> Grow together
        </p>
        <h1 className="font-display text-4xl font-black tracking-tight">Referrals</h1>
        <p className="text-zinc-400 text-sm mt-2">
          Share your link. Anyone who signs up through it is tracked below.
        </p>
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6 mb-6">
        <label className="text-xs uppercase tracking-wider text-zinc-500">Your referral link</label>
        <div className="mt-2 flex gap-2">
          <input
            readOnly
            value={status.referral_url}
            data-testid="referral-link-input"
            className="flex-1 bg-[#0f0f11] border border-zinc-800 rounded-sm px-3 py-2 text-sm font-mono text-cyan-300"
          />
          <button
            onClick={copyLink}
            data-testid="copy-referral-link-button"
            className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors"
          >
            <Copy className="w-4 h-4" /> Copy
          </button>
        </div>
        <p className="text-xs text-zinc-500 mt-2 font-mono">Code: {status.referral_code}</p>
      </div>

      <div className="bg-[#18181B] border border-zinc-800 rounded-md p-6">
        <div className="flex items-center gap-3">
          <Users className="w-5 h-5 text-cyan-400" />
          <div>
            <p className="font-display text-3xl font-black" data-testid="referred-count">{status.referred_count}</p>
            <p className="text-xs text-zinc-500">people signed up via your link</p>
          </div>
        </div>
      </div>
    </div>
  );
}
