"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useState } from "react";
import Avatar from "@/components/Avatar";

export default function Navbar() {
  const { user, logout, isLoggedIn } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  return (
    <nav className="glass sticky top-0 z-50 w-full px-6 py-4 shadow-sm backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-2xl font-black tracking-wider text-transparent">
            DIVA
          </span>
          <span className="rounded-full bg-purple-900/40 px-2.5 py-0.5 text-xxs font-semibold uppercase tracking-widest text-purple-300 border border-purple-800/50">
            Studio
          </span>
        </Link>

        <div className="flex items-center gap-6">
          <Link
            href="/"
            className="text-sm font-medium text-zinc-300 hover:text-purple-400 transition"
          >
            Create
          </Link>
          <Link
            href="/feed"
            className="text-sm font-medium text-zinc-300 hover:text-purple-400 transition"
          >
            Feed
          </Link>
          <Link
            href="/explore"
            className="text-sm font-medium text-zinc-300 hover:text-purple-400 transition"
          >
            Explore
          </Link>
          {isLoggedIn && (
            <Link
              href="/dashboard"
              className="text-sm font-medium text-zinc-300 hover:text-purple-400 transition"
            >
              Dashboard
            </Link>
          )}

          {isLoggedIn && user ? (
            <div className="relative">
              <button
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800/80 px-3 py-1.5 text-sm hover:border-purple-500 hover:bg-zinc-800 transition"
              >
                <Avatar src={user.avatar_url} name={user.display_name} size={24} className="shadow-sm" />
                <span className="max-w-[100px] truncate text-zinc-200">
                  {user.display_name}
                </span>
                <svg
                  className={`h-4 w-4 text-zinc-400 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {dropdownOpen && (
                <>
                  <div 
                    className="fixed inset-0 z-10" 
                    onClick={() => setDropdownOpen(false)}
                  />
                  <div className="glass absolute right-0 mt-2 w-48 origin-top-right rounded-lg bg-zinc-950/95 p-1.5 shadow-xl border border-zinc-800/85 z-20">
                    <div className="px-3 py-2 text-xs border-b border-zinc-800/60 mb-1 text-zinc-400 truncate">
                      {user.email}
                    </div>
                    {user.username && (
                      <Link
                        href={`/u/${user.username}`}
                        onClick={() => setDropdownOpen(false)}
                        className="flex w-full items-center px-3 py-2 text-sm text-zinc-300 hover:bg-purple-900/30 hover:text-purple-400 rounded-md transition"
                      >
                        My Profile
                      </Link>
                    )}
                    <Link
                      href="/dashboard"
                      onClick={() => setDropdownOpen(false)}
                      className="flex w-full items-center px-3 py-2 text-sm text-zinc-300 hover:bg-purple-900/30 hover:text-purple-400 rounded-md transition"
                    >
                      My Dashboard
                    </Link>
                    {user.is_admin && (
                      <Link
                        href="/admin"
                        onClick={() => setDropdownOpen(false)}
                        className="flex w-full items-center px-3 py-2 text-sm text-amber-300 hover:bg-amber-900/20 hover:text-amber-200 rounded-md transition"
                      >
                        Admin Dashboard
                      </Link>
                    )}
                    <button
                      onClick={() => {
                        setDropdownOpen(false);
                        logout();
                      }}
                      className="flex w-full items-center px-3 py-2 text-sm text-red-400 hover:bg-red-950/20 hover:text-red-300 rounded-md transition text-left"
                    >
                      Logout
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <Link
              href="/login"
              className="rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-5 py-2 text-sm font-semibold text-white hover:opacity-90 shadow-md transition hover:shadow-purple-500/25"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
