'use client';

import { useRef, useEffect } from 'react';
import { Message } from './message';
import { SourcesPanel } from './sources-panel';
import { ChatMessage } from './message';

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto space-y-4 p-4">
      {messages.map((msg, i) => (
        <Message key={i} message={msg} />
      ))}
      <div ref={endRef} />
      {messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.sources && (
        <SourcesPanel sources={messages[messages.length - 1].sources!} />
      )}
    </div>
  );
}