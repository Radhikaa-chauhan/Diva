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
  username: string | null;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  is_admin: boolean;
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

export async function updateProfile(fields: { display_name?: string; bio?: string | null }): Promise<User> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to update profile.");
  }
  return res.json();
}

export async function uploadAvatar(file: File): Promise<User> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithAuth(`${API_BASE_URL}/api/auth/me/avatar`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to upload avatar.");
  }
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

// ── Social types ──────────────────────────────────────────────────────

export type AuthorSummary = {
  id: string;
  username: string | null;
  display_name: string;
  avatar_url: string | null;
};

export type Post = {
  id: string;
  author: AuthorSummary;
  reference_photo_id: string | null;
  image_url: string;
  caption: string | null;
  visibility: "public" | "private";
  likes_count: number;
  comments_count: number;
  saves_count: number;
  is_liked: boolean;
  is_saved: boolean;
  created_at: string;
};

export type Profile = {
  id: string;
  username: string | null;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  followers_count: number;
  following_count: number;
  posts_count: number;
  is_following: boolean;
  created_at: string;
};

export type Comment = {
  id: string;
  author: AuthorSummary;
  text: string;
  created_at: string;
};

// ── Social helpers ────────────────────────────────────────────────────

async function requestJson<T>(url: string, options: RequestInit = {}, errorMsg = "Request failed."): Promise<T> {
  const res = await fetchWithAuth(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? errorMsg);
  }
  return res.json();
}

// ── Posts ─────────────────────────────────────────────────────────────

export async function createPost(
  jobId: string,
  caption?: string,
  visibility: "public" | "private" = "public"
): Promise<Post> {
  return requestJson<Post>(`${API_BASE_URL}/api/posts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, caption, visibility }),
  }, "Failed to publish post.");
}

export async function fetchPost(postId: string): Promise<Post> {
  return requestJson<Post>(`${API_BASE_URL}/api/posts/${postId}`, {}, "Failed to load post.");
}

export async function deletePost(postId: string): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/posts/${postId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete post.");
}

// ── Feed / Explore ────────────────────────────────────────────────────

export async function fetchFeed(page = 1, perPage = 20): Promise<PaginatedResponse<Post>> {
  return requestJson(`${API_BASE_URL}/api/feed?page=${page}&per_page=${perPage}`, {}, "Failed to load feed.");
}

export async function fetchExplore(page = 1, perPage = 20): Promise<PaginatedResponse<Post>> {
  return requestJson(`${API_BASE_URL}/api/explore?page=${page}&per_page=${perPage}`, {}, "Failed to load explore.");
}

// ── Engagement ────────────────────────────────────────────────────────

export async function likePost(postId: string): Promise<{ is_liked: boolean; likes_count: number }> {
  return requestJson(`${API_BASE_URL}/api/posts/${postId}/like`, { method: "POST" }, "Failed to like post.");
}

export async function unlikePost(postId: string): Promise<{ is_liked: boolean; likes_count: number }> {
  return requestJson(`${API_BASE_URL}/api/posts/${postId}/like`, { method: "DELETE" }, "Failed to unlike post.");
}

export async function savePost(postId: string): Promise<{ is_saved: boolean; saves_count: number }> {
  return requestJson(`${API_BASE_URL}/api/posts/${postId}/save`, { method: "POST" }, "Failed to save post.");
}

export async function unsavePost(postId: string): Promise<{ is_saved: boolean; saves_count: number }> {
  return requestJson(`${API_BASE_URL}/api/posts/${postId}/save`, { method: "DELETE" }, "Failed to unsave post.");
}

export async function fetchSavedPosts(page = 1, perPage = 20): Promise<PaginatedResponse<Post>> {
  return requestJson(`${API_BASE_URL}/api/saved?page=${page}&per_page=${perPage}`, {}, "Failed to load saved posts.");
}

export async function fetchComments(postId: string, page = 1, perPage = 20): Promise<PaginatedResponse<Comment>> {
  return requestJson(
    `${API_BASE_URL}/api/posts/${postId}/comments?page=${page}&per_page=${perPage}`,
    {},
    "Failed to load comments."
  );
}

export async function createComment(postId: string, text: string): Promise<Comment> {
  return requestJson(`${API_BASE_URL}/api/posts/${postId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }, "Failed to post comment.");
}

export async function deleteComment(commentId: string): Promise<void> {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/comments/${commentId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete comment.");
}

// ── Follow ────────────────────────────────────────────────────────────

export async function followUser(userId: string): Promise<{ is_following: boolean; followers_count: number }> {
  return requestJson(`${API_BASE_URL}/api/users/${userId}/follow`, { method: "POST" }, "Failed to follow.");
}

export async function unfollowUser(userId: string): Promise<{ is_following: boolean; followers_count: number }> {
  return requestJson(`${API_BASE_URL}/api/users/${userId}/follow`, { method: "DELETE" }, "Failed to unfollow.");
}

export async function fetchFollowers(userId: string, page = 1): Promise<PaginatedResponse<AuthorSummary>> {
  return requestJson(`${API_BASE_URL}/api/users/${userId}/followers?page=${page}`, {}, "Failed to load followers.");
}

export async function fetchFollowing(userId: string, page = 1): Promise<PaginatedResponse<AuthorSummary>> {
  return requestJson(`${API_BASE_URL}/api/users/${userId}/following?page=${page}`, {}, "Failed to load following.");
}

// ── Profiles ──────────────────────────────────────────────────────────

export async function fetchProfile(username: string): Promise<Profile> {
  return requestJson(
    `${API_BASE_URL}/api/users/by-username/${encodeURIComponent(username)}`,
    {},
    "Failed to load profile."
  );
}

export async function fetchProfilePosts(username: string, page = 1, perPage = 20): Promise<PaginatedResponse<Post>> {
  return requestJson(
    `${API_BASE_URL}/api/users/by-username/${encodeURIComponent(username)}/posts?page=${page}&per_page=${perPage}`,
    {},
    "Failed to load posts."
  );
}

// ── Search ────────────────────────────────────────────────────────────

export async function searchUsers(q: string, page = 1): Promise<PaginatedResponse<AuthorSummary>> {
  return requestJson(`${API_BASE_URL}/api/search/users?q=${encodeURIComponent(q)}&page=${page}`, {}, "Search failed.");
}

export async function searchPosts(q: string, page = 1): Promise<PaginatedResponse<Post>> {
  return requestJson(`${API_BASE_URL}/api/search/posts?q=${encodeURIComponent(q)}&page=${page}`, {}, "Search failed.");
}

// ── Admin ─────────────────────────────────────────────────────────────

export type AdminStats = {
  total_users: number;
  active_24h: number;
  active_7d: number;
  new_users_7d: number;
  verified_users: number;
  total_generations: number;
  total_posts: number;
};

export type AdminUser = {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  is_email_verified: boolean;
  is_active: boolean;
  generation_count: number;
  followers_count: number;
  last_login_at: string | null;
  created_at: string;
};

export async function fetchAdminStats(): Promise<AdminStats> {
  return requestJson(`${API_BASE_URL}/api/admin/stats`, {}, "Failed to load stats.");
}

export async function fetchAdminUsers(page = 1, q = ""): Promise<PaginatedResponse<AdminUser>> {
  const qp = q ? `&q=${encodeURIComponent(q)}` : "";
  return requestJson(`${API_BASE_URL}/api/admin/users?page=${page}${qp}`, {}, "Failed to load users.");
}