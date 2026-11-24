import { test, expect } from '@playwright/test';
import { waitForHydration } from './support';

test.describe('Chat', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat');
    await waitForHydration(page);
    await expect(page.locator('textarea[aria-label="Message"]')).toBeVisible();
  });

  test('shows the empty state with suggestions', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'What would you like to know?' })).toBeVisible();
    await expect(page.locator('button:has-text("What uptime does the SLA promise?")')).toBeVisible();
  });

  test('keeps the sessions in the sidebar', async ({ page }) => {
    await expect(page.locator('aside button:has-text("New chat")')).toBeVisible();
    await expect(page.locator('aside button:has-text("New conversation")')).toBeVisible();
  });

  test('sends a message and shows it in the thread', async ({ page }) => {
    await page.fill('textarea[aria-label="Message"]', 'What is in the handbook?');
    // The button waits for the document list before it will send, and a
    // click before the page is interactive is swallowed.
    const bubble = page.locator('div.bg-primary');
    await expect(page.locator('button:has-text("Send")')).toBeEnabled();
    for (let attempt = 0; attempt < 5; attempt++) {
      await page.click('button:has-text("Send")');
      await page.waitForTimeout(500);
      if (await bubble.count()) break;
    }

    await expect(bubble.getByText('What is in the handbook?')).toBeVisible();
    // The composer is emptied once the message is on its way.
    await expect(page.locator('textarea[aria-label="Message"]')).toHaveValue('');
  });

  test('a new chat starts an empty thread', async ({ page }) => {
    await page.fill('textarea[aria-label="Message"]', 'What is in the handbook?');
    const bubble = page.locator('div.bg-primary');
    await expect(page.locator('button:has-text("Send")')).toBeEnabled();
    for (let attempt = 0; attempt < 5; attempt++) {
      await page.click('button:has-text("Send")');
      await page.waitForTimeout(500);
      if (await bubble.count()) break;
    }
    await expect(bubble.getByText('What is in the handbook?')).toBeVisible();

    await page.click('aside button:has-text("New chat")');

    await expect(page.getByRole('heading', { name: 'What would you like to know?' })).toBeVisible();
  });
});
