import { Nav } from '@/components/layout/nav';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-screen grid-cols-[232px_1fr] max-[820px]:grid-cols-1 max-[820px]:grid-rows-[1fr_auto]">
      <Nav />
      <main className="h-full min-w-0 overflow-hidden">{children}</main>
    </div>
  );
}
