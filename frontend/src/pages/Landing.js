import { Link } from "react-router-dom";
import {
  Radar, Users, Sparkles, Mail, MessageCircle, RefreshCcw, Inbox,
  ArrowRight, Zap, Globe, ShieldCheck, Check,
} from "lucide-react";

const HERO =
  "https://images.unsplash.com/photo-1639322537228-f710d846310a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzV8MHwxfHNlYXJjaHwyfHxkYXJrJTIwYWJzdHJhY3QlMjBuZXR3b3JrJTIwbm9kZXMlMjB0ZWNobm9sb2d5fGVufDB8fHxibGFja3wxNzg1NzQ0NTQ2fDA&ixlib=rb-4.1.0&q=85";

const features = [
  { icon: Users, title: "AI Lead Discovery", desc: "The agent finds real decision-makers in Dubai, the US & high-IT cities — no lists to buy, no manual scraping." },
  { icon: Sparkles, title: "Skill-Matched Projects", desc: "Set your skills once. Every lead comes with a tailored project idea and an estimated deal value." },
  { icon: Mail, title: "Personalized Cold Emails", desc: "Each email is hand-written by AI around the prospect's real pain point — then sent from your own inbox." },
  { icon: MessageCircle, title: "WhatsApp Proposals", desc: "Got a phone number? A ready-to-fire WhatsApp proposal is generated for instant, high-response outreach." },
  { icon: RefreshCcw, title: "Auto Follow-ups", desc: "Two smart follow-ups are scheduled automatically for every prospect who doesn't reply." },
  { icon: Inbox, title: "Reply Detection", desc: "The app reads your inbox and instantly stops the sequence the moment someone replies. Zero manual work." },
];

const steps = [
  { n: "01", title: "Set your skills", desc: "Tell the agent what you build and who you want to reach. Takes 60 seconds." },
  { n: "02", title: "Agent finds & drafts", desc: "It discovers matching clients, writes personalized emails, and builds WhatsApp proposals." },
  { n: "03", title: "Send or autopilot", desc: "Review and hit send — or flip on autopilot and let 100+ go out daily, hands-free." },
];

const plans = [
  { name: "Starter", price: "Free", tag: "While in beta", features: ["AI lead discovery", "Personalized cold emails", "WhatsApp proposal links", "Manual send from dashboard"], cta: "Get started", highlight: false },
  { name: "Pro", price: "$29", per: "/mo", tag: "Most popular", features: ["Everything in Starter", "Daily autopilot (100+/day)", "Auto follow-up sequences", "Inbox reply detection", "Send from your own SMTP"], cta: "Get started", highlight: true },
  { name: "Agency", price: "$99", per: "/mo", tag: "Scale", features: ["Everything in Pro", "Real lead provider (Apollo)", "Automated WhatsApp (Twilio)", "Priority support"], cta: "Get started", highlight: false },
];

