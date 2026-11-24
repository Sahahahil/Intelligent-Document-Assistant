'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Download, FileText, Copy, Check } from 'lucide-react';
import { api } from '@intelligent-doc-assistant/shared/client';
import { DocumentDetail } from '@intelligent-doc-assistant/shared/schemas';
import { formatDate } from '@/lib/utils';

interface DocumentPreviewProps {
  doc: DocumentDetail;
}

export function DocumentPreview({ doc }: DocumentPreviewProps) {
  const handleDownload = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/documents/${doc.id}/download`);
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const handleCopyText = async () => {
    try {
      const text = doc.chunks.map((c) => c.content).join('\n\n');
      await navigator.clipboard.writeText(text);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5" />
          {doc.filename}
        </CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{doc.chunking_strategy}</Badge>
          <Badge variant={doc.status === 'completed' ? 'success' : doc.status === 'processing' ? 'warning' : 'destructive'}>
            {doc.status}
          </Badge>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="h-4 w-4 mr-1" />
            Download
          </Button>
          <Button variant="outline" size="sm" onClick={handleCopyText}>
            <Copy className="h-4 w-4 mr-1" />
            Copy Text
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="preview" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="preview">Preview</TabsTrigger>
            <TabsTrigger value="metadata">Metadata</TabsTrigger>
          </TabsList>

          <TabsContent value="preview" className="mt-4">
            <div className="prose max-w-none">
              {doc.chunks.length === 0 ? (
                <p className="text-muted-foreground">No content available</p>
              ) : (
                doc.chunks.map((chunk, index) => (
                  <div key={chunk.id} className="mb-6 p-4 border rounded-lg bg-muted/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-muted-foreground">
                        Chunk {chunk.chunk_index} ({chunk.token_count} tokens)
                      </span>
                      {chunk.score !== undefined && (
                        <Badge variant="secondary">Score: {chunk.score.toFixed(4)}</Badge>
                      )}
                    </div>
                    <pre className="whitespace-pre-wrap text-sm">{chunk.content}</pre>
                  </div>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="metadata" className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <label className="text-muted-foreground">Document ID</label>
                <p className="font-mono break-all">{doc.id}</p>
              </div>
              <div>
                <label className="text-muted-foreground">Filename</label>
                <p>{doc.filename}</p>
              </div>
              <div>
                <label className="text-muted-foreground">Status</label>
                <p><Badge variant={doc.status === 'completed' ? 'success' : doc.status === 'processing' ? 'warning' : 'destructive'}>{doc.status}</Badge></p>
              </div>
              <div>
                <label className="text-muted-foreground">Chunking Strategy</label>
                <p>{doc.chunking_strategy}</p>
              </div>
              <div>
                <label className="text-muted-foreground">Total Chunks</label>
                <p>{doc.total_chunks}</p>
              </div>
              <div>
                <label className="text-muted-foreground">Embedding Model</label>
                <p>{doc.embedding_model}</p>
              </div>
              <div>
                <label className="text-muted-foreground">Embedding Dimension</label>
                <p>{doc.embedding_dim}</p>
              </div>
              <div>
                <label className="text-muted-foreground">Created</label>
                <p>{formatDate(doc.created_at)}</p>
              </div>
              {doc.completed_at && (
                <div>
                  <label className="text-muted-foreground">Completed</label>
                  <p>{formatDate(doc.completed_at)}</p>
                </div>
              )}
              {doc.error_message && (
                <div className="col-span-2">
                  <label className="text-destructive">Error</label>
                  <p className="text-destructive">{doc.error_message}</p>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}