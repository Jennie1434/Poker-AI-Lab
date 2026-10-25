import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import path from 'node:path';
import fs from 'node:fs/promises';

// Generated aggregate page only; no application API or provider access.
const dashboard = process.env.PB_BENCHMARK_DASHBOARD;
assert.ok(dashboard, 'Set PB_BENCHMARK_DASHBOARD to the generated dashboard path');
const browser = await chromium.launch({headless: true, executablePath: process.env.PB_BROWSER_EXECUTABLE || '/usr/bin/chromium'});
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(/^https?:/, () => { throw new Error('Offline dashboard attempted a network request'); });
  await page.setContent(await fs.readFile(path.resolve(dashboard), 'utf8'));
  const reports = await page.locator('#data').textContent().then(JSON.parse);
  assert.ok(reports.length >= 2, 'Comparison test requires at least two experiments');
  assert.equal(await page.locator('#results tr').count(), reports.length * 2);
  assert.equal(await page.locator('#bars svg').count(), reports.length * 2);
  const net = await page.locator('#results').innerText();
  await page.selectOption('#metric', 'gross');
  assert.notEqual(await page.locator('#results').innerText(), net);
  await page.selectOption('#experiment', '0');
  assert.equal(await page.locator('#results tr').count(), 2);
  assert.equal(await page.locator('#settings p').count(), 1);
  await page.selectOption('#experiment', 'all');
  await page.selectOption('#metric', 'net');
  await fs.mkdir('test-results', {recursive: true});
  await page.screenshot({path: 'test-results/benchmark-dashboard-desktop.png', fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page overflow');
  await page.screenshot({path: 'test-results/benchmark-dashboard-mobile.png', fullPage: true});
  assert.deepEqual(errors, []);
  console.log('Benchmark dashboard passed: aggregates, gross/net switch, experiment filter, charts, desktop/mobile, offline.');
} finally {
  await browser.close();
}
