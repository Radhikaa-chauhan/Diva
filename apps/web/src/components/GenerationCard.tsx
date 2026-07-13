"use client";

import { useState } from "react";
import { type JobHistoryItem, toggleFavorite, deleteGeneration } from "@/lib/api";

type GenerationCardProps = {
  item: JobHistoryItem;
  onUpdate: () => void;
  onViewDetails: (item: JobHistoryItem) => void;
};

export default function GenerationCard({ item, onUpdate, onViewDetails }: GenerationCardProps) {
  const [isFaving, setIsFaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleFavorite = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsFaving(true);
    try {
      await toggleFavorite(item.id);
      onUpdate();
    } catch (err) {
      alert("Failed to update favorite status");
    } finally {
      setIsFaving(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this generation from your history?")) return;
    setIsDeleting(true);
    try {
      await deleteGeneration(item.id);
      onUpdate();
    } catch (err) {
      alert("Failed to delete generation");
    } finally {
      setIsDeleting(false);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return dateStr;
    }
  };

  const getStatusBadge = () => {
    switch (item.status) {
      case "complete":
        return (
          <span className="rounded-full bg-emerald-950/60 border border-emerald-800/50 px-2 py-0.5 text-xxs font-semibold uppercase tracking-wider text-emerald-400">
            Success
          </span>
        );
      case "failed":
        return (
          <span className="rounded-full bg-red-950/60 border border-red-800/50 px-2 py-0.5 text-xxs font-semibold uppercase tracking-wider text-red-400">
            Failed
          </span>
        );
      case "generating":
        return (
          <span className="rounded-full bg-blue-950/60 border border-blue-800/50 px-2 py-0.5 text-xxs font-semibold uppercase tracking-wider text-blue-400 animate-pulse">
            Generating
          </span>
        );
      case "quality_check":
        return (
          <span className="rounded-full bg-amber-950/60 border border-amber-800/50 px-2 py-0.5 text-xxs font-semibold uppercase tracking-wider text-amber-400 animate-pulse">
            Verifying
          </span>
        );
      default:
        return (
          <span className="rounded-full bg-zinc-800 border border-zinc-700 px-2 py-0.5 text-xxs font-semibold uppercase tracking-wider text-zinc-400">
            Queued
          </span>
        );
    }
  };

  const mainImageUrl = item.status === "complete" && item.result_urls?.[0]
    ? item.result_urls[0]
    : item.reference_thumbnail || item.selfie_image_url;

  return (
    <div
      onClick={() => onViewDetails(item)}
      className="glass glass-hover group relative flex flex-col overflow-hidden rounded-xl border border-zinc-800/80 cursor-pointer transition-all duration-300 transform hover:-translate-y-1 hover:shadow-lg"
    >
      <div className="relative aspect-[4/5] w-full overflow-hidden bg-zinc-950">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={mainImageUrl}
          alt={item.reference_title}
          className={`h-full w-full object-cover transition-all duration-500 group-hover:scale-103 ${item.status !== 'complete' && item.status !== 'failed' ? 'blur-sm opacity-50' : ''}`}
          loading="lazy"
        />

        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-60 transition-opacity duration-300 group-hover:opacity-75" />

        {/* Top bar indicators */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
          {getStatusBadge()}
          {item.status === "complete" && (
            <button
              onClick={handleFavorite}
              disabled={isFaving}
              className={`rounded-full p-1.5 backdrop-blur-md border transition-all duration-200 ${
                item.is_favorite
                  ? "bg-pink-900/60 border-pink-700/50 text-pink-400"
                  : "bg-black/40 border-white/10 text-zinc-400 hover:text-pink-400 hover:bg-black/60"
              }`}
            >
              <svg
                className={`h-4 w-4 ${item.is_favorite ? "fill-current" : ""}`}
                fill={item.is_favorite ? "currentColor" : "none"}
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
                />
              </svg>
            </button>
          )}
        </div>

        {/* Loading shimmer for generating states */}
        {(item.status === "generating" || item.status === "quality_check") && (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-4">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-6 w-6 bg-purple-500"></span>
            </div>
            <p className="mt-3 text-xs font-semibold text-purple-300 tracking-wide uppercase">
              Rendering AI Image
            </p>
          </div>
        )}
      </div>

      <div className="p-4 bg-zinc-900/40 backdrop-blur-xs flex flex-col justify-between flex-1">
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
            {item.reference_title}
          </h4>
          <span className="text-xxs text-zinc-500 font-mono">
            {formatDate(item.created_at)}
          </span>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-zinc-800/40 pt-3">
          <span className="text-xxs text-purple-400 font-semibold uppercase tracking-wider group-hover:underline">
            View Details
          </span>
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="text-zinc-500 hover:text-red-400 p-1 rounded hover:bg-zinc-800/40 transition"
            title="Delete generation"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
