"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  fetchHistory,
  fetchFavorites,
  fetchDashboardStats,
  type JobHistoryItem,
  type DashboardStats,
} from "@/lib/api";
import GenerationCard from "@/components/GenerationCard";

export default function DashboardPage() {
  const { user } = useAuth();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [items, setItems] = useState<JobHistoryItem[]>([]);
  const [tab, setTab] = useState<"all" | "favorites">("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<JobHistoryItem | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      // Fetch stats
      const statsData = await fetchDashboardStats();
      setStats(statsData);

      // Fetch items
      const paginatedData =
        tab === "all"
          ? await fetchHistory(page, 12)
          : await fetchFavorites(page, 12);
      
      setItems(paginatedData.items);
      setTotalPages(paginatedData.pages);
    } catch (err) {
      console.error("Failed to load dashboard data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [tab, page]);

  const handleUpdate = () => {
    loadData();
    // Update active modal details if open
    if (selectedItem) {
      const updated = items.find(i => i.id === selectedItem.id);
      if (updated) setSelectedItem(updated);
    }
  };

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-10 animate-fade-in">
      <header className="mb-10">
        <h1 className="text-3xl font-extrabold tracking-tight text-white">
          Studio Dashboard
        </h1>
        <p className="mt-1.5 text-sm text-zinc-400">
          Monitor your usage, browse past generation results, and manage your favorites.
        </p>
      </header>

      {/* Metric Cards */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4 mb-10">
        <div className="glass rounded-xl p-5 border border-zinc-800/80">
          <p className="text-xxs font-semibold uppercase tracking-widest text-zinc-500">
            Total Projects
          </p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">
            {stats?.total_generations ?? 0}
          </p>
        </div>
        <div className="glass rounded-xl p-5 border border-zinc-800/80">
          <p className="text-xxs font-semibold uppercase tracking-widest text-zinc-500">
            Successful Renders
          </p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">
            {stats?.completed_generations ?? 0}
          </p>
        </div>
        <div className="glass rounded-xl p-5 border border-zinc-800/80">
          <p className="text-xxs font-semibold uppercase tracking-widest text-zinc-500">
            Favorites
          </p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">
            {stats?.favorites_count ?? 0}
          </p>
        </div>
        <div className="glass rounded-xl p-5 border border-zinc-800/80">
          <p className="text-xxs font-semibold uppercase tracking-widest text-zinc-500">
            Storage Used
          </p>
          <p className="mt-2 text-2xl font-bold text-zinc-100">
            {stats?.storage_used_mb ?? 0} MB
          </p>
        </div>
      </section>

      {/* Main Panel */}
      <section className="glass rounded-2xl border border-zinc-800/80 p-6 md:p-8">
        {/* Toggle + Header */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-900 pb-5">
          <div className="flex gap-1.5 p-1 bg-zinc-950/60 rounded-lg border border-zinc-900">
            <button
              onClick={() => {
                setTab("all");
                setPage(1);
              }}
              className={`rounded-md px-4 py-1.5 text-xs font-semibold tracking-wide transition-all ${
                tab === "all"
                  ? "bg-purple-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              All Generations
            </button>
            <button
              onClick={() => {
                setTab("favorites");
                setPage(1);
              }}
              className={`rounded-md px-4 py-1.5 text-xs font-semibold tracking-wide transition-all ${
                tab === "favorites"
                  ? "bg-purple-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              My Favorites
            </button>
          </div>

          <div className="text-xs text-zinc-500">
            Logged in as <span className="font-semibold text-zinc-300">{user?.display_name}</span>
          </div>
        </div>

        {/* Loading State */}
        {loading && items.length === 0 && (
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="aspect-[4/5] w-full rounded-xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && items.length === 0 && (
          <div className="text-center py-16">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-zinc-900/60 border border-zinc-850 text-zinc-500 mb-4">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="text-sm font-bold text-zinc-300 uppercase tracking-wide">
              No Generations Found
            </h3>
            <p className="mt-2 text-xs text-zinc-500 max-w-sm mx-auto">
              {tab === "all"
                ? "You haven't generated any portraits yet. Head to the generator to start!"
                : "You don't have any favorited portraits yet."}
            </p>
          </div>
        )}

        {/* Grid List */}
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4">
          {items.map((item) => (
            <GenerationCard
              key={item.id}
              item={item}
              onUpdate={handleUpdate}
              onViewDetails={setSelectedItem}
            />
          ))}
        </div>

        {/* Pagination buttons */}
        {totalPages > 1 && (
          <div className="mt-8 flex justify-center gap-2 border-t border-zinc-900 pt-6">
            <button
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3.5 py-1.5 text-xs font-semibold text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
            >
              Previous
            </button>
            <span className="flex items-center text-xs text-zinc-500 font-medium px-2">
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3.5 py-1.5 text-xs font-semibold text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </section>

      {/* Details Lightbox Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm">
          <div className="glass glass-premium max-w-3xl w-full rounded-2xl p-6 md:p-8 border border-zinc-800/80 shadow-2xl relative max-h-[90vh] overflow-y-auto animate-fade-in">
            <button
              onClick={() => setSelectedItem(null)}
              className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-200 p-1.5 rounded-full hover:bg-zinc-800/60"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h3 className="text-xl font-bold tracking-wide text-zinc-100 mb-6 uppercase">
              Project Specification Details
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Left Side: Images */}
              <div>
                <p className="text-xxs font-semibold uppercase tracking-wider text-purple-400 mb-2">
                  Rendering Output
                </p>
                <div className="relative aspect-[4/5] w-full bg-zinc-950 rounded-xl overflow-hidden border border-zinc-800">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={selectedItem.status === "complete" && selectedItem.result_urls?.[0] ? selectedItem.result_urls[0] : selectedItem.selfie_image_url}
                    alt="Output Preview"
                    className="h-full w-full object-cover"
                  />
                </div>
              </div>

              {/* Right Side: Identity, Style description, metadata */}
              <div className="flex flex-col justify-between">
                <div>
                  <div className="mb-4">
                    <p className="text-xxs font-semibold uppercase tracking-wider text-purple-400 mb-1">
                      Reference Type
                    </p>
                    <p className="text-sm font-bold text-zinc-200">
                      {selectedItem.reference_title}
                    </p>
                  </div>

                  <div className="mb-4">
                    <p className="text-xxs font-semibold uppercase tracking-wider text-purple-400 mb-1.5">
                      Input Selfie Source
                    </p>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={selectedItem.selfie_image_url}
                      alt="Selfie source"
                      className="h-20 w-20 rounded-lg object-cover border border-zinc-800"
                    />
                  </div>

                  <div className="mb-4">
                    <p className="text-xxs font-semibold uppercase tracking-wider text-purple-400 mb-1">
                      Render Status
                    </p>
                    <p className="text-xs text-zinc-300 font-medium">
                      {selectedItem.status.toUpperCase()}
                    </p>
                  </div>

                  {selectedItem.error && (
                    <div className="mb-4 rounded-lg bg-red-950/20 border border-red-900/40 p-3 text-xs text-red-400">
                      {selectedItem.error}
                    </div>
                  )}
                </div>

                {selectedItem.status === "complete" && selectedItem.result_urls?.[0] && (
                  <div className="mt-6">
                    <a
                      href={selectedItem.result_urls[0]}
                      download="diva-render.jpg"
                      className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 py-3 text-sm font-bold tracking-wider text-white shadow-lg transition hover:opacity-90 uppercase"
                    >
                      Download Render File
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
