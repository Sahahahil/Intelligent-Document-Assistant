import './global.css';
import type { Metadata } from 'next';
import { QueryProvider } from '@/lib/query-client';
import { AuthProvider } from '@/lib/auth-context';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: 'Intelligent Document Assistant',
  description: 'RAG-powered document chat with interview booking',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}