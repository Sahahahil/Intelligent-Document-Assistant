'use client';

import { useEffect, useRef, useState } from 'react';

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function MessageInput({
  onSend,
  disabled = false,
  placeholder = 'Ask about your documents',
}: MessageInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const send = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue('');
  };

  return (
    <div className="px-8 pb-[22px] pt-3.5">
      <div className="mx-auto flex max-w-[720px] items-end gap-2.5 rounded-[14px] border border-line bg-card py-2 pl-3.5 pr-2">
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          placeholder={placeholder}
          aria-label="Message"
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          className="max-h-[140px] flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-[1.55] outline-none placeholder:text-muted-foreground"
        />
        <button type="button" className="btn" onClick={send} disabled={disabled || !value.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
