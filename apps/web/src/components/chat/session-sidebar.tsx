'use client';

export interface ChatSession {
  id: string;
  title: string;
  messages: { role: 'user' | 'assistant'; content: string; sources?: unknown[] }[];
}

interface SessionSidebarProps {
  sessions: ChatSession[];
  currentId: string;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
}

export function SessionSidebar({
  sessions,
  currentId,
  onNewSession,
  onSelectSession,
}: SessionSidebarProps) {
  return (
    <aside className="flex-none overflow-auto border-r border-line bg-card px-2.5 py-4 max-[820px]:hidden">
      <button
        type="button"
        onClick={onNewSession}
        className="mb-2.5 w-full rounded-lg border border-dashed border-line px-2.5 py-2 text-center text-[14px] text-foreground transition-colors hover:border-primary"
      >
        New chat
      </button>
      {sessions.map((session) => (
        <button
          key={session.id}
          type="button"
          onClick={() => onSelectSession(session.id)}
          aria-current={session.id === currentId ? 'true' : undefined}
          className={`block w-full truncate rounded-lg px-2.5 py-2 text-left text-[14px] transition-colors hover:bg-background ${
            session.id === currentId
              ? 'bg-secondary text-secondary-foreground'
              : 'text-muted-foreground'
          }`}
        >
          {session.title}
        </button>
      ))}
    </aside>
  );
}
