// The live state of a session room: replayed history + realtime frames, presence,
// and the shared initiative order. One hook the table page and its panels read
// from, so there's a single source of truth for the WebSocket connection.
//
// On connect it replays the durable timeline (GET /sessions/{id}/log) so a late
// joiner sees everything that already happened, then layers live frames on top,
// deduped by `seq`. Chat (IC), out-of-character, and dice rolls are timeline-backed
// (they carry a `seq`); initiative is persisted and replayed by the server.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ApiClient } from "./api";
import { useAuthSession } from "./auth";
import { maintainRoom, type ConnectionStatus } from "./roomConnection";
import { API_BASE_URL } from "./useApi";
import type { EventAudience, EventKind } from "./types";
import {
  connectSessionRoom,
  type PresenceEntry,
  type RoomMessage,
} from "./ws";

/** A normalized, renderable line in the shared log (history or live, unified). */
export interface LogEntry {
  seq: number;
  kind: EventKind;
  label: string | null;
  body: string | null;
  payload: Record<string, unknown>;
  aiGenerated: boolean;
  audience: EventAudience;
}

/** The DM-driven turn order, relayed to the table (persisted in the session timeline). */
export interface InitiativeState {
  order: string[];
  activeIndex: number;
}

export type RoomStatus = ConnectionStatus;

/** The frame types the service persists + echoes with a `seq`, mapped to a kind. */
const FRAME_KIND: Record<string, EventKind> = {
  chat: "in_character",
  ooc: "out_of_character",
  roll: "roll",
};

export interface Room {
  status: RoomStatus;
  /** Application close code, when the socket closed abnormally (e.g. 4403). */
  closeCode: number | null;
  entries: LogEntry[];
  present: PresenceEntry[];
  initiative: InitiativeState | null;
  thinking: string[];
  sendChat: (body: string) => boolean;
  sendOoc: (body: string) => boolean;
  sendRoll: (body: string, payload: Record<string, unknown>) => boolean;
  setInitiative: (state: InitiativeState) => void;
}

export function useRoom(sessionId: string, api: ApiClient | null): Room {
  const { getToken, isLoaded, isSignedIn } = useAuthSession();
  const [status, setStatus] = useState<RoomStatus>("connecting");
  const [closeCode, setCloseCode] = useState<number | null>(null);
  const [present, setPresent] = useState<PresenceEntry[]>([]);
  const [thinking, setThinking] = useState<string[]>([]);
  const [initiative, setInitiativeState] = useState<InitiativeState | null>(null);
  // Timeline entries keyed by seq so history and live frames dedupe cleanly.
  const [bySeq, setBySeq] = useState<Map<number, LogEntry>>(() => new Map());
  const roomRef = useRef<ReturnType<typeof maintainRoom> | null>(null);

  const upsert = useCallback((entry: LogEntry) => {
    setBySeq((prev) => {
      if (prev.has(entry.seq)) return prev;
      const next = new Map(prev);
      next.set(entry.seq, entry);
      return next;
    });
  }, []);

  const initiativeSeq = useRef(0);

  const onMessage = useCallback(
    (message: RoomMessage) => {
      // RelayMessage's `type: string` defeats discriminated-union narrowing, so
      // read fields off a permissive frame view and validate each one by hand.
      const m = message as {
        type: string;
        kind?: EventKind;
        character_id?: string;
        thinking?: boolean;
        ai_generated?: boolean;
        present?: PresenceEntry[];
        order?: unknown;
        activeIndex?: unknown;
        seq?: unknown;
        body?: unknown;
        payload?: unknown;
        display_name?: unknown;
        audience?: unknown;
      };

      if (m.type === "standin_status" && m.character_id) {
        const id = m.character_id;
        setThinking((prev) => m.thinking ? [...new Set([...prev, id])] : prev.filter(c => c !== id));
        return;
      }
      if (m.type === "presence") {
        setPresent(m.present ?? []);
        return;
      }
      if (m.type === "initiative") {
        if (typeof m.seq !== "number" || m.seq <= initiativeSeq.current) return;
        initiativeSeq.current = m.seq;
        setInitiativeState({
          order: Array.isArray(m.order) ? (m.order as string[]) : [],
          activeIndex: typeof m.activeIndex === "number" ? m.activeIndex : 0,
        });
        return;
      }
      const kind = m.type === "event" ? m.kind : FRAME_KIND[m.type];
      if (kind && typeof m.seq === "number") {
        upsert({
          seq: m.seq,
          kind,
          label: typeof m.display_name === "string" ? m.display_name : null,
          body: typeof m.body === "string" ? m.body : null,
          payload:
            m.payload && typeof m.payload === "object"
              ? (m.payload as Record<string, unknown>)
              : {},
          aiGenerated: Boolean(m.ai_generated),
          audience: m.audience === "characters" || m.audience === "dm" ? m.audience : "table",
        });
      }
    },
    [upsert],
  );

  useEffect(() => {
    if (!api || !isLoaded || !isSignedIn) return;
    let cancelled = false;
    const room = maintainRoom({
      baseUrl: API_BASE_URL,
      sessionId,
      getToken,
      connect: connectSessionRoom,
      onMessage,
      onStatus: (next, code) => {
        if (cancelled) return;
        setStatus(next);
        setCloseCode(code);
        if (next !== "open") { setPresent([]); setThinking([]); }
      },
      recover: async () => {
        const log = await api.getSessionLog(sessionId);
        if (cancelled) return;
        setBySeq((prev) => {
          const next = new Map(prev);
          for (const e of log) {
            next.set(e.seq, {
              seq: e.seq, kind: e.kind, label: e.actor_label,
              body: e.body, payload: e.payload, aiGenerated: e.ai_generated,
              audience: e.audience,
            });
          }
          return next;
        });
      },
    });
    roomRef.current = room;
    return () => {
      cancelled = true;
      room.close();
      roomRef.current = null;
    };
  }, [api, sessionId, getToken, isLoaded, isSignedIn, onMessage]);

  const entries = useMemo(
    () => Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq),
    [bySeq],
  );

  const sendChat = useCallback((body: string) => (roomRef.current?.send({ type: "chat", body }) ?? false), []);
  const sendOoc = useCallback((body: string) => (roomRef.current?.send({ type: "ooc", body }) ?? false), []);
  const sendRoll = useCallback(
    (body: string, payload: Record<string, unknown>) =>
      (roomRef.current?.send({ type: "roll", body, payload }) ?? false),
    [],
  );
  const setInitiative = useCallback((state: InitiativeState) => {
    roomRef.current?.send({ type: "initiative", ...state });
  }, []);

  return {
    status,
    closeCode,
    entries,
    present,
    initiative,
    thinking,
    sendChat,
    sendOoc,
    sendRoll,
    setInitiative,
  };
}
