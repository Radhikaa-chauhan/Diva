"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  createReference,
  deleteReference,
  draftReferencePrompt,
  fetchAdminReferences,
  updateReference,
  type AdminReference,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminReferencesPage() {
  const { user, loading: authLoading } = useAuth();

  const [refs, setRefs] = useState<AdminReference[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Create form state
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [collection, setCollection] = useState("");
  const [prompt, setPrompt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function loadRefs() {
    fetchAdminReferences().then(setRefs).catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    if (authLoading || !user?.is_admin) return;
    loadRefs();
  }, [authLoading, user]);

  function pickImage(file: File | null) {
    setImage(file);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(file ? URL.createObjectURL(file) : null);
  }

  async function autoWrite() {
    if (!image) return;
    setDrafting(true);
    setError(null);
    try {
      const draft = await draftReferencePrompt(image);
      setPrompt(draft.prompt_template);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDrafting(false);
    }
  }

  async function save() {
    if (!image || !title.trim() || !prompt.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createReference({ image, title: title.trim(), prompt_template: prompt.trim(), collection: collection.trim() || undefined });
      setTitle("");
      setCollection("");
      setPrompt("");
      pickImage(null);
      if (fileRef.current) fileRef.current.value = "";
      loadRefs();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(r: AdminReference) {
    try {
      const updated = await updateReference(r.id, { active: !r.active });
      setRefs((prev) => prev.map((x) => (x.id === r.id ? updated : x)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(r: AdminReference) {
    if (!confirm(`Delete "${r.title}"? This can't be undone.`)) return;
    try {
      await deleteReference(r.id);
      setRefs((prev) => prev.filter((x) => x.id !== r.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!authLoading && !user?.is_admin) {
    return (
      <div className="mx-auto max-w-lg flex-1 px-6 py-24 text-center">
        <h1 className="text-2xl font-bold text-zinc-100">Admins only</h1>
        <Link href="/" className="mt-6 inline-block text-sm font-semibold text-purple-400 hover:text-purple-300 transition">← Back home</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-wide text-zinc-100">Reference Styles</h1>
        <Link href="/admin" className="text-sm font-semibold text-purple-400 hover:text-purple-300 transition">← Dashboard</Link>
      </div>

      {error && <p className="mb-4 rounded-xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">{error}</p>}

      {/* Create form */}
      <section className="glass mb-10 rounded-2xl border border-zinc-800/80 p-5">
        <h2 className="mb-4 text-sm font-bold uppercase tracking-wider text-zinc-400">Add a reference</h2>
        <div className="flex flex-col gap-4 sm:flex-row">
          {/* Image */}
          <div className="w-full sm:w-44 shrink-0">
            <label className="block aspect-[4/5] w-full cursor-pointer overflow-hidden rounded-xl border border-dashed border-zinc-700 bg-zinc-950/50 hover:border-purple-500 transition">
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="preview" className="h-full w-full object-cover" />
              ) : (
                <span className="flex h-full items-center justify-center text-xs text-zinc-500">Click to upload image</span>
              )}
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => pickImage(e.target.files?.[0] ?? null)} />
            </label>
          </div>

          {/* Fields */}
          <div className="flex flex-1 flex-col gap-3">
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="Title (e.g. Golden Hour Editorial)"
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none" />
            <input value={collection} onChange={(e) => setCollection(e.target.value)} maxLength={100} placeholder="Collection (optional, e.g. Editorial)"
              className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none" />
            <div className="relative">
              <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={2000} rows={4} placeholder="Hidden prompt — describe the style/scene to apply while keeping the user's face..."
                className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none" />
              <button type="button" onClick={autoWrite} disabled={!image || drafting}
                className="absolute bottom-2 right-2 rounded-md border border-purple-800/60 bg-purple-900/40 px-2 py-1 text-xs font-semibold text-purple-300 disabled:opacity-40 hover:bg-purple-900/60 transition">
                {drafting ? "Writing…" : "✨ Auto-write from image"}
              </button>
            </div>
            <button onClick={save} disabled={saving || !image || !title.trim() || !prompt.trim()}
              className="self-start rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2 text-sm font-bold text-white disabled:opacity-40 hover:opacity-90 transition">
              {saving ? "Saving…" : "Save reference"}
            </button>
          </div>
        </div>
      </section>

      {/* Existing references */}
      <section>
        <h2 className="mb-4 text-sm font-bold uppercase tracking-wider text-zinc-400">All references ({refs.length})</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {refs.map((r) => (
            <div key={r.id} className={`flex gap-3 rounded-xl border p-3 ${r.active ? "border-zinc-800/60" : "border-zinc-800/40 opacity-60"}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={r.thumbnail_url} alt={r.title} className="h-20 w-16 shrink-0 rounded-lg object-cover" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-zinc-200">{r.title}</p>
                {r.collection && <p className="text-xs text-zinc-500">{r.collection}</p>}
                <p className="mt-1 line-clamp-2 text-xs text-zinc-600">{r.prompt_template}</p>
                <div className="mt-2 flex gap-3 text-xs">
                  <button onClick={() => toggleActive(r)} className={r.active ? "text-amber-400 hover:text-amber-300" : "text-emerald-400 hover:text-emerald-300"}>
                    {r.active ? "Deactivate" : "Activate"}
                  </button>
                  <button onClick={() => remove(r)} className="text-red-400 hover:text-red-300">Delete</button>
                </div>
              </div>
            </div>
          ))}
          {refs.length === 0 && <p className="text-sm text-zinc-600">No references yet.</p>}
        </div>
      </section>
    </div>
  );
}
