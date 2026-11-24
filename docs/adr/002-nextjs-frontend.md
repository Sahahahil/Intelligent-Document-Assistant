# ADR 002: Next.js Frontend

**Date**: 2024-11-24  
**Status**: Accepted

## Context

We need a modern React-based frontend for the Intelligent Document Assistant. The frontend needs to support:
- Server-side rendering for SEO and performance
- Server-side authentication with NextAuth.js
- Streaming chat responses via SSE
- Real-time document processing status
- Responsive, accessible UI components

## Decision

We will use **Next.js 16+ with App Router** as the frontend framework.

### Key Technology Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | Next.js 16+ (App Router) | React Server Components, streaming, server actions |
| Styling | Tailwind CSS 4 | Utility-first, JIT compilation, small bundle |
| UI Components | shadcn/ui (Radix UI) | Accessible, customizable, no runtime overhead |
| State Management | TanStack Query | Server state caching, mutations, optimistic updates |
| Auth | NextAuth.js v4 | Multiple providers, JWT sessions, middleware |
| Forms | React Hook Form + Zod | Type-safe validation, minimal re-renders |
| Date Picker | react-day-picker | Lightweight, accessible, unstyled |
| Markdown | react-markdown | Secure, extensible, plugin system |
| Icons | lucide-react | Tree-shakeable, consistent design |
| Date Utils | date-fns | Immutable, modular, small bundle |

### Architecture Decisions

1. **App Router over Pages Router**: Enables React Server Components, streaming, nested layouts, and server actions.

2. **Route Groups**: Use `(dashboard)` route group for authenticated routes with shared layout (Sidebar + Navbar).

3. **Server Components by Default**: Use `'use client'` only for interactive components (forms, chat, dropdowns).

4. **TanStack Query for Server State**: All API calls go through TanStack Query with proper caching, retries, and optimistic updates.

5. **Path Aliases**: Use `@/` for `src/` and `@intelligent-doc-assistant/shared/*` for shared package.

## Consequences

### Positive
- ✅ Excellent developer experience with hot reload, TypeScript, ESLint
- ✅ Excellent performance with RSC, streaming, automatic code splitting
- ✅ Excellent SEO with static generation and metadata API
- ✅ Strong ecosystem and community
- ✅ Excellent TypeScript support with strict mode
- ✅ shadcn/ui provides accessible, customizable components without runtime overhead

### Negative
- ❌ Learning curve for App Router, Server Components, Server Actions
- ❌ Next.js 16 Turbopack is default and has some bugs with route groups
- ❌ Larger bundle size than vanilla React (mitigated by code splitting)
- ❌ Turbopack has issues with route groups containing parentheses

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Vite + React SPA | Simpler, faster dev server | No SSR, worse SEO, no streaming |
| Remix | Nested routing, loaders | Smaller ecosystem, different mental model |
| Astro + React Islands | Partial hydration, fast | Less mature, limited interactivity |
| TanStack Start | File-based routing, SSR | Very new, less mature |

## References

- [Next.js Documentation](https://nextjs.org/docs)
- [App Router Documentation](https://nextjs.org/docs/app)
- [Next.js 16 Release Notes](https://nextjs.org/blog/next-16)