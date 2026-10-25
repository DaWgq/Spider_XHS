const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.XHS_UI_URL || 'http://127.0.0.1:18080';
if (new URL(baseURL).port !== '18080') throw new Error('Deletion regression requires isolated port 18080');
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
    const recent = page.locator('tbody tr').filter({ hasText: '本地删除验证任务' });
    await recent.getByRole('button', { name: '删除', exact: true }).click();
    await page.getByRole('button', { name: '取消', exact: true }).click();
    assert.equal(await recent.count(), 1);
    await recent.getByRole('button', { name: '删除', exact: true }).click();
    await page.getByRole('button', { name: '确认删除', exact: true }).click();
    await recent.waitFor({ state: 'detached' });
    await page.goto(`${baseURL}/tasks/ui-delete-detail`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: '删除任务', exact: true }).click();
    await page.getByRole('button', { name: '确认删除', exact: true }).click();
    await page.getByRole('heading', { name: '任务管理', exact: true }).waitFor();
    for (const [entity, content] of [['bloggers', '本地删除验证博主'], ['comments', '本地删除验证评论'], ['notes', '本地删除验证笔记']]) {
      await page.goto(`${baseURL}/data/${entity}`, { waitUntil: 'networkidle' });
      const row = page.locator('tbody tr').filter({ hasText: content });
      await row.getByRole('button', { name: '删除', exact: true }).click();
      await page.getByRole('button', { name: '确认删除', exact: true }).click();
      await row.waitFor({ state: 'detached' });
      if (entity === 'comments') assert.equal(await page.getByText('本地删除验证回复', { exact: true }).count(), 0);
    }
    assert.deepEqual(errors, []);
    console.log('Deletion UI passed: cancel, recent task deletion, task detail deletion, blogger/comment/note deletion and refreshed lists; isolated fixtures only.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
