'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@intelligent-doc-assistant/shared/client';
import { DocumentSummary } from '@intelligent-doc-assistant/shared/schemas';

interface Stage {
  stage: string;
  progress: number;
  total_chunks?: number;
}

const STAGE_LABEL: Record<string, string> = {
  extracting: 'Extracting text',
  chunking: 'Chunking',
  embedding: 'Embedding',
  indexing: 'Indexing',
  processing: 'Indexing',
  completed: 'Ready',
  failed: 'Failed',
};

function fileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

function Pill({ status, label }: { status: string; label: string }) {
  const tone =
    status === 'completed'
      ? 'var(--ok)'
      : status === 'failed'
        ? 'var(--danger)'
        : 'var(--warn)';
  return (
    <span
      className="justify-self-end rounded-full px-2.5 py-0.5 text-[12px] font-semibold"
      style={{
        background: `color-mix(in srgb, ${tone} 16%, transparent)`,
        color: tone,
      }}
    >
      {label}
    </span>
  );
}

function DocumentCard({
  document,
  stage,
  onDelete,
}: {
  document: DocumentSummary;
  stage?: Stage;
  onDelete: (document: DocumentSummary) => void;
}) {
  const working = document.status === 'processing';
  const label = STAGE_LABEL[stage?.stage ?? document.status] ?? document.status;
  const progress = stage?.progress ?? (working ? 5 : 100);
  const chunks = stage?.total_chunks ?? document.total_chunks;

  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1.5 rounded-xl border border-line bg-card px-4 py-3.5">
      <div className="min-w-0">
        <a
          href={`/documents/${document.id}`}
          className="block truncate font-semibold hover:underline"
        >
          {document.filename}
        </a>
        <small className="text-muted-foreground">
          {fileSize(document.file_size)}
          {chunks > 0 ? ` · ${chunks} ${chunks === 1 ? 'chunk' : 'chunks'}` : ''}
          {document.status === 'failed' ? ' · could not be indexed' : ''}
        </small>
      </div>
      <Pill status={document.status === 'failed' ? 'failed' : working ? 'busy' : 'completed'} label={label} />
      {working ? (
        <div className="col-span-full h-1 overflow-hidden rounded-full bg-line">
          <i
            className="block h-full rounded-full bg-primary transition-[width] duration-300"
            style={{ width: `${Math.max(4, progress)}%` }}
          />
        </div>
      ) : (
        <>
          <span />
          <button
            type="button"
            onClick={() => onDelete(document)}
            className="justify-self-end text-[13px] text-destructive"
          >
            Delete
          </button>
        </>
      )}
    </div>
  );
}

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [stages, setStages] = useState<Record<string, Stage>>({});
  const [error, setError] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: () => api.documents.list({ limit: 100, offset: 0 }),
  });

  const documents = data?.items ?? [];
  const processingIds = documents
    .filter((document) => document.status === 'processing')
    .map((document) => document.id)
    .join(',');

  // Follow the documents that are still being indexed.
  useEffect(() => {
    if (!processingIds) return;
    const stops = processingIds.split(',').map((id) =>
      api.documents.statusStream(id, (event) => {
        setStages((current) => ({ ...current, [id]: event }));
        if (event.stage === 'completed' || event.stage === 'failed') {
          queryClient.invalidateQueries({ queryKey: ['documents'] });
        }
      }),
    );
    return () => stops.forEach((stop) => stop());
  }, [processingIds, queryClient]);

  const upload = async (files: File[]) => {
    setError('');
    for (const file of files) {
      if (!/\.(pdf|txt)$/i.test(file.name)) {
        setError(`${file.name}: only PDF and TXT files are allowed`);
        continue;
      }
      try {
        await api.documents.ingest(file, { chunking_strategy: 'recursive' });
        queryClient.invalidateQueries({ queryKey: ['documents'] });
      } catch {
        setError(`${file.name}: the upload failed`);
      }
    }
  };

  const remove = async (document: DocumentSummary) => {
    if (!window.confirm(`Delete "${document.filename}" and everything indexed from it?`)) {
      return;
    }
    await api.documents.delete(document.id);
    queryClient.invalidateQueries({ queryKey: ['documents'] });
  };

  return (
    <div className="h-full w-full overflow-auto px-8 py-7 max-[820px]:px-4 max-[820px]:py-5">
      <div className="mx-auto max-w-[820px]">
        <div className="mb-[22px] flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[28px]">Documents</h1>
            <p className="mt-1 text-muted-foreground">
              Files are split into chunks and embedded so chat can cite them.
            </p>
          </div>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            upload(Array.from(e.dataTransfer.files));
          }}
          className={`mb-[22px] rounded-[14px] border-[1.5px] border-dashed bg-card px-8 py-7 text-center text-muted-foreground transition-colors ${
            dragOver ? 'border-primary bg-secondary' : 'border-line'
          }`}
        >
          Drop PDF or TXT files here
          <br />
          <button
            type="button"
            className="btn sec mt-2.5"
            onClick={() => fileInput.current?.click()}
          >
            Choose files
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.txt"
            multiple
            hidden
            onChange={(e) => {
              upload(Array.from(e.target.files ?? []));
              e.target.value = '';
            }}
          />
        </div>

        {error && <p className="mb-[22px] text-[13px] text-destructive">{error}</p>}

        {isLoading ? (
          <p className="text-muted-foreground">Loading documents…</p>
        ) : documents.length === 0 ? (
          <p className="text-muted-foreground">
            No documents yet. Upload one to start asking questions.
          </p>
        ) : (
          <div className="grid gap-2.5">
            {documents.map((document) => (
              <DocumentCard
                key={document.id}
                document={document}
                stage={stages[document.id]}
                onDelete={remove}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
