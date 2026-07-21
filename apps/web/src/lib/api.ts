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

export type User = {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  generation_count: number;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
};

export type JobHistoryItem = {
  id: string;
  status: JobStatus;
  reference_title: string;
  reference_thumbnail: string;
  selfie_image_url: string;
  result_urls: string[] | null;
  is_favorite: boolean;
  created_at: string;
  error: string | null;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
};

export type DashboardStats = {
  total_generations: number;
  completed_generations: number;
  favorites_count: number;
  storage_used_mb: number;
};

// Local storage helpers
export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("diva_access_token");
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("diva_refresh_token");
}

export function setTokens(accessToken: string, refreshToken: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("diva_access_token", accessToken);
  localStorage.setItem("diva_refresh_token", refreshToken);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("diva_access_token");
  localStorage.removeItem("diva_refresh_token");
}

// Fetch wrapper with auth injection & auto refresh
async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  let headers = new Headers(options.headers);
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  options.headers = headers;

  let res = await fetch(url, options);

  // If unauthorized, try to refresh token once
  if (res.status === 401) {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        const refreshRes = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refreshRes.ok) {
          const refreshData: TokenResponse = await refreshRes.json();
          setTokens(refreshData.access_token, refreshData.refresh_token);
          
          // Retry the request with new token
          headers.set("Authorization", `Bearer ${refreshData.access_token}`);
          options.headers = headers;
          res = await fetch(url, options);
        } else {
          // Refresh failed, clear tokens
          clearTokens();
        }
      } catch (err) {
        clearTokens();
      }
    }
  }

  return res;
}

export async function signup(email: string, display_name: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, display_name, password }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail ?? "Signup failed");
  }
  const data: TokenResponse = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail ?? "Login failed");
  }
  const data: TokenResponse = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function sendOtp(email: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/send-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail ?? "Failed to send OTP.");
  }
  return res.json();
}

export async function verifyOtp(email: string, otp: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, otp }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail ?? "Invalid or expired OTP code.");
  }
  const data: TokenResponse = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function socialLogin(provider: string, token: string, displayName?: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/social-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, token, display_name: displayName }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail ?? "Social login failed.");
  }
  const data: TokenResponse = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function fetchMe(): Promise<User> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/auth/me`);
  if (!res.ok) throw new Error("Failed to fetch profile");
  return res.json();
}

export async function fetchReferences(): Promise<ReferencePhoto[]> {
  const res = await fetch(`${API_BASE_URL}/api/references`);
  if (!res.ok) throw new Error("Failed to load the reference library.");
  return res.json();
}

export async function createJob(referencePhotoId: string, selfie: File): Promise<string> {
  const form = new FormData();
  form.append("selfie_image", selfie);
  const res = await fetchWithAuth(
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
  const res = await fetchWithAuth(`${API_BASE_URL}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error("Failed to check job status.");
  return res.json();
}

export async function fetchHistory(page = 1, perPage = 12, status?: string): Promise<PaginatedResponse<JobHistoryItem>> {
  const statusParam = status ? `&status=${encodeURIComponent(status)}` : "";
  const res = await fetchWithAuth(
    `${API_BASE_URL}/api/dashboard/history?page=${page}&per_page=${perPage}${statusParam}`
  );
  if (!res.ok) throw new Error("Failed to load history.");
  return res.json();
}

export async function fetchFavorites(page = 1, perPage = 12): Promise<PaginatedResponse<JobHistoryItem>> {
  const res = await fetchWithAuth(
    `${API_BASE_URL}/api/dashboard/favorites?page=${page}&per_page=${perPage}`
  );
  if (!res.ok) throw new Error("Failed to load favorites.");
  return res.json();
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/dashboard/stats`);
  if (!res.ok) throw new Error("Failed to load dashboard stats.");
  return res.json();
}

export async function toggleFavorite(jobId: string): Promise<boolean> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/jobs/${jobId}/favorite`, {
    method: "PATCH",
  });
  if (!res.ok) throw new Error("Failed to update favorite status.");
  const data = await res.json();
  return data.is_favorite;
}

export async function deleteGeneration(jobId: string): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/jobs/${jobId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete generation.");
}