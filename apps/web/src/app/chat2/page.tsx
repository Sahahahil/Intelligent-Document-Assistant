'use client';

import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { MessageList } from '@/components/chat/message-list';
import { MessageInput } from '@/components/chat/message-input';
import { SessionSidebar } from '@/components/chat/session-sidebar';
import { ChatMessage } from '@/components/chat/message';
import { Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function ChatPage() {
  const [sessionId] = useState(() => `session-${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [documentIds, setDocumentIds] = useState<string[]>([]);

  const streamMutation = useMutation({
    mutationFn: async (message: string) => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/chat/stream`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message, document_ids: documentIds }),
        }
      );

      if (!response.ok) throw new Error('Stream failed');

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader!.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'token') {
                setMessages(prev => updateLastMessage(prev, event.content));
              } else if (event.type === 'sources') {
                setMessages(prev => {
                  const newMessages = [...prev];
                  if (newMessages.length > 0) {
                    newMessages[newMessages.length - 1] = {
                      ...newMessages[newMessages.length - 1],
                      sources: event.sources,
                    };
                  }
                  return newMessages;
                });
              } else if (event.type === 'done') {
                setMessages(prev => {
                  const newMessages = [...prev];
                  if (newMessages.length > 0) {
                    newMessages[newMessages.length - 1] = {
                      ...newMessages[newMessages.length - 1],
                      streaming: false,
                    };
                  }
                  return newMessages;
                });
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
    },
    onSuccess: () => {
      setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }]);
    },
  });

  const updateLastMessage = (messages: ChatMessage[], token: string): ChatMessage[] => {
    const newMessages = [...messages];
    if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === 'assistant') {
      newMessages[newMessages.length - 1] = {
        ...newMessages[newMessages.length - 1],
        content: newMessages[newMessages.length - 1].content + token,
      };
    }
    return newMessages;
  };

  const handleSend = (message: string) => {
    setMessages(prev => [...prev, { role: 'user', content: message }, { role: 'assistant', content: '', streaming: true }]);
    streamMutation.mutate(message);
  };

  return (
    <div className="flex h-full gap-6">
      <SessionSidebar
        sessionId={sessionId}
        onNewSession={() => {
          setMessages([]);
          setDocumentIds([]);
        }}
        onSelectSession={(id) => {
          // TODO: Load session messages
        }}
        onDeleteSession={(id) => {
          // TODO: Delete session
        }}
        onRenameSession={(id, title) => {
          // TODO: Rename session
        }}
      />
      <div className="flex-1 flex flex-col">
        <div className="flex items-center justify-between p-4 border-b">
          <h1 className="text-xl font-semibold">Chat</h1>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Session: {sessionId.slice(0, 8)}...</span>
          </div>
        </div>
        <MessageList messages={messages} />
        <MessageInput onSend={handleSend} disabled={streamMutation.isPending} />
      </div>
    </div>
  );
}
