import type { z } from 'zod';
import type {
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  Source,
  DocumentIngestResponse,
  DocumentSummary,
  DocumentDetail,
  DocumentListParams,
  DocumentListResponse,
  DocumentStatusEvent,
  Booking,
  BookingListParams,
  BookingListResponse,
} from '../schemas';

function getApiBase(): string {
  if (typeof window !== 'undefined') {
    return (window as any).__NEXT_PUBLIC_API_URL__ || '/api';
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

type FetchOptions = RequestInit & { params?: Record<string, string | number | boolean | undefined> };

class ApiError extends Error {
  constructor(
    public status: number,
    public data: unknown,
  ) {
    super(`API Error: ${status}`);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const url = new URL(`${getApiBase()}${path}`);
  if (options.params) {
    Object.entries(options.params).forEach(([k, v]) => {
      if (v !== undefined) url.searchParams.set(k, String(v));
    });
  }

  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.json().catch(() => ({})));
  }
  return res.json();
}

async function fetchFormData<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, { method: 'POST', body: formData });
  if (!res.ok) {
    throw new ApiError(res.status, await res.json().catch(() => ({})));
  }
  return res.json();
}

function fetchSSE<T>(
  path: string,
  options: FetchOptions,
  onEvent: (event: T) => void,
): () => void {
  const controller = new AbortController();
  const url = new URL(`${getApiBase()}${path}`);

  fetch(url, { ...options, signal: controller.signal })
    .then((res) => {
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const read = async () => {
        while (true) {
          const { done, value } = await reader!.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                onEvent(JSON.parse(line.slice(6)));
              } catch {
                // Ignore parse errors
              }
            }
          }
        }
      };
      return read();
    })
    .catch(() => {
      // Ignore abort errors
    });

  return () => controller.abort();
}

export const api = {
  chat: {
    send: (req: ChatRequest) =>
      fetchJson<ChatResponse>('/api/v1/chat', { method: 'POST', body: JSON.stringify(req) }),
    stream: (req: ChatRequest, onToken: (token: string) => void) =>
      fetchSSE<ChatStreamEvent>('/api/v1/chat/stream', { method: 'POST', body: JSON.stringify(req) }, (event) => {
        if (event.type === 'token') onToken(event.content);
      }),
  },
  documents: {
    ingest: (file: File, opts: { chunking_strategy?: string; chunk_size?: number; chunk_overlap?: number } = {}) => {
      const fd = new FormData();
      fd.append('file', file);
      if (opts.chunking_strategy) fd.append('chunking_strategy', opts.chunking_strategy);
      if (opts.chunk_size) fd.append('chunk_size', String(opts.chunk_size));
      if (opts.chunk_overlap) fd.append('chunk_overlap', String(opts.chunk_overlap));
      return fetchFormData<DocumentIngestResponse>('/api/v1/documents/ingest', fd);
    },
    list: (params: DocumentListParams) =>
      fetchJson<DocumentListResponse>('/api/v1/documents', { params }),
    get: (id: string) => fetchJson<DocumentDetail>(`/api/v1/documents/${id}`),
    delete: (id: string) => fetchJson<void>(`/api/v1/documents/${id}`, { method: 'DELETE' }),
    statusStream: (id: string, onEvent: (e: DocumentStatusEvent) => void) =>
      fetchSSE<DocumentStatusEvent>(`/api/v1/documents/${id}/status/stream`, {}, onEvent),
  },
  bookings: {
    list: (params: BookingListParams) => fetchJson<BookingListResponse>('/api/v1/bookings', { params }),
    get: (id: string) => fetchJson<Booking>(`/api/v1/bookings/${id}`),
    create: (data: { name: string; email: string; date: string; time: string }) =>
      fetchJson<Booking>('/api/v1/bookings', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Booking>) =>
      fetchJson<Booking>(`/api/v1/bookings/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) => fetchJson<void>(`/api/v1/bookings/${id}`, { method: 'DELETE' }),
  },
};

export { ApiError };