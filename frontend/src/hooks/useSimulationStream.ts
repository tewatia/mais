import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { eventsUrl } from '../api/simulations';

export type StreamStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'started'
  | 'typing'
  | 'finished'
  | 'stopped'
  | 'stopping'
  | 'error';

export type ChatItem = {
  id: string;
  role: 'agent' | 'moderator' | 'synthesizer' | 'system';
  name: string;
  content: string;
  turn?: number;
  model?: string;
  streaming?: boolean;
};

type TokenEvent = { name: string; turn: number; token: string; role: 'agent' | 'moderator' | 'synthesizer' };
type MessagePayload = {
  name: string;
  turn: number;
  content: string;
  role: 'agent' | 'moderator' | 'synthesizer';
  model?: string;
};
type StatusEvent = { status: StreamStatus; name?: string; turn?: number };
type ErrorEvent = { message: string };

function safeJsonParse<T>(s: string): T | null {
  try {
    return JSON.parse(s) as T;
  } catch {
    return null;
  }
}

function itemId(role: string, turn: number, name: string): string {
  return `${role}:${turn}:${name}`;
}

export function useSimulationStream(simulationId: string | null) {
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [typingName, setTypingName] = useState<string | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);

  const esRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    setItems([]);
    setTypingName(null);
    setStatus('idle');
  }, []);

  const disconnect = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setTypingName(null);
  }, []);

  const connect = useCallback(() => {
    if (!simulationId) return;
    disconnect();

    setStatus('connecting');
    const es = new EventSource(eventsUrl(simulationId));
    esRef.current = es;

    const onStatus = (ev: MessageEvent) => {
      const data = safeJsonParse<StatusEvent>(ev.data);
      if (!data) return;
      setStatus(data.status);
      if (data.status === 'typing' && data.name) setTypingName(data.name);
      if (['finished', 'stopped', 'error'].includes(data.status)) {
        setTypingName(null);
        disconnect();
      }
    };

    const onToken = (ev: MessageEvent) => {
      const data = safeJsonParse<TokenEvent>(ev.data);
      if (!data) return;

      setItems((prev) => {
        const id = itemId(data.role, data.turn, data.name);
        const idx = prev.findIndex((x) => x.id === id);
        if (idx === -1) {
          return [
            ...prev,
            {
              id,
              role: data.role,
              name: data.name,
              content: data.token,
              turn: data.turn,
              streaming: true,
            },
          ];
        }
        const next = prev.slice();
        next[idx] = { ...next[idx], content: next[idx].content + data.token, streaming: true };
        return next;
      });
    };

    const onMessage = (ev: MessageEvent) => {
      const data = safeJsonParse<MessagePayload>(ev.data);
      if (!data) return;

      setItems((prev) => {
        const id = itemId(data.role, data.turn, data.name);
        const idx = prev.findIndex((x) => x.id === id);
        if (idx === -1) {
          return [
            ...prev,
            { id, role: data.role, name: data.name, content: data.content, turn: data.turn, model: data.model },
          ];
        }
        const next = prev.slice();
        next[idx] = { ...next[idx], content: data.content, streaming: false, model: data.model };
        return next;
      });
    };

    const onError = (ev: MessageEvent) => {
      const data = safeJsonParse<ErrorEvent>(ev.data);
      if (!data) return;
      setStatus('error');
      setTypingName(null);
      setItems((prev) => [
        ...prev,
        { id: `system:${Date.now()}`, role: 'system', name: 'System', content: data.message },
      ]);
    };

    es.addEventListener('status', onStatus as any);
    es.addEventListener('token', onToken as any);
    es.addEventListener('message', onMessage as any);
    es.addEventListener('error', onError as any);

    es.onerror = () => {
      // Network error / server disconnect. Surface in UI but don't spam.
      setStatus('error');
      setTypingName(null);
    };
  }, [disconnect, simulationId]);

  useEffect(() => {
    if (!simulationId) {
      disconnect();
      return;
    }
    connect();
    return () => disconnect();
  }, [connect, disconnect, simulationId]);

  const canStop = useMemo(() => {
    return status === 'started' || status === 'typing' || status === 'connected' || status === 'stopping';
  }, [status]);

  return { status, typingName, items, reset, connect, disconnect, canStop };
}


