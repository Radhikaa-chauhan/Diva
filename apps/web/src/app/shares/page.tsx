"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchShares, markSharesRead, type SharedPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Avatar from "@/components/Avatar";

export default function SharesPage() {
  const { isLoggedIn, loading: authLoading } = useAuth();
  const [shares, setShares] = useState<SharedPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !isLoggedIn) return;
    fetchShares()
      .then((r) => {
        setShares(r.items);
        return markSharesRead(); // opening the inbox clears the unread badge
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [authLoading, isLoggedIn]);

  if (!authLoading && !isLoggedIn) {
    return (
      <div className="mx-auto max-w-lg flex-1 px-6 py-24 text-center">
        <h1 className="text-2xl font-bold text-zinc-100">Shared with you</h1>
        <p className="mt-3 text-sm text-zinc-400">Sign in to see posts your friends sent you.</p>
        <Link href="/login" className="mt-6 inline-block rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition">
          Sign In
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-lg flex-1 px-4 py-8">
      <h1 className="mb-6 text-xl font-bold tracking-wide text-zinc-100">Shared with you</h1>

      {error && <p className="rounded-xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">{error}</p>}

      {loading ? (
        <div className="flex flex-col gap-3">
          {[...Array(3)].map((_, i) => <div key={i} className="h-20 rounded-xl bg-zinc-900 animate-pulse border border-zinc-800/60" />)}
        </div>
      ) : shares.length === 0 ? (
        <div className="rounded-2xl border border-zinc-800/80 p-10 text-center">
          <p className="text-sm text-zinc-400">Nothing shared with you yet.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {shares.map((s) => (
            <Link
              key={s.share_id}
              href={`/p/${s.post.id}`}
              className={`flex items-center gap-3 rounded-xl border p-3 transition hover:bg-zinc-900/50 ${
                s.is_read ? "border-zinc-800/60" : "border-purple-800/50 bg-purple-900/10"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={s.post.image_url} alt="" className="h-16 w-16 shrink-0 rounded-lg object-cover" loading="lazy" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Avatar src={s.sender.avatar_url} name={s.sender.display_name} size={20} />
                  <span className="truncate text-sm text-zinc-300">
                    <strong className="text-zinc-100">{s.sender.display_name}</strong> shared a post
                  </span>
                </div>
                {s.post.caption && <p className="mt-1 truncate text-xs text-zinc-500">{s.post.caption}</p>}
              </div>
              {!s.is_read && <span className="h-2 w-2 shrink-0 rounded-full bg-purple-500" />}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
