# 小红书数据采集系统

基于 Spider_XHS 的本机单用户采集后台。Vue 3 + TypeScript + Naive UI；FastAPI + SQLAlchemy + SQLite。复用原 PC 端鉴权、Python/JavaScript 签名与单页采集接口。原项目文档保存在 `README.upstream.md`。

## 功能范围

- Cookie 配置及当前账号检测；完整 Cookie 只保存在后端本机 SQLite，不回显、不记录日志。
- 博主资料、博主发布笔记、关键词笔记搜索、指定笔记详情、一级/二级评论。
- 图片、视频只保存平台返回链接，不下载媒体；详情抽屉点击链接打开。
- 单任务后台工作线程；其余排队；协作停止、失败项重试、增量日志及重启中断标记。
- 数据库真实统计，后端分页/筛选/排序，按当前筛选或任务导出 Excel/CSV。
- 不接入发布、创作者运营、直播、私信、合作和分销功能。原模块保留以保护共用签名依赖。

## 目录

```text
backend/
  app.py          FastAPI 路由、应用生命周期与前端静态服务
  auth.py         单账号登录、服务端会话与退出登录
  config.py       数据目录、强制本机代理与端口预检查
  db.py           数据模型、SQLite WAL、会话及进程内数据库锁
  schemas.py      请求校验
  collector.py    原项目 API 适配、请求间隔/超时/停止/重试与分页
  scheduler.py    单工作线程队列、任务状态和日志
  storage.py      平台返回映射、按 ID 更新及任务关联
  queries.py      后端分页查询使用的筛选构造
  exports.py      中文导出字段映射、文本 ID、公式注入防护
frontend/         Vue 3、Vite、TypeScript、Naive UI、Router、Pinia、Axios
scripts/          PowerShell 代理检查及可选浏览器验证
tests/test_system.py  离线合成数据回归测试
apis/             原项目 API，采集使用 xhs_pc_apis.py
xhs_utils/        原签名、鉴权、Cookie、HTTP 与 JavaScript 运行时
spider/           原同步命令行采集示例，Web 入口不使用其下载流程
local_data/       本机数据库、验证截图（已被 Git 忽略）
```

## 环境与安装

推荐 Python 3.11–3.13（原项目要求 3.10+），Node.js 20.19+ 或 22.12+。本机已使用 Python 3.13.5、Node 24.11.0 验证。无需浏览器即可进行 Cookie 采集。

在项目根目录的 PowerShell 中执行。**每个联网命令前均执行代理脚本**，脚本设置大小写代理环境变量并在 800ms 内检查 `127.0.0.1:7897`；不可用时抛错停止。不要绕过代理或直接重试。HTTP/HTTPS 使用 7897，ALL_PROXY 使用 socks5://127.0.0.1:7898；本机地址列入 NO_PROXY。

```powershell
cd D:\codexXhs\Spider_XHS
python -m venv .venv
. ./.venv/Scripts/Activate.ps1
. ./scripts/proxy.ps1
python -m pip install -r requirements-web.txt
. ./scripts/proxy.ps1
npm ci --ignore-scripts --no-audit --no-fund --fetch-retries=0 --fetch-timeout=30000
Set-Location frontend
. ../scripts/proxy.ps1
npm ci --ignore-scripts --no-audit --no-fund --fetch-retries=0 --fetch-timeout=30000
npm run build
Set-Location ..
```

Python Web 依赖扩展放在 `requirements-web.txt`，原 `requirements.txt` 保留。根目录 npm 依赖 `crypto-js` 用于原签名实现，不能只安装 frontend 依赖。安装失败时保留报错；检查代理与端口后再处理，不反复执行同一失败命令。

Bash/WSL 请在联网前 export HTTP_PROXY、HTTPS_PROXY 为 `http://127.0.0.1:7897`，ALL_PROXY 为 `socks5://127.0.0.1:7898`，NO_PROXY 为 `localhost,127.0.0.1,::1`，并 export 对应小写变量；使用短超时检查端口后再安装。WSL 中该地址必须实际映射到运行 Clash 的本机。

## 启动

### 云端直连部署

云端无需代理时，在服务器后端进程设置环境变量 `XHS_NETWORK_MODE=direct`，重启后生效。例如：

