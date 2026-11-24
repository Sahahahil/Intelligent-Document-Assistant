import { z } from 'zod';

export const UUIDSchema = z.string().uuid();

export const PaginationParamsSchema = z.object({
  limit: z.number().int().positive().max(100).default(50),
  offset: z.number().int().nonnegative().default(0),
});

export const PaginationResponseSchema = z.object({
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export const ErrorResponseSchema = z.object({
  detail: z.string(),
  code: z.string().optional(),
});

export type PaginationParams = z.infer<typeof PaginationParamsSchema>;
export type PaginationResponse = z.infer<typeof PaginationResponseSchema>;
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;