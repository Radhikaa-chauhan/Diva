"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchFeed, type Post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PostCard from "@/components/PostCard";

export default function FeedPage() {
  const { isLoggedIn, loading: authLoading } = useAuth();

  const [posts, setPosts] = useState<Post[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !isLoggedIn) return;
    setLoading(true);
    fetchFeed(page)
      .then((result) => {
        setPosts((prev) => (page === 1 ? result.items : [...prev, ...result.items]));
        setPages(result.pages);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page, isLoggedIn, authLoading]);

  if (!authLoading && !isLoggedIn) {
    return (
      <div className="mx-auto max-w-lg flex-1 px-6 py-24 text-center">
        <h1 className="text-2xl font-bold text-zinc-100">Your feed awaits</h1>
        <p className="mt-3 text-sm text-zinc-400">
          Sign in to see creations from people you follow.
        </p>
        <Link
          href="/login"
          className="mt-6 inline-block rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition"
        >
          Sign In
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-lg flex-1 px-4 py-8">
      <h1 className="mb-6 text-xl font-bold tracking-wide text-zinc-100">Feed</h1>

      {error && (
        <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-6">
        {posts.map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
      </div>

      {loading && (
        <div className="flex flex-col gap-6 mt-6">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="aspect-[4/5] w-full rounded-2xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
          ))}
        </div>
      )}

      {!loading && posts.length === 0 && !error && (
        <div className="rounded-2xl border border-zinc-800/80 p-10 text-center">
          <p className="text-sm text-zinc-400">
            Nothing here yet. Generate an image and share it, or find creators to follow.
          </p>
          <Link href="/" className="mt-4 inline-block text-sm font-semibold text-purple-400 hover:text-purple-300 transition">
            Create your first image →
          </Link>
        </div>
      )}

      {!loading && page < pages && (
        <button
          onClick={() => setPage((p) => p + 1)}
          className="mt-8 w-full rounded-xl border border-zinc-800 bg-zinc-900/60 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-900 transition"
        >
          Load more
        </button>
      )}
    </div>
  );
}
