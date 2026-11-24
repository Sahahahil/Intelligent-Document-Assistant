# ADR 001: Nx Monorepo

**Date**: 2024-11-24  
**Status**: Accepted

## Context

We need to manage a full-stack application with a Python FastAPI backend and a Next.js TypeScript frontend, plus shared TypeScript/Python schemas. The codebase needs to support:
- Independent deployment of frontend and backend
- Shared type definitions between frontend and backend
- Efficient builds and caching
- Scalable development workflow

## Decision

We will use **Nx** as the monorepo tool with the following structure:

```
apps/
  ├── api/          # FastAPI backend
  ├── web/          # Next.js frontend
packages/
  └── shared/       # Shared TypeScript/Zod schemas
```

### Key Configuration
- **Nx Workspace**: TypeScript/JavaScript focus with `@nx/next`, `@nx/js`, `@nx/playwright`, `@nx/vitest` plugins
- **Package Manager**: npm (root) + uv (Python backend)
- **Build System**: Nx with Turborepo-style caching
- **TypeScript**: Shared `tsconfig.base.json` with path aliases

## Consequences

### Positive
- ✅ Shared TypeScript types between frontend/backend via `packages/shared`
- ✅ Incremental builds and caching via Nx
- ✅ Unified linting, testing, and typechecking
- ✅ Single `npm run dev` starts both frontend and backend
- ✅ Shared ESLint/Prettier config
- ✅ Atomic commits across frontend/backend

### Negative
- ❌ Learning curve for Nx concepts
- ❌ Extra configuration overhead vs separate repos
- ❌ Nx version lock-in (though migration is possible)
- ❌ Python backend uses uv, not Nx's built-in Python support

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Separate repos | Complete independence | Duplicate types, complex CI, sync issues |
| Turborepo | Similar to Nx, simpler config | Less mature Python support |
| Single Next.js API routes | Simpler deployment | Limited Python ecosystem, no FastAPI |
| pnpm workspaces | Native, no tool lock-in | No built-in caching, less tooling |

## References

- [Nx Documentation](https://nx.dev)
- [Nx Monorepo Best Practices](https://nx.dev/concepts/monorepo)