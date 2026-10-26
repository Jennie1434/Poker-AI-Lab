// End-to-end check against a real, isolated backend (no mocks): register, open a
// heads-up table against the local CFR policy, play hands, read history and stats.
// Usage: PB_BASE_URL=http://127.0.0.1:8097 node tests/cfr-room.mjs [screenshot-dir]
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.PB_BASE_URL || 'http://127.0.0.1:8097';
const shots = process.argv[2];
const browser = await chromium.launch(process.env.PB_BROWSER_EXECUTABLE ? {executablePath: process.env.PB_BROWSER_EXECUTABLE} : {});
const page = await browser.newPage({viewport: {width: 1365, height: 900}});
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const button = (name) => page.getByRole('button', {name, exact: true});
const user = `cfr${Date.now().toString(36)}`;

await page.goto(base + '/#rooms');
await button('Register').click();
await page.getByLabel('Player ID', {exact: true}).fill(user);
await page.getByLabel('Password', {exact: true}).fill('password123');
await page.getByLabel('Confirm password', {exact: true}).fill('password123');
await page.locator('.account-form').getByRole('button', {name: 'Create account', exact: true}).click();

// The CFR policy is the default opponent; it needs no key or invitation.
await page.waitForFunction(() => document.querySelector('output[aria-label="CFR V1 · 200k seat count"]')?.textContent === '1');
await page.getByText(/CFR opponent: heads-up cash table/).waitFor();
assert.equal(await page.locator('output[aria-label="CFR V1 · 20k seat count"]').textContent(), '0');
if (shots) await page.screenshot({path: `${shots}/cfr-setup.png`, fullPage: true});
await button('Create table & take a seat').click();
await button('Start game').click();

const roomId = () => location.hash.split('/')[1];
const state = async () => page.evaluate(async id => (await fetch(`/api/rooms/${id}/state`)).json(), await page.evaluate(roomId));
let hands = 0, actions = 0;
const target = 6;
while (hands < target) {
  await page.waitForFunction(() => [...document.querySelectorAll('.action-buttons button,.next-hand-button')].some(b => !b.disabled), null, {timeout: 30000});
  const data = await state();
  const snapshot = data.record.events.at(-1).snapshot;
  const bot = snapshot.seats.find(s => s.id !== 'human-player');
  if (!snapshot.complete) assert.deepEqual(bot.cards, ['??', '??'], 'opponent hole cards must stay hidden during the hand');
  const next = page.locator('.next-hand-button');
  if (await next.isVisible() && await next.isEnabled()) {
    hands += 1;
    if (hands === 1 && shots) await page.screenshot({path: `${shots}/cfr-hand-complete.png`, fullPage: true});
    if (hands < target) await next.click();
    continue;
  }
  // Mix passive and aggressive play so raises and folds by the policy are exercised.
  const labels = await page.locator('.action-buttons button').allTextContents();
  const pick = actions % 4 === 3 ? labels.find(l => l.startsWith('Min raise') || l.includes('→')) : labels.find(l => /^(Check|Call)/.test(l));
  if (actions === 1 && shots) await page.screenshot({path: `${shots}/cfr-human-turn.png`, fullPage: true});
  await page.locator('.action-buttons button', {hasText: pick || labels[0]}).first().click();
  actions += 1;
}
await page.getByRole('region', {name: 'Hand history and statistics'}).waitFor();
await page.getByText(`Statistics · ${target} hands played`).waitFor({timeout: 10000});
const history = await page.evaluate(async id => (await fetch(`/api/rooms/${id}/history`)).json(), await page.evaluate(roomId));
assert.equal(history.completed_hands, target);
assert.equal(history.stats['human-player'].net_chips + history.stats['opponent-1'].net_chips, 0);
const details = page.locator('.hand-history-list details').first();
await details.locator('summary').click();
await details.locator('ol li').first().waitFor();
if (shots) await page.screenshot({path: `${shots}/cfr-history.png`, fullPage: true});

await page.setViewportSize({width: 390, height: 844});
await page.waitForTimeout(300);
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
assert.ok(overflow <= 1, `no horizontal page scroll on mobile (overflow ${overflow}px)`);
if (shots) await page.screenshot({path: `${shots}/cfr-mobile.png`, fullPage: true});
assert.deepEqual(errors, []);
console.log(JSON.stringify({ok: true, user, hands, human_actions: actions, stats: history.stats}));
await browser.close();
