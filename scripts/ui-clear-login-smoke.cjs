// Uses only synthetic Cookie strings in the dedicated local UI database.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.XHS_UI_URL || 'http://127.0.0.1:18080';
if (new URL(baseURL).port !== '18080') throw new Error('Clear-login regression requires isolated port 18080');
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
    const input = page.getByPlaceholder('粘贴完整请求 Cookie', { exact: true });
    async function save(value) {
      await input.fill(value);
      const saved = page.waitForResponse(r => r.url().endsWith('/api/login') && r.request().method() === 'PUT');
      await page.getByRole('button', { name: '保存 Cookie', exact: true }).click();
      assert.equal((await saved).status(), 200);
      await page.getByText('已保存（内容隐藏）', { exact: true }).waitFor();
    }
    const clear = page.getByRole('button', { name: '清除 Cookie', exact: true });
    await save('a1=ui-device; web_session=ui-synthetic-session');
    await clear.click();
    await page.getByRole('button', { name: '取消', exact: true }).click();
    assert.ok(await clear.isEnabled());
    async function confirmClear() {
      await clear.click();
      const response = page.waitForResponse(r => r.url().endsWith('/api/login') && r.request().method() === 'DELETE');
      await page.getByRole('button', { name: '确认清除', exact: true }).click();
      const result = await response;
      assert.equal(result.status(), 200);
      assert.equal((await result.json()).configured, false);
      await page.getByText('Cookie 已清除，可以扫码登录其他账号', { exact: true }).first().waitFor();
      assert.ok(await clear.isDisabled());
      assert.ok(await page.getByRole('button', { name: '检测当前登录', exact: true }).isDisabled());
      assert.equal(await input.inputValue(), '');
      assert.ok(await page.getByRole('button', { name: '扫码登录小红书', exact: true }).isEnabled());
    }
    await confirmClear();
    await save('a1=ui-new-device; web_session=ui-new-account');
    await confirmClear();
    await page.reload({ waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: '登录配置', exact: true }).waitFor();
    assert.ok(await clear.isDisabled());
    assert.deepEqual(errors, []);
    console.log('Clear Cookie UI passed: cancel, confirm, metadata reset, disabled check, system session retained, new credentials save and reload persistence. Synthetic local Cookie only; no platform requests.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
