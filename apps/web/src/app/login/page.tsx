"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signup, login } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { checkAuth } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams?.get("redirect") || "";

  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isSignUp) {
        if (!displayName) {
          throw new Error("Name is required");
        }
        await signup(email, displayName, password);
      } else {
        await login(email, password);
      }
      
      // Update global context auth state
      await checkAuth();

      // Redirect accordingly
      if (redirect === "create") {
        router.push("/");
      } else {
        router.push("/dashboard");
      }
    } catch (err: any) {
      setError(err.message || "An authentication error occurred.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center py-12 px-6">
      <div className="glass glass-premium w-full max-w-md rounded-2xl p-8 border border-zinc-800/80 shadow-2xl relative overflow-hidden animate-fade-in">
        {/* Glow effect */}
        <div className="absolute -top-24 -left-24 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute -bottom-24 -right-24 h-48 w-48 rounded-full bg-pink-500/10 blur-3xl" />

        <div className="text-center mb-8 relative z-10">
          <h2 className="text-3xl font-extrabold tracking-tight text-white">
            {isSignUp ? "Create Studio Account" : "Access DIVA Studio"}
          </h2>
          <p className="mt-2 text-sm text-zinc-400">
            {isSignUp ? "Join and generate high-end AI portraits" : "Manage and track your custom AI generation history"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 relative z-10">
          {error && (
            <div className="rounded-lg bg-red-950/20 border border-red-900/40 p-3 text-xs text-red-400">
              {error}
            </div>
          )}

          {isSignUp && (
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
                Display Name
              </label>
              <input
                type="text"
                required
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Jane Doe"
                className="w-full rounded-xl border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@example.com"
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 py-3 text-sm font-bold tracking-wider text-white shadow-lg shadow-purple-950/30 transition hover:opacity-90 disabled:opacity-40 uppercase"
          >
            {loading ? "Authenticating..." : isSignUp ? "Create Account" : "Access Studio"}
          </button>
        </form>

        <div className="mt-8 text-center relative z-10 border-t border-zinc-900 pt-6">
          <button
            onClick={() => {
              setIsSignUp(!isSignUp);
              setError(null);
            }}
            className="text-xs font-medium text-purple-400 hover:text-purple-300 transition hover:underline"
          >
            {isSignUp
              ? "Already registered? Sign in here"
              : "New to DIVA? Create an account here"}
          </button>
        </div>
      </div>
    </div>
  );
}
