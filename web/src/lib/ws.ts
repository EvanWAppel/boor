// Client for a game session's realtime room (the service's WS /ws/sessions/{id}).
//
// The service authenticates the WebSocket handshake with the Clerk token, which
// browsers can't send as a header — so it goes in the query string, matching
// boor_service.realtime. Usage:
//
//   const room = connectSessionRoom({
//     baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL!,
//     sessionId, token: await getToken(),
//     onMessage: (m) => { ... },
//   });
//   room.sendChat("Well met.");
//   room.close();

import type { RiskTolerance } from "./types"; // re-exported below for convenience

export type { RiskTolerance };

/** Application close codes the service uses (mirror boor_service.realtime). */
export const WS_UNAUTHORIZED = 4401;
export const WS_FORBIDDEN = 4403;
export const WS_NOT_FOUND = 4404;

export interface PresenceEntry {
  user_id: string;
  display_name: string | null;
}

export interface PresenceMessage {
  type: "presence";
  event: "join" | "leave";
  user_id: string;
  display_name: string | null;
  present: PresenceEntry[];
}

export interface ChatMessage {
  type: "chat";
  user_id: string;
  display_name: string | null;
  body: string;
  seq: number;
}

/** Any other typed frame the service relays (cursor, token move, ...). */
export interface RelayMessage {
  type: string;
  user_id: string;
  display_name: string | null;
  [key: string]: unknown;
}

export type RoomMessage = PresenceMessage | ChatMessage | RelayMessage;

export interface SessionRoomOptions {
  /** Service base URL (http/https); converted to ws/wss automatically. */
  baseUrl: string;
  sessionId: string;
  token: string;
  onMessage: (message: RoomMessage) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
}

export interface SessionRoom {
  /** Send a chat line (persisted to the timeline + relayed to the room). */
  sendChat: (body: string) => void;
  /** Send an arbitrary typed frame (relayed as-is with sender attribution). */
  send: (message: { type: string } & Record<string, unknown>) => void;
  close: () => void;
  readonly socket: WebSocket;
}

export function connectSessionRoom(options: SessionRoomOptions): SessionRoom {
  const wsBase = options.baseUrl.replace(/^http/, "ws");
  const url = `${wsBase}/ws/sessions/${options.sessionId}?token=${encodeURIComponent(options.token)}`;
  const socket = new WebSocket(url);

  socket.onopen = () => options.onOpen?.();
  socket.onclose = (event) => options.onClose?.(event);
  socket.onerror = (event) => options.onError?.(event);
  socket.onmessage = (event) => {
    try {
      options.onMessage(JSON.parse(event.data as string) as RoomMessage);
    } catch {
      // ignore frames that aren't JSON we understand
    }
  };

  return {
    sendChat: (body: string) => socket.send(JSON.stringify({ type: "chat", body })),
    send: (message) => socket.send(JSON.stringify(message)),
    close: () => socket.close(),
    socket,
  };
}
