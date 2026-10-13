import axios from "axios";
import type { Session } from "../types";

// Local CPU inference can take longer; ordinary API calls keep their 60s timeout.
export const AI_REQUEST_TIMEOUT = 200000;

export const api = axios.create({
  baseURL: "/api/v1",
  withCredentials: true,
  timeout: 60000,
});
let accessToken: string | null = null;
let listener: ((session: Session | null) => void) | null = null;
let refreshing: Promise<Session> | null = null;

export function onSessionChange(callback: typeof listener) {
  listener = callback;
}
export function applySession(session: Session | null) {
  accessToken = session?.access_token ?? null;
  listener?.(session);
}
export async function refreshSession(): Promise<Session> {
  if (!refreshing) {
    const perform = () => api.post<Session>("/auth/refresh");
    // Serialize cookie rotation across browser tabs when the Web Locks API is available.
    const request = navigator.locks
      ? navigator.locks.request("sentinelx-refresh", perform)
      : perform();
    refreshing = request
      .then(({ data }) => {
        applySession(data);
        return data;
      })
      .catch((error) => {
        applySession(null);
        throw error;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config;
    if (
      error.response?.status === 401 &&
      config &&
      !config._retried &&
      !config.url?.startsWith("/auth/")
    ) {
      config._retried = true;
      await refreshSession();
      return api(config);
    }
    return Promise.reject(error);
  },
);

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail.map((item: { msg: string }) => item.msg).join("; ");
    if (!error.response)
      return "Cannot reach SentinelX. Check your connection and try again. If it continues, ask the server administrator to check the service.";
  }
  return "The request could not be completed. Try again.";
}

export function reconcile() {
  window.dispatchEvent(new Event("sentinelx:refresh"));
}
