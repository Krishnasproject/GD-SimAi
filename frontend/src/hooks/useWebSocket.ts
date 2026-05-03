import { useEffect, useRef, useState, useCallback } from 'react';

type WebSocketMessage = {
  type: string;
  [key: string]: unknown;
};

type MessageHandler = (data: WebSocketMessage) => void;

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

export function useWebSocket(url: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);

  // Handlers registered by components
  const handlers = useRef<Record<string, MessageHandler>>({});
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const urlRef = useRef<string | null>(url);
  const intentionalCloseRef = useRef(false);

  // Keep urlRef in sync
  useEffect(() => {
    urlRef.current = url;
  }, [url]);

  const connect = useCallback((endpoint: string) => {
    // Close any existing socket intentionally before opening a new one
    if (ws.current) {
      intentionalCloseRef.current = true;
      ws.current.close();
    }

    intentionalCloseRef.current = false;
    const socket = new WebSocket(endpoint);
    ws.current = socket;

    socket.onopen = () => {
      // Ignore events from a socket that's no longer current (StrictMode double-invoke)
      if (ws.current !== socket) return;
      console.log('🔗 WebSocket Connected to', endpoint);
      setIsConnected(true);
      setIsReconnecting(false);
      retryCountRef.current = 0;
    };

    socket.onmessage = (event) => {
      if (ws.current !== socket) return;
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        if (data.type && handlers.current[data.type]) {
          handlers.current[data.type](data);
        } else {
          console.debug('📬 Unhandled WS Message:', data);
        }
      } catch (err) {
        console.error('❌ Failed to parse WS message:', event.data, err);
      }
    };

    socket.onclose = () => {
      // If this socket is no longer the active one, it was replaced — don't retry
      if (ws.current !== socket) return;
      console.log('🔴 WebSocket Disconnected');
      setIsConnected(false);

      // Only retry if not an intentional close and retries remain
      if (!intentionalCloseRef.current && retryCountRef.current < MAX_RETRIES) {
        retryCountRef.current += 1;
        setIsReconnecting(true);
        console.log(`🔄 Reconnecting... attempt ${retryCountRef.current}/${MAX_RETRIES}`);

        retryTimerRef.current = setTimeout(() => {
          // Double-check we still want to reconnect (intentional close may have come in during delay)
          if (!intentionalCloseRef.current && urlRef.current) {
            connect(urlRef.current);
          }
        }, RETRY_DELAY_MS);
      } else {
        setIsReconnecting(false);
      }
    };

    socket.onerror = (error) => {
      if (ws.current !== socket) return;
      console.error('⚠️ WebSocket Error:', error);
    };
  }, []);

  useEffect(() => {
    if (url) {
      connect(url);
    }
    return () => {
      intentionalCloseRef.current = true;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      if (ws.current) ws.current.close();
    };
  }, [url, connect]);

  const addHandler = useCallback((msgType: string, handler: MessageHandler) => {
    handlers.current[msgType] = handler;
  }, []);

  const removeHandler = useCallback((msgType: string) => {
    delete handlers.current[msgType];
  }, []);

  const sendJson = useCallback((data: WebSocketMessage) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data));
    } else {
      console.warn('⚠️ WebSocket not open, failed to send:', data);
    }
  }, []);

  return {
    isConnected,
    isReconnecting,
    addHandler,
    removeHandler,
    sendJson,
    connect,
  };
}
