// The live state of a session room: replayed history + realtime frames, presence,
// and the shared initiative order. One hook the table page and its panels read
// from, so there's a single source of truth for the WebSocket connection.
//
// On connect it replays the durable timeline (GET /sessions/{id}/log) so a late
// joiner sees everything that already happened, then layers live frames on top,
// deduped by `seq`. Chat (IC), out-of-character, and dice rolls are timeline-backed
// (they carry a `seq`); initiative is an ephemeral relayed frame the DM drives.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ApiClient } from "./api";
import { useToken } from "./auth";
import { API_BASE_URL } from "./useApi";
import type { EventAudience, EventKind } from "./types";
import {
  connectSessionRoom,
  type PresenceEntry,
  type RoomMessage,
  type SessionRoom,
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

/** The DM-driven turn order, relayed to the table (ephemeral, not persisted). */
export interface InitiativeState {
  order: string[];
  activeIndex: number;
}

export type RoomStatus = "connecting" | "open" | "closed" | "error";

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
  sendChat: (body: string) => void;
  sendOoc: (body: string) => void;
  sendRoll: (body: string, payload: Record<string, unknown>) => void;
  setInitiative: (state: InitiativeState) => void;
}

export function useRoom(sessionId: string, api: ApiClient | null): Room {
  const getToken = useToken();
  const [status, setStatus] = useState<RoomStatus>("connecting");
  const [closeCode, setCloseCode] = useState<number | null>(null);
  const [present, setPresent] = useState<PresenceEntry[]>([]);
  const [initiative, setInitiativeState] = useState<InitiativeState | null>(null);
  // Timeline entries keyed by seq so history and live frames dedupe cleanly.
  const [bySeq, setBySeq] = useState<Map<number, LogEntry>>(() => new Map());
  const roomRef = useRef<SessionRoom | null>(null);

  const upsert = useCallback((entry: LogEntry) => {
    setBySeq((prev) => {
      if (prev.has(entry.seq)) return prev;
      const next = new Map(prev);
      next.set(entry.seq, entry);
      return next;
    });
  }, []);

  const onMessage = useCallback(
    (message: RoomMessage) => {
      // RelayMessage's `type: string` defeats discriminated-union narrowing, so
      // read fields off a permissive frame view and validate each one by hand.
      const m = message as {
        type: string;
        present?: PresenceEntry[];
        order?: unknown;
        activeIndex?: unknown;
        seq?: unknown;
        body?: unknown;
        payload?: unknown;
        display_name?: unknown;
        audience?: unknown;
      };

      if (m.type === "presence") {
        setPresent(m.present ?? []);
        return;
      }
      if (m.type === "initiative") {
        setInitiativeState({
          order: Array.isArray(m.order) ? (m.order as string[]) : [],
          activeIndex: typeof m.activeIndex === "number" ? m.activeIndex : 0,
        });
        return;
      }
      const kind = FRAME_KIND[m.type];
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
          aiGenerated: false,
          audience: m.audience === "characters" || m.audience === "dm" ? m.audience : "table",
        });
      }
    },
    [upsert],
  );

  useEffect(() => {
    let cancelled = false;
    let room: SessionRoom | null = null;

    async function connect() {
      // Replay durable history first so the log isn't empty on join.
      if (api) {
        try {
          const log = await api.getSessionLog(sessionId);
          if (cancelled) return;
          setBySeq((prev) => {
            const next = new Map(prev);
            for (const e of log) {
              next.set(e.seq, {
                seq: e.seq,
                kind: e.kind,
                label: e.actor_label,
                body: e.body,
                payload: e.payload,
                aiGenerated: e.ai_generated,
                audience: e.audience,
              });
            }
            return next;
          });
        } catch {
          // A missing/blocked history is non-fatal; the live feed still works.
        }
      }

      const token = await getToken();
      if (cancelled) return;
      if (!token || !API_BASE_URL) {
        setStatus("error");
        return;
      }

      room = connectSessionRoom({
        baseUrl: API_BASE_URL,
        sessionId,
        token,
        onMessage,
        onOpen: () => !cancelled && setStatus("open"),
        onError: () => !cancelled && setStatus("error"),
        onClose: (event) => {
          if (cancelled) return;
          setStatus("closed");
          setCloseCode(event.code);
        },
      });
      roomRef.current = room;
    }

    void connect();
    return () => {
      cancelled = true;
      room?.close();
      roomRef.current = null;
    };
  }, [sessionId, api, getToken, onMessage]);

  const entries = useMemo(
    () => Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq),
    [bySeq],
  );

  const sendChat = useCallback((body: string) => roomRef.current?.sendChat(body), []);
  const sendOoc = useCallback((body: string) => roomRef.current?.sendOoc(body), []);
  const sendRoll = useCallback(
    (body: string, payload: Record<string, unknown>) =>
      roomRef.current?.sendRoll(body, payload),
    [],
  );
  const setInitiative = useCallback((state: InitiativeState) => {
    setInitiativeState(state); // optimistic local update
    roomRef.current?.send({ type: "initiative", ...state });
  }, []);

  return {
    status,
    closeCode,
    entries,
    present,
    initiative,
    sendChat,
    sendOoc,
    sendRoll,
    setInitiative,
  };
}