```bash
cd /www/wwwroot/Spider_XHS
XHS_NETWORK_MODE=direct python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

宝塔 Python 项目可在“环境变量”中添加 `XHS_NETWORK_MODE=direct`，启动命令保持不变。此模式跳过本机 Clash 端口检查，清空进程继承的代理变量，并显式禁用 HTTP/HTTPS 代理。无需调整 Nginx。必须同步最新 `backend/config.py` 与 `backend/collector.py`。

未设置或设置为 `proxy` 时仍为本地强制代理模式，不会因端口不可达自动切换直连。云端直连是用户显式选择的部署模式，不改变本机开发的代理要求。

构建前端后，推荐只启动一个后端进程，它会同时提供前端与 API：

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

也可在项目根目录直接运行 `python main.py`，默认入口已移除原 Creator 手动测试。打开 http://127.0.0.1:8000 。OpenAPI 文档 http://127.0.0.1:8000/docs ，健康检查 `/api/health`。

开发模式使用两个终端：后端运行上述命令，另一个执行：

```powershell
cd D:\codexXhs\Spider_XHS\frontend
npm run dev
```

前端地址 http://127.0.0.1:5173 ，Vite 将 `/api` 转发给 8000。浏览器不会直接请求小红书，媒体只显示外链。只运行一个后端实例/worker，不能开启多 worker；不建议在采集中使用自动重载。首次构建或重新构建静态目录后重启后端。

## 系统登录

打开页面后首先进入左右布局的系统登录页。唯一账号为 `dawg`，密码为 `123456`。登录由后端校验；会话使用 HttpOnly、SameSite=Strict Cookie，前端不保存密码或会话令牌到 localStorage。会话有效期 12 小时，退出登录或重启后端后需要重新登录。顶部提供退出登录按钮。

未登录时任务、数据查询、Cookie 配置和导出 API 均返回 401。系统登录与小红书 Cookie 登录独立，登录系统后仍需配置有效平台 Cookie 才能采集。

## Cookie 配置与使用步骤

1. 在浏览器登录小红书，开发者工具 Network 中找到已登录的站内请求，复制请求头完整 Cookie；不能只复制 `document.cookie`，它不包含 HttpOnly 的 web_session。
2. 打开“登录配置”，粘贴并保存。必须包含 `a1` 和 `web_session`。保存成功后输入框清空，接口仅返回“已保存（内容隐藏）”。
3. 点击“检测当前登录”，成功时显示账号 ID/昵称；失效、访问限制或本地依赖错误会显示失败信息，不能当作采集成功。
4. 打开“创建采集任务”，默认选择博主采集。直接粘贴完整博主主页 URL 即可，页面自动识别博主/笔记链接并切换方式，保留 xsec_token 等参数；也可手动选择博主、关键词或指定笔记。笔记使用完整 `https://www.xiaohongshu.com/explore/...` 或 `/discovery/item/...` 链接，保留 xsec_token 与 xsec_source；不支持 xhslink 短链接，请在官方页面展开后复制完整链接。博主也可使用 24 位用户 ID。
5. 设置笔记数量、详情、一级评论上限、是否二级评论和每篇二级评论总上限。默认每次请求结束后随机等待 3～5 秒、最多 2 次网络重试。图片和视频仅记录链接。
6. 创建后直接进入任务详情。查看开始/结束时间、处理/成功/失败数、终止原因及增量日志。停止只阻止后续请求，当前网络请求最多 15 秒；本地 Node 签名子进程单次上限 30 秒。
7. “博主/笔记/评论数据”支持分页、搜索、任务筛选。笔记额外支持博主 ID、采集来源关键词、类型和发布时间范围。当前筛选导出涵盖全部匹配记录，不限当前分页。
8. 任务详情“导出任务 Excel”导出该任务关联的三类数据；“重试失败项”仍创建新任务。“继续采集（剩余数量）”沿用原任务，保留累计成功进度，仅补未完成笔记；失败、部分失败、已停止和已中断且目标未完成时可用。重启后不会自动续跑，需要手动点击继续。

## 手动继续采集

例如目标 20 篇，成功 13 篇后中止，任务列表、概览最近任务与详情会提供“继续采集（7）”。确认后原任务重新排队，进度保留 13/20。后台重新遍历博主/搜索列表以取得当前链接参数，跳过已成功笔记的详情和评论请求，最多补到原目标 20 篇。指定笔记任务从原链接列表中跳过已成功项。

每篇笔记及其所需评论全部成功后，写入 `task_completed_notes` 完成记录，因此部分保存但评论失败的笔记会再次处理。重复采集按原 ID 更新。当前轮失败数和错误摘要在继续时清空，原错误日志保留；成功数量累计。若平台已无更多数据则按实际返回结束，不保证达到目标。

