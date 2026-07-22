"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  fetchProfile,
  fetchProfilePosts,
  followUser,
  unfollowUser,
  updateProfile,
  uploadAvatar,
  type Post,
  type Profile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Avatar from "@/components/Avatar";

export default function ProfilePage({ params }: { params: Promise<{ username: string }> }) {
  const { username } = use(params);
  const { user, isLoggedIn, checkAuth } = useAuth();
  const router = useRouter();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [followBusy, setFollowBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftBio, setDraftBio] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);

  async function saveProfile() {
    const name = draftName.trim();
    if (!name || !profile) return;
    setSavingEdit(true);
    try {
      await updateProfile({ display_name: name, bio: draftBio.trim() || null });
      await checkAuth();
      setProfile({ ...profile, display_name: name, bio: draftBio.trim() || null });
      setEditing(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleAvatarChange(file: File | null) {
    if (!file || !profile) return;
    setAvatarBusy(true);
    try {
      const updated = await uploadAvatar(file);
      await checkAuth();
      setProfile({ ...profile, avatar_url: updated.avatar_url });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAvatarBusy(false);
    }
  }

  useEffect(() => {
    fetchProfile(username).then(setProfile).catch((err: Error) => setError(err.message));
  }, [username]);

  useEffect(() => {
    fetchProfilePosts(username, page)
      .then((result) => {
        setPosts((prev) => (page === 1 ? result.items : [...prev, ...result.items]));
        setPages(result.pages);
      })
      .catch(() => {});
  }, [username, page]);

  const isOwnProfile = user?.id === profile?.id;

  async function toggleFollow() {
    if (!isLoggedIn) return router.push("/login");
    if (!profile || followBusy) return;
    setFollowBusy(true);
    try {
      const result = profile.is_following
        ? await unfollowUser(profile.id)
        : await followUser(profile.id);
      setProfile({
        ...profile,
        is_following: result.is_following,
        followers_count: result.followers_count,
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setFollowBusy(false);
    }
  }

  if (error && !profile) {
    return (
      <div className="mx-auto max-w-lg flex-1 px-6 py-24 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <Link href="/feed" className="mt-4 inline-block text-sm font-semibold text-purple-400 hover:text-purple-300 transition">
          ← Back to feed
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      {/* Header */}
      {!profile ? (
        <div className="h-28 rounded-2xl bg-zinc-900 animate-pulse border border-zinc-800/60" />
      ) : (
        <header className="flex items-center gap-6">
          <div className="relative shrink-0">
            <Avatar src={profile.avatar_url} name={profile.display_name} size={80} className="shadow-lg" />
            {isOwnProfile && (
              <label
                className={`absolute -bottom-1 -right-1 flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-xs hover:bg-zinc-800 transition ${avatarBusy ? "opacity-50" : ""}`}
                title="Change photo"
              >
                {avatarBusy ? "…" : "📷"}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  disabled={avatarBusy}
                  onChange={(e) => handleAvatarChange(e.target.files?.[0] ?? null)}
                />
              </label>
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              {!editing && (
                <h1 className="truncate text-xl font-bold text-zinc-100">{profile.display_name}</h1>
              )}
              {profile.username && !editing && (
                <span className="text-sm text-zinc-500">@{profile.username}</span>
              )}
              {isOwnProfile && !editing && (
                <button
                  onClick={() => {
                    setDraftName(profile.display_name);
                    setDraftBio(profile.bio ?? "");
                    setEditing(true);
                  }}
                  className="rounded-full border border-zinc-700 bg-zinc-800/80 px-4 py-1.5 text-xs font-bold uppercase tracking-wide text-zinc-300 hover:border-purple-500 hover:text-purple-300 transition"
                >
                  Edit Profile
                </button>
              )}
              {!isOwnProfile && (
                <button
                  onClick={toggleFollow}
                  disabled={followBusy}
                  className={`rounded-full px-4 py-1.5 text-xs font-bold uppercase tracking-wide transition disabled:opacity-50 ${
                    profile.is_following
                      ? "border border-zinc-700 bg-zinc-800/80 text-zinc-300 hover:border-red-800 hover:text-red-400"
                      : "bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:opacity-90"
                  }`}
                >
                  {profile.is_following ? "Following" : "Follow"}
                </button>
              )}
            </div>

            <div className="mt-3 flex gap-6 text-sm">
              <span className="text-zinc-300">
                <strong className="text-zinc-100">{profile.posts_count}</strong>{" "}
                <span className="text-zinc-500">posts</span>
              </span>
              <span className="text-zinc-300">
                <strong className="text-zinc-100">{profile.followers_count}</strong>{" "}
                <span className="text-zinc-500">followers</span>
              </span>
              <span className="text-zinc-300">
                <strong className="text-zinc-100">{profile.following_count}</strong>{" "}
                <span className="text-zinc-500">following</span>
              </span>
            </div>

            {/* Bio / edit form */}
            {editing ? (
              <div className="mt-4 flex flex-col gap-2">
                <input
                  type="text"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  maxLength={100}
                  placeholder="Display name"
                  className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-purple-500 focus:outline-none"
                />
                <textarea
                  value={draftBio}
                  onChange={(e) => setDraftBio(e.target.value)}
                  maxLength={300}
                  rows={3}
                  placeholder="Add a bio..."
                  className="resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-purple-500 focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    onClick={saveProfile}
                    disabled={savingEdit || !draftName.trim()}
                    className="rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-1.5 text-xs font-bold text-white disabled:opacity-40 hover:opacity-90 transition"
                  >
                    {savingEdit ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="rounded-lg border border-zinc-800 px-4 py-1.5 text-xs font-semibold text-zinc-400 hover:text-zinc-200 transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              profile.bio && <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-300">{profile.bio}</p>
            )}
          </div>
        </header>
      )}

      {/* Post grid */}
      <section className="mt-10">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {posts.map((post) => (
            <Link key={post.id} href={`/p/${post.id}`} className="group relative block overflow-hidden rounded-xl border border-zinc-800/60">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={post.image_url}
                alt={post.caption ?? "Post"}
                className="aspect-[4/5] w-full object-cover transition group-hover:scale-105"
                loading="lazy"
              />
              {post.visibility === "private" && (
                <span className="absolute right-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-xxs font-semibold uppercase tracking-wider text-zinc-300">
                  Private
                </span>
              )}
            </Link>
          ))}
        </div>

        {posts.length === 0 && profile && (
          <p className="py-16 text-center text-sm text-zinc-600">No posts yet.</p>
        )}

        {page < pages && (
          <button
            onClick={() => setPage((p) => p + 1)}
            className="mt-8 w-full rounded-xl border border-zinc-800 bg-zinc-900/60 py-3 text-sm font-semibold text-zinc-300 hover:bg-zinc-900 transition"
          >
            Load more
          </button>
        )}
      </section>
    </div>
  );
}
