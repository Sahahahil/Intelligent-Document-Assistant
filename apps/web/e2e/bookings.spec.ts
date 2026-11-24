import { test, expect } from '@playwright/test';
import { waitForHydration } from './support';

test.describe('Bookings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/bookings');
    await waitForHydration(page);
    await expect(page.getByRole('heading', { name: 'Interview bookings' })).toBeVisible();
  });

  test('walks the wizard to a confirmed booking', async ({ page }) => {
    // A click before the page is interactive is swallowed, so each step is
    // clicked until it sticks.
    const continueButton = page.locator('button:has-text("Continue")');

    // Date: the first day that is not in the past.
    const day = page.locator('.grid-cols-7 button:not([disabled])').first();
    for (let attempt = 0; attempt < 5; attempt++) {
      await day.click();
      await page.waitForTimeout(300);
      if (await continueButton.isEnabled()) break;
    }
    await expect(continueButton).toBeEnabled();
    await continueButton.click();

    // Time: the first slot nobody holds.
    const slot = page.locator('button:not([disabled])').filter({ hasText: /^\d{2}:\d{2}$/ }).first();
    for (let attempt = 0; attempt < 5; attempt++) {
      await slot.click();
      await page.waitForTimeout(300);
      if (await continueButton.isEnabled()) break;
    }
    await expect(continueButton).toBeEnabled();
    await continueButton.click();

    // Details.
    await page.fill('input[autocomplete="name"]', 'Priya Shah');
    await page.fill('input[autocomplete="email"]', 'priya@example.com');
    await page.click('button:has-text("Continue")');

    // Review and confirm.
    await expect(page.getByRole('heading', { name: 'Review your booking' })).toBeVisible();
    await page.click('button:has-text("Confirm booking")');

    await expect(page.getByRole('heading', { name: 'Booking confirmed' })).toBeVisible();
    await expect(page.getByText('A confirmation will go to priya@example.com.')).toBeVisible();
  });

  test('lists the upcoming interviews', async ({ page }) => {
    const response = await page.request.get('/api/v1/bookings?limit=100&offset=0');
    const body = await response.json();
    const today = new Date().toISOString().slice(0, 10);
    const bookings = (body.items as { name: string; interview_date: string }[]).filter(
      (booking) => booking.interview_date >= today,
    );

    for (const booking of bookings) {
      await expect(page.getByText(booking.name).first()).toBeVisible();
    }
  });
});