已有旧任务首次继续时，按任务关联的插入顺序及历史成功数量恢复完成记录，并排除已知失败笔记；若已完成记录被删除导致无法恢复，则明确提示新建任务。新任务的完成标记独立保留，手动删除采集数据不会抹除任务的历史完成状态。删除任务会清理对应完成标记。

遇到 Cookie 失效、验证或访问限制，仍会停止；请先在官方客户端处理并在登录配置页检测，再点继续。不得用此按钮绕过访问限制。

搜索排序仅提供原 `search_note` 实际写入的综合、最新、最多点赞、最多评论、最多收藏；类型为不限、视频、图文。不暴露未验证的地理位置、已看过等筛选。

### 网页二维码登录

需要切换账号时，可点击“清除 Cookie”并确认。后端清空 Cookie、账号信息与登录状态，取消并移除二维码会话，随后可扫码或粘贴其他账号 Cookie。已采集的博主、笔记、评论、任务和系统登录保持不变。运行中或停止中的采集任务需先结束，否则清除接口返回 409。旧扫码回调与旧账号检测结果不能恢复已清除凭证。

清除接口为 `DELETE /api/login`，要求系统登录；重复清除仍成功。升级该功能需要同步 backend/app.py、backend/qr_login.py 和整个 frontend/dist，随后重启后端。专项验证命令为 `python scripts/test_clear_login.py`，使用临时数据库和模拟登录请求，不操作实际账号。

在“登录配置”点击“扫码登录小红书”，弹窗展示二维码，用小红书 App 扫描并在手机确认。后端取得正式凭证后再次验证账号，只有非访客且返回用户 ID 才自动保存 Cookie；前端不接收完整 Cookie。

复用原 XHSLoginApi 的 generate_init_cookies、generate_qrcode、check_qrcode_status、ensure_webprofile 和 get_user_info，保留原签名和请求顺序，不需要服务器浏览器。二维码生成及平台轮询在独立后台线程执行，网页只轮询缓存状态。支持本地代理与云端 direct 模式。

状态包含初始化、待扫码、待确认、验证中、成功、过期、取消和失败。初始化最长 120 秒，二维码生成后单独等待扫码 180 秒，最终账号验证最长 45 秒；各阶段有独立定时器，即使上游初始化尚未返回也会结束转圈并提示具体阶段。过期可手动重新生成；关闭弹窗、退出系统、更新 Cookie 或重新生成会取消旧会话，避免旧结果覆盖新配置。采集运行中需先停止任务再扫码切换账号。手动 Cookie 登录继续保留。

二维码匿名设备初始化按原项目登录接口的顺序连续执行，不额外叠加采集业务的 3～5 秒间隔；二维码展示后的扫码轮询和采集仍有间隔限制。初始化前检查后端 PATH 中的 Node.js、根目录 crypto-js 和 Python qrcode 依赖。界面显示阶段、耗时、剩余时间及不含查询参数的请求诊断；日志只记录阶段和异常类型，不记录 Cookie。

只检查二维码能否生成时，可在服务器根目录执行 `XHS_NETWORK_MODE=direct python scripts/diagnose_qr_login.py`。该脚本使用临时独立数据库，不读取或覆盖现有 Cookie，生成二维码后立即取消，不扫码。输出的阶段与请求路径可用于定位云端网络或依赖问题。本地仍需使用指定代理。

2026-10-25 修正初始化等待问题后，6 项针对性离线回归通过；在本机指定代理下实际生成匿名二维码，观察到耗时从约 50 秒降至约 2～3 秒。此结果不代表服务器耗时或手机扫码已验证。浏览器合成场景验证了阶段计时、初始化超时停止转圈、重新生成和原有状态交互。

服务器升级需同步 backend/app.py、backend/auth.py、backend/collector.py、新增 backend/qr_login.py，以及整个 frontend/dist。qrcode 已在原 requirements.txt 中，无新增依赖。仍需单个后端 worker；二维码会话不持久化，重启后需重新生成。

接口为 POST /api/login/qrcode、GET /api/login/qrcode/{id} 和 DELETE /api/login/qrcode/{id}；均要求系统登录，并绑定创建二维码的系统会话。遇到验证码或明确访问限制立即停止，需人工在官方客户端处理。

本次验证：前端构建及 34 项离线测试通过，覆盖自动保存、凭证脱敏、访客拒绝、过期取消、手动 Cookie 覆盖保护、会话隔离、退出取消和验证码限制。浏览器使用明确的合成二维码验证弹窗及状态变化，未请求真实小红书二维码接口。真实手机扫码需要部署后验收，不能据模拟测试声称平台登录已成功。测试预览 local_data/ui-qr-login.png 不能用于真实登录。

