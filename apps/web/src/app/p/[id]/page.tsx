"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  createComment,
  deleteComment,
  fetchComments,
  fetchPost,
  type Comment,
  type Post,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PostCard from "@/components/PostCard";
import EmojiGifPicker from "@/components/EmojiGifPicker";

// A comment that is just a GIF/sticker URL renders as an image. Restricted to
// known media hosts + .gif so arbitrary URLs can't be rendered as <img>.
function gifUrl(text: string): string | null {
  const t = text.trim();
  if (!/^https?:\/\//.test(t) || /\s/.test(t)) return null;
  const ok = /(^https:\/\/media\.tenor\.com\/)|(giphy\.com\/media\/)|(\.gif($|\?))/i.test(t);
  return ok ? t : null;
}

export default function PostDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, isLoggedIn } = useAuth();

  const [post, setPost] = useState<Post | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [commentText, setCommentText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  async function sendComment(text: string) {
    const clean = text.trim();
    if (!clean) return;
    try {
      const comment = await createComment(id, clean);
      setComments((prev) => [...prev, comment]);
      setCommentText("");
      setPost((p) => (p ? { ...p, comments_count: p.comments_count + 1 } : p));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    fetchPost(id).then(setPost).catch((err: Error) => setError(err.message));
    fetchComments(id).then((r) => setComments(r.items)).catch(() => {});
  }, [id]);

  async function handleComment(e: React.FormEvent) {
    e.preventDefault();
    if (!commentText.trim()) return;
    setSubmitting(true);
    await sendComment(commentText);
    setSubmitting(false);
  }

  async function handleDelete(commentId: string) {
    try {
      await deleteComment(commentId);
      setComments((prev) => prev.filter((c) => c.id !== commentId));
      setPost((p) => (p ? { ...p, comments_count: Math.max(0, p.comments_count - 1) } : p));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (error && !post) {
    return (
      <div className="mx-auto max-w-lg flex-1 px-6 py-24 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <Link href="/feed" className="mt-4 inline-block text-sm font-semibold text-purple-400 hover:text-purple-300 transition">
          ← Back to feed
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-lg flex-1 px-4 py-8">
      {!post ? (
        <div className="aspect-[4/5] w-full rounded-2xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
      ) : (
        <PostCard post={post} />
      )}

      {/* Comments */}
      <section className="mt-6">
        <h2 className="mb-4 text-sm font-bold uppercase tracking-wider text-zinc-400">
          Comments
        </h2>

        <div className="flex flex-col gap-4">
          {comments.map((comment) => {
            const canDelete =
              isLoggedIn &&
              (comment.author.id === user?.id || post?.author.id === user?.id);
            return (
              <div key={comment.id} className="flex items-start gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-pink-600 text-xs font-bold text-white uppercase">
                  {comment.author.display_name[0]}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-zinc-300">
                    {comment.author.username ? (
                      <Link href={`/u/${comment.author.username}`} className="hover:text-purple-400 transition">
                        {comment.author.display_name}
                      </Link>
                    ) : (
                      comment.author.display_name
                    )}
                  </p>
                  {gifUrl(comment.text) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={gifUrl(comment.text)!}
                      alt="GIF comment"
                      className="mt-1 max-w-[200px] rounded-lg border border-zinc-800"
                      loading="lazy"
                    />
                  ) : (
                    <p className="text-sm text-zinc-400 break-words">{comment.text}</p>
                  )}
                </div>
                {canDelete && (
                  <button
                    onClick={() => handleDelete(comment.id)}
                    className="text-xs text-zinc-600 hover:text-red-400 transition"
                    aria-label="Delete comment"
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })}

          {comments.length === 0 && (
            <p className="text-sm text-zinc-600">No comments yet. Be the first.</p>
          )}
        </div>

        {/* Composer */}
        {isLoggedIn ? (
          <form onSubmit={handleComment} className="relative mt-5 flex gap-2">
            <div className="relative flex flex-1 items-center rounded-xl border border-zinc-800 bg-zinc-950/50 focus-within:border-purple-500 transition">
              <input
                type="text"
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                maxLength={500}
                placeholder="Add a comment..."
                className="flex-1 bg-transparent px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setPickerOpen((o) => !o)}
                className="px-3 text-lg text-zinc-400 hover:text-purple-400 transition"
                aria-label="Emoji, GIFs and stickers"
              >
                😊
              </button>
              {pickerOpen && (
                <EmojiGifPicker
                  onEmoji={(e) => setCommentText((t) => (t + e).slice(0, 500))}
                  onGif={(url) => sendComment(url)}
                  onClose={() => setPickerOpen(false)}
                />
              )}
            </div>
            <button
              type="submit"
              disabled={submitting || !commentText.trim()}
              className="rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40 hover:opacity-90 transition"
            >
              Post
            </button>
          </form>
        ) : (
          <p className="mt-5 text-sm text-zinc-500">
            <Link href="/login" className="font-semibold text-purple-400 hover:text-purple-300 transition">
              Sign in
            </Link>{" "}
            to comment.
          </p>
        )}

        {error && post && (
          <p className="mt-3 text-xs text-red-400">{error}</p>
        )}
      </section>
    </div>
  );
}
