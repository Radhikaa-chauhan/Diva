"use client";

import Link from "next/link";
import { useState } from "react";
import {
  likePost,
  unlikePost,
  savePost,
  unsavePost,
  type Post,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function PostCard({ post }: { post: Post }) {
  const { isLoggedIn } = useAuth();
  const router = useRouter();

  const [isLiked, setIsLiked] = useState(post.is_liked);
  const [likesCount, setLikesCount] = useState(post.likes_count);
  const [isSaved, setIsSaved] = useState(post.is_saved);

  async function toggleLike() {
    if (!isLoggedIn) return router.push("/login");
    // Optimistic update; revert on failure
    const wasLiked = isLiked;
    setIsLiked(!wasLiked);
    setLikesCount((c) => c + (wasLiked ? -1 : 1));
    try {
      const result = wasLiked ? await unlikePost(post.id) : await likePost(post.id);
      setIsLiked(result.is_liked);
      setLikesCount(result.likes_count);
    } catch {
      setIsLiked(wasLiked);
      setLikesCount((c) => c + (wasLiked ? 1 : -1));
    }
  }

  async function toggleSave() {
    if (!isLoggedIn) return router.push("/login");
    const wasSaved = isSaved;
    setIsSaved(!wasSaved);
    try {
      const result = wasSaved ? await unsavePost(post.id) : await savePost(post.id);
      setIsSaved(result.is_saved);
    } catch {
      setIsSaved(wasSaved);
    }
  }

  const profileHref = post.author.username ? `/u/${post.author.username}` : null;

  return (
    <article className="glass overflow-hidden rounded-2xl border border-zinc-800/80">
      {/* Author header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-pink-600 text-xs font-bold text-white uppercase">
          {post.author.display_name[0]}
        </div>
        <div className="min-w-0">
          {profileHref ? (
            <Link href={profileHref} className="block truncate text-sm font-semibold text-zinc-200 hover:text-purple-400 transition">
              {post.author.display_name}
            </Link>
          ) : (
            <span className="block truncate text-sm font-semibold text-zinc-200">
              {post.author.display_name}
            </span>
          )}
          {post.author.username && (
            <span className="block truncate text-xs text-zinc-500">@{post.author.username}</span>
          )}
        </div>
      </div>

      {/* Image */}
      <Link href={`/p/${post.id}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={post.image_url}
          alt={post.caption ?? "AI generated image"}
          className="aspect-[4/5] w-full object-cover"
          loading="lazy"
        />
      </Link>

      {/* Actions */}
      <div className="flex items-center gap-4 px-4 pt-3">
        <button
          onClick={toggleLike}
          className={`flex items-center gap-1.5 text-sm font-medium transition ${
            isLiked ? "text-pink-500" : "text-zinc-400 hover:text-pink-400"
          }`}
          aria-label={isLiked ? "Unlike" : "Like"}
        >
          <svg className="h-5 w-5" fill={isLiked ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
          {likesCount}
        </button>

        <Link
          href={`/p/${post.id}`}
          className="flex items-center gap-1.5 text-sm font-medium text-zinc-400 hover:text-purple-400 transition"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          {post.comments_count}
        </Link>

        <button
          onClick={toggleSave}
          className={`ml-auto transition ${isSaved ? "text-amber-400" : "text-zinc-400 hover:text-amber-300"}`}
          aria-label={isSaved ? "Unsave" : "Save"}
        >
          <svg className="h-5 w-5" fill={isSaved ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
          </svg>
        </button>
      </div>

      {/* Caption + use-this-style */}
      <div className="px-4 pb-4 pt-2">
        {post.caption && <p className="text-sm text-zinc-300">{post.caption}</p>}
        {post.reference_photo_id && (
          <Link
            href={`/?ref=${post.reference_photo_id}`}
            className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-purple-800/50 bg-purple-900/30 px-3 py-1 text-xs font-semibold text-purple-300 hover:bg-purple-900/50 transition"
          >
            ✨ Use this style
          </Link>
        )}
      </div>
    </article>
  );
}
