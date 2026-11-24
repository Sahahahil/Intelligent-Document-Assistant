'use client';

import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { DocumentPreview } from '@/components/documents/document-preview';
import { ChunkList } from '@/components/documents/chunk-list';
import { DocumentMetadata } from '@/components/documents/document-metadata';
import { Skeleton } from '@/components/ui/skeleton';
import { notFound } from 'next/navigation';
import { formatDate } from '@/lib/utils';

export default function DocumentDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const { data, isLoading } = useQuery({
    queryKey: ['document', id],
    queryFn: () => api.documents.get(id),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-10 w-32" />
        </div>
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-96 w-full" />
          </div>
          <Skeleton className="h-96 w-full" />
        </div>
      </div>
    );
  }

  if (!data) {
    notFound();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{data.filename}</h1>
          <p className="text-muted-foreground">Document details and chunks</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {formatDate(data.created_at)}
          </span>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <DocumentPreview doc={data} />
          <ChunkList chunks={data.chunks} />
        </div>
        <DocumentMetadata document={data} />
      </div>
    </div>
  );
}