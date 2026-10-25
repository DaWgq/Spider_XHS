const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.XHS_UI_URL || 'http://127.0.0.1:18080';
if (new URL(baseURL).port !== '18080') throw new Error('Resume UI regression requires isolated port 18080');
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
    proxy: { server: 'http://127.0.0.1:7897', bypass: 'localhost,127.0.0.1,::1' }, args: ['--disable-background-networking'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await page.goto(`${baseURL}/signin`, { waitUntil: 'networkidle' });
    await page.getByPlaceholder('请输入账号', { exact: true }).fill('dawg');
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('123456');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.getByRole('heading', { name: '数据概览', exact: true }).waitFor();
    await page.goto(`${baseURL}/tasks`, { waitUntil: 'networkidle' });
    const row = page.locator('tbody tr').filter({ hasText: 'ui-resume-fi' });
    await row.getByRole('button', { name: '继续采集（7）', exact: true }).click();
    await page.getByText('已成功 13 / 20 篇。', { exact: false }).waitFor();
    await page.getByRole('button', { name: '取消', exact: true }).click();
    await page.screenshot({ path: path.resolve('local_data/ui-resume-task.png'), fullPage: true });
    await row.getByRole('button', { name: '详情', exact: true }).click();
    await page.getByRole('heading', { name: '任务详情', exact: true }).waitFor();
    await page.getByRole('button', { name: '继续采集（7）', exact: true }).click();
    const response = page.waitForResponse(r => r.url().endsWith('/api/tasks/ui-resume-fixture/resume'));
    await page.getByRole('button', { name: '继续采集', exact: true }).click();
    assert.equal((await response).status(), 409, 'Missing platform Cookie must prevent actual collection');
    await page.getByText('请先配置有效 Cookie，并在登录配置页检测通过后再继续采集', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('Resume UI passed: list and detail show remaining 7, confirmation preserves 13/20, cancel works, missing Cookie blocks enqueue; no platform requests.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
