import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from '@playwright/test';

const root = new URL('../../', import.meta.url);
const summary = JSON.parse(await readFile(new URL('benchmarks/scanned-strategies-summary.json', root)));
const audit = summary.protocol_10k_audit;
const proof = audit.dikibagast_wfa_10k;
const origin = 'http://public-site.test';
const starter = 'https://whop.com/freqpilot/freqpilot-free-starter-bundle-sha-256-verified/';
const langs = ['vi', 'en', 'zh', 'ru', 'ko'];
const missing = ['Chưa có kết quả', 'No results yet', '暂无结果', 'Пока нет результатов', '아직 결과가 없습니다'];
const demoNames = ['DikibagastEmaRsi1h', 'RocketHunterSma501h', 'TarsisVolTargetSma501h',
  'BdrEmaRideFutures1h', 'TrendCoreBagging1h', 'CodexBotVibe4h', 'StarterFuturesResearch'];
let browser;
before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

async function pageFor(t, device = {}) {
  const page = await browser.newPage({ ...device, baseURL: origin });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(async () => {
    await page.context().close();
    assert.deepEqual(errors, []);
  });
  // Use the deployable directory directly. Keep Studio probes and checkout entirely offline.
  const files = { '/': 'index.html', '/demo': 'demo.html', '/demo.html': 'demo.html', '/public-evidence.js': 'public-evidence.js' };
  await page.context().route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === 'https://whop.com') return route.fulfill({ body: '' });
    const file = url.origin === origin && files[url.pathname];
    if (!file) return route.abort();
    return route.fulfill({ path: fileURLToPath(new URL('site/' + file, root)), contentType: file.endsWith('.js') ? 'application/javascript' : 'text/html; charset=utf-8' });
  });
  return page;
}

test('each published audit row matches the 10k benchmark and its period', async t => {
  const page = await pageFor(t);
  await page.goto('/');
  const rows = await page.locator('#audit-table tr[data-group]').evaluateAll(rows => rows.map(row => ({
    name: row.querySelector('strong').textContent, run: row.cells[0].querySelector('code').textContent,
    period: row.parentElement.dataset.period, group: row.dataset.group,
    pnl: Number.parseFloat(row.cells[2].querySelector('b').textContent), trades: Number(row.cells[3].textContent),
  })));
  assert.equal(new Set(rows.map(r => r.name)).size, rows.length);
  const discovered = { ...audit.runs };
  delete discovered.StarterFuturesResearch; // Installation control, outside the discovery table.
  const longAlchemy = discovered.CodeAlchemyLowPassFisher1h_67m;
  delete discovered.CodeAlchemyLowPassFisher1h_67m; // The same strategy has two time windows.
  assert.deepEqual(rows.map(r => r.name).sort(), Object.keys(discovered).sort());
  for (const row of rows) {
    const r = row.name === 'CodeAlchemyLowPassFisher1h' ? longAlchemy : discovered[row.name];
    assert.equal(row.run, r.id);
    assert.equal(row.trades, r.summary.total_trades);
    assert.equal(row.pnl, +r.summary.profit_total_abs.toFixed(2));
    assert.equal(row.period, r.timerange === '20260401-20261021' ? 'long' : 'short');
    assert.equal(row.group, row.period === 'long' && row.pnl > 0 ? 'survived' : 'dropped');
  }
  for (const lang of langs) {
    await page.selectOption('#lang-select', lang);
    const numbers = text => text.match(/\d+(?:[.,]\d+)?/g);
    const long = rows.filter(r => r.period === 'long').length;
    const short = rows.length - long;
    const badge = page.locator('.eyebrow-pill');
    const label = await badge.innerText();
    for (const n of [rows.length, long, short]) assert.ok(numbers(label).includes(String(n)), label);
    assert.equal(await badge.getAttribute('href'), '#audit');
    for (const [period, count] of [['long', long], ['short', short]]) {
      assert.match(await page.locator(`[data-period="${period}"] [data-group-hdr]`).innerText(), new RegExp(`(^|\\D)${count}(\\D|$)`));
    }
    for (const [i, group] of ['all', 'survived', 'dropped'].entries()) {
      const button = page.locator('#audit .filter-bar button').nth(i);
      await button.click();
      const count = rows.filter(r => group === 'all' || r.group === group).length;
      assert.match(await button.innerText(), new RegExp(`\\(${count}\\)`));
      assert.equal(await page.locator('#audit-table tr[data-group]:visible').count(), count);
    }
  }
});

