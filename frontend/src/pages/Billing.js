import { useEffect, useState } from "react";
import api from "@/lib/api";
import { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { CreditCard, Check, Loader2, ExternalLink } from "lucide-react";

const PLANS = [
  { key: "starter", name: "Starter", price: "$29/mo", features: ["2 inboxes", "1 seat", "50 emails/day"] },
  { key: "pro", name: "Pro", price: "$79/mo", features: ["5 inboxes", "3 seats", "300 emails/day"] },
  { key: "agency", name: "Agency", price: "$199/mo", features: ["15 inboxes", "15 seats", "1000 emails/day"] },
];

export default function Billing() {
  const [status, setStatus] = useState(null);
  const [loadingPlan, setLoadingPlan] = useState(null);
  const [loadingPortal, setLoadingPortal] = useState(false);

  const load = () => api.get("/billing/status").then((r) => setStatus(r.data)).catch(() => setStatus(null));

  useEffect(() => {
    load();
  }, []);

  const upgrade = async (plan) => {
    setLoadingPlan(plan);
    try {
      const r = await api.post("/billing/checkout", { plan });
      window.location.href = r.data.url;
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Checkout failed.");
    } finally {
      setLoadingPlan(null);
    }
  };

  const openPortal = async () => {
    setLoadingPortal(true);
    try {
      const r = await api.post("/billing/portal");
      window.location.href = r.data.url;
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not open billing portal.");
    } finally {
      setLoadingPortal(false);
    }
  };

  if (!status) return <div className="p-8 text-zinc-500 font-mono text-sm">Loading billing…</div>;

  return (
    <div className="p-8 max-w-5xl">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2 flex items-center gap-2">
          <CreditCard className="w-3.5 h-3.5" /> Plan & billing
        </p>
        <h1 className="font-display text-4xl font-black tracking-tight">Billing</h1>
        <p className="text-zinc-400 text-sm mt-2">
          Current plan: <span className="text-cyan-400 font-semibold capitalize">{status.plan}</span>
          {status.subscription_status && <span className="text-zinc-500"> · {status.subscription_status}</span>}
        </p>
      </div>

      {!status.is_owner && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-md p-4 mb-6 text-sm text-amber-300">
          You're a team member on this workspace — only the owner can change plans or billing details.
        </div>
      )}

      {!status.stripe_configured && (
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-md p-4 mb-6 text-sm text-zinc-400">
          Billing isn't configured yet — add <code className="text-zinc-300">STRIPE_SECRET_KEY</code> and price IDs
          to the backend environment to enable real checkout.
        </div>
      )}

      <div className="grid sm:grid-cols-3 gap-4 mb-8">
        {PLANS.map((p) => {
          const isCurrent = status.plan === p.key;
          return (
            <div
              key={p.key}
              data-testid={`plan-card-${p.key}`}
              className={`bg-[#18181B] border rounded-md p-6 ${isCurrent ? "border-cyan-500/60" : "border-zinc-800"}`}
            >
              <h3 className="font-display font-bold text-lg">{p.name}</h3>
              <p className="text-2xl font-black text-cyan-400 mt-1">{p.price}</p>
              <ul className="mt-4 space-y-1.5">
                {p.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-zinc-300">
                    <Check className="w-3.5 h-3.5 text-emerald-400" /> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => upgrade(p.key)}
                disabled={isCurrent || !status.is_owner || loadingPlan === p.key}
                data-testid={`plan-select-${p.key}`}
                className="mt-5 w-full flex items-center justify-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-40"
              >
                {loadingPlan === p.key ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {isCurrent ? "Current plan" : "Upgrade"}
              </button>
            </div>
          );
        })}
      </div>

      {status.is_owner && (
        <button
          onClick={openPortal}
          disabled={loadingPortal}
          data-testid="manage-billing-button"
          className="flex items-center gap-2 text-sm bg-zinc-800 text-white px-4 py-2 rounded-sm hover:bg-zinc-700 transition-colors disabled:opacity-60"
        >
          {loadingPortal ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
          Manage billing / invoices
        </button>
      )}
    </div>
  );
}
