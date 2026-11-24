'use client';

import { Source } from '@intelligent-doc-assistant/shared/schemas';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  sources?: Source[];
}

/** The inline citations the model writes, e.g. "(Leave_Policy.pdf)". */
const CITATION = /\(([^()\s]+\.[a-z]{2,4})\)/g;

function Answer({ content }: { content: string }) {
  const paragraphs = content.split(/\n\n+/).filter(Boolean);
  return (
    <>
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="mb-2.5 last:mb-0">
          {paragraph.split(CITATION).map((part, i) =>
            i % 2 === 1 ? (
              <span
                key={i}
                className="mx-0.5 inline-block rounded-[5px] border border-hi bg-hi-soft px-[5px] align-[1px] text-[11px] font-semibold text-foreground"
              >
                {part}
              </span>
            ) : (
              <span key={i}>{part}</span>
            ),
          )}
        </p>
      ))}
    </>
  );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  return (
    <div className="max-w-[260px] rounded-lg border border-line bg-card px-2.5 py-1.5 text-[12.5px] text-muted-foreground">
      <b className="block font-semibold text-foreground">
        {index + 1} · {source.filename}
      </b>
      Chunk {source.chunk_index} · score {source.score.toFixed(3)}
    </div>
  );
}

export function Message({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="mb-[22px] flex justify-end">
        <div className="max-w-[80%] rounded-[14px_14px_3px_14px] bg-primary px-3.5 py-2.5 text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="mb-[22px]">
      <div className="text-[16px] leading-[1.65]">
        <Answer content={message.content} />
        {message.streaming && (
          <span className="inline-block h-[1em] w-[7px] translate-y-[2px] animate-[blink_1s_steps(2)_infinite] bg-primary" />
        )}
      </div>
      {message.sources && message.sources.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {message.sources.map((source, index) => (
            <SourceCard key={`${source.document_id}-${source.chunk_index}`} source={source} index={index} />
          ))}
        </div>
      )}
    </div>
  );
}
