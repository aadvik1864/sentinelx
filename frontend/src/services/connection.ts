// REST stays on the frontend origin so refresh cookies remain first-party.
// A separately hosted backend receives live updates directly over WebSockets.
export function websocketUrl(
  channel: string,
  origin = import.meta.env.VITE_BACKEND_ORIGIN || window.location.origin,
): string {
  const url = new URL(origin);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
    throw new Error('The backend must have an HTTP(S) origin without credentials.');
  const socket = new URL(`/ws/${encodeURIComponent(channel)}`, url.origin);
  socket.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return socket.toString();
}
