# ADR 004: Server-Sent Events (SSE) for Streaming

**Date**: 2024-11-24  
**Status**: Accepted

## Context

The chat interface requires real-time token streaming from the LLM to provide a responsive user experience. We need to stream tokens from the FastAPI backend to the Next.js frontend.

## Decision

We will use **Server-Sent Events (SSE)** for streaming chat responses and document processing status.

### Why SSE over WebSockets?

| Factor | SSE | WebSockets |
|--------|-----|------------|
| Protocol | HTTP/1.1 or HTTP/2 | ws://, wss:// |
| Browser Support | Universal | Universal |
| Auto-reconnection | Built-in | Manual |
| Firewall/Proxy Friendly | Yes (standard HTTP) | Often blocked |
| Complexity | Low | Higher |
| Binary Data | No (text only) | Yes |
| Bidirectional | No (server→client) | Yes |
| Load Balancer Friendly | Yes | Requires sticky sessions |

Since our use case is **server-to-client streaming only** (LLM tokens, document status), SSE is the simpler and more robust choice.

## Implementation

### Backend (FastAPI)

```python
from sse_starlette.sse import EventSourceResponse

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    async def event_generator():
        # Check for booking first
        turn = await booking_service.handle_turn(...)
        if turn.is_booking:
            yield {"event": "booking", "data": turn.model_dump_json()}
            yield {"event": "done", "data": "{}"}
            return

        # Stream RAG response
        async for token in rag_service.astream(...):
            yield {"event": "token", "data": json.dumps({"content": token})}

        # Send sources at end
        yield {"event": "sources", "data": json.dumps([...])}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())
```

### Frontend (Next.js)

```typescript
// Streaming with fetch + ReadableStream
const response = await fetch('/api/v1/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id, message, document_ids })
});

const reader = response.body?.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n\n');
  buffer = lines.pop() || '';
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6));
      // Handle token, sources, booking, done events
    }
  }
}
```

### Document Status Streaming

```python
@router.get("/{document_id}/status/stream")
async def document_status_stream(document_id: UUID) -> EventSourceResponse:
    async def event_generator():
        while True:
            doc = await document_repo.get(document_id)
            if not doc:
                yield {"data": json.dumps({"stage": "error", "error": "Not found"})}
                break
            
            stage_map = {
                DocumentStatus.PROCESSING: "processing",
                DocumentStatus.COMPLETED: "completed",
                DocumentStatus.FAILED: "failed",
            }
            yield {"data": json.dumps({
                "stage": stage_map[doc.status],
                "progress": 100 if doc.status != DocumentStatus.PROCESSING else 50,
                "total_chunks": doc.total_chunks,
            })}
            
            if doc.status != DocumentStatus.PROCESSING:
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())
```

## Consequences

### Positive
- ✅ Simple implementation with standard HTTP
- ✅ Automatic reconnection on disconnect
- ✅ Works through all proxies, firewalls, load balancers
- ✅ Native browser support with `EventSource` API
- ✅ Lightweight (no WebSocket handshake overhead)
- ✅ Works seamlessly with HTTP/2 multiplexing
- ✅ Easy debugging with browser DevTools (Network tab)

### Negative
- ❌ Unidirectional only (server → client)
- ❌ No binary data support (base64 encoding needed)
- ❌ Connection limits per domain (6 connections in HTTP/1.1)
- ❌ No built-in heartbeat/ping (application-level needed)
- ❌ No client-to-server streaming (use regular POST for that)

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| WebSockets | Bidirectional, binary, lower latency | Complex, proxy issues, reconnection logic |
| Long Polling | Universal support | Higher latency, more server load |
| gRPC Streaming | Efficient, typed | Browser support limited, complex |
| GraphQL Subscriptions | Typed, integrated | Complex setup, overkill |

## Implementation Notes

### Event Format
```json
// Token event
{"event": "token", "data": "{\"content\": \"Hello\"}"}

// Sources event
{"event": "sources", "data": "[{\"document_id\": \"...\", \"score\": 0.95}]"}

// Booking event
{"event": "booking", "data": "{\"id\": \"...\", \"name\": \"John\"}"}

// Done event
{"event": "done", "data": "{}"}

// Error event
{"event": "error", "data": "{\"message\": \"Rate limited\"}"}
```

### Error Handling
- Client should handle `done` event to reset streaming state
- Server should send `error` event for recoverable errors
- Client should implement exponential backoff reconnection
- Server should send `heartbeat` comment every 30s to prevent proxy timeouts

### Browser Compatibility
- `EventSource` API supported in all modern browsers
- Polyfill available for IE11 (not needed)
- CORS headers required for cross-origin (not needed in same-origin)

## References

- [MDN Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [SSE Starlette Documentation](https://github.com/sysid/sse-starlette)
- [HTML Standard - Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)