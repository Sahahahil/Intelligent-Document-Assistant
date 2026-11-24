import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('shows login form', async ({ page }) => {
    await expect(page.locator('h1:has-text("Sign in")')).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button:has-text("Sign in")')).toBeVisible();
  });

  test('shows validation errors for empty submit', async ({ page }) => {
    await page.click('button:has-text("Sign in")');
    await expect(page.locator('text=Email is required')).toBeVisible();
    await expect(page.locator('text=Password is required')).toBeVisible();
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.fill('input[type="email"]', 'invalid@example.com');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button:has-text("Sign in")');
    await expect(page.locator('text=Invalid email or password')).toBeVisible({ timeout: 5000 });
  });

  test('redirects to dashboard on successful login', async ({ page }) => {
    // This test requires a valid test user - skip if no test user exists
    test.skip(true, 'Requires test user setup');
  });

  test('shows OAuth buttons', async ({ page }) => {
    await expect(page.locator('button:has-text("GitHub")')).toBeVisible();
    await expect(page.locator('button:has-text("Google")')).toBeVisible();
  });

  test('has link to register', async ({ page }) => {
    await expect(page.locator('a:has-text("Sign up")')).toBeVisible();
  });
});