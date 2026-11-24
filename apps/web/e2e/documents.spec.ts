import { test, expect } from '@playwright/test';
import { waitForHydration } from './support';

const FILE = {
  name: 'e2e-notes.txt',
  mimeType: 'text/plain',
  buffer: Buffer.from('The interview process has three stages.\n'),
};

test.describe('Documents', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/documents');
    await waitForHydration(page);
    await expect(page.getByRole('heading', { name: 'Documents' })).toBeVisible();
  });

  test('shows the drop zone', async ({ page }) => {
    await expect(page.getByText('Drop PDF or TXT files here')).toBeVisible();
    await expect(page.locator('button:has-text("Choose files")')).toBeVisible();
  });

  test('lists the documents that are already indexed', async ({ page }) => {
    const response = await page.request.get('/api/v1/documents?limit=100&offset=0');
    const body = await response.json();
    const documents = body.items as { filename: string }[];

    for (const document of documents) {
      await expect(page.getByText(document.filename).first()).toBeVisible();
    }
  });

  test('uploads a file and shows it being indexed', async ({ page }) => {
    await page.setInputFiles('input[type="file"]', FILE);

    await expect(page.getByText(FILE.name).first()).toBeVisible({ timeout: 30000 });
  });
});
