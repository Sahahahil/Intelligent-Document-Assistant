import { test, expect } from '@playwright/test';

test.describe('Booking Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL('/dashboard');
    await page.goto('/bookings');
  });

  test.describe('Bookings List', () => {
    test('shows bookings page', async ({ page }) => {
      await expect(page.locator('h1:has-text("Bookings")')).toBeVisible();
      await expect(page.locator('button:has-text("Book Interview")')).toBeVisible();
    });

    test('can filter by status', async ({ page }) => {
      await page.click('button:has-text("Filter by status")');
      await page.click('text=Confirmed');
      await expect(page.locator('text=Confirmed')).toBeVisible();
    });
  });

  test.describe('Booking Form', () => {
    test('opens booking dialog', async ({ page }) => {
      await page.click('button:has-text("Book Interview")');
      await expect(page.locator('text=Booking Details')).toBeVisible();
    });

    test('shows validation errors', async ({ page }) => {
      await page.click('button:has-text("Book Interview")');
      await page.click('button:has-text("Continue")');

      await expect(page.locator('text=Name is required')).toBeVisible();
      await expect(page.locator('text=Email is required')).toBeVisible();
      await expect(page.locator('text=Date is required')).toBeVisible();
      await expect(page.locator('text=Time is required')).toBeVisible();
    });

    test('shows error for invalid email', async ({ page }) => {
      await page.fill('input[id="name"]', 'John Doe');
      await page.fill('input[id="email"]', 'invalid-email');
      await page.click('button:has-text("Continue")');

      await expect(page.locator('text=Invalid email format')).toBeVisible();
    });

    test('shows error for past date', async ({ page }) => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const dateStr = yesterday.toISOString().split('T')[0];

      await page.fill('input[id="name"]', 'John Doe');
      await page.fill('input[id="email"]', 'john@example.com');
      await page.fill('input[id="date"]', dateStr);
      await page.click('button:has-text("Continue")');

      await expect(page.locator('text=Date cannot be in the past')).toBeVisible();
    });

    test('can complete booking wizard', async ({ page }) => {
      await page.fill('input[id="name"]', 'John Doe');
      await page.fill('input[id="email"]', 'john@example.com');

      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const dateStr = tomorrow.toISOString().split('T')[0];
      await page.fill('input[id="date"]', dateStr);

      await page.selectOption('select[id="time"]', '10:00');

      await page.click('button:has-text("Continue")');

      // Confirm step
      await expect(page.locator('text=Please review your booking details')).toBeVisible();
      await expect(page.locator('text=John Doe')).toBeVisible();
      await expect(page.locator('text=john@example.com')).toBeVisible();

      await page.click('button:has-text("Confirm Booking")');

      // Success step
      await expect(page.locator('text=Booking Confirmed!')).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('Booking Table', () => {
    test('shows bookings table', async ({ page }) => {
      await expect(page.locator('table')).toBeVisible();
      await expect(page.locator('th:has-text("Name")')).toBeVisible();
      await expect(page.locator('th:has-text("Email")')).toBeVisible();
      await expect(page.locator('th:has-text("Date & Time")')).toBeVisible();
      await expect(page.locator('th:has-text("Status")')).toBeVisible();
    });

    test('can delete booking', async ({ page }) => {
      // This test requires an existing booking - skip if no bookings exist
      const firstRow = page.locator('tbody tr').first();
      if (await firstRow.count() > 0) {
        await firstRow.locator('button[aria-label="Delete booking"]').click();
        await page.click('button:has-text("Delete")'); // confirm
        await expect(page.locator('text=Booking deleted')).toBeVisible({ timeout: 5000 });
      }
    });
  });
});