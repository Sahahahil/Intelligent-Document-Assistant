'use client';

import Markdown from 'react-markdown';
import { Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Source } from '@intelligent-doc-assistant/shared/schemas';
import { useState } from 'react';
import { useToast } from '@/hooks/use-toast';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  sources?: Source[];
}

interface MessageProps {
  message: ChatMessage;
  onCopy?: (text: string) => void;
}

export function Message({ message, onCopy }: MessageProps) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast({ title: 'Copied', description: 'Message copied to clipboard' });
      onCopy?.(message.content);
    } catch {
      toast({ title: 'Error', description: 'Failed to copy', variant: 'destructive' });
    }
  };

  return (
    <div className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : ''}`}>
      <div
        className={`max-w-[70%] ${
          message.role === 'assistant'
            ? 'bg-white dark:bg-gray-800 p-4 rounded-lg shadow'
            : 'bg-blue-600 text-white p-4 rounded-lg'
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <Markdown>{message.content}</Markdown>
            </div>
            {message.streaming && (
              <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleCopy}
            className="opacity-0 group-hover:opacity-100 transition-opacity"
          >
            {copied ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            )}
          </Button>
        </div>
        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
              <span>Sources:</span>
              {message.sources.map((source, i) => (
                <Badge key={i} variant="outline" className="text-xs">
                  {source.filename} (chunk {source.chunk_index})
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}