"use client";

import { useEffect, useRef, useState } from "react";
import {
  createJob,
  fetchJob,
  fetchReferences,
  type Job,
  type JobStatus,
  type ReferencePhoto,
} from "@/lib/api";

const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "Queued...",
  generating: "Generating your version...",
  quality_check: "Checking quality...",
  complete: "Done!",
  failed: "Failed",
};

const POLL_INTERVAL_MS = 1500;

export default function Home() {
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

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchReferences()
      .then(setReferences)
      .catch((err: Error) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      try {
        const result = await fetchJob(jobId);
        setJob(result);
        if (result.status === "complete" || result.status === "failed") {
          if (pollTimer.current) clearInterval(pollTimer.current);
        }
      } catch (err) {
        setSubmitError((err as Error).message);
        if (pollTimer.current) clearInterval(pollTimer.current);
      }
    };

    poll();
    pollTimer.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [jobId]);

  function handleSelfieChange(file: File | null) {
    setSelfieFile(file);
    if (selfiePreviewUrl) URL.revokeObjectURL(selfiePreviewUrl);
    setSelfiePreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  async function handleSubmit() {
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
  }

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold">Mirror</h1>
        <p className="text-sm text-neutral-500">
          Pick a style from the library, upload your selfie, get your own version.
        </p>
      </header>

      {!selected && (
        <section>
          <h2 className="mb-4 text-lg font-medium">1. Pick a style</h2>
          {loadError && <p className="text-sm text-red-600">{loadError}</p>}
          {!references && !loadError && <p className="text-sm text-neutral-500">Loading library...</p>}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
            {references?.map((ref) => (
              <button
                key={ref.id}
                onClick={() => setSelected(ref)}
                className="group overflow-hidden rounded-lg border border-neutral-200 text-left transition hover:border-neutral-400 dark:border-neutral-800"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={ref.thumbnail_url}
                  alt={ref.title}
                  className="aspect-[4/5] w-full object-cover"
                />
                <div className="p-2">
                  <p className="text-sm font-medium">{ref.title}</p>
                  {ref.collection && (
                    <p className="text-xs text-neutral-500">{ref.collection}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {selected && !jobId && (
        <section>
          <button
            onClick={reset}
            className="mb-4 text-sm text-neutral-500 underline hover:text-neutral-800"
          >
            &larr; Choose a different style
          </button>
          <h2 className="mb-4 text-lg font-medium">2. Upload your selfie</h2>
          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="w-40 shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={selected.thumbnail_url}
                alt={selected.title}
                className="aspect-[4/5] w-full rounded-lg object-cover"
              />
              <p className="mt-1 text-xs text-neutral-500">{selected.title}</p>
            </div>

            <div className="flex-1">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => handleSelfieChange(e.target.files?.[0] ?? null)}
                className="block w-full text-sm"
              />

              {selfiePreviewUrl && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={selfiePreviewUrl}
                  alt="Your selfie preview"
                  className="mt-3 h-40 w-40 rounded-lg object-cover"
                />
              )}

              <label className="mt-4 flex items-start gap-2 text-sm text-neutral-600">
                <input
                  type="checkbox"
                  checked={consented}
                  onChange={(e) => setConsented(e.target.checked)}
                  className="mt-0.5"
                />
                I consent to my selfie being used to generate this image. It will be
                stored temporarily and not used for training.
              </label>

              {submitError && <p className="mt-2 text-sm text-red-600">{submitError}</p>}

              <button
                onClick={handleSubmit}
                disabled={!selfieFile || !consented || submitting}
                className="mt-4 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-neutral-900"
              >
                {submitting ? "Starting..." : "Generate my version"}
              </button>
            </div>
          </div>
        </section>
      )}

      {jobId && job && (
        <section>
          <h2 className="mb-4 text-lg font-medium">3. Result</h2>

          {job.status !== "complete" && job.status !== "failed" && (
            <p className="text-sm text-neutral-600">{STATUS_LABEL[job.status]}</p>
          )}

          {job.status === "failed" && (
            <div>
              <p className="text-sm text-red-600">{job.error ?? "Something went wrong."}</p>
              <button
                onClick={reset}
                className="mt-4 rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium"
              >
                Try again
              </button>
            </div>
          )}

          {job.status === "complete" && job.result_urls && (
            <div>
              <div className="flex flex-wrap gap-4">
                {job.result_urls.map((url) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={url}
                    src={url}
                    alt="Your generated result"
                    className="w-full max-w-sm rounded-lg object-cover"
                  />
                ))}
              </div>
              <div className="mt-4 flex gap-3">
                {job.result_urls.map((url) => (
                  <a
                    key={url}
                    href={url}
                    download
                    className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-white dark:text-neutral-900"
                  >
                    Download
                  </a>
                ))}
                <button
                  onClick={reset}
                  className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium"
                >
                  Start over
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}