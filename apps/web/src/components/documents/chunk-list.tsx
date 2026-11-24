'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Copy, Check } from 'lucide-react';
import { DocumentChunk } from '@intelligent-doc-assistant/shared/schemas';
import { useState } from 'react';
import { useToast } from '@/hooks/use-toast';

interface ChunkListProps {
  chunks: DocumentChunk[];
}

export function ChunkList({ chunks }: ChunkListProps) {
  const { toast } = useToast();
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopy = async (index: number, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
      toast({ title: 'Copied', description: 'Chunk copied to clipboard' });
    } catch {
      toast({ title: 'Error', description: 'Failed to copy', variant: 'destructive' });
    }
  };

  if (!chunks || chunks.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          No chunks available
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Chunks ({chunks.length})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {chunks.map((chunk, index) => (
            <div
              key={chunk.id}
              className="p-4 border rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Chunk {chunk.chunk_index}</Badge>
                  <Badge variant="outline">{chunk.token_count} tokens</Badge>
                  {chunk.score !== undefined && (
                    <Badge variant="default">Score: {chunk.score.toFixed(4)}</Badge>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleCopy(index, chunk.content)}
                  aria-label="Copy chunk"
                >
                  {copiedIndex === index ? (
                    <Check className="h-4 w-4 text-green-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
              <pre className="whitespace-pre-wrap text-sm font-mono max-h-40 overflow-y-auto">
                {chunk.content}
              </pre>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}