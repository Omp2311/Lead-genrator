import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Radar, Loader2 } from "lucide-react";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const ref = searchParams.get("ref");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(name, email, password, ref);
      toast.success("Account created. Welcome aboard.");
      navigate("/app");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-[#09090B]">
      <div className="w-full max-w-sm op-fade-up">
        <div className="flex items-center gap-2 mb-8">
          <Radar className="w-6 h-6 text-cyan-400" />
          <span className="font-display font-extrabold text-lg">OutreachPilot</span>
        </div>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500 mb-2">New operator</p>
        <h2 className="font-display text-3xl font-bold tracking-tight mb-2">Create account</h2>
        {ref && (
          <p className="text-xs text-cyan-400 mb-4" data-testid="referral-banner">Signing up via a referral link.</p>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">Name</label>
            <input
              data-testid="register-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="mt-1 w-full bg-[#18181B] border border-zinc-800 rounded-sm px-3 py-2.5 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-500">Email</label>
            <input
              data-testid="register-email-input"
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
              data-testid="register-password-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="mt-1 w-full bg-[#18181B] border border-zinc-800 rounded-sm px-3 py-2.5 text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-colors"
            />
          </div>
          <button
            data-testid="register-submit-button"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-cyan-400 text-[#09090B] font-semibold py-2.5 rounded-sm hover:bg-cyan-300 transition-colors disabled:opacity-60"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Create account
          </button>
        </form>

        <p className="text-sm text-zinc-500 mt-6">
          Already have an account?{" "}
          <Link to="/login" data-testid="go-login-link" className="text-cyan-400 hover:text-cyan-300">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
