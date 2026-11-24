'use client';

import { Plus, MessageSquare, Trash2, Edit2, X, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useState } from 'react';
import { formatDate } from '@/lib/utils';

interface Session {
  id: string;
  title: string;
  created_at: string;
  message_count: number;
}

interface SessionSidebarProps {
  sessionId: string;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
}

const mockSessions: Session[] = [
  { id: '1', title: 'Project Discussion', created_at: '2024-01-15T10:00:00Z', message_count: 12 },
  { id: '2', title: 'API Documentation', created_at: '2024-01-14T15:30:00Z', message_count: 8 },
  { id: '3', title: 'Code Review', created_at: '2024-01-13T09:15:00Z', message_count: 24 },
];

export function SessionSidebar({
  sessionId,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
}: SessionSidebarProps) {
  const [sessions] = useState<Session[]>(mockSessions);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const handleRenameStart = (session: Session) => {
    setEditingId(session.id);
    setEditTitle(session.title);
  };

  const handleRenameConfirm = (id: string) => {
    if (editTitle.trim()) {
      onRenameSession(id, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  };

  return (
    <div className="w-72 border-r bg-background flex flex-col">
      <div className="p-4 border-b">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Conversations</h2>
          <Button variant="ghost" size="icon" onClick={onNewSession} aria-label="New conversation">
            <Plus className="h-5 w-5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center gap-2 p-2 rounded-lg transition-colors ${
              session.id === sessionId ? 'bg-primary/10' : 'hover:bg-accent'
            }`}
          >
            {editingId === session.id ? (
              <div className="flex-1 flex items-center gap-2">
                <Input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleRenameConfirm(session.id);
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  autoFocus
                  className="flex-1"
                />
                <Button variant="ghost" size="icon" onClick={() => handleRenameConfirm(session.id)}>
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </Button>
                <Button variant="ghost" size="icon" onClick={() => setEditingId(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <>
                <MessageSquare className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{session.title}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {formatDate(session.created_at)} • {session.message_count} messages
                  </p>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRenameStart(session);
                    }}
                    aria-label="Rename"
                  >
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('Delete this conversation?')) onDeleteSession(session.id);
                    }}
                    aria-label="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </>
            )}
            <Button
              variant="ghost"
              className="w-full justify-start h-9"
              onClick={() => onSelectSession(session.id)}
              disabled={session.id === sessionId}
            >
              <div className="w-full flex items-center justify-between">
                <div />
                {session.id === sessionId && (
                  <span className="text-xs text-primary font-medium">Active</span>
                )}
              </div>
            </Button>
          </div>
        ))}
      </div>

      <div className="p-4 border-t">
        <p className="text-xs text-muted-foreground text-center">
          {sessions.length} conversation{sessions.length !== 1 ? 's' : ''}
        </p>
      </div>
    </div>
  );
}