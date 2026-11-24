export const API_PREFIX = '/api/v1';

export const MAX_HISTORY = 20;
export const MAX_MESSAGE_LENGTH = 8000;
export const MAX_SESSION_ID_LENGTH = 128;

export const CHUNKING_STRATEGIES = ['fixed_size', 'recursive'] as const;
export const DOCUMENT_STATUSES = ['processing', 'completed', 'failed'] as const;
export const BOOKING_STATUSES = ['draft', 'confirmed', 'cancelled'] as const;

export const DEFAULT_CHUNK_SIZE = 1000;
export const DEFAULT_CHUNK_OVERLAP = 200;
export const MAX_CHUNK_SIZE = 4000;
export const MIN_CHUNK_SIZE = 100;
export const MAX_CHUNK_OVERLAP = 1000;

export const SUPPORTED_FILE_TYPES = ['application/pdf', 'text/plain'];
export const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

export const STREAM_EVENT_TYPES = ['token', 'sources', 'booking', 'error', 'done'] as const;

export const SKELETON_ANIMATION_DURATION = 1000;