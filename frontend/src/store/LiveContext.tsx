import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "./AuthContext";
import { reconcile, refreshSession } from "../services/api";
import { websocketUrl } from "../services/connection";

const LiveContext = createContext(false);
export function LiveProvider({ children }: { children: ReactNode }) {
  const { token, user } = useAuth();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!token) return;
    let disposed = false;
    let updateTimer: number | undefined;
    const sockets: WebSocket[] = [];
    const timers: number[] = [];
    const channels =
      user?.role === "VIEWER"
        ? ["alerts", "incidents"]
        : ["events", "alerts", "incidents"];
    function connect(channel: string, attempt = 0) {
      if (disposed) return;
      const socket = new WebSocket(websocketUrl(channel));
      sockets.push(socket);
      socket.onopen = () => socket.send(JSON.stringify({ token }));
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "connected") {
          if (channel === "alerts") setConnected(true);
          reconcile();
        } else if (message.type !== "heartbeat" && !updateTimer) {
          updateTimer = window.setTimeout(() => {
            reconcile();
            updateTimer = undefined;
          }, 400);
        }
      };
      socket.onclose = (event) => {
        if (channel === "alerts") setConnected(false);
        if (disposed) return;
        if (event.code === 1008 && attempt === 0)
          refreshSession().catch(() => {});
        timers.push(
          window.setTimeout(
            () => connect(channel, attempt + 1),
            Math.min(1000 * 2 ** attempt, 30000),
          ),
        );
      };
    }
    channels.forEach((channel) => connect(channel));
    return () => {
      disposed = true;
      setConnected(false);
      sockets.forEach((socket) => socket.close());
      timers.forEach(window.clearTimeout);
      window.clearTimeout(updateTimer);
    };
  }, [token, user?.role]);
  return (
    <LiveContext.Provider value={connected}>{children}</LiveContext.Provider>
  );
}
export function useLive() {
  return useContext(LiveContext);
}
