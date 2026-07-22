"use client";

import { useState } from "react";
import Link from "next/link";
import { createPost, type Post } from "@/lib/api";

type PublishDialogProps = {
  jobId: string;
  onClose: () => void;
};

export default function PublishDialog({ jobId, onClose }: PublishDialogProps) {
  const [caption, setCaption] = useState("");
  const [visibility, setVisibility] = useState<"public" | "private">("public");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [published, setPublished] = useState<Post | null>(null);

  async function handlePublish(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const post = await createPost(jobId, caption.trim() || undefined, visibility);
      setPublished(post);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950/95 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {published ? (
          <div className="text-center">
            <h2 className="text-lg font-bold text-zinc-100">Shared! 🎉</h2>
            <p className="mt-2 text-sm text-zinc-400">
              Your creation is {published.visibility === "public" ? "live on the feed" : "saved privately"}.
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <Link
                href={`/p/${published.id}`}
                className="rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition"
              >
                View post
              </Link>
              <button
                onClick={onClose}
                className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-2.5 text-sm font-semibold text-zinc-300 hover:bg-zinc-900 transition"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handlePublish}>
            <h2 className="text-lg font-bold text-zinc-100">Share to feed</h2>

            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="Write a caption... (optional)"
              className="mt-4 w-full rounded-xl border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none transition resize-none"
            />

            <label className="mt-3 flex items-center justify-between text-sm text-zinc-400">
              Visibility
              <select
                value={visibility}
                onChange={(e) => setVisibility(e.target.value as "public" | "private")}
                className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 focus:border-purple-500 focus:outline-none"
              >
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>
            </label>

            {error && (
              <p className="mt-3 rounded-lg bg-red-950/20 border border-red-900/40 p-2.5 text-xs text-red-400">
                {error}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-2 text-sm font-semibold text-zinc-300 hover:bg-zinc-900 transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2 text-sm font-bold text-white disabled:opacity-40 hover:opacity-90 transition"
              >
                {submitting ? "Sharing..." : "Share"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
