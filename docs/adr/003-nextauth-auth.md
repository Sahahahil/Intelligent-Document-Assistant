# ADR 003: NextAuth.js Authentication

**Date**: 2024-11-24  
**Status**: Accepted

## Context

We need authentication for the Intelligent Document Assistant frontend that integrates with the FastAPI backend. Requirements:
- Email/password credentials authentication
- OAuth providers (GitHub, Google) for future extensibility
- JWT tokens shared with FastAPI backend
- Server-side session management
- Protected routes with middleware

## Decision

We will use **NextAuth.js v4 (Auth.js)** as the authentication solution.

### Configuration

```typescript
// providers: Credentials, GitHub, Google
// session: JWT strategy
// callbacks: JWT for access token, session for user data
// pages: custom sign-in page
```

### Provider Configuration

| Provider | Purpose | Configuration |
|----------|---------|---------------|
| Credentials | Email/password | Custom authorize function calls FastAPI `/api/v1/auth/login` |
| GitHub | OAuth 2.0 | Standard OAuth flow |
| Google | OAuth 2.0 | Standard OAuth flow |

### Token Flow

1. User submits credentials on `/login`
2. NextAuth calls FastAPI `/api/v1/auth/login`
3. FastAPI validates credentials, returns JWT + user data
4. NextAuth stores JWT in session cookie (httpOnly, secure, sameSite=lax)
6. Client includes cookie in API requests
7. FastAPI validates JWT via shared `NEXTAUTH_SECRET` (HS256)

### Middleware Protection

```typescript
// middleware.ts
export { auth as middleware } from '@/lib/auth';
export const config = { matcher: ['/dashboard/:path*', '/bookings/:path*', '/chat2', '/dashboard/documents/:path*'] };
```

## Consequences

### Positive
- ✅ Battle-tested, widely used authentication library
- ✅ Built-in CSRF protection, secure cookies
- ✅ Multiple providers with unified API
- ✅ TypeScript support with module augmentation
- ✅ Middleware integration for route protection
- ✅ JWT strategy avoids database session storage
- ✅ Shared secret with FastAPI enables token validation

### Negative
- ❌ NextAuth v4 API differs from v5 (Auth.js)
- ❌ Credentials provider requires custom authorize function
- ❌ JWT in cookies has size limits (~4KB)
- ❌ No built-in refresh token rotation (manual implementation needed)
- ❌ OAuth providers require HTTPS in production

## Security Considerations

1. **CSRF Protection**: Built-in with double-submit cookie pattern
2. **Secure Cookies**: `httpOnly`, `secure`, `sameSite=lax`
3. **JWT Validation**: FastAPI validates signature, expiry, audience
3. **Rate Limiting**: Implement at API gateway or FastAPI level
4. **Password Hashing**: FastAPI uses bcrypt (handled server-side)

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Custom JWT + Cookies | Full control | Reinventing security, easy to mess up |
| Clerk/Auth0 | Managed, feature-rich | Vendor lock-in, cost, less control |
| Supabase Auth | Integrated with Supabase | Vendor lock-in, PostgreSQL required |
| Custom Session + Redis | Full control | More boilerplate, session management |

## References

- [NextAuth.js Documentation](https://next-auth.js.org)
- [NextAuth.js Credentials Provider](https://next-auth.js.org/providers/credentials)
- [NextAuth.js Middleware](https://next-auth.js.org/configuration/nextjs#middleware)