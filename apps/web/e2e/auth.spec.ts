import { test, expect } from '@playwright/test';
import { waitForHydration } from './support';

test.describe('App shell', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat');
    await waitForHydration(page);
  });

  test('shows the three sections', async ({ page }) => {
    await expect(page.locator('nav a:has-text("Chat")')).toBeVisible();
    await expect(page.locator('nav a:has-text("Documents")')).toBeVisible();
    await expect(page.locator('nav a:has-text("Bookings")')).toBeVisible();
  });

  test('the landing page lands on the chat', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/chat$/);
  });

  test('the theme can be switched', async ({ page }) => {
    const toggle = page.locator('button[aria-label*="theme"]');

    await expect(toggle).toBeVisible();
    await toggle.click();

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await toggle.click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });

  test('the navigation marks the current section', async ({ page }) => {
    await page.click('nav a:has-text("Documents")');

    await expect(page).toHaveURL(/\/documents$/);
    await expect(page.locator('nav a:has-text("Documents")')).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});