const Nav = () => (
  <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-md bg-[#09090B]/70 border-b border-zinc-800/80">
    <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
      <Link to="/" className="flex items-center gap-2" data-testid="landing-logo">
        <Radar className="w-6 h-6 text-cyan-400" strokeWidth={2.2} />
        <span className="font-display font-extrabold text-lg tracking-tight">
          Outreach<span className="text-cyan-400">Pilot</span>
        </span>
      </Link>
      <div className="hidden md:flex items-center gap-8 text-sm text-zinc-400">
        <a href="#features" className="hover:text-white transition-colors">Features</a>
        <a href="#how" className="hover:text-white transition-colors">How it works</a>
        <a href="#pricing" className="hover:text-white transition-colors">Pricing</a>
      </div>
      <div className="flex items-center gap-3">
        <Link to="/login" data-testid="landing-login-link" className="text-sm text-zinc-300 hover:text-white transition-colors">
          Log in
        </Link>
        <Link to="/register" data-testid="landing-getstarted-nav" className="text-sm font-semibold bg-cyan-400 text-[#09090B] px-4 py-2 rounded-sm hover:bg-cyan-300 transition-colors">
          Get started
        </Link>
      </div>
    </div>
  </nav>
);

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#09090B] text-white">
      <Nav />

      {/* Hero */}
      <header className="relative pt-32 pb-24 overflow-hidden">
        <img src={HERO} alt="" className="absolute inset-0 w-full h-full object-cover opacity-25" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#09090B] via-[#09090B]/70 to-[#09090B]" />
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-cyan-500/10 blur-[120px] rounded-full" />
        <div className="relative max-w-5xl mx-auto px-6 text-center op-fade-up">
          <span className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-cyan-300 border border-cyan-500/30 bg-cyan-500/5 rounded-full px-4 py-1.5 mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 op-live-dot" /> Autonomous outreach agent
          </span>
          <h1 className="font-display text-5xl sm:text-6xl lg:text-7xl font-black tracking-tight leading-[1.02]">
            Your cold outreach,<br />
            <span className="text-cyan-400">running itself.</span>
          </h1>
          <p className="text-zinc-400 text-base sm:text-lg max-w-2xl mx-auto mt-6 leading-relaxed">
            OutreachPilot finds real clients in Dubai & the US, writes hyper-personalized emails,
            fires WhatsApp proposals, follows up, and stops the moment they reply —
            <span className="text-white"> 100+ a day, zero manual work.</span>
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4 mt-10">
            <Link to="/register" data-testid="hero-getstarted-btn" className="flex items-center gap-2 bg-cyan-400 text-[#09090B] font-semibold px-6 py-3.5 rounded-sm hover:bg-cyan-300 transition-colors">
              Start free <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="#how" className="flex items-center gap-2 border border-zinc-700 text-zinc-200 px-6 py-3.5 rounded-sm hover:bg-zinc-800/60 transition-colors">
              See how it works
            </a>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-2 mt-10 text-xs text-zinc-500">
            <span className="flex items-center gap-2"><Globe className="w-3.5 h-3.5" /> Dubai · USA · high-IT cities</span>
            <span className="flex items-center gap-2"><ShieldCheck className="w-3.5 h-3.5" /> Sends from your own inbox</span>
            <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5" /> No payment to start</span>
          </div>
        </div>
      </header>

      {/* Stats */}
      <section className="max-w-5xl mx-auto px-6 -mt-8 mb-24 grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { k: "100+", v: "Emails / day on autopilot" },
          { k: "6", v: "Outreach steps automated" },
          { k: "0", v: "Manual busywork" },
          { k: "24/7", v: "Agent always working" },
        ].map((s) => (
          <div key={s.v} className="bg-[#18181B] border border-zinc-800 rounded-md p-5 text-center">
            <div className="font-display text-3xl font-black text-cyan-400">{s.k}</div>
            <p className="text-xs text-zinc-500 mt-1">{s.v}</p>
          </div>
        ))}
      </section>

      {/* Features */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-14 max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-400 mb-3">What it does</p>
          <h2 className="font-display text-4xl sm:text-5xl font-black tracking-tight">
            One agent. The entire outreach pipeline.
          </h2>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((f, i) => (
            <div
              key={f.title}
              data-testid={`feature-${i}`}
              className="op-fade-up bg-[#18181B] border border-zinc-800 rounded-md p-6 hover:border-cyan-500/40 hover:-translate-y-1 transition-all duration-200"
              style={{ animationDelay: `${Math.min(i * 60, 400)}ms` }}
            >
              <div className="w-10 h-10 rounded-sm bg-cyan-400/10 flex items-center justify-center mb-4">
                <f.icon className="w-5 h-5 text-cyan-400" />
              </div>
              <h3 className="font-display font-semibold text-lg">{f.title}</h3>
              <p className="text-sm text-zinc-400 mt-2 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="max-w-6xl mx-auto px-6 py-24">
        <div className="mb-14 max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-400 mb-3">How it works</p>
          <h2 className="font-display text-4xl sm:text-5xl font-black tracking-tight">Live in three steps.</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          {steps.map((s) => (
            <div key={s.n} className="relative bg-[#18181B] border border-zinc-800 rounded-md p-6">
              <div className="font-display text-5xl font-black text-zinc-800">{s.n}</div>
              <h3 className="font-display font-semibold text-lg mt-3">{s.title}</h3>
              <p className="text-sm text-zinc-400 mt-2 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-14 text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-400 mb-3">Pricing</p>
          <h2 className="font-display text-4xl sm:text-5xl font-black tracking-tight">Start free. Scale when you win.</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-4 items-start">
          {plans.map((p) => (
            <div
              key={p.name}
              data-testid={`plan-${p.name.toLowerCase()}`}
              className={`rounded-md p-6 border transition-all duration-200 ${
                p.highlight
                  ? "border-cyan-500/50 bg-cyan-500/5 md:-translate-y-2 shadow-[0_0_40px_-12px_rgba(0,240,255,0.4)]"
                  : "border-zinc-800 bg-[#18181B]"
              }`}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-display font-bold text-xl">{p.name}</h3>
                <span className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm ${p.highlight ? "bg-cyan-400 text-[#09090B]" : "bg-zinc-800 text-zinc-400"}`}>{p.tag}</span>
              </div>
              <div className="mt-4 flex items-baseline gap-1">
                <span className="font-display text-4xl font-black">{p.price}</span>
                {p.per && <span className="text-zinc-500 text-sm">{p.per}</span>}
              </div>
              <ul className="mt-6 space-y-2.5">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-zinc-300">
                    <Check className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/register"
                className={`mt-6 flex items-center justify-center gap-2 w-full py-2.5 rounded-sm font-semibold transition-colors ${
                  p.highlight ? "bg-cyan-400 text-[#09090B] hover:bg-cyan-300" : "bg-zinc-800 text-white hover:bg-zinc-700"
                }`}
              >
                {p.cta} <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-zinc-600 mt-6">Plans shown for illustration — no payment required to start.</p>
      </section>

      {/* CTA */}
      <section className="max-w-5xl mx-auto px-6 py-24">
        <div className="relative overflow-hidden rounded-lg border border-cyan-500/30 bg-gradient-to-br from-[#0e1416] to-[#18181B] p-12 text-center">
          <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-cyan-500/10 blur-[100px] rounded-full" />
          <div className="relative">
            <h2 className="font-display text-4xl sm:text-5xl font-black tracking-tight">
              Stop prospecting.<br /><span className="text-cyan-400">Start closing.</span>
            </h2>
            <p className="text-zinc-400 mt-4 max-w-xl mx-auto">
              Turn on your autonomous sales agent today and wake up to a full pipeline tomorrow.
            </p>
            <Link to="/register" data-testid="cta-getstarted-btn" className="inline-flex items-center gap-2 mt-8 bg-cyan-400 text-[#09090B] font-semibold px-7 py-3.5 rounded-sm hover:bg-cyan-300 transition-colors">
              Get started free <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-800">
        <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Radar className="w-5 h-5 text-cyan-400" />
            <span className="font-display font-bold">OutreachPilot</span>
          </div>
          <p className="text-xs text-zinc-600">© {new Date().getFullYear()} OutreachPilot. Autonomous cold outreach.</p>
        </div>
      </footer>
    </div>
  );
}
