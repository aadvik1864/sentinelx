import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  api,
  applySession,
  onSessionChange,
  refreshSession,
} from "../services/api";
import type { Session, User } from "../types";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string, otp?: string) => Promise<void>;
  logout: () => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    onSessionChange(setSession);
    refreshSession()
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => onSessionChange(null);
  }, []);
  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(
      () => {
        refreshSession().catch(() => {});
      },
      12 * 60 * 1000,
    );
    return () => window.clearInterval(timer);
  }, [session]);
  async function login(email: string, password: string, otp?: string) {
    const { data } = await api.post<Session>("/auth/login", {
      email,
      password,
      ...(otp ? { otp } : {}),
    });
    applySession(data);
  }
  async function logout() {
    await api.post("/auth/logout");
    applySession(null);
  }
  return (
    <AuthContext.Provider
      value={{
        user: session?.user ?? null,
        token: session?.access_token ?? null,
        loading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is required");
  return context;
}
