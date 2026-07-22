"use client";

import { useEffect, useState } from "react";

// Curated emoji set — offline, no dependency. Extend the array to add more.
const EMOJIS = [
  "😀", "😂", "🥹", "😍", "😎", "🤩", "🥳", "😭", "😅", "😉",
  "🙌", "👏", "🔥", "✨", "💯", "❤️", "💜", "🩷", "👍", "👎",
  "🙏", "💪", "👀", "🎉", "🌈", "⭐", "💫", "🥰", "😇", "🤗",
  "😱", "🤯", "😴", "🤔", "🙈", "💅", "👑", "🦋", "🌸", "🍿",
];

const TENOR_KEY = process.env.NEXT_PUBLIC_TENOR_KEY;
type Tab = "emoji" | "gif" | "sticker";
type TenorResult = { id: string; media_formats: { tinygif?: { url: string }; gif?: { url: string } } };

async function tenor(kind: "gif" | "sticker", query: string): Promise<string[]> {
  if (!TENOR_KEY) return [];
  const base = query.trim()
    ? `https://tenor.googleapis.com/v2/search?q=${encodeURIComponent(query)}`
    : `https://tenor.googleapis.com/v2/featured?`;
  const sticker = kind === "sticker" ? "&searchfilter=sticker" : "";
  const url = `${base}&key=${TENOR_KEY}&client_key=diva&limit=24&media_filter=tinygif,gif${sticker}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to load from Tenor");
  const data = await res.json();
  return (data.results as TenorResult[])
    .map((r) => r.media_formats.gif?.url ?? r.media_formats.tinygif?.url)
    .filter((u): u is string => Boolean(u));
}

export default function EmojiGifPicker({
  onEmoji,
  onGif,
  onClose,
}: {
  onEmoji: (emoji: string) => void;
  onGif: (url: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("emoji");
  const [query, setQuery] = useState("");
  const [gifs, setGifs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (tab === "emoji" || !TENOR_KEY) return;
    setLoading(true);
    setError(null);
    const timer = setTimeout(() => {
      tenor(tab, query)
        .then(setGifs)
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    }, query ? 350 : 0);
    return () => clearTimeout(timer);
  }, [tab, query]);

  return (
    <div className="absolute bottom-full right-0 mb-2 w-72 rounded-xl border border-zinc-800 bg-zinc-950 p-2 shadow-2xl z-30">
      {/* Tabs */}
      <div className="mb-2 flex gap-1">
        {(["emoji", "gif", "sticker"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`flex-1 rounded-lg px-2 py-1 text-xs font-semibold capitalize transition ${
              tab === t ? "bg-purple-600 text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "emoji" ? (
        <div className="grid max-h-56 grid-cols-8 gap-0.5 overflow-y-auto">
          {EMOJIS.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => onEmoji(e)}
              className="rounded p-1 text-lg hover:bg-zinc-800 transition"
            >
              {e}
            </button>
          ))}
        </div>
      ) : !TENOR_KEY ? (
        <p className="p-3 text-center text-xs text-zinc-500">
          Set <code className="text-purple-400">NEXT_PUBLIC_TENOR_KEY</code> to enable {tab}s.
          Emojis work without a key.
        </p>
      ) : (
        <>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${tab}s...`}
            className="mb-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none"
          />
          {error && <p className="p-2 text-center text-xs text-red-400">{error}</p>}
          {loading ? (
            <div className="grid grid-cols-3 gap-1">
              {[...Array(9)].map((_, i) => (
                <div key={i} className="aspect-square rounded bg-zinc-900 animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid max-h-56 grid-cols-3 gap-1 overflow-y-auto">
              {gifs.map((url) => (
                <button
                  key={url}
                  type="button"
                  onClick={() => {
                    onGif(url);
                    onClose();
                  }}
                  className="overflow-hidden rounded border border-zinc-800 hover:border-purple-500 transition"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={url} alt="" className="aspect-square w-full object-cover" loading="lazy" />
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
