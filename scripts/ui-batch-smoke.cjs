const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.XHS_UI_URL || 'http://127.0.0.1:18080';
if (new URL(baseURL).port !== '18080') throw new Error('Batch deletion regression requires isolated port 18080');
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
    async function filter(value) {
      await page.getByPlaceholder('搜索昵称、标题或内容', { exact: true }).fill(value);
      const loaded = page.waitForResponse(response => response.url().includes('/api/data/') && response.request().method() === 'GET');
      await page.getByRole('button', { name: '查询', exact: true }).click();
      await loaded;
    }
    async function confirmBatch(count) {
      await page.getByRole('button', { name: `批量删除（${count}）`, exact: true }).click();
      const done = page.waitForResponse(response => response.url().includes('/batch-delete') && response.request().method() === 'POST');
      await page.getByRole('button', { name: '确认删除', exact: true }).click();
      assert.equal((await done).status(), 200);
      await page.getByRole('button', { name: '批量删除（0）', exact: true }).waitFor();
    }
    await page.goto(`${baseURL}/data/notes`, { waitUntil: 'networkidle' });
    assert.ok(await page.getByRole('button', { name: '批量删除（0）', exact: true }).isDisabled());
    await filter('本地批量验证');
    await page.locator('thead .n-checkbox').click();
    await page.getByRole('button', { name: '批量删除（20）', exact: true }).waitFor();
    await page.getByRole('button', { name: '批量删除（20）', exact: true }).click();
    await page.getByRole('button', { name: '取消', exact: true }).click();
    assert.equal(await page.locator('tbody tr').count(), 20);
    await filter('本地批量验证笔记01');
    assert.ok(await page.getByRole('button', { name: '批量删除（0）', exact: true }).isDisabled());
    await filter('本地批量验证');
    await page.locator('thead .n-checkbox').click();
    await page.screenshot({ path: path.resolve('local_data/ui-batch-delete.png'), fullPage: true });
    await confirmBatch(20);
    await page.getByText('共 2 条记录', { exact: false }).waitFor();
    await page.locator('thead .n-checkbox').click();
    await confirmBatch(2);
    await page.getByText('共 0 条记录', { exact: false }).waitFor();
    await page.goto(`${baseURL}/data/comments`, { waitUntil: 'networkidle' });
    await filter('本地删除验证');
    await page.locator('thead .n-checkbox').click();
    await confirmBatch(2);
    await page.getByText('共 0 条记录', { exact: false }).waitFor();
    assert.deepEqual(errors, []);
    console.log('Batch UI passed: select all current page, count, cancel, clear selection on query, batch 20+2 notes, cascade comments and batch overlapping comments; isolated fixtures only.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
