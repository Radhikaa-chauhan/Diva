const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ReferencePhoto = {
  id: string;
  title: string;
  collection: string | null;
  thumbnail_url: string;
};

export type JobStatus = "pending" | "generating" | "quality_check" | "complete" | "failed";

export type Job = {
  status: JobStatus;
  result_urls: string[] | null;
  error: string | null;
};

export async function fetchReferences(): Promise<ReferencePhoto[]> {
  const res = await fetch(`${API_BASE_URL}/api/references`);
  if (!res.ok) throw new Error("Failed to load the reference library.");
  return res.json();
}

export async function createJob(referencePhotoId: string, selfie: File): Promise<string> {
  const form = new FormData();
  form.append("selfie_image", selfie);
  const res = await fetch(
    `${API_BASE_URL}/api/jobs?reference_photo_id=${encodeURIComponent(referencePhotoId)}`,
    { method: "POST", body: form }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to start generation.");
  }
  const data = await res.json();
  return data.job_id as string;
}

export async function fetchJob(jobId: string): Promise<Job> {
  const res = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error("Failed to check job status.");
  return res.json();
}