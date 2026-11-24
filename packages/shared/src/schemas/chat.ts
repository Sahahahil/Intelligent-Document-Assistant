import { z } from 'zod';
import { UUIDSchema } from './common';

export const ChatRequestSchema = z.object({
  session_id: z.string().min(1).max(128),
  message: z.string().min(1).max(8000),
  document_ids: z.array(UUIDSchema).optional(),
});

export const SourceSchema = z.object({
  document_id: UUIDSchema,
  filename: z.string(),
  chunk_index: z.number().int(),
  score: z.number().min(0).max(1),
});

export const BookingModelSchema = z.object({
  id: UUIDSchema.nullable(),
  name: z.string().nullable(),
  email: z.string().email().nullable(),
  interview_date: z.string().date().nullable(),
  interview_time: z.string().nullable(),
  status: z.enum(['pending', 'confirmed', 'cancelled']),
  missing_fields: z.array(z.string()),
  awaiting_confirmation: z.boolean(),
});

export const ChatResponseSchema = z.object({
  session_id: z.string(),
  answer: z.string(),
  sources: z.array(SourceSchema),
  booking: BookingModelSchema.nullable(),
  context_used: z.boolean(),
  created_at: z.string().datetime(),
});

export const ChatStreamEventSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('token'), content: z.string() }),
  z.object({ type: z.literal('sources'), sources: z.array(SourceSchema) }),
  z.object({
    type: z.literal('booking'),
    reply: z.string().nullable(),
    booking: BookingModelSchema.nullable(),
  }),
  z.object({ type: z.literal('error'), message: z.string() }),
  z.object({ type: z.literal('done') }),
]);

export type ChatRequest = z.infer<typeof ChatRequestSchema>;
export type ChatResponse = z.infer<typeof ChatResponseSchema>;
export type Source = z.infer<typeof SourceSchema>;
export type BookingModel = z.infer<typeof BookingModelSchema>;
export type ChatStreamEvent = z.infer<typeof ChatStreamEventSchema>;