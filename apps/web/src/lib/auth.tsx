"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { fetchMe, getAccessToken, clearTokens, type User } from "./api";
import { useRouter, usePathname } from "next/navigation";

type AuthContextType = {
  user: User | null;
  loading: boolean;
  isLoggedIn: boolean;
  logout: () => void;
  checkAuth: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isLoggedIn: false,
  logout: () => {},
  checkAuth: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const checkAuth = async () => {
    const token = getAccessToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const userData = await fetchMe();
      setUser(userData);
    } catch (err) {
      // Token is invalid/expired
      clearTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const logout = () => {
    clearTokens();
    setUser(null);
    router.push("/login");
  };

  // Protect dashboard routes
  useEffect(() => {
    if (!loading) {
      const isDashboardRoute = pathname?.startsWith("/dashboard");
      const isLoginRoute = pathname === "/login";

      if (isDashboardRoute && !user) {
        router.push("/login");
      } else if (isLoginRoute && user) {
        router.push("/dashboard");
      }
    }
  }, [user, loading, pathname, router]);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isLoggedIn: !!user,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
