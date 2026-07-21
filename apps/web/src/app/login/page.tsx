"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signup, login, sendOtp, verifyOtp, socialLogin } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type AuthMode = "login" | "signup" | "otp";

function LoginForm() {
  const { checkAuth } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams?.get("redirect") || "";

  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resendingOtp, setResendingOtp] = useState(false);

  const handleFinishAuth = async () => {
    await checkAuth();
    if (redirect === "create") {
      router.push("/");
    } else {
      router.push("/dashboard");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfoMessage(null);
    setLoading(true);

    try {
      if (mode === "signup") {
        if (!displayName) {
          throw new Error("Name is required for sign up");
        }
        await signup(email, displayName, password);
        // After signup, backend generates an OTP
        setInfoMessage(`An OTP code has been sent to your email address (${email}). Please enter it below to verify your account.`);
        setMode("otp");
      } else if (mode === "login") {
        await login(email, password);
        await handleFinishAuth();
      } else if (mode === "otp") {
        if (!otpCode || otpCode.trim().length === 0) {
          throw new Error("Please enter the OTP code sent to your email");
        }
        await verifyOtp(email, otpCode.trim());
        await handleFinishAuth();
      }
    } catch (err: any) {
      setError(err.message || "An authentication error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleRequestOtp = async () => {
    if (!email) {
      setError("Please enter your email address first to receive an OTP.");
      return;
    }
    setError(null);
    setInfoMessage(null);
    setLoading(true);

    try {
      await sendOtp(email);
      setInfoMessage(`OTP code has been sent to your email address: ${email}`);
      setMode("otp");
    } catch (err: any) {
      setError(err.message || "Failed to send OTP code.");
    } finally {
      setLoading(false);
    }
  };

  const handleResendOtp = async () => {
    if (!email) return;
    setError(null);
    setResendingOtp(true);
    try {
      await sendOtp(email);
    } finally {
      setResendingOtp(false);
    }
  };

  const handleOAuthLogin = async (provider: "google" | "github") => {
    setError(null);
    setInfoMessage(null);
    setLoading(true);

    try {
      const userEmail = email && email.trim() ? email.trim() : `${provider}_user@gmail.com`;
      const userDisplayName = displayName || (userEmail ? userEmail.split("@")[0] : `${provider.toUpperCase()} User`);
      const token = `mock:${userEmail}:${userDisplayName}`;
      
      await socialLogin(provider, token, userDisplayName);
      await handleFinishAuth();
    } catch (err: any) {
      setError(err.message || `${provider} authentication failed.`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center py-12 px-6">
      <div className="glass glass-premium w-full max-w-md rounded-2xl p-8 border border-zinc-800/80 shadow-2xl relative overflow-hidden animate-fade-in">
        {/* Ambient background glow */}
        <div className="absolute -top-24 -left-24 h-48 w-48 rounded-full bg-purple-500/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 h-48 w-48 rounded-full bg-pink-500/10 blur-3xl pointer-events-none" />

        <div className="text-center mb-6 relative z-10">
          <h2 className="text-3xl font-extrabold tracking-tight text-white">
            {mode === "signup"
              ? "Create Studio Account"
              : mode === "otp"
              ? "Enter Verification OTP"
              : "Access DIVA Studio"}
          </h2>
          <p className="mt-2 text-sm text-zinc-400">
            {mode === "signup"
              ? "Join and generate high-end AI portraits"
              : mode === "otp"
              ? "Check your inbox for the 6-digit passcode"
              : "Manage and track your custom AI generation history"}
          </p>
        </div>

        {/* Notifications & Error Alerts */}
        {infoMessage && (
          <div className="mb-4 rounded-xl bg-purple-950/40 border border-purple-800/60 p-3.5 text-xs text-purple-200 flex items-start space-x-2 relative z-10 animate-fade-in">
            <span className="text-base leading-none">✉️</span>
            <div>
              <p className="font-semibold text-purple-100">OTP Sent to Email</p>
              <p className="mt-0.5 opacity-90">{infoMessage}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-xl bg-red-950/40 border border-red-900/60 p-3 text-xs text-red-300 relative z-10 animate-fade-in">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
          {mode === "signup" && (
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

          {mode !== "otp" && (
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
          )}

          {mode !== "otp" && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  Password
                </label>
                {mode === "login" && (
                  <button
                    type="button"
                    onClick={handleRequestOtp}
                    className="text-xs text-purple-400 hover:text-purple-300 transition"
                  >
                    Login with OTP code instead?
                  </button>
                )}
              </div>
              <input
                type="password"
                required={mode !== "otp"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition"
              />
            </div>
          )}

          {/* OTP Code Entry Mode */}
          {mode === "otp" && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-purple-400 mb-1.5">
                  6-Digit OTP Code
                </label>
                <input
                  type="text"
                  required
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder="123456"
                  className="w-full rounded-xl border border-purple-500/50 bg-purple-950/20 px-4 py-3 text-center text-xl font-mono tracking-widest text-white placeholder-zinc-600 focus:border-purple-400 focus:outline-none transition"
                />
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={resendingOtp}
                  className="text-purple-400 hover:text-purple-300 hover:underline disabled:opacity-50"
                >
                  {resendingOtp ? "Resending..." : "Didn't receive code? Resend OTP"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode("login");
                    setError(null);
                    setInfoMessage(null);
                  }}
                  className="text-zinc-400 hover:text-zinc-200 transition"
                >
                  ← Back to Email & Password
                </button>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 py-3 text-sm font-bold tracking-wider text-white shadow-lg shadow-purple-950/30 transition hover:opacity-90 disabled:opacity-40 uppercase"
          >
            {loading
              ? "Processing..."
              : mode === "signup"
              ? "Create Account"
              : mode === "otp"
              ? "Verify OTP & Access Studio"
              : "Access Studio"}
          </button>
        </form>

        {/* Social OAuth Buttons */}
        <div className="mt-6 relative z-10">
          <div className="relative flex py-2 items-center">
            <div className="flex-grow border-t border-zinc-800"></div>
            <span className="flex-shrink mx-4 text-xs font-semibold uppercase text-zinc-500 tracking-wider">
              Or continue with
            </span>
            <div className="flex-grow border-t border-zinc-800"></div>
          </div>

          <div className="grid grid-cols-2 gap-3 mt-3">
            <button
              type="button"
              onClick={() => handleOAuthLogin("google")}
              disabled={loading}
              className="flex items-center justify-center space-x-2 rounded-xl border border-zinc-800 bg-zinc-900/60 py-2.5 px-4 text-xs font-semibold text-zinc-200 hover:bg-zinc-800 hover:border-zinc-700 transition disabled:opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path
                  fill="#EA4335"
                  d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.4 9 5 12 5z"
                />
                <path
                  fill="#4285F4"
                  d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.6h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.9z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.6 14.8c-.2-.7-.4-1.5-.4-2.3s.2-1.6.4-2.3L1.9 7.3C.7 9.7 0 10.8 0 12.5s.7 2.8 1.9 5.2l3.7-2.9z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.4-6.4-5.2L1.9 16c1.8 3.7 5.6 7 10.1 7z"
                />
              </svg>
              <span>Google</span>
            </button>

            <button
              type="button"
              onClick={() => handleOAuthLogin("github")}
              disabled={loading}
              className="flex items-center justify-center space-x-2 rounded-xl border border-zinc-800 bg-zinc-900/60 py-2.5 px-4 text-xs font-semibold text-zinc-200 hover:bg-zinc-800 hover:border-zinc-700 transition disabled:opacity-50"
            >
              <svg className="w-4 h-4 fill-current text-white" viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              <span>GitHub</span>
            </button>
          </div>
        </div>

        {/* Footer Mode Switcher */}
        <div className="mt-8 text-center relative z-10 border-t border-zinc-900 pt-5">
          <button
            onClick={() => {
              setError(null);
              setInfoMessage(null);
              setMode(mode === "login" ? "signup" : "login");
            }}
            className="text-xs font-medium text-purple-400 hover:text-purple-300 transition hover:underline"
          >
            {mode === "signup"
              ? "Already registered? Sign in here"
              : "New to DIVA? Create an account here"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center py-12 px-6">
          <div className="text-zinc-400 animate-pulse text-sm font-semibold uppercase tracking-wider">
            Loading authentication form...
          </div>
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
