import { test, expect } from '@playwright/test';

test.describe('Chat Interface', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL('/dashboard');
    await page.goto('/chat2');
  });

  test('shows chat page', async ({ page }) => {
    await expect(page.locator('h1:has-text("Chat")')).toBeVisible();
    await expect(page.locator('textarea[placeholder="Ask a question..."]')).toBeVisible();
    await expect(page.locator('button:has-text("Send")')).toBeVisible();
  });

  test('can send a message', async ({ page }) => {
    await page.fill('textarea[placeholder="Ask a question..."]', 'Hello, how are you?');
    await page.click('button:has-text("Send")');

    // Wait for user message to appear
    await expect(page.locator('text=Hello, how are you?')).toBeVisible();

    // Wait for assistant response (streaming)
    await expect(page.locator('.animate-pulse')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.animate-pulse')).toBeHidden({ timeout: 30000 });
  });

  test('shows streaming indicator while waiting', async ({ page }) => {
    await page.fill('textarea[placeholder="Ask a question..."]', 'Test message');
    await page.click('button:has-text("Send")');

    // Streaming indicator should appear
    await expect(page.locator('.animate-pulse')).toBeVisible({ timeout: 5000 });
  });

  test('disables input while streaming', async ({ page }) => {
    await page.fill('textarea[placeholder="Ask a question..."]', 'Test');
    await page.click('button:has-text("Send")');

    await expect(page.locator('textarea[placeholder="Ask a question..."]')).toBeDisabled({ timeout: 5000 });
  });

  test('can send multiple messages', async ({ page }) => {
    await page.fill('textarea[placeholder="Ask a question..."]', 'First message');
    await page.click('button:has-text("Send")');
    await expect(page.locator('.animate-pulse')).toBeHidden({ timeout: 30000 });

    await page.fill('textarea[placeholder="Ask a question..."]', 'Second message');
    await page.click('button:has-text("Send")');
    await expect(page.locator('.animate-pulse')).toBeVisible({ timeout: 5000 });
  });

  test('shows session sidebar', async ({ page }) => {
    await expect(page.locator('text=Conversations')).toBeVisible();
    await expect(page.locator('button:has-text("+")')).toBeVisible();
  });

  test('can create new session', async ({ page }) => {
    await page.click('button:has-text("+")');
    await expect(page.locator('text=Conversations')).toBeVisible();
  });
});