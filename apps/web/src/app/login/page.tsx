import { Suspense } from 'react';
import { LoginForm } from './login-form';

export default function LoginPage({ searchParams }: { searchParams: Promise<{ callbackUrl?: string }> }) {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center">Loading...</div>}>
      <LoginForm searchParams={searchParams} />
    </Suspense>
  );
}