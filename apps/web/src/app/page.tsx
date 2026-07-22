"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  createJob,
  fetchJob,
  fetchReferences,
  type Job,
  type JobStatus,
  type ReferencePhoto,
} from "@/lib/api";
import StyleCard from "@/components/StyleCard";
import UploadZone from "@/components/UploadZone";
import PublishDialog from "@/components/PublishDialog";

const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "Securing your spot in the generation queue...",
  generating: "Applying style details and rendering pixels...",
  quality_check: "Verifying image composition and quality gates...",
  complete: "Production successful!",
  failed: "Generation failed",
};

const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 15000;
const POLL_MAX_ATTEMPTS = 60;

export default function Home() {
  const { isLoggedIn } = useAuth();
  const router = useRouter();

  const [references, setReferences] = useState<ReferencePhoto[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selected, setSelected] = useState<ReferencePhoto | null>(null);
  const [selfieFile, setSelfieFile] = useState<File | null>(null);
  const [selfiePreviewUrl, setSelfiePreviewUrl] = useState<string | null>(null);
  const [consented, setConsented] = useState(false);

  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("All");
  const [showPublish, setShowPublish] = useState(false);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetchReferences()
      .then((refs) => {
        setReferences(refs);
        // Deep link from a post's "Use this style" button: /?ref=<id>
        const refId = new URLSearchParams(window.location.search).get("ref");
        if (refId) {
          const match = refs.find((r) => r.id === refId);
          if (match) setSelected(match);
        }
      })
      .catch((err: Error) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    if (!jobId) return;

    let attemptCount = 0;
    let currentInterval = POLL_INITIAL_MS;

    const poll = async () => {
      attemptCount++;
      try {
        const result = await fetchJob(jobId);
        setJob(result);
        if (result.status === "complete" || result.status === "failed") {
          return; // Stop polling
        }
      } catch (err) {
        setSubmitError((err as Error).message);
        return; // Stop polling on error
      }

      if (attemptCount >= POLL_MAX_ATTEMPTS) {
        setSubmitError("Generation is taking longer than expected. Check your dashboard for updates.");
        return; // Stop polling
      }

      // Exponential backoff: double interval each time, up to max
      currentInterval = Math.min(currentInterval * 1.5, POLL_MAX_MS);
      pollTimer.current = setTimeout(poll, currentInterval);
    };

    poll();
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [jobId]);

  function handleSelfieChange(file: File | null) {
    setSelfieFile(file);
    if (selfiePreviewUrl) URL.revokeObjectURL(selfiePreviewUrl);
    setSelfiePreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  async function handleSubmit() {
    if (!isLoggedIn) {
      router.push("/login?redirect=create");
      return;
    }
    if (!selected || !selfieFile) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const id = await createJob(selected.id, selfieFile);
      setJobId(id);
      setJob({ status: "pending", result_urls: null, error: null });
    } catch (err) {
      setSubmitError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setSelected(null);
    handleSelfieChange(null);
    setConsented(false);
    setJobId(null);
    setJob(null);
    setSubmitError(null);
    setShowPublish(false);
  }

  const collections = ["All", ...Array.from(new Set(references?.map(r => r.collection).filter(Boolean) as string[]))];
  const filteredReferences = references?.filter(r => activeTab === "All" || r.collection === activeTab);

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-12 flex flex-col justify-start">
      {/* Hero Header */}
      {!selected && (
        <div className="text-center mb-12 animate-fade-in">
          <h1 className="bg-gradient-to-r from-purple-400 via-pink-500 to-amber-400 bg-clip-text text-4xl font-extrabold tracking-tight text-transparent sm:text-5xl">
            Stunning Studio Portraits. Instantly.
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-base text-zinc-400">
            Generate high-end editorial and cinematic images matching your look perfectly. Select an inspiration reference, upload your selfie, and watch the transformation.
          </p>
        </div>
      )}

      {/* STEP 1: Select Style */}
      {!selected && (
        <section className="animate-fade-in">
          <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-900 pb-5">
            <h2 className="text-xl font-bold tracking-wide text-zinc-100 flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-900/50 text-xs font-semibold text-purple-400 border border-purple-800/40">
                1
              </span>
              Choose Inspiration Preset
            </h2>

            {/* Filter Tabs */}
            {references && references.length > 0 && (
              <div className="flex flex-wrap gap-1.5 p-1 bg-zinc-900/50 rounded-lg border border-zinc-800">
                {collections.map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`rounded-md px-3 py-1 text-xs font-semibold tracking-wide transition-all ${
                      activeTab === tab
                        ? "bg-purple-600 text-white shadow-sm"
                        : "text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            )}
          </div>

          {loadError && (
            <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-400">
              {loadError}
            </div>
          )}

          {!references && !loadError && (
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="aspect-[4/5] w-full rounded-xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 md:grid-cols-4">
            {filteredReferences?.map((ref) => (
              <StyleCard key={ref.id} style={ref} onSelect={setSelected} />
            ))}
          </div>
        </section>
      )}

      {/* STEP 2: Upload selfie */}
      {selected && !jobId && (
        <section className="max-w-2xl mx-auto w-full animate-fade-in">
          <button
            onClick={reset}
            className="group mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-zinc-500 hover:text-zinc-300 transition"
          >
            <svg
              className="h-4 w-4 transition-transform group-hover:-translate-x-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Choose a different style
          </button>

          <div className="glass rounded-2xl border border-zinc-800/80 p-6 md:p-8">
            <h2 className="text-xl font-bold tracking-wide text-zinc-100 flex items-center gap-2 mb-6">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-900/50 text-xs font-semibold text-purple-400 border border-purple-800/40">
                2
              </span>
              Configure Identity & Source
            </h2>

            <div className="flex flex-col gap-6 md:flex-row">
              {/* Inspiration preview */}
              <div className="w-full md:w-44 shrink-0">
                <div className="relative aspect-[4/5] w-full overflow-hidden rounded-xl border border-zinc-800 shadow-md">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={selected.thumbnail_url}
                    alt={selected.title}
                    className="h-full w-full object-cover"
                  />
                </div>
                <p className="mt-2 text-center text-xs font-semibold text-zinc-400 tracking-wider uppercase">
                  {selected.title}
                </p>
              </div>

              {/* Upload settings */}
              <div className="flex-1 flex flex-col justify-between">
                <UploadZone
                  onFileSelect={handleSelfieChange}
                  selectedFile={selfieFile}
                  previewUrl={selfiePreviewUrl}
                  maxSizeMB={10}
                />

                <div className="mt-5">
                  <label className="flex items-start gap-2.5 text-xs text-zinc-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={consented}
                      onChange={(e) => setConsented(e.target.checked)}
                      className="mt-0.5 rounded border-zinc-800 bg-zinc-950 text-purple-600 focus:ring-purple-500 focus:ring-offset-zinc-950"
                    />
                    <span>
                      I consent to my selfie being processed to generate this rendering. It will be stored temporarily on secure cloud storage.
                    </span>
                  </label>
                </div>

                {submitError && (
                  <div className="mt-4 rounded-lg bg-red-950/20 border border-red-900/40 p-3 text-xs text-red-400">
                    {submitError}
                  </div>
                )}

                <button
                  onClick={handleSubmit}
                  disabled={!selfieFile || !consented || submitting}
                  className="mt-6 w-full rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 py-3 text-sm font-bold tracking-wider text-white shadow-lg shadow-purple-950/30 transition hover:shadow-purple-500/20 disabled:cursor-not-allowed disabled:opacity-40 uppercase"
                >
                  {submitting ? "Initializing engine..." : isLoggedIn ? "Generate My Image" : "Sign In to Generate"}
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* STEP 3: Results & Polling */}
      {jobId && job && (
        <section className="max-w-2xl mx-auto w-full animate-fade-in">
          <div className="glass rounded-2xl border border-zinc-800/80 p-6 md:p-8">
            <h2 className="text-xl font-bold tracking-wide text-zinc-100 flex items-center gap-2 mb-6">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-900/50 text-xs font-semibold text-purple-400 border border-purple-800/40">
                3
              </span>
              Processing Render Output
            </h2>

            {job.status !== "complete" && job.status !== "failed" && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                {/* Custom animation loader */}
                <div className="relative flex h-16 w-16 items-center justify-center mb-6">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-20"></span>
                  <div className="h-10 w-10 animate-spin rounded-full border-4 border-purple-500 border-t-transparent"></div>
                </div>
                
                <h3 className="text-sm font-semibold tracking-wider text-purple-400 uppercase animate-pulse">
                  {job.status === "generating" ? "Rendering AI Frame" : "Validating Image"}
                </h3>
                <p className="mt-2 text-xs text-zinc-500 max-w-sm">
                  {STATUS_LABEL[job.status]}
                </p>
              </div>
            )}

            {job.status === "failed" && (
              <div className="text-center py-8">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-950/40 border border-red-900/40 text-red-400 mb-4">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <h3 className="text-sm font-bold text-red-400 uppercase tracking-wide">
                  Generation Failed
                </h3>
                <p className="mt-2 text-xs text-zinc-500 max-w-md mx-auto">
                  {job.error ?? "An unexpected error occurred during rendering."}
                </p>
                <button
                  onClick={reset}
                  className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/60 px-5 py-2.5 text-xs font-semibold tracking-wide text-zinc-300 hover:bg-zinc-900 transition"
                >
                  Configure and Retry
                </button>
              </div>
            )}

            {job.status === "complete" && job.result_urls && (
              <div className="animate-fade-in">
                <div className="flex flex-col items-center gap-6">
                  {job.result_urls.map((url) => (
                    <div key={url} className="relative w-full max-w-md overflow-hidden rounded-xl border border-zinc-800 shadow-2xl">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={url}
                        alt="Generated result"
                        className="h-auto w-full object-cover"
                      />
                    </div>
                  ))}
                </div>

                <div className="mt-8 flex flex-col sm:flex-row justify-center gap-3 border-t border-zinc-800/60 pt-6">
                  {job.result_urls.map((url) => (
                    <a
                      key={url}
                      href={url}
                      download="diva-portrait.jpg"
                      className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-3 text-sm font-bold tracking-wider text-white shadow-md transition hover:opacity-90 uppercase"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download Render
                    </a>
                  ))}
                  <button
                    onClick={() => setShowPublish(true)}
                    className="flex items-center justify-center gap-2 rounded-xl border border-purple-700/60 bg-purple-900/30 px-6 py-3 text-sm font-bold tracking-wider text-purple-300 hover:bg-purple-900/50 transition uppercase"
                  >
                    Share to Feed
                  </button>
                  <button
                    onClick={reset}
                    className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-6 py-3 text-sm font-semibold tracking-wide text-zinc-300 hover:bg-zinc-900/80 transition"
                  >
                    Start New Image
                  </button>
                </div>

                {showPublish && jobId && (
                  <PublishDialog jobId={jobId} onClose={() => setShowPublish(false)} />
                )}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}