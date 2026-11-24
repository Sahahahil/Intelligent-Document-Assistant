import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock next-auth/react
vi.mock('next-auth/react', () => ({
  useSession: vi.fn(() => ({
    data: {
      user: {
        id: 'test-user',
        name: 'Test User',
        email: 'test@example.com',
        image: null,
      },
      expires: new Date(Date.now() + 86400000).toISOString(),
    },
    status: 'authenticated',
  })),
  signIn: vi.fn(),
  signOut: vi.fn(),
}));

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  })),
  usePathname: vi.fn(() => '/dashboard'),
  useSearchParams: vi.fn(() => new URLSearchParams()),
}));

// Mock next-auth
vi.mock('next-auth', () => ({
  getServerSession: vi.fn(),
}));

// Mock TanStack Query
vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(({ queryFn }) => ({ data: undefined, isLoading: false, error: null })),
  useMutation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
  })),
  useQueryClient: vi.fn(() => ({
    invalidateQueries: vi.fn(),
    setQueryData: vi.fn(),
    getQueryData: vi.fn(),
  })),
  QueryClient: vi.fn(() => ({
    invalidateQueries: vi.fn(),
    setQueryData: vi.fn(),
    getQueryData: vi.fn(),
  })),
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock next-auth/providers/credentials
vi.mock('next-auth/providers/credentials', () => ({
  default: vi.fn(),
}));

// Mock next-auth/providers/github
vi.mock('next-auth/providers/github', () => ({
  default: vi.fn(),
}));

// Mock next-auth/providers/google
vi.mock('next-auth/providers/google', () => ({
  default: vi.fn(),
}));

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  FileText: () => <svg data-testid="file-text" />,
  MessageSquare: () => <svg data-testid="message-square" />,
  Calendar: () => <svg data-testid="calendar" />,
  Settings: () => <svg data-testid="settings" />,
  Upload: () => <svg data-testid="upload" />,
  Search: () => <svg data-testid="search" />,
  Filter: () => <svg data-testid="filter" />,
  Plus: () => <svg data-testid="plus" />,
  Loader2: () => <svg data-testid="loader" />,
  Send: () => <svg data-testid="send" />,
  LogOut: () => <svg data-testid="logout" />,
  LayoutDashboard: () => <svg data-testid="layout-dashboard" />,
  FileText: () => <svg data-testid="file-text" />,
  Mail: () => <svg data-testid="mail" />,
  Github: () => <svg data-testid="github" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
  ChevronRight: () => <svg data-testid="chevron-right" />,
  ChevronLeft: () => <svg data-testid="chevron-left" />,
  X: () => <svg data-testid="x" />,
  Check: () => <svg data-testid="check" />,
  Copy: () => <svg data-testid="copy" />,
  Download: () => <svg data-testid="download" />,
  Eye: () => <svg data-testid="eye" />,
  Trash2: () => <svg data-testid="trash" />,
  User: () => <svg data-testid="user" />,
  Clock: () => <svg data-testid="clock" />,
  AlertCircle: () => <svg data-testid="alert-circle" />,
  CheckCircle: () => <svg data-testid="check-circle" />,
}));

// Mock react-day-picker
vi.mock('react-day-picker', () => ({
  DayPicker: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
    <div {...props} data-testid="day-picker" />
  ),
}));

// Mock @/lib/utils
vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(' '),
}));

// Suppress console.error for known warnings in tests
const originalError = console.error;
beforeAll(() => {
  console.error = (...args) => {
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('Warning: ReactDOM.render is no longer supported') ||
        args[0].includes('act(...)') ||
        args[0].includes('Warning: An update to'))
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});