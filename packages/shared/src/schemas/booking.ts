import { z } from 'zod';
import { UUIDSchema, PaginationParamsSchema, PaginationResponseSchema } from './common';

export const BookingStatusEnum = z.enum(['draft', 'confirmed', 'cancelled']);

export const BookingSchema = z.object({
  id: UUIDSchema,
  name: z.string(),
  email: z.string().email(),
  date: z.string().date(),
  time: z.string(),
  status: BookingStatusEnum,
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export const BookingListParamsSchema = PaginationParamsSchema.extend({
  status: BookingStatusEnum.optional(),
  date_from: z.string().date().optional(),
  date_to: z.string().date().optional(),
  email: z.string().email().optional(),
});

export const BookingListResponseSchema = PaginationResponseSchema.extend({
  items: z.array(BookingSchema),
});

export const BookingCreateRequestSchema = z.object({
  name: z.string().min(1).max(255),
  email: z.string().email(),
  date: z.string().date(),
  time: z.string().regex(/^([01]?[0-9]|2[0-3]):[0-5][0-9]$/),
});

export const BookingUpdateRequestSchema = z.object({
  status: BookingStatusEnum.optional(),
  name: z.string().min(1).max(255).optional(),
  email: z.string().email().optional(),
  date: z.string().date().optional(),
  time: z.string().regex(/^([01]?[0-9]|2[0-3]):[0-5][0-9]$/).optional(),
});

export type BookingStatus = z.infer<typeof BookingStatusEnum>;
export type Booking = z.infer<typeof BookingSchema>;
export type BookingListParams = z.infer<typeof BookingListParamsSchema>;
export type BookingListResponse = z.infer<typeof BookingListResponseSchema>;
export type BookingCreateRequest = z.infer<typeof BookingCreateRequestSchema>;
export type BookingUpdateRequest = z.infer<typeof BookingUpdateRequestSchema>;