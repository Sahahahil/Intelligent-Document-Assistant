'use client';

import { signIn } from 'next-auth/react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface LoginFormProps {
  searchParams: Promise<{ callbackUrl?: string }>;
}

export function LoginForm({ searchParams }: LoginFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const params = await searchParams;
    const callbackUrl = params.callbackUrl || '/chat';

    try {
      const res = await signIn('credentials', {
        email,
        password,
        redirect: false,
        callbackUrl,
      });

      if (res?.error) {
        setError('Invalid email or password');
      } else {
        router.push(callbackUrl);
        router.refresh();
      }
    } catch {
      setError('Something went wrong. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-[400px]">
        <div className="mb-6 text-center">
          <h1 className="text-[26px]">Document Assistant</h1>
          <p className="mt-1 text-muted-foreground">
            Ask your files. Book the interview.
          </p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit}>
            <label className="field" htmlFor="email">
              Email
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isLoading}
                className="h-10 rounded-lg border-line bg-background text-[15px]"
              />
            </label>

            <label className="field" htmlFor="password">
              Password
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isLoading}
                className="h-10 rounded-lg border-line bg-background text-[15px]"
              />
            </label>

            {error && <p className="mb-2 text-[13px] text-destructive">{error}</p>}

            <Button
              type="submit"
              disabled={isLoading}
              className="mt-1 h-10 w-full rounded-lg bg-primary text-[15px] font-semibold text-primary-foreground hover:bg-primary/90"
            >
              {isLoading ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
