import { z } from 'zod';
import { PaginationParamsSchema, PaginationResponseSchema, UUIDSchema } from './common';

export const ChunkingStrategyEnum = z.enum(['fixed_size', 'recursive']);
export const DocumentStatusEnum = z.enum(['processing', 'completed', 'failed']);

export const DocumentIngestRequestSchema = z.object({
  file: z.instanceof(File),
  chunking_strategy: ChunkingStrategyEnum.optional(),
  chunk_size: z.number().int().positive().optional(),
  chunk_overlap: z.number().int().nonnegative().optional(),
});

export const DocumentIngestResponseSchema = z.object({
  document_id: UUIDSchema,
  filename: z.string(),
  status: DocumentStatusEnum,
  chunking_strategy: ChunkingStrategyEnum,
  total_chunks: z.number().int(),
  embedding_model: z.string(),
  embedding_dim: z.number().int(),
  duration_ms: z.number().int(),
});

export const DocumentSummarySchema = z.object({
  id: UUIDSchema,
  filename: z.string(),
  file_extension: z.string(),
  file_size: z.number().int(),
  chunking_strategy: ChunkingStrategyEnum,
  total_chunks: z.number().int(),
  embedding_model: z.string(),
  status: DocumentStatusEnum,
  created_at: z.string().datetime(),
});

export const DocumentChunkSchema = z.object({
  document_id: UUIDSchema,
  chunk_index: z.number().int(),
  content: z.string(),
});

export const DocumentDetailSchema = DocumentSummarySchema.extend({
  content_type: z.string(),
  file_hash: z.string(),
  chunk_size: z.number().int(),
  chunk_overlap: z.number().int(),
  embedding_dim: z.number().int(),
  error_message: z.string().nullable(),
});

export const DocumentListParamsSchema = PaginationParamsSchema.extend({
  status: DocumentStatusEnum.optional(),
  search: z.string().optional(),
});

export const DocumentListResponseSchema = PaginationResponseSchema.extend({
  items: z.array(DocumentSummarySchema),
});

export const DocumentStatusEventSchema = z.object({
  stage: z.enum([
    'extracting',
    'chunking',
    'embedding',
    'indexing',
    'processing',
    'completed',
    'failed',
  ]),
  progress: z.number().int().min(0).max(100),
  total_chunks: z.number().int().optional(),
  error: z.string().optional(),
});

export type ChunkingStrategy = z.infer<typeof ChunkingStrategyEnum>;
export type DocumentStatus = z.infer<typeof DocumentStatusEnum>;
export type DocumentIngestRequest = z.infer<typeof DocumentIngestRequestSchema>;
export type DocumentIngestResponse = z.infer<typeof DocumentIngestResponseSchema>;
export type DocumentSummary = z.infer<typeof DocumentSummarySchema>;
export type DocumentChunk = z.infer<typeof DocumentChunkSchema>;
export type DocumentDetail = z.infer<typeof DocumentDetailSchema>;
export type DocumentListParams = z.infer<typeof DocumentListParamsSchema>;
export type DocumentListResponse = z.infer<typeof DocumentListResponseSchema>;
export type DocumentStatusEvent = z.infer<typeof DocumentStatusEventSchema>;