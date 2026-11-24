import { z } from 'zod';
import { PaginationParamsSchema, PaginationResponseSchema, UUIDSchema } from './common';

// The API stores the slot as a date and a 24h time - the same two fields
// the booking state machine collects from a conversation.
export const BookingStatusEnum = z.enum(['draft', 'confirmed', 'cancelled']);

export const BookingSchema = z.object({
  id: UUIDSchema,
  name: z.string(),
  email: z.string().email(),
  interview_date: z.string().date(),
  interview_time: z.string(),
  created_at: z.string().datetime(),
});

export const BookingListParamsSchema = PaginationParamsSchema.extend({
  email: z.string().email().optional(),
  interview_date: z.string().date().optional(),
});

export const BookingListResponseSchema = PaginationResponseSchema.extend({
  items: z.array(BookingSchema),
});

export const BookingCreateRequestSchema = z.object({
  name: z.string().min(1).max(255),
  email: z.string().email(),
  interview_date: z.string().date(),
  interview_time: z.string().regex(/^([01]?[0-9]|2[0-3]):[0-5][0-9]$/),
});

export const BookingUpdateRequestSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  email: z.string().email().optional(),
  interview_date: z.string().date().optional(),
  interview_time: z.string().regex(/^([01]?[0-9]|2[0-3]):[0-5][0-9]$/).optional(),
});

export type BookingStatus = z.infer<typeof BookingStatusEnum>;
export type Booking = z.infer<typeof BookingSchema>;
export type BookingListParams = z.infer<typeof BookingListParamsSchema>;
export type BookingListResponse = z.infer<typeof BookingListResponseSchema>;
export type BookingCreateRequest = z.infer<typeof BookingCreateRequestSchema>;
export type BookingUpdateRequest = z.infer<typeof BookingUpdateRequestSchema>;