test('walk-forward requires the reviewed strategy, revision, backtest, ZIP and validation ID', async t => {
  const page = await pageFor(t);
  await page.goto('/demo?lang=en&tab=walk');
  const { runs, evidence } = await page.evaluate(() => ({ runs: PUBLIC_RUNS, evidence: WALK_FORWARD }));
  assert.deepEqual(Object.keys(runs).sort(), [...demoNames].sort());
  const [wf] = evidence;
  assert.equal(wf.id, proof.id);
  assert.equal(wf.rev, proof.revision);
  assert.equal(wf.strategy, proof.strategy);
  assert.equal(wf.holdout, proof.holdout_timerange);
  assert.deepEqual(wf.windows, proof.windows);
  for (const [side, source] of [[wf.baseline, proof.holdout_baseline], [wf.candidate, proof.holdout_candidate]]) {
    for (const [key, value] of Object.entries(side)) assert.equal(value, source[key]);
  }
  for (const [id, run] of Object.entries(runs)) {
    const r = audit.runs[id];
    assert.deepEqual(run, { rev: r.revision, runId: r.id, sha: r.sha256, period: r.timerange, detail: r.detail, walkId: r.wfa_10k_id });
  }
  const summaries = await page.evaluate(() => STRATEGIES.map(({ id, pnl, trades, dd, pf }) => ({ id, pnl, trades, dd, pf })));
  for (const { id, pnl, trades, dd, pf } of summaries) {
    const s = audit.runs[id].summary;
    assert.deepEqual([pnl, trades, dd, pf], [+s.profit_total_abs.toFixed(2), s.total_trades,
      +(100 * s.max_drawdown_account).toFixed(2), +s.profit_factor.toFixed(2)]);
  }
  for (const field of ['id', 'rev', 'runId', 'sha', 'walkId']) {
    assert.equal(await page.evaluate(field => !!walkForwardFor({ ...currentStrat, [field]: 'stale' }), field), false);
  }
  for (const [i, lang] of langs.entries()) {
    await page.selectOption('#lang-select', lang);
    for (const id of [...demoNames, demoNames[0]]) {
      await page.locator('.strat-item').filter({ hasText: id }).click();
      const panel = await page.locator('[data-walk]').innerText();
      assert.ok(panel.includes(id));
      assert.ok((await page.locator('.sandbox-banner').innerText()).includes(runs[id].sha.slice(0, 12)));
      if (runs[id].walkId) {
        assert.ok(panel.includes(proof.id.slice(0, 10)));
        assert.match(panel, /\+94[.,]44/);
        assert.match(panel, /-50[.,]85/);
      } else {
        assert.ok(panel.includes(missing[i]));
        assert.doesNotMatch(panel, /3215a26798|94[.,]44|50[.,]85|OOS #|Hyperopt/);
      }
    }
    await page.reload();
    assert.equal(await page.locator('#lang-select').inputValue(), lang);
    assert.match(await page.locator('[data-walk]').innerText(), /DikibagastEmaRsi1h/);
  }
  await page.goto('/?lang=en');
  await page.locator('.strat-btn').nth(1).click();
  await page.locator('.win-tab').nth(1).click();
  assert.match(await page.locator('#pane-matrix').innerText(), /RocketHunterSma501h\s+No results yet/);
  assert.doesNotMatch(await page.locator('#pane-matrix').innerText(), /3215a26798|94\.44|Dikibagast/);
});

for (const lang of ['en', 'vi']) {
  for (const [width, device] of [[393, devices['iPhone 15']], [1280, { viewport: { width: 1280, height: 900 } }]]) {
    test(`${lang} · ${width}px · Studio, public sample, results, walk-forward and Starter offer`, async t => {
      const page = await pageFor(t, device);
      const fits = async () => assert.deepEqual(await page.evaluate(() => [
        document.documentElement.clientWidth, document.documentElement.scrollWidth,
      ]), [width, width]);
      await page.goto('/?lang=' + lang);
      await fits();
      const launch = page.locator('.nav-right .primary');
      const rect = await launch.boundingBox();
      assert.ok(rect.x >= 0 && rect.x + rect.width <= width + 0.01);
      await launch.click();
      assert.ok(await page.locator('#studio-modal.open').isVisible());
      await fits();
      await page.locator('#studio-modal .modal-close').click();
      const card = page.locator('#starter-bundle');
      assert.equal(await card.locator('a').count(), 2);
      const details = lang === 'vi' ? /cấu hình và nhật ký backtest/ : /configuration and backtest logs/;
      const paidAccess = lang === 'vi' ? /dành cho khách trả phí/ : /for paying customers/;
      assert.match(await card.innerText(), details);
      assert.match(await card.innerText(), paidAccess);
      assert.match(await card.locator('#starter-download').innerText(), /Whop.*\$0/);
      const gates = page.locator('a[data-i18n="nav_registry"]');
      assert.equal(await gates.count(), 2);
      for (const gate of await gates.all()) {
        assert.equal(new URL(await gate.getAttribute('href')).origin, 'https://strategies.freqpilot.dev');
        assert.match(await gate.textContent(), lang === 'vi' ? /Thư viện trả phí/ : /Paid library/);
      }
      const openWhop = async link => {
        const waitForPopup = page.waitForEvent('popup');
        await link.click();
        const whop = await waitForPopup;
        await whop.waitForURL(url => url.origin + url.pathname === starter);
        await whop.close();
      };
      await openWhop(card.locator('#starter-download'));
      await card.locator('[data-i18n="hero_cta_starter"]').click();
      assert.equal(await page.locator('#ws-name').innerText(), 'TrendCoreBagging1h');
      assert.match(await page.locator('#ctx3-val').innerText(), /\+28[.,]58 USDT · 2 (trades|lệnh)/);
      assert.match(await page.locator('#tab-content').innerText(), lang === 'vi' ? /Lãi \/ lỗ ròng/ : /Net P&L/);
      await fits();
      await page.locator('.step-btn').nth(7).click();
      assert.match(await page.locator('[data-walk]').innerText(), lang === 'vi' ? /Chưa có kết quả/ : /No results yet/);
      await fits();
      for (const link of await page.locator('#btn-buy-pack, #ws-download-btn, .sandbox-banner .primary').all()) {
        assert.equal(await link.getAttribute('href'), starter);
        assert.match(await link.innerText(), /Whop.*\$0/);
      }
      const banner = page.locator('.sandbox-banner');
      assert.match(await banner.innerText(), details);
      assert.match(await banner.innerText(), paidAccess);
      await openWhop(page.locator('#ws-download-btn'));
      assert.equal(await page.locator('#lang-select').inputValue(), lang);
      assert.equal(await page.locator('#ws-name').innerText(), 'TrendCoreBagging1h');
      await page.locator('.strat-item').filter({ hasText: proof.strategy }).click();
      assert.doesNotMatch(await banner.innerText(), details);
      assert.equal(await page.locator('#btn-buy-pack').getAttribute('target'), '_self');
      await page.locator('.step-btn').nth(7).click();
      assert.match(await page.locator('[data-walk]').innerText(), /\+94[.,]44/);
      await fits();
      await page.locator('.step-btn').nth(1).click();
      assert.match(await page.locator('#tab-content').innerText(), lang === 'vi' ? /Trích đoạn công khai/ : /Public strategy excerpt/);
      await page.locator('.sandbox-banner .primary').click();
      assert.equal(new URL(page.url()).hash, '#verified-pack');
      assert.equal(await page.locator('html').getAttribute('lang'), lang);
      await fits();
    });
  }
}
