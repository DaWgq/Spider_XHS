// Optional UI regression. Point PLAYWRIGHT_MODULE to an existing Playwright package.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.XHS_UI_URL || 'http://127.0.0.1:8000';

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}), proxy: { server: 'http://127.0.0.1:7897', bypass: 'localhost,127.0.0.1,::1' }, args: ['--disable-background-networking'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await page.goto(`${baseURL}/data/notes`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: '登录工作空间', exact: true }).waitFor();
    assert.match(page.url(), /\/signin/);
    assert.ok(await page.locator('.signin-doge').evaluate(img => img.complete && img.naturalWidth > 0), 'Doge illustration loads');
    assert.ok(await page.locator('.signin-brand img').evaluate(img => img.complete && img.naturalWidth > 0), 'Dogecoin logo loads');
    await page.screenshot({ path: path.resolve('local_data/ui-signin.png'), fullPage: true });
    await page.setViewportSize({ width: 1000, height: 884 });
    await page.screenshot({ path: path.resolve('local_data/ui-signin-compact.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.getByRole('button', { name: '登录', exact: true }).isVisible());
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Mobile sign-in has no horizontal overflow');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByPlaceholder('请输入账号', { exact: true }).fill('dawg');
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('incorrect');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.getByText('账号或密码不正确', { exact: true }).waitFor();
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('123456');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.getByRole('heading', { name: '笔记数据', exact: true }).waitFor();
    await page.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: '数据概览', exact: true }).waitFor();
    await page.getByText('数据库累计记录').first().waitFor();
    assert.ok(await page.locator('.sidebar .brand img').evaluate(img => img.complete && img.naturalWidth > 0), 'Sidebar Dogecoin logo loads');
    assert.equal(await page.locator('.sidebar .n-menu .app-icon').count(), 7);
    await page.screenshot({ path: path.resolve('local_data/ui-overview.png'), fullPage: true });
    for (const [url, heading] of [['/login', '登录配置'], ['/create', '创建采集任务'], ['/tasks', '任务管理'], ['/data/bloggers', '博主数据'], ['/data/notes', '笔记数据'], ['/data/comments', '评论数据']]) {
      await page.goto(`${baseURL}${url}`, { waitUntil: 'networkidle' });
      await page.getByRole('heading', { name: heading, exact: true }).waitFor();
      if (url.startsWith('/data/')) {
        const headers = await page.locator('thead th').allTextContents();
        assert.ok(headers.every(header => !/\bID\b/i.test(header)), 'Data tables hide internal IDs');
      }
    }
    await page.goto(`${baseURL}/create`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: '创建并查看任务 →' }).click();
    await page.getByText('请填写采集目标', { exact: true }).waitFor();
    assert.equal(await page.locator('.n-form-item').filter({ hasText: '随机间隔下限（秒）' }).locator('input').inputValue(), '3');
    assert.equal(await page.locator('.n-form-item').filter({ hasText: '随机间隔上限（秒）' }).locator('input').inputValue(), '5');
    for (const label of ['博主采集', '关键词采集', '指定笔记']) {
      assert.ok(await page.getByRole('radio', { name: label, exact: true }).isVisible(), `Collection option visible: ${label}`);
    }
    await page.getByText('指定笔记', { exact: true }).click();
    const profile = 'https://www.xiaohongshu.com/user/profile/abcdef0123456789abcdef01?xsec_token=synthetic%2Btoken&xsec_source=pc_feed';
    await page.locator('textarea').fill(profile);
    await page.getByText('已识别为博主主页', { exact: false }).waitFor();
    assert.ok(await page.getByRole('radio', { name: '博主采集', exact: true }).isChecked());
    assert.equal(await page.getByPlaceholder('https://www.xiaohongshu.com/user/profile/… 或 24 位 ID').inputValue(), profile);
    await page.screenshot({ path: path.resolve('local_data/ui-blogger-create.png'), fullPage: true });
    let submitted;
    await page.route('**/api/tasks', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      submitted = route.request().postDataJSON();
      // Test-only interception: verify the payload without creating a real collection task.
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '本地验证：任务已拦截，未发起平台请求' }) });
    });
    await page.getByRole('button', { name: '创建并查看任务 →' }).click();
    await page.getByText('本地验证：任务已拦截，未发起平台请求', { exact: true }).waitFor();
    assert.equal(submitted.kind, 'blogger');
    assert.equal(submitted.target, profile);
    assert.deepEqual(submitted.urls, []);
    assert.equal(submitted.interval_min, 3);
    assert.equal(submitted.interval_max, 5);
    await page.unroute('**/api/tasks');
    await page.goto(`${baseURL}/data/notes`, { waitUntil: 'networkidle' });
    const downloaded = page.waitForEvent('download');
    const exportResponse = page.waitForResponse(r => r.url().includes('/api/export'));
    await page.getByRole('button', { name: '导出 Excel', exact: true }).click();
    const file = await downloaded;
    assert.match(file.suggestedFilename(), /\.xlsx$/);
    const disposition = (await exportResponse).headers()['content-disposition'];
    const expectedFilename = decodeURIComponent(disposition.split("filename*=UTF-8''")[1]);
    assert.equal(file.suggestedFilename(), expectedFilename, 'Browser must use the blogger filename supplied by the backend');
    await page.getByRole('button', { name: '退出登录', exact: true }).click();
    await page.getByRole('heading', { name: '登录工作空间', exact: true }).waitFor();
    await page.goto(`${baseURL}/tasks`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: '登录工作空间', exact: true }).waitFor();
    assert.deepEqual(errors, [], 'No browser runtime errors');
    console.log('UI smoke passed: login, invalid password, protected routes, logout, 7 routes, SVG menu icons, hidden ID columns, random 3-to-5-second interval, blogger URL detection, intercepted task submission and Excel download; no runtime errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
