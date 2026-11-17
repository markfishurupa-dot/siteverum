import { test, expect } from '@playwright/test';

test('static demo navigates synthetic photos without an API', async ({ page }) => {
  const apiRequests = [];
  page.on('request', request => { if (new URL(request.url()).pathname.includes('/api/')) apiRequests.push(request.url()); });
  await page.goto('demo/');
  await expect(page.locator('#caption')).toContainText('Photo 1 of 12');
  await expect(page.locator('#photo')).toHaveJSProperty('complete', true);
  await expect(page.locator('#photo')).toHaveJSProperty('naturalWidth', 960);
  await page.getByRole('button', { name: 'Next photo' }).click();
  await expect(page.locator('#caption')).toContainText('Photo 2 of 12');
  await page.getByRole('button', { name: 'Previous photo' }).click();
  await expect(page.locator('#caption')).toContainText('Photo 1 of 12');
  await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(1);
  await expect(page.locator('.photo-marker').first()).toBeVisible();
  await expect(page.getByText('OpenStreetMap', { exact: true })).toBeVisible();
  await page.locator('.leaflet-control-zoom-in').click();
  await page.locator('.leaflet-control-zoom-in').click();
  await expect(page.locator('.arrow-marker').first()).toBeVisible();
  await page.locator('.arrow-marker').first().click();
  await expect(page.locator('.point-popup')).toContainText('Bearing');
  expect(apiRequests).toEqual([]);
});

test('documentation navigation is available', async ({ page }) => {
  await page.goto('');
  await page.getByRole('link', { name: 'Get started' }).click();
  await expect(page.getByRole('heading', { name: 'Install the portal' })).toBeVisible();
});
