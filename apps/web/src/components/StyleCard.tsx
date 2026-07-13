"use client";

import { type ReferencePhoto } from "@/lib/api";

type StyleCardProps = {
  style: ReferencePhoto;
  onSelect: (style: ReferencePhoto) => void;
};

export default function StyleCard({ style, onSelect }: StyleCardProps) {
  return (
    <button
      onClick={() => onSelect(style)}
      className="glass glass-hover group relative flex flex-col overflow-hidden rounded-xl border border-zinc-800/80 text-left transition-all duration-300 transform hover:-translate-y-1 hover:shadow-lg focus:outline-none"
    >
      <div className="relative aspect-[4/5] w-full overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={style.thumbnail_url}
          alt={style.title}
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-60 transition-opacity duration-300 group-hover:opacity-80" />
        
        {style.collection && (
          <span className="absolute top-3 left-3 rounded-full bg-purple-950/70 border border-purple-800/60 px-2.5 py-0.5 text-xxs font-medium uppercase tracking-wider text-purple-300 backdrop-blur-md">
            {style.collection}
          </span>
        )}
      </div>

      <div className="p-4 bg-zinc-900/50 backdrop-blur-sm flex-1 flex flex-col justify-end">
        <h3 className="text-sm font-semibold tracking-wide text-zinc-100 group-hover:text-purple-400 transition-colors">
          {style.title}
        </h3>
        <p className="mt-1 text-xxs text-zinc-400 font-medium uppercase tracking-widest flex items-center gap-1">
          Select style
          <svg
            className="h-3 w-3 text-purple-500 transition-transform duration-300 group-hover:translate-x-1"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </p>
      </div>
    </button>
  );
}
