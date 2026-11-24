'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Trash2, FileText, Loader2, Eye } from 'lucide-react';
import { api } from '@intelligent-doc-assistant/shared/client';
import { DocumentDetail } from '@intelligent-doc-assistant/shared/schemas';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/hooks/use-toast';
import { formatDate } from '@/lib/utils';

interface DocumentMetadataProps {
  document: DocumentDetail;
  onDelete?: () => void;
}

export function DocumentMetadata({ document, onDelete }: DocumentMetadataProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.documents.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      toast({ title: 'Success', description: 'Document deleted' });
      onDelete?.();
    },
    onError: (error: Error) => {
      toast({ title: 'Error', description: error.message, variant: 'destructive' });
    },
  });

  const handleDelete = () => {
    if (confirm(`Are you sure you want to delete "${document.filename}"?`)) {
      deleteMutation.mutate(document.id);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Details
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3 text-sm">
          <div>
            <label className="text-muted-foreground">Document ID</label>
            <p className="font-mono break-all">{document.id}</p>
          </div>
          <div>
            <label className="text-muted-foreground">Status</label>
            <Badge variant={
              document.status === 'completed' ? 'success' :
              document.status === 'processing' ? 'warning' : 'destructive'
            }>
              {document.status}
            </Badge>
          </div>
          <div>
            <label className="text-muted-foreground">Chunking Strategy</label>
            <p>{document.chunking_strategy}</p>
          </div>
          <div>
            <label className="text-muted-foreground">Total Chunks</label>
            <p>{document.total_chunks}</p>
          </div>
          <div>
            <label className="text-muted-foreground">Embedding Model</label>
            <p className="text-xs break-all">{document.embedding_model}</p>
          </div>
          <div>
            <label className="text-muted-foreground">Embedding Dimension</label>
            <p>{document.embedding_dim}</p>
          </div>
          <div>
            <label className="text-muted-foreground">Created</label>
            <p>{formatDate(document.created_at)}</p>
          </div>
          {document.completed_at && (
            <div>
              <label className="text-muted-foreground">Completed</label>
              <p>{formatDate(document.completed_at)}</p>
            </div>
          )}
          {document.duration_ms && (
            <div>
              <label className="text-muted-foreground">Processing Time</label>
              <p>{(document.duration_ms / 1000).toFixed(1)}s</p>
            </div>
          )}
          {document.error_message && (
            <div className="text-destructive">
              <label>Error</label>
              <p>{document.error_message}</p>
            </div>
          )}
        </div>

        <div className="pt-4 border-t space-y-2">
          <Button variant="outline" className="w-full" onClick={handleDelete} disabled={deleteMutation.isPending}>
            <Trash2 className="h-4 w-4 mr-2" />
            {deleteMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Deleting...
              </>
            ) : (
              'Delete Document'
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}