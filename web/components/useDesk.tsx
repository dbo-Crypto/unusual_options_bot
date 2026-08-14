"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { WS_URL, api } from "@/lib/api";
import type { Overview } from "@/lib/types";

type Desk = {
  data: Overview | null;
  error: string | null;
  live: boolean;
  refresh: () => Promise<void>;
};

const DeskContext = createContext<Desk | null>(null);

export function DeskProvider({ children, pollMs = 8000 }: { children: ReactNode; pollMs?: number }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const busy = useRef(false);
  const queued = useRef(false);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    if (busy.current) {
      queued.current = true;
      return;
    }
    busy.current = true;
    try {
      do {
        queued.current = false;
        try {
          const next = await api.overview();
          if (mounted.current) {
            setData(next);
            setError(null);
          }
        } catch (err) {
          if (mounted.current) setError(err instanceof Error ? err.message : "API unavailable");
        }
      } while (queued.current);
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const id = setInterval(() => void refresh(), pollMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [pollMs, refresh]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(WS_URL);
      socket.onopen = () => setLive(true);
      socket.onclose = () => setLive(false);
      socket.onerror = () => setLive(false);
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data as string) as { type?: string };
          if (message.type === "signal" || message.type === "hello") {
            void refresh();
          }
        } catch {
          /* ignore */
        }
      };
    } catch {
      setLive(false);
    }
    return () => {
      socket?.close();
    };
  }, [refresh]);

  return <DeskContext.Provider value={{ data, error, live, refresh }}>{children}</DeskContext.Provider>;
}

export function useDesk(): Desk {
  const ctx = useContext(DeskContext);
  if (!ctx) {
    throw new Error("useDesk must be used inside DeskProvider");
  }
  return ctx;
}
