// Test-only browser responses; no real platform QR or credential is requested.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.XHS_UI_URL || 'http://127.0.0.1:18080';
if (new URL(baseURL).port !== '18080') throw new Error('QR UI regression requires isolated port 18080');
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}),
    proxy: { server: 'http://127.0.0.1:7897', bypass: 'localhost,127.0.0.1,::1' }, args: ['--disable-background-networking'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await page.goto(`${baseURL}/signin`, { waitUntil: 'networkidle' });
    await page.getByPlaceholder('请输入账号', { exact: true }).fill('dawg');
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('123456');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.getByRole('heading', { name: '数据概览', exact: true }).waitFor();
    await page.goto(`${baseURL}/login`, { waitUntil: 'networkidle' });
    const image = 'data:image/svg+xml;base64,' + fs.readFileSync('local_data/ui-qr-fixture.svg').toString('base64');
    let phase = 'waiting', starts = 0, cancelled = 0;
    const messages = { initializing: '初始化小红书匿名设备与安全会话：正在请求平台', failed: '初始化小红书匿名设备与安全会话超时，原 Cookie 未修改', waiting: '请使用小红书 App 扫描二维码', scanned: '已扫码，请在小红书 App 中确认登录', expired: '二维码已过期，请重新生成', succeeded: '登录成功，Cookie 已自动保存在后端' };
    function response() { return { id: 'ui-test-only', state: phase, message: messages[phase], stage: 'anonymous', stage_label: '初始化小红书匿名设备与安全会话', elapsed_seconds: 12, remaining_seconds: 108, request_count: 2, request: 'GET example.invalid/api/login', image: phase === 'waiting' || phase === 'scanned' ? image : null, account: phase === 'succeeded' ? { nickname: '二维码测试账号' } : {} }; }
    await page.route('**/api/login/qrcode**', async route => {
      if (route.request().method() === 'DELETE') { cancelled++; return route.fulfill({ json: { state: 'cancelled' } }); }
      if (route.request().method() === 'POST') { starts++; phase = starts === 1 ? 'initializing' : 'waiting'; }
      await route.fulfill({ status: route.request().method() === 'POST' ? 202 : 200, json: response() });
    });
    await page.route('**/api/login', async route => {
      if (phase !== 'succeeded') return route.continue();
      await route.fulfill({ json: { configured: true, masked: '已保存（内容隐藏）', status: 'valid', account: { nickname: '二维码测试账号' } } });
    });
    await page.getByRole('button', { name: '扫码登录小红书', exact: true }).click();
    await page.getByText(messages.initializing, { exact: true }).waitFor();
    await page.getByText('已用 12 秒', { exact: false }).waitFor();
    phase = 'failed';
    await page.getByText(messages.failed, { exact: true }).waitFor();
    assert.equal(await page.locator('.n-modal .n-spin').count(), 0, 'Timeout must stop the spinner');
    await page.getByRole('button', { name: '重新生成二维码', exact: true }).click();
    await page.getByAltText('小红书登录二维码', { exact: true }).waitFor();
    assert.ok(await page.getByAltText('小红书登录二维码').evaluate(img => img.complete && img.naturalWidth > 0));
    await page.waitForTimeout(350); // Let the modal's opening transition finish before visual QA.
    await page.screenshot({ path: path.resolve('local_data/ui-qr-login.png'), fullPage: true });
    phase = 'scanned';
    await page.getByText(messages.scanned, { exact: true }).waitFor();
    phase = 'expired';
    await page.getByRole('button', { name: '重新生成二维码', exact: true }).waitFor();
    await page.getByRole('button', { name: '重新生成二维码', exact: true }).click();
    await page.getByAltText('小红书登录二维码', { exact: true }).waitFor();
    await page.locator('.n-card__footer').getByRole('button', { name: '关闭', exact: true }).click();
    await page.waitForTimeout(150);
    assert.equal(cancelled, 1);
    await page.getByRole('button', { name: '扫码登录小红书', exact: true }).click();
    await page.getByAltText('小红书登录二维码', { exact: true }).waitFor();
    phase = 'succeeded';
    await page.getByText('登录成功，Cookie 已自动保存', { exact: true }).waitFor();
    await page.getByText('登录有效', { exact: true }).waitFor();
    await page.getByRole('button', { name: '完成', exact: true }).click();
    assert.equal(starts, 4);
    assert.deepEqual(errors, []);
    console.log('QR UI passed: popup, image, phone-confirm state, expiry, refresh, cancel and verified account refresh. All QR responses are synthetic; no real platform requests.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
