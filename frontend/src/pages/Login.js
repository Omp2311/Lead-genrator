import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Radar, Loader2 } from "lucide-react";

const BG =
  "https://images.unsplash.com/photo-1532190872407-280735d27e08?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Nzh8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMHRlY2glMjB0ZXh0dXJlJTIwZGFya3xlbnwwfHx8fDE3ODU2OTM5MTN8MA&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back, operator.");
      navigate("/app");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#09090B]">
      <div className="hidden lg:block relative border-r border-zinc-800">
        <img src={BG} alt="" className="absolute inset-0 w-full h-full object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#09090B] via-[#09090B]/60 to-transparent" />
        <div className="relative z-10 h-full flex flex-col justify-between p-12">
          <div className="flex items-center gap-2">
            <Radar className="w-7 h-7 text-cyan-400" />
            <span className="font-display font-extrabold text-xl">OutreachPilot</span>
          </div>
          <div>
            <h1 className="font-display text-4xl sm:text-5xl font-black tracking-tight leading-[1.05]">
              Your sales floor,<br />
              <span className="text-cyan-400">running itself.</span>
            </h1>
            <p className="text-zinc-400 mt-4 max-w-md text-sm leading-relaxed">
              Autonomously discover decision-makers in Dubai & the US, write
              hyper-personalized cold emails, and fire WhatsApp proposals — 100+ a day,
              zero manual work.
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm op-fade-up">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <Radar className="w-6 h-6 text-cyan-400" />
            <span className="font-display font-extrabold text-lg">OutreachPilot</span>
          </div>
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">Access terminal</p>
          <h2 className="font-display text-3xl font-bold tracking-tight mb-6">Sign in</h2>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Email</label>
              <input
                data-testid="login-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1 w-full bg-[#18181B] border border-zinc-800 rounded-sm px-3 py-2.5 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-zinc-500">Password</label>
              <input
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1 w-full bg-[#18181B] border border-zinc-800 rounded-sm px-3 py-2.5 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
              />
            </div>
            <button
              data-testid="login-submit-button"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-cyan-400 text-[#09090B] font-semibold py-2.5 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              Enter dashboard
            </button>
          </form>

          <p className="text-sm text-zinc-500 mt-6">
            No account?{" "}
            <Link to="/register" data-testid="go-register-link" className="text-cyan-400 hover:text-cyan-300">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
