'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { useEffect, useState } from 'react';

const TABS = [
  {
    name: 'Chat',
    href: '/chat',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 5h16v11H9l-5 4z" />
      </svg>
    ),
  },
  {
    name: 'Documents',
    href: '/documents',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 3h8l5 5v13H6zM14 3v5h5" />
      </svg>
    ),
  },
  {
    name: 'Bookings',
    href: '/bookings',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 6h16v14H4zM4 10h16M8 3v5M16 3v5" />
      </svg>
    ),
  },
];

function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    if (current === 'dark' || current === 'light') {
      setTheme(current);
      return;
    }
    setTheme(
      window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
    );
  }, []);

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('ida-theme', next);
    setTheme(next);
  };

  return (
    <button
      type="button"
      className="ghost"
      onClick={toggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
    >
      Theme
    </button>
  );
}

export function Nav() {
  const pathname = usePathname();
  const { data: session } = useSession();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav
      aria-label="Sections"
      className="flex flex-col gap-1.5 border-r border-line bg-card p-5 max-[820px]:order-2 max-[820px]:flex-row max-[820px]:justify-around max-[820px]:border-r-0 max-[820px]:border-t max-[820px]:p-1.5"
    >
      <div className="px-2.5 pt-1 pb-4.5 max-[820px]:hidden">
        <p className="font-serif text-[19px] leading-[1.15] font-semibold">
          Document Assistant
          <small className="block mt-1 font-sans text-[12px] font-medium text-muted-foreground">
            Ask your files. Book the interview.
          </small>
        </p>
      </div>

      {TABS.map((tab) => {
        const active = isActive(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 font-medium text-muted-foreground transition-colors hover:bg-background max-[820px]:flex-col max-[820px]:gap-0.5 max-[820px]:px-3.5 max-[820px]:py-1.5 max-[820px]:text-[12px] ${
              active ? 'bg-secondary text-secondary-foreground' : ''
            }`}
          >
            <span className="[&>svg]:h-[18px] [&>svg]:w-[18px] [&>svg]:fill-none [&>svg]:stroke-current [&>svg]:[stroke-width:1.7]">
              {tab.icon}
            </span>
            {tab.name}
          </Link>
        );
      })}

      <div className="flex-1 max-[820px]:hidden" />

      <div className="flex items-center justify-between gap-2 border-t border-line px-2.5 pt-2 text-[13px] text-muted-foreground max-[820px]:hidden">
        <span className="truncate">{session?.user?.name || 'Demo user'}</span>
        <ThemeToggle />
      </div>
    </nav>
  );
}
