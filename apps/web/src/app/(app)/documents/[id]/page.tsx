'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';

function fileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const id = params.id as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ['document', id],
    queryFn: () => api.documents.get(id),
  });

  const remove = useMutation({
    mutationFn: () => api.documents.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      router.push('/documents');
    },
  });

  if (isLoading) {
    return <p className="px-8 py-7 text-muted-foreground">Loading document…</p>;
  }

  if (error || !data) {
    return (
      <div className="px-8 py-7">
        <p className="text-muted-foreground">This document could not be loaded.</p>
        <Link href="/documents" className="text-primary hover:underline">
          ← Back to documents
        </Link>
      </div>
    );
  }

  const facts: [string, string][] = [
    ['Status', data.status],
    ['Size', fileSize(data.file_size)],
    ['Chunks', String(data.total_chunks)],
    ['Chunking', data.chunking_strategy],
    ['Chunk size', `${data.chunk_size} words`],
    ['Overlap', `${data.chunk_overlap} words`],
    ['Embedding model', data.embedding_model],
    ['Dimensions', String(data.embedding_dim)],
    ['Added', new Date(data.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })],
  ];

  if (data.error_message) {
    facts.push(['Error', data.error_message]);
  }

  return (
    <div className="h-full w-full overflow-auto px-8 py-7 max-[820px]:px-4 max-[820px]:py-5">
      <div className="mx-auto max-w-[900px]">
        <Link href="/documents" className="text-[13px] text-muted-foreground hover:text-foreground">
          ← Documents
        </Link>
        <div className="mb-5 mt-2">
          <h1 className="text-[28px]">{data.filename}</h1>
          <p className="mt-1 text-muted-foreground">
            {fileSize(data.file_size)} · {data.total_chunks} chunks · {data.chunking_strategy} chunking
          </p>
        </div>

        <div className="card">
          <h3 className="mb-3 text-[19px]">Details</h3>
          <dl className="grid gap-2.5 text-[14px]">
            {facts.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3 border-b border-line pb-2.5 last:border-0">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="text-right break-all">{value}</dd>
              </div>
            ))}
          </dl>
          <button
            type="button"
            className="mt-4 w-full rounded-lg border border-line px-3 py-2 text-[14px] text-destructive"
            onClick={() => {
              if (window.confirm(`Delete "${data.filename}" and everything indexed from it?`)) {
                remove.mutate();
              }
            }}
            disabled={remove.isPending}
          >
            {remove.isPending ? 'Deleting…' : 'Delete document'}
          </button>
        </div>
      </div>
    </div>
  );
}
