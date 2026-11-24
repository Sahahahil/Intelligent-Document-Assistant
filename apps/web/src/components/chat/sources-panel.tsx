'use client';

import { ChevronDown, ChevronUp, FileText, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { Source } from '@intelligent-doc-assistant/shared/schemas';
import { useState } from 'react';
import { useToast } from '@/hooks/use-toast';

interface SourcesPanelProps {
  sources: Source[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  const [open, setOpen] = useState(true);
  const { toast } = useToast();

  const handleCopy = async (source: Source) => {
    try {
      const text = `Source: ${source.filename}, Chunk: ${source.chunk_index}, Score: ${source.score.toFixed(4)}\n\n${source.content}`;
      await navigator.clipboard.writeText(text);
      toast({ title: 'Copied', description: 'Source copied to clipboard' });
    } catch {
      toast({ title: 'Error', description: 'Failed to copy', variant: 'destructive' });
    }
  };

  if (!sources || sources.length === 0) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="w-full justify-start px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground">
        <div className="flex items-center gap-2">
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          <FileText className="h-4 w-4" />
          Sources ({sources.length})
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="p-4 space-y-3 border-t">
        {sources.map((source, index) => (
          <div key={index} className="p-3 border rounded-lg bg-muted/30">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="font-medium text-sm">{source.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    Chunk {source.chunk_index} • Score: {source.score.toFixed(4)}
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={() => handleCopy(source)} aria-label="Copy source">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </Button>
            </div>
            <pre className="whitespace-pre-wrap text-sm font-mono max-h-40 overflow-y-auto text-muted-foreground">
              {source.content}
            </pre>
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}