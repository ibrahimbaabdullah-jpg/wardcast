import { expect, test } from '@playwright/test';
import type { Trust } from '../src/types';

test('real public-data forecast, scenario arithmetic, and historical replay', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Make room for what’s next.' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The forecast in numbers' })).toBeVisible();
  const prediction = await page
    .locator('.projection-panel tbody tr')
    .first()
    .locator('td')
    .nth(1)
    .textContent();
  const originalCapacity = await page.getByLabel('Assumed available beds').inputValue();
  await page.getByLabel('Assumed available beds').fill('1');
  await expect(page.getByTestId('margin-1')).toHaveText(/^-/);
  expect(
    await page.locator('.projection-panel tbody tr').first().locator('td').nth(1).textContent(),
  ).toBe(prediction);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByLabel('Assumed available beds')).toHaveValue(originalCapacity);
  await page.getByLabel('Compare last-observed baseline').check();
  await expect(page.getByLabel('Compare last-observed baseline')).toBeChecked();

  const cutoff = page.getByLabel('Observation cutoff');
  const options = await cutoff.locator('option').all();
  expect(options.length).toBeGreaterThan(3);
  const historicalValue = await options[Math.min(6, options.length - 1)].getAttribute('value');
  await cutoff.selectOption(historicalValue!);
  await expect(page.getByText('Historical replay', { exact: true })).toBeVisible();
  await expect(page.locator('.projection-panel th').last()).toHaveText('Actual');
  await expect(
    page.locator('.projection-panel tbody tr').first().locator('td').last(),
  ).not.toHaveText('—');
});

test('trust selection, evaluation views and source methods', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'The forecast in numbers' })).toBeVisible();
  const trustSelect = page.getByLabel('NHS trust', { exact: true });
  const options = await trustSelect.locator('option').all();
  expect(options.length).toBeGreaterThan(1);
  const available = (await (await page.request.get('/api/trusts')).json()) as { trusts: Trust[] };
  const current = await trustSelect.inputValue();
  const second = available.trusts.find(
    (trust) =>
      trust.code !== current &&
      (trust.latest_available ?? 0) > 0 &&
      trust.last_month === '2026-03-01',
  )!.code;
  await trustSelect.selectOption(second);
  await expect(page.locator('.trust-identifier')).toContainText(second);
  await expect(page.getByRole('heading', { name: 'The forecast in numbers' })).toBeVisible();

  await page.getByRole('button', { name: 'Model evidence', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Every model, the same test' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Results across trusts' })).toBeVisible();
  await page.getByLabel('Evaluation horizon').selectOption('3');
  await expect(
    page.getByText('Selected on development MAE · horizon 3', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await expect(
    page.getByText('April 2024–March 2025 · rolling model development', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('.evidence-table').first().locator('tbody tr')).toHaveCount(5);

  await page.getByRole('button', { name: 'Data & methods', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A forecast you can interrogate' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'NHS England source publications' })).toHaveAttribute(
    'href',
    /england.nhs.uk/,
  );
  await expect(page.getByText(/Missing values are never treated as zero/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Source manifest' })).toBeVisible();
  await expect(page.locator('.manifest-table tbody tr')).toHaveCount(48);
});

test('zero-adult-capacity trust keeps observed zeros without fabricating forecasts', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'The forecast in numbers' })).toBeVisible();
  const response = (await (await page.request.get('/api/trusts')).json()) as { trusts: Trust[] };
  const zeroCapacity = response.trusts.find((trust) => trust.latest_available === 0)!;
  expect(zeroCapacity).toBeTruthy();
  await page.getByLabel('NHS trust', { exact: true }).selectOption(zeroCapacity.code);
  await expect(
    page.getByRole('heading', { name: 'No eligible forecasts for this trust' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Reported monthly bed records' })).toBeVisible();
  await expect(page.locator('tbody tr').first().locator('td').nth(2)).toHaveText('0.0');
});

test('small screens keep the workspace usable without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'The forecast in numbers' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByLabel('Assumed available beds').fill('0');
  await expect(page.getByText('Enter a capacity greater than zero.')).toBeVisible();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByTestId('margin-1')).toBeVisible();
  await page.getByRole('button', { name: 'Model evidence', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Every model, the same test' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
