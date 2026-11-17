import { test, expect } from '@playwright/test';

test('static demo navigates survey photos without an API', async ({ page }) => {
  const apiRequests = [];
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  page.on('request', request => { if (new URL(request.url()).pathname.includes('/api/')) apiRequests.push(request.url()); });
  await page.goto('demo/');
  await expect(page.locator('#caption')).toContainText('Photo 1 of 183');
  await expect(page.locator('#photo')).toHaveJSProperty('complete', true);
  await expect(page.locator('#photo')).toHaveJSProperty('complete', true);
  const firstPhoto = await page.locator('#photo').getAttribute('src');
  await page.getByRole('button', { name: 'Next photo' }).click();
  await expect(page.locator('#caption')).toContainText('Photo 2 of 183');
  await expect(page.locator('#photo')).not.toHaveAttribute('src', firstPhoto);
  await page.locator('#photo').evaluate(photo => photo.decode());
  await page.getByRole('button', { name: 'Previous photo' }).click();
  await expect(page.locator('#caption')).toContainText('Photo 1 of 183');
  await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(1);
  await expect(page.locator('.photo-marker').first()).toBeVisible();
  await expect(page.locator('.leaflet-control-layers').getByText('OpenStreetMap', { exact: true })).toBeVisible();
  for (let i = 0; i < 8 && await page.locator('.arrow-marker').count() === 0; i++) {
    await page.locator('.leaflet-control-zoom-in').click();
    await page.waitForTimeout(350);
  }
  await expect(page.locator('.arrow-marker').first()).toBeVisible();
  await page.locator('.arrow-marker').first().dispatchEvent('click');
  await expect(page.locator('.point-popup')).toContainText('Bearing');
  await page.locator('.leaflet-control-layers').getByText('OpenStreetMap', { exact: true }).click();
  await expect(page.locator('.leaflet-tile-pane img').first()).toBeAttached();
  await page.getByText('Survey only', { exact: true }).click();
  expect(apiRequests).toEqual([]);
});

test('documentation navigation is available', async ({ page }) => {
  await page.goto('');
  await page.getByRole('link', { name: 'Get started' }).click();
  await expect(page.getByRole('heading', { name: 'Install the portal' })).toBeVisible();
});

test('the documentation demo link opens the viewer', async ({ page }) => {
  await page.goto('');
  await page.getByRole('link', { name: 'Try the demo' }).click();
  await expect(page.locator('#caption')).toContainText('Photo 1 of 183');
});
