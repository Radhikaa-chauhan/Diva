"use client";

import { useEffect, useState } from "react";
import { fetchFollowing, sharePost, type AuthorSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Avatar from "@/components/Avatar";

export default function ShareDialog({ postId, onClose }: { postId: string; onClose: () => void }) {
  const { user } = useAuth();
  const [friends, setFriends] = useState<AuthorSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    fetchFollowing(user.id)
      .then((r) => setFriends(r.items))
      .catch((e: Error) => setError(e.message));
  }, [user]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function send() {
    if (selected.size === 0) return;
    setSending(true);
    setError(null);
    try {
      const res = await sharePost(postId, [...selected]);
      setDone(res.shared_with);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="glass w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950/95 p-6" onClick={(e) => e.stopPropagation()}>
        {done !== null ? (
          <div className="text-center">
            <h2 className="text-lg font-bold text-zinc-100">Sent! 🚀</h2>
            <p className="mt-2 text-sm text-zinc-400">Shared with {done} {done === 1 ? "friend" : "friends"}.</p>
            <button onClick={onClose} className="mt-6 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition">
              Done
            </button>
          </div>
        ) : (
          <>
            <h2 className="text-lg font-bold text-zinc-100">Share with friends</h2>
            <p className="mt-1 text-xs text-zinc-500">Send this to people you follow.</p>

            {error && <p className="mt-3 rounded-lg bg-red-950/20 border border-red-900/40 p-2.5 text-xs text-red-400">{error}</p>}

            <div className="mt-4 max-h-64 overflow-y-auto flex flex-col gap-1">
              {friends.length === 0 ? (
                <p className="py-6 text-center text-sm text-zinc-600">You aren&apos;t following anyone yet.</p>
              ) : (
                friends.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => toggle(f.id)}
                    className={`flex items-center gap-3 rounded-xl border p-2.5 text-left transition ${
                      selected.has(f.id) ? "border-purple-600 bg-purple-900/20" : "border-zinc-800/60 hover:bg-zinc-900/50"
                    }`}
                  >
                    <Avatar src={f.avatar_url} name={f.display_name} size={32} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-zinc-200">{f.display_name}</p>
                      {f.username && <p className="truncate text-xs text-zinc-500">@{f.username}</p>}
                    </div>
                    {selected.has(f.id) && <span className="text-purple-400">✓</span>}
                  </button>
                ))
              )}
            </div>

            <div className="mt-5 flex justify-end gap-3">
              <button onClick={onClose} className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-2 text-sm font-semibold text-zinc-300 hover:bg-zinc-900 transition">
                Cancel
              </button>
              <button
                onClick={send}
                disabled={sending || selected.size === 0}
                className="rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2 text-sm font-bold text-white disabled:opacity-40 hover:opacity-90 transition"
              >
                {sending ? "Sending..." : `Send${selected.size ? ` (${selected.size})` : ""}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