## 存储与时间

- 默认数据库：`local_data/collector.sqlite3`，含登录配置、任务、日志、博主、笔记、评论和任务关联；WAL/SHM 文件由 SQLite 管理。
- 可在启动前通过 `XHS_DATA_DIR` 指定绝对本机数据目录。该目录由后端创建；请勿将该目录或数据库加入 Git。数据库包含 Cookie，供当前本机账号使用。
- 媒体：不下载、不创建媒体目录；在笔记记录及导出中保存链接。
- 导出：服务器生成后直接响应下载，不在后端保留文件；实际保存到浏览器选择的下载目录。
- 原始返回数据保存在各数据表 raw JSON 中，剔除认证字段；列表 API 不暴露 raw。
- 平台 ID 为文本主键；同 ID 重采集更新，稀疏列表字段不清空已有详情；不同任务分别保留关联。
- SQLite 使用 WAL、busy_timeout 和同进程锁；每次操作独立创建/关闭会话，线程之间不共享会话。
- 内部存储 UTC ISO 8601；界面按 Asia/Shanghai（北京时间）格式化；导出列名明确 UTC。未知平台数值/时间保持空，不补 0；本机实际计数允许为 0。
- 二级评论的根 ID 来自所在根评论，直接父 ID 只读取真实 target_comment.id 或 parent_comment_id，缺失则为空，不推测。

## 任务终止和异常

状态包括待执行、运行中、停止中、已停止、已完成、部分失败、失败、已中断。数量上限不保证平台能提供相同数量：没有下一页时按实际数量结束。单条错误记录失败链接；已经保存的笔记和评论不回滚。游标不推进或连续重复数据会结束当前采集，避免无限循环。

登录失效、验证要求及明确访问限制会中止整个任务，提示人工处理；不实现账号池、代理池和验证码绕过。只对传输故障做有限重试及退避，重试前重新核验代理；普通业务错误不重复请求。重启将运行中/停止中标记为已中断，排队任务在启动后继续排队执行。

## API

统一 `/api` 前缀；同步数据库与导出路由由 FastAPI 在线程池执行，后台采集由独立单工作线程执行。

- `POST /api/auth/login`、`GET /api/auth/session`、`POST /api/auth/logout`
- `GET /api/health`、`GET /api/stats`
- `GET/PUT /api/login`、`POST /api/login/check`
- `POST/GET /api/tasks`、`GET /api/tasks/{id}`
- `POST /api/tasks/{id}/stop`、`POST /api/tasks/{id}/retry`
- `POST /api/tasks/{id}/resume`：将未完成的终态任务重新排队，保留原 ID 和累计成功进度；重复点击、已完成或登录失效时返回 409
- `DELETE /api/tasks/{id}`：删除任务、日志及关联，保留采集数据；运行中/停止中返回 409
- `DELETE /api/data/{bloggers|notes|comments}/{id}`：删除数据及全部任务关联；笔记连同评论删除，评论连同已知关联回复删除，博主仅删除资料
- `POST /api/data/{notes|comments}/batch-delete`：请求体 `{"ids":["..."]}`，单次 1–500 条；去重后在一个事务内删除。部分记录不存在则整批不删除，返回 404。
- `GET /api/tasks/{id}/logs?after=0&limit=200`
- `GET /api/data/{bloggers|notes|comments}?page=1&page_size=20`
- `GET /api/notes/{id}`
- `GET /api/export?fmt=xlsx&entity=notes&task_id=...`

数据筛选：q、task_id；笔记增加 user_id、keyword、note_type、published_from、published_to；评论增加 note_id、level。日期必须带时区。排序白名单为 collected_at/id/published_at（博主不支持 published_at），order=asc/desc。page_size 最大 100。完整参数及约束见 `/docs`。

Excel 固定博主、笔记、评论三个工作表，当前筛选仅作用于所选实体，任务筛选作用于全部工作表；CSV 仅输出当前实体，使用 UTF-8 BOM。字段和中文列名集中在 `backend/exports.py`。数据列表和详情不展示内部数据 ID，Excel 的三个工作表也不包含用户、笔记、评论及关联 ID。内部主键和任务关联继续保留于数据库。CSV 保留原有机器处理字段，ID 按文本写入；单元格有公式注入防护；CSV 的 ID 会添加单引号文本前缀以防止 Excel 自动转换，该前缀可能在部分 CSV 查看器中可见；Excel 单个单元格文本受 32767 字符限制，完整正文可用 CSV 或数据库读取。第一版导出在内存生成，建议通过筛选控制大量数据的导出范围。

