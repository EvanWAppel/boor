// Owns retries and heartbeats independently of React so lifecycle races are testable.
import type { SessionRoom, SessionRoomOptions } from "./ws";

export type ConnectionStatus = "connecting" | "reconnecting" | "open" | "closed" | "error";

export function maintainRoom(options: {
  baseUrl: string;
  sessionId: string;
  getToken: () => string | null | Promise<string | null>;
  connect: (options: SessionRoomOptions) => SessionRoom;
  onMessage: SessionRoomOptions["onMessage"];
  onStatus: (status: ConnectionStatus, code: number | null) => void;
  recover: () => Promise<void>;
}) {
  let stopped = false;
  let generation = 0;
  let attempts = 0;
  let socket: SessionRoom | null = null;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let lastMessage = Date.now();

  function disconnect() {
    clearInterval(heartbeat);
    heartbeat = undefined;
    const old = socket;
    socket = null;
    old?.close();
  }

  function schedule() {
    if (stopped) return;
    ++generation; // invalidate callbacks before closing the old connection
    disconnect();
    options.onStatus("reconnecting", null);
    retry = setTimeout(() => void start(), Math.min(1000 * 2 ** attempts++, 15000));
  }

  async function start() {
    const current = ++generation;
    const active = () => !stopped && generation === current;
    try {
      const token = await options.getToken();
      if (!active()) return;
      if (!token) {
        options.onStatus("closed", 4401);
        return;
      }
      socket = options.connect({
        baseUrl: options.baseUrl,
        sessionId: options.sessionId,
        token,
        onMessage: (message) => {
          if (!active()) return;
          lastMessage = Date.now();
          if (message.type === "ready") {
            // The server has authenticated and subscribed this socket now.
            void options.recover().then(() => {
              if (!active()) return;
              attempts = 0;
              options.onStatus("open", null);
            }).catch(() => { if (active()) schedule(); });
          } else if (message.type !== "pong") options.onMessage(message);
        },
        onOpen: () => {
          if (!active()) return;
          lastMessage = Date.now();
          heartbeat = setInterval(() => {
            if (!active()) return;
            if (Date.now() - lastMessage > 45000) {
              schedule();
              return;
            }
            try { socket?.send({ type: "ping" }); } catch { schedule(); }
          }, 15000);

        },
        onClose: (event) => {
          if (!active()) return;
          if ([4401, 4403, 4404].includes(event.code)) {
            ++generation;
            disconnect();
            options.onStatus("closed", event.code);
          } else schedule();
        },
        onError: () => { if (active()) schedule(); },
      });
    } catch {
      if (active()) schedule();
    }
  }

  options.onStatus("connecting", null);
  void start();
  return {
    send(message: { type: string } & Record<string, unknown>) {
      if (!socket || socket.socket.readyState !== 1) return false;
      try { socket.send(message); return true; } catch { schedule(); return false; }
    },
    close() {
      stopped = true;
      ++generation;
      clearTimeout(retry);
      disconnect();
    },
  };
}
