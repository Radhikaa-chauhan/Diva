"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchExplore,
  searchPosts,
  searchUsers,
  type AuthorSummary,
  type Post,
} from "@/lib/api";
import PostCard from "@/components/PostCard";

export default function ExplorePage() {
  const [query, setQuery] = useState("");
  const [posts, setPosts] = useState<Post[]>([]);
  const [users, setUsers] = useState<AuthorSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Explore grid (no query) — load once.
  useEffect(() => {
    if (query.trim()) return;
    setLoading(true);
    fetchExplore()
      .then((r) => setPosts(r.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [query]);

  // Search (debounced) — runs when there's a query.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setUsers([]);
      return;
    }
    setLoading(true);
    const timer = setTimeout(() => {
      Promise.all([searchUsers(q), searchPosts(q)])
        .then(([u, p]) => {
          setUsers(u.items);
          setPosts(p.items);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const searching = query.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
      <h1 className="mb-5 text-xl font-bold tracking-wide text-zinc-100">Explore</h1>

      {/* Search */}
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search people and posts..."
        className="w-full rounded-xl border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition"
      />

      {error && (
        <p className="mt-4 rounded-xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">
          {error}
        </p>
      )}

      {/* User results (search only) */}
      {searching && users.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-zinc-500">People</h2>
          <div className="flex flex-col gap-2">
            {users.map((u) => (
              <Link
                key={u.id}
                href={u.username ? `/u/${u.username}` : "#"}
                className="flex items-center gap-3 rounded-xl border border-zinc-800/60 p-3 hover:bg-zinc-900/50 transition"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-pink-600 text-sm font-bold text-white uppercase">
                  {u.display_name[0]}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-zinc-200">{u.display_name}</p>
                  {u.username && <p className="truncate text-xs text-zinc-500">@{u.username}</p>}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Posts: explore grid, or post search results */}
      <section className="mt-6">
        {searching && (
          <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-zinc-500">Posts</h2>
        )}

        {loading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="aspect-[4/5] w-full rounded-xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
            ))}
          </div>
        ) : posts.length === 0 ? (
          <p className="py-12 text-center text-sm text-zinc-600">
            {searching ? "No matches." : "No public posts yet."}
          </p>
        ) : searching ? (
          // Compact grid for search results
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {posts.map((post) => (
              <Link key={post.id} href={`/p/${post.id}`} className="group block overflow-hidden rounded-xl border border-zinc-800/60">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={post.image_url}
                  alt={post.caption ?? "Post"}
                  className="aspect-[4/5] w-full object-cover transition group-hover:scale-105"
                  loading="lazy"
                />
              </Link>
            ))}
          </div>
        ) : (
          // Full cards for the explore feed
          <div className="flex flex-col gap-6">
            {posts.map((post) => (
              <PostCard key={post.id} post={post} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
