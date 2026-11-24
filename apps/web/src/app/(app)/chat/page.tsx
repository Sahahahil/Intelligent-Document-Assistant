'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { MessageList } from '@/components/chat/message-list';
import { MessageInput } from '@/components/chat/message-input';
import { ChatSession, SessionSidebar } from '@/components/chat/session-sidebar';
import { ChatMessage } from '@/components/chat/message';

const STORAGE_KEY = 'ida.sessions';

function newSession(): ChatSession {
  return {
    id: `session-${Date.now()}-${Math.floor(Math.random() * 1e4)}`,
    title: 'New conversation',
    messages: [],
  };
}

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as ChatSession[];
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    // A corrupt store is not worth a crash: start again.
  }
  return [newSession()];
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentId, setCurrentId] = useState('');
  const [busy, setBusy] = useState(false);

  const { data: documents, isPending: documentsPending } = useQuery({
    queryKey: ['documents'],
    queryFn: () => api.documents.list({ limit: 100, offset: 0 }),
  });

  useEffect(() => {
    const loaded = loadSessions();
    setSessions(loaded);
    setCurrentId(loaded[0].id);
  }, []);

  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    }
  }, [sessions]);

  const current = useMemo(
    () => sessions.find((session) => session.id === currentId),
    [sessions, currentId],
  );
  const messages = (current?.messages ?? []) as ChatMessage[];

  const updateCurrent = useCallback(
    (update: (session: ChatSession) => ChatSession) => {
      setSessions((all) =>
        all.map((session) => (session.id === currentId ? update(session) : session)),
      );
    },
    [currentId],
  );

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      // Until the document list has loaded, "no documents" is not a fact yet.
      if (!text || busy || !currentId || documentsPending) return;

      const ready = (documents?.items ?? []).filter(
        (document) => document.status === 'completed',
      );
      if (ready.length === 0) {
        updateCurrent((session) => ({
          ...session,
          messages: [
            ...session.messages,
            { role: 'user', content: text },
            {
              role: 'assistant',
              content:
                'There are no processed documents yet. Upload a PDF or TXT file in Documents, then ask again.',
            },
          ],
        }));
        return;
      }

      setBusy(true);
      updateCurrent((session) => ({
        ...session,
        title: session.messages.length === 0 ? text.slice(0, 40) : session.title,
        messages: [
          ...session.messages,
          { role: 'user', content: text },
          { role: 'assistant', content: '', streaming: true },
        ],
      }));

      try {
        await api.chat.stream(
          { session_id: currentId, message: text },
          (event) => {
            if (event.type === 'token') {
              updateCurrent((session) => ({
                ...session,
                messages: session.messages.map((message, index) =>
                  index === session.messages.length - 1
                    ? { ...message, content: message.content + event.content }
                    : message,
                ),
              }));
            } else if (event.type === 'sources') {
              updateCurrent((session) => ({
                ...session,
                messages: session.messages.map((message, index) =>
                  index === session.messages.length - 1
                    ? { ...message, sources: event.sources }
                    : message,
                ),
              }));
            } else if (event.type === 'booking') {
              // A booking turn answers with one message - there are no
              // tokens to stream.
              updateCurrent((session) => ({
                ...session,
                messages: session.messages.map((message, index) =>
                  index === session.messages.length - 1
                    ? { ...message, content: event.reply ?? '', streaming: false }
                    : message,
                ),
              }));
            } else if (event.type === 'error') {
              updateCurrent((session) => ({
                ...session,
                messages: session.messages.map((message, index) =>
                  index === session.messages.length - 1
                    ? { ...message, content: event.message, streaming: false }
                    : message,
                ),
              }));
            } else if (event.type === 'done') {
              updateCurrent((session) => ({
                ...session,
                messages: session.messages.map((message, index) =>
                  index === session.messages.length - 1
                    ? { ...message, streaming: false }
                    : message,
                ),
              }));
            }
          },
          () => {
            updateCurrent((session) => ({
              ...session,
              messages: session.messages.map((message, index) =>
                index === session.messages.length - 1
                  ? {
                      ...message,
                      content:
                        'The assistant could not be reached. Check that the API is running.',
                      streaming: false,
                    }
                  : message,
              ),
            }));
          },
        );
      } finally {
        setBusy(false);
      }
    },
    [busy, currentId, documents, documentsPending, updateCurrent],
  );

  return (
    <div className="flex h-full">
      <h1 className="sr-only">Chat</h1>
      <SessionSidebar
        sessions={sessions}
        currentId={currentId}
        onNewSession={() => {
          const session = newSession();
          setSessions((all) => [session, ...all]);
          setCurrentId(session.id);
        }}
        onSelectSession={setCurrentId}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <MessageList messages={messages} onSuggest={ask} />
        <MessageInput onSend={ask} disabled={busy || documentsPending} />
      </div>
    </div>
  );
}
