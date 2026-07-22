"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchAdminStats,
  fetchAdminUsers,
  type AdminStats,
  type AdminUser,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

function StatCard({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="glass rounded-xl border border-zinc-800/80 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-zinc-100">{value.toLocaleString()}</p>
      {hint && <p className="mt-0.5 text-xxs text-zinc-600">{hint}</p>}
    </div>
  );
}

function formatDate(s: string | null) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !user?.is_admin) return;
    fetchAdminStats().then(setStats).catch((err: Error) => setError(err.message));
  }, [authLoading, user]);

  useEffect(() => {
    if (authLoading || !user?.is_admin) return;
    const timer = setTimeout(() => {
      fetchAdminUsers(page, query.trim())
        .then((r) => {
          setUsers(r.items);
          setPages(r.pages);
        })
        .catch((err: Error) => setError(err.message));
    }, query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [authLoading, user, page, query]);

  if (!authLoading && !user?.is_admin) {
    return (
      <div className="mx-auto max-w-lg flex-1 px-6 py-24 text-center">
        <h1 className="text-2xl font-bold text-zinc-100">Admins only</h1>
        <p className="mt-3 text-sm text-zinc-400">You don&apos;t have access to this page.</p>
        <Link href="/" className="mt-6 inline-block text-sm font-semibold text-purple-400 hover:text-purple-300 transition">
          ← Back home
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="mb-6 text-xl font-bold tracking-wide text-zinc-100">Admin Dashboard</h1>

      {error && (
        <p className="mb-4 rounded-xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">{error}</p>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats ? (
          <>
            <StatCard label="Total Users" value={stats.total_users} />
            <StatCard label="Active (24h)" value={stats.active_24h} hint="logged in today" />
            <StatCard label="Active (7d)" value={stats.active_7d} hint="logged in this week" />
            <StatCard label="New (7d)" value={stats.new_users_7d} hint="signed up this week" />
            <StatCard label="Verified" value={stats.verified_users} />
            <StatCard label="Generations" value={stats.total_generations} />
            <StatCard label="Posts" value={stats.total_posts} />
          </>
        ) : (
          [...Array(7)].map((_, i) => (
            <div key={i} className="h-20 rounded-xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
          ))
        )}
      </div>

      {/* Users */}
      <section className="mt-10">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">Users</h2>
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setPage(1);
              setQuery(e.target.value);
            }}
            placeholder="Search users..."
            className="w-56 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition"
          />
        </div>

        <div className="overflow-x-auto rounded-xl border border-zinc-800/80">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-900/60 text-xs uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Email</th>
                <th className="px-4 py-3 font-semibold text-right">Gens</th>
                <th className="px-4 py-3 font-semibold text-right">Followers</th>
                <th className="px-4 py-3 font-semibold">Last login</th>
                <th className="px-4 py-3 font-semibold">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-zinc-900/40 transition">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-zinc-200">{u.display_name}</span>
                      {!u.is_email_verified && (
                        <span className="rounded bg-amber-950/50 px-1.5 py-0.5 text-xxs text-amber-500">unverified</span>
                      )}
                      {!u.is_active && (
                        <span className="rounded bg-red-950/50 px-1.5 py-0.5 text-xxs text-red-500">inactive</span>
                      )}
                    </div>
                    {u.username && <span className="text-xs text-zinc-500">@{u.username}</span>}
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{u.email}</td>
                  <td className="px-4 py-3 text-right text-zinc-300">{u.generation_count}</td>
                  <td className="px-4 py-3 text-right text-zinc-300">{u.followers_count}</td>
                  <td className="px-4 py-3 text-zinc-500">{formatDate(u.last_login_at)}</td>
                  <td className="px-4 py-3 text-zinc-500">{formatDate(u.created_at)}</td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-zinc-600">No users found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {pages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-4">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2 text-sm text-zinc-300 disabled:opacity-40 hover:bg-zinc-900 transition"
            >
              Previous
            </button>
            <span className="text-sm text-zinc-500">Page {page} of {pages}</span>
            <button
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
              disabled={page >= pages}
              className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2 text-sm text-zinc-300 disabled:opacity-40 hover:bg-zinc-900 transition"
            >
              Next
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
