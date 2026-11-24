import { Page } from '@playwright/test';

/**
 * Wait until React has hydrated the page.
 *
 * The server sends the markup straight away, so a button is there before it
 * does anything - a click that lands in that window is swallowed. React
 * marks the nodes it has taken over, which is the signal to wait for.
 */
export async function waitForHydration(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const node = document.querySelector('button');
    if (!node) return false;
    return Object.keys(node).some((key) => key.startsWith('__reactFiber$'));
  });
}