## 导出文件名

Excel 下载文件以当前导出结果对应的博主昵称命名，例如 `Super Winnie.xlsx`；评论导出按笔记作者而非评论者命名。包含多个博主时为 `多博主数据.xlsx`，没有可用昵称时使用明确的通用名称。文件名中的非法字符会被替换，前端使用后端返回的 UTF-8 文件名。

## 删除记录

概览最近任务、任务列表及任务详情提供删除入口，博主/笔记/评论列表也提供删除。点击后需确认，确认框说明影响范围，取消不会修改数据。

笔记和评论表格额外提供复选框与“批量删除（数量）”按钮。可逐项选择或用表头全选当前页；翻页、调整每页数量或重新查询时清空选择，避免误删其他页面记录。确认批量删除后统一清理所选数据及其评论/已知回复和任务关联，成功后清空选择、刷新记录数及分页。未选择时按钮禁用，取消确认不会删除。批量删除同样受登录与活动任务保护。

- 删除任务：删除任务与日志和关联，保留实际采集数据。待执行任务可直接删除，运行中或停止中需先停止并等待结束。
- 删除博主：仅删除博主资料和该资料的任务关联，笔记与评论保留。
- 删除笔记：同时删除该篇笔记的已采集评论和所有相关任务关联。
- 删除评论：按数据库中真实的根评论/父评论关系删除已知关联回复，不推测未知关系。
- 任意任务运行中或停止中时，数据删除返回明确提示，需先停止任务再操作，避免后台写回。确认删除不可撤销，后续重新采集仍可生成记录。
- 删除后刷新列表、分页和数据库统计；任务历史处理数量保留原执行记录，不等同于当前存储数量。

## 验证

```powershell
python -m unittest discover -s tests -p test_system.py -v
cd frontend
npm run build
```

测试使用临时独立 SQLite 和合成平台数据，不请求真实小红书；覆盖 API 校验/脱敏、幂等更新、多任务关联、评论关系/上限、分页停滞、停止、排队、重启中断、部分失败重试、增量日志、CSV 与 Excel 文本 ID/公式安全。可选 `scripts/ui-smoke.cjs` 需已安装 Playwright 及 Chromium；设置 PLAYWRIGHT_MODULE 为现有 Playwright 包路径，先运行代理检查再执行。UI 验证仅访问本机服务，截图保存到 local_data。

**尚未提供有效 Cookie，真实平台登录、签名接受情况与实际采集结果尚未验证，不能据离线测试声称真实采集成功。**

## 常见问题

- 代理不可用：启动 Clash/Mihomo，确认 HTTP 7897 / SOCKS 7898，再运行代理脚本。若沙箱内本机端口检查失败、沙箱外正常，需要允许本机 TCP 访问，不应改为直连。
- crypto-js / Node 缺失：在项目根目录按代理策略安装 npm 依赖，并确认 `node --version`。前端依赖不能替代根目录签名依赖。
- 前端空白或 404：先在 frontend 执行 npm run build，再重启后端；开发模式确认 8000/5173 均启动。
- Cookie 失效/验证码/访问限制：在官方客户端完成验证或重新登录，更新 Cookie 后检测，再手动重试；不会自动绕过验证。
- HTTP 422：检查完整链接、数量范围和排序选项；接口不会在错误响应中回显 Cookie 输入。
- 实际数量较少：检查任务终止原因；平台无下一页、重复游标或单条不可访问均可能使数量不足。
- 字段为空：平台未返回或该笔记只采集了列表摘要；开启详情后重新采集。平台评论数与本机已采集评论数不同是正常现象。
- 数据库锁定：确认只运行一个服务实例，避免外部程序长期占用写锁。备份时先停止服务，并同时考虑 WAL 状态。

原项目 LICENSE 保留，原上游使用说明见 README.upstream.md。原 Dockerfile 仍为上游命令行示例，第一版按上述本机命令运行，不使用它部署 Web 系统。


请求间隔由 interval_min / interval_max 配置，默认 3 / 5 秒，每次独立均匀随机取值。上限须大于下限，两者允许 0.5–60 秒。旧任务仅保存固定 interval 时，执行、继续或重试会自动使用新的 3～5 秒默认范围。登录检测也遵循同样间隔；停止指令可中断等待。
