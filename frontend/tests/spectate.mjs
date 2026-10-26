// Real-backend check of the spectator page: CFR V1 against TightAggressive.
// Usage: PB_BASE_URL=http://127.0.0.1:8097 node tests/spectate.mjs [screenshot-dir]
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.PB_BASE_URL || 'http://127.0.0.1:8097';
const shots = process.argv[2];
const browser = await chromium.launch(process.env.PB_BROWSER_EXECUTABLE ? {executablePath: process.env.PB_BROWSER_EXECUTABLE} : {});
const page = await browser.newPage({viewport: {width: 1365, height: 900}});
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.goto(base + '/#spectate');
await page.getByRole('button', {name: 'Register', exact: true}).click();
await page.getByLabel('Player ID', {exact: true}).fill(`watch${Date.now().toString(36)}`);
await page.getByLabel('Password', {exact: true}).fill('password123');
await page.getByLabel('Confirm password', {exact: true}).fill('password123');
await page.locator('.account-form').getByRole('button', {name: 'Create account', exact: true}).click();
await page.getByRole('heading', {name: 'Spectate', exact: true}).waitFor();
assert.equal(await page.getByLabel('Agent A').inputValue(), 'cfr-v2-adapt');
assert.equal(await page.getByLabel('Agent B').inputValue(), 'tag');
await page.getByRole('button', {name: 'Start watching', exact: true}).click();
await page.getByRole('heading', {name: 'CFR V2 · adaptive vs TightAggressive'}).waitFor();
// Normal speed reveals one action per second, starting from the deal.
await page.locator('.room-table').waitFor();
await page.waitForTimeout(2500);
const faceUp = await page.locator('.room-table .card:not(.back)').count();
assert.ok(faceUp >= 4, `spectator sees both hands (${faceUp} face-up cards)`);
if (shots) await page.screenshot({path: `${shots}/spectate-live.png`, fullPage: true});
await page.getByRole('button', {name: 'Fast forward', exact: true}).click();
await page.waitForFunction(() => {
  const cells = [...document.querySelectorAll('.room-standings tbody tr td:nth-child(2)')];
  return cells.length === 2 && cells.every(c => Number(c.textContent) >= 3);
}, null, {timeout: 60000});
await page.getByRole('button', {name: 'Pause auto-deal', exact: true}).click();
const nets = await page.locator('.room-standings tbody tr td:nth-child(3)').allTextContents();
assert.equal(nets.map(n => Number(n.replace(/,/g, ''))).reduce((x, y) => x + y, 0), 0, 'zero-sum without rake');
if (shots) await page.screenshot({path: `${shots}/spectate-stats.png`, fullPage: true});
await page.setViewportSize({width: 390, height: 844});
await page.waitForTimeout(300);
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
assert.ok(overflow <= 1, `no horizontal page scroll on mobile (overflow ${overflow}px)`);
if (shots) await page.screenshot({path: `${shots}/spectate-mobile.png`, fullPage: true});
assert.deepEqual(errors, []);
console.log(JSON.stringify({ok: true, nets}));
await browser.close();
