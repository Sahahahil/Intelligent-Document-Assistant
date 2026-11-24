import { describe, expect, it } from 'vitest';
import { parseSseEvents, sseData } from './api';

describe('parseSseEvents', () => {
  it('splits events on a blank line', () => {
    const { events, rest } = parseSseEvents('data: {"a":1}\n\ndata: {"b":2}\n\n');

    expect(events).toEqual(['data: {"a":1}', 'data: {"b":2}']);
    expect(rest).toBe('');
  });

  it('splits events the way the Python server writes them', () => {
    const { events } = parseSseEvents('data: {"a":1}\r\n\r\ndata: {"b":2}\r\n\r\n');

    expect(events).toEqual(['data: {"a":1}', 'data: {"b":2}']);
  });

  it('keeps a partial event for the next chunk', () => {
    const { events, rest } = parseSseEvents('data: {"a":1}\n\ndata: {"b":');

    expect(events).toEqual(['data: {"a":1}']);
    expect(rest).toBe('data: {"b":');
  });
});

describe('sseData', () => {
  it('reads the payload of an event', () => {
    expect(sseData('data: {"type":"done"}')).toBe('{"type":"done"}');
  });

  it('has no payload when the event carries none', () => {
    expect(sseData(': a comment')).toBeNull();
  });
});
