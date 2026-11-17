// Capture the real portal against a disposable stack and synthetic source files.
// Generate those files with: python site/scripts/generate-fixture.py site/public/demo/photos/001.webp
import { chromium, expect } from '@playwright/test';
import path from 'node:path';
import { mkdir } from 'node:fs/promises';

const root = path.resolve('..');
const output = path.join(root, 'site/public/images/screenshots');
const sources = path.join(root, 'private-samples/synthetic');
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
  httpCredentials: { username: 'admin', password: 'syntheticadministratorpasswordonly' } });
const page = await context.newPage();
const shot = name => page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
const surveyName = 'Synthetic demo ' + Date.now();
try {
  await page.goto('http://127.0.0.1:18093/');
  await page.locator('#label').fill(surveyName);
  await page.getByRole('button', { name: 'Create survey' }).click();
  await expect(page.locator('#title')).toHaveText(surveyName);
  await shot('upload');
  await page.locator('#files').setInputFiles([path.join(sources, 'demo.mp4'), path.join(sources, 'demo.log')]);
  await page.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(page.locator('#message')).toHaveText('Sources staged');
  await page.getByRole('button', { name: 'Validate sources' }).click();
  await expect(page.locator('#validation-report')).toBeVisible({ timeout: 120000 });
  await shot('validation');
  await page.getByRole('button', { name: 'Process survey' }).click();
  await expect(page.locator('#processing-progress')).toBeVisible();
  await shot('processing');
  await expect(page.locator('#caption')).toContainText('Photo 1 of 12', { timeout: 180000 });
  await shot('viewer');
  await page.locator('[title="Photo 1"]').click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await shot('edit');
  await page.locator('body').press('Escape');
  await page.getByRole('button', { name: 'Publish locally' }).click();
  await expect(page.getByRole('link', { name: 'Open published map' })).toBeVisible();
  await shot('publish');
} finally {
  await browser.close();
}
