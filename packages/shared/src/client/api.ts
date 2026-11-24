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
    // The browser talks to its own origin: the app proxies /api/v1 to the
    // API, so there is one origin and no CORS to negotiate.
    return '';
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

/** The API on the same origin in the browser, so the app has one origin. */
function apiUrl(path: string): string {
  const base = getApiBase();
  const origin = typeof window !== 'undefined' ? window.location.origin : base;
  return new URL(`${base}${path}`, origin).toString();
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
  const url = new URL(apiUrl(path));
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
  // A 204 carries no body: parsing it as JSON would throw.
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function fetchFormData<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(apiUrl(path), { method: 'POST', body: formData });
  if (!res.ok) {
    throw new ApiError(res.status, await res.json().catch(() => ({})));
  }
  return res.json();
}

/**
 * The events in one chunk of a server-sent-events stream.
 *
 * The server separates events with a blank line; SSE allows either \n or
 * \r\n, and the Python server uses \r\n.
 */
export function parseSseEvents(buffer: string): { events: string[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? '';
  return { events: parts, rest };
}

/** The payload of one SSE event, or null when it carries no data. */
export function sseData(event: string): string | null {
  for (const line of event.split(/\r?\n/)) {
    if (line.startsWith('data: ')) return line.slice(6);
  }
  return null;
}

/**
 * One server-sent-events stream.
 *
 * `done` settles when the stream ends, so a caller can wait for the answer;
 * `stop` closes it.
 */
function fetchSSE<T>(
  path: string,
  options: FetchOptions,
  onEvent: (event: T) => void,
  onError?: (error: Error) => void,
): { stop: () => void; done: Promise<void> } {
  const controller = new AbortController();
  const url = apiUrl(path);

  const done = (async () => {
    try {
      const res = await fetch(url, {
        ...options,
        // A body means a JSON payload: without the header the browser sends
        // text/plain and the API cannot read it.
        headers: options.body
          ? { 'Content-Type': 'application/json', ...options.headers }
          : options.headers,
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new ApiError(res.status, await res.text().catch(() => ''));
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done: finished, value } = await reader.read();
        if (finished) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseSseEvents(buffer);
        buffer = rest;
        for (const event of events) {
          const data = sseData(event);
          if (data === null) continue;
          try {
            onEvent(JSON.parse(data));
          } catch {
            // Ignore parse errors
          }
        }
      }
    } catch (error: unknown) {
      if (controller.signal.aborted) return;
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  })();

  return { stop: () => controller.abort(), done };
}

export const api = {
  chat: {
    send: (req: ChatRequest) =>
      fetchJson<ChatResponse>('/api/v1/chat', { method: 'POST', body: JSON.stringify(req) }),
    stream: (
      req: ChatRequest,
      onEvent: (event: ChatStreamEvent) => void,
      onError?: (error: Error) => void,
    ) =>
      fetchSSE<ChatStreamEvent>(
        '/api/v1/chat/stream',
        { method: 'POST', body: JSON.stringify(req) },
        onEvent,
        onError,
      ).done,
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
      fetchSSE<DocumentStatusEvent>(
        `/api/v1/documents/${id}/status/stream`,
        {},
        onEvent,
      ).stop,
  },
  bookings: {
    list: (params: BookingListParams) => fetchJson<BookingListResponse>('/api/v1/bookings', { params }),
    get: (id: string) => fetchJson<Booking>(`/api/v1/bookings/${id}`),
    create: (data: { name: string; email: string; interview_date: string; interview_time: string }) =>
      fetchJson<Booking>('/api/v1/bookings', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: string) => fetchJson<void>(`/api/v1/bookings/${id}`, { method: 'DELETE' }),
  },
};

export { ApiError };