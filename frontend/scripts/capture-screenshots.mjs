import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const baseURL = process.env.WARDCAST_WEB_URL ?? 'http://127.0.0.1:8000';
const destination = resolve(import.meta.dirname, '../../docs/screenshots');
await mkdir(destination, { recursive: true });

const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1512, height: 1120 },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  });
  await page.goto(baseURL);
  await page.getByRole('heading', { name: 'The forecast in numbers' }).waitFor();
  await page.getByTestId('margin-1').waitFor();
  await page.evaluate(() => document.fonts.ready);
  const assertNoOverflow = async () => {
    if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) {
      throw new Error('The workspace has horizontal page overflow.');
    }
  };
  const capturePage = async (filename, lastPanel) => {
    const bounds = await lastPanel.boundingBox();
    await page.setViewportSize({ width: 1512, height: Math.ceil(bounds.y + bounds.height + 14) });
    await page.screenshot({ path: resolve(destination, filename) });
  };
  await assertNoOverflow();
  await capturePage('dashboard.png', page.locator('.analysis-grid'));

  await page.getByRole('button', { name: 'Model evidence', exact: true }).click();
  await page.getByRole('heading', { name: 'Every model, the same test' }).waitFor();
  await assertNoOverflow();
  await capturePage('evidence.png', page.locator('section.panel').first());

  await page.setViewportSize({ width: 390, height: 844 });
  await assertNoOverflow();
  await page.getByRole('button', { name: 'Capacity overview', exact: true }).click();
  await page.getByRole('heading', { name: 'The forecast in numbers' }).waitFor();
  await assertNoOverflow();
  console.log(
    `Saved dashboard.png and evidence.png to ${destination}. Desktop and mobile: no page overflow.`,
  );
} finally {
  await browser.close();
}
