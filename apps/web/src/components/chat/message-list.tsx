'use client';

import { useEffect, useRef } from 'react';
import { ChatMessage, Message } from './message';

const SUGGESTIONS = [
  'What uptime does the SLA promise?',
  'How does a release get rolled back?',
  'How quickly do support requests get a first response?',
];

interface MessageListProps {
  messages: ChatMessage[];
  onSuggest: (question: string) => void;
}

export function MessageList({ messages, onSuggest }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-auto px-8 py-7">
      <div className="mx-auto max-w-[720px]">
        {messages.length === 0 ? (
          <div className="flex min-h-[52vh] flex-col justify-center text-center">
            <h2 className="mb-2 text-[32px]">What would you like to know?</h2>
            <p className="mb-[22px] text-muted-foreground">
              Answers come from your uploaded documents, with sources.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => onSuggest(question)}
                  className="rounded-full border border-line bg-card px-3.5 py-[7px] text-[14px] transition-colors hover:border-primary"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <Message key={index} message={message} />
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
