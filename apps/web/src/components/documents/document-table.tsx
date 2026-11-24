'use client';

import { useState } from 'react';
import { formatDate } from '@/lib/utils';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Trash2, FileText, Eye, Loader2 } from 'lucide-react';
import { api } from '@intelligent-doc-assistant/shared/client';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/hooks/use-toast';
import { DocumentSummary } from '@intelligent-doc-assistant/shared/schemas';

interface DocumentTableProps {
  documents: DocumentSummary[];
  onView?: (id: string) => void;
}

export function DocumentTable({ documents, onView }: DocumentTableProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.documents.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      toast({ title: 'Success', description: 'Document deleted' });
    },
    onError: (error: Error) => {
      toast({ title: 'Error', description: error.message, variant: 'destructive' });
    },
  });

  const handleSort = (key: string) => {
    setSortConfig((current) => ({
      key,
      direction: current?.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const sortedDocuments = [...documents].sort((a, b) => {
    if (!sortConfig) return 0;
    const aValue = a[sortConfig.key as keyof DocumentSummary];
    const bValue = b[sortConfig.key as keyof DocumentSummary];
    if (aValue === undefined || bValue === undefined) return 0;
    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
    return 0;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success">{status}</Badge>;
      case 'processing':
        return <Badge variant="warning">{status}</Badge>;
      case 'failed':
        return <Badge variant="destructive">{status}</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (confirm(`Are you sure you want to delete "${name}"?`)) {
      deleteMutation.mutate(id);
    }
  };

  if (documents.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
        <h3 className="text-lg font-medium">No documents yet</h3>
        <p className="text-muted-foreground">Upload your first document to get started</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="cursor-pointer" onClick={() => handleSort('filename')}>
              Filename {sortConfig?.key === 'filename' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
            </TableHead>
            <TableHead className="cursor-pointer" onClick={() => handleSort('status')}>
              Status {sortConfig?.key === 'status' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
            </TableHead>
            <TableHead className="cursor-pointer" onClick={() => handleSort('total_chunks')}>
              Chunks {sortConfig?.key === 'total_chunks' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
            </TableHead>
            <TableHead className="cursor-pointer" onClick={() => handleSort('created_at')}>
              Uploaded {sortConfig?.key === 'created_at' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
            </TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedDocuments.map((doc) => (
            <TableRow key={doc.id} className="hover:bg-muted/50">
              <TableCell>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <span className="max-w-[300px] truncate">{doc.filename}</span>
                </div>
              </TableCell>
              <TableCell>{getStatusBadge(doc.status)}</TableCell>
              <TableCell>{doc.total_chunks}</TableCell>
              <TableCell>{formatDate(doc.created_at)}</TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  {onView && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => onView(doc.id)}
                      aria-label="View document"
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(doc.id, doc.filename)}
                    disabled={deleteMutation.isPending}
                    aria-label="Delete document"
                  >
                    {deleteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}