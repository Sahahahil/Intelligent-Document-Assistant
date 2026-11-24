import { test, expect } from '@playwright/test';

test.describe('Document Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    // Login with test credentials - adjust as needed
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL('/dashboard');
  });

  test.describe('Document List', () => {
    test('shows documents page', async ({ page }) => {
      await page.goto('/dashboard/documents');
      await expect(page.locator('h1:has-text("Documents")')).toBeVisible();
      await expect(page.locator('button:has-text("Upload Document")')).toBeVisible();
    });

    test('can search documents', async ({ page }) => {
      await page.goto('/dashboard/documents');
      await page.fill('input[placeholder="Search documents..."]', 'test');
      await expect(page.locator('input[placeholder="Search documents..."]')).toHaveValue('test');
    });

    test('can filter by status', async ({ page }) => {
      await page.goto('/dashboard/documents');
      await page.click('button:has-text("Filter by status")');
      await page.click('text=Completed');
      await expect(page.locator('text=Completed')).toBeVisible();
    });
  });

  test.describe('Document Upload', () => {
    test('opens upload dialog', async ({ page }) => {
      await page.goto('/dashboard/documents');
      await page.click('button:has-text("Upload Document")');
      await expect(page.locator('text=Upload Document')).toBeVisible();
      await expect(page.locator('input[type="file"]')).toBeVisible();
    });

    test('can select file', async ({ page }) => {
      await page.goto('/dashboard/documents');
      await page.click('button:has-text("Upload Document")');

      const fileInput = page.locator('input[type="file"]');
      await fileInput.setInputFiles({
        name: 'test.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('Test document content')
      });

      await expect(page.locator('text=test.txt')).toBeVisible();
    });

    test('shows validation error for invalid file type', async ({ page }) => {
      await page.goto('/dashboard/documents');
      await page.click('button:has-text("Upload Document")');

      const fileInput = page.locator('input[type="file"]');
      await fileInput.setInputFiles({
        name: 'test.exe',
        mimeType: 'application/x-msdownload',
        buffer: Buffer.from('fake exe')
      });

      await expect(page.locator('text=Only PDF and TXT files are allowed')).toBeVisible();
    });
  });

  test.describe('Document Detail', () => {
    test('navigates to document detail on click', async ({ page }) => {
      await page.goto('/dashboard/documents');

      // Wait for document table to load
      await page.waitForSelector('table', { state: 'attached' });

      // Click on first document if exists
      const firstRow = page.locator('tbody tr').first();
      if (await firstRow.count() > 0) {
        await firstRow.locator('button[aria-label="View document"]').click();
        await expect(page.locator('text=Document Details')).toBeVisible();
      }
    });
  });
});