'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { DocumentPreview } from './document-preview';
import { DocumentMetadata } from './document-metadata';
import { Skeleton } from '@/components/ui/skeleton';

interface DocumentDetailProps {
  id: string;
  onClose: () => void;
}

export function DocumentDetail({ id, onClose }: DocumentDetailProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['document', id],
    queryFn: () => api.documents.get(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex gap-6">
        <div className="flex-1 space-y-4">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-64 w-full" />
        </div>
        <div className="w-72 space-y-4">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Document not found</p>
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      <div className="flex-1">
        <DocumentPreview doc={data} />
      </div>
      <div className="w-72 flex-shrink-0">
        <DocumentMetadata document={data} onDelete={onClose} />
      </div>
    </div>
  );
}