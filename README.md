# 观澜 · Invest Watch

个人自部署投资观察平台：股票与加密现货自选、财经资讯、100 份持仓、确定性程序策略、可选 AI 分析与 Webhook 提醒。

**代码版本：v0.1.0。镜像已发布：`stylle/money-web:0.1.0` / `latest`，支持 linux/amd64 与 linux/arm64。发布摘要见 [核验记录](docs/docker-release.json)。**

## 包含什么

- A 股 / 港股 / 美股股票与场内 ETF，以及加密现货独立搜索、自选、分时与历史图表。
- 加密现货支持明确的 BTC-USDT / ETH-USD 交易对、Binance / Coinbase 同交易对切换、7×24 监控、UTC 日线及北京时间 08:30 日报。
- RSS/Atom 新闻源、标题去重、关键词方向订阅。新闻不调用 AI。
- 内置财联社、证券时报、金十数据公开市场参考、华尔街见闻、TradingView 社区观点、Seeking Alpha、CoinDesk、Cointelegraph；雪球列为需授权来源，显示实际状态。
- 100 份持仓，现金/目标/仓位上限、单次调整限制；不存总资金金额。
- MA20/MA60、RSI、MACD、ATR、历史量比，多条件程序观察；AI 与程序模式独立开关。
- 开盘后 30 分钟日报、盘中较昨收涨跌阈值、三市场日历、美股夏令时、静默/去重/重试/过期控制。
- OpenAI 兼容 Chat Completions / Responses，密钥加密、限额、引用和仓位校验。
- 通用 JSON Webhook，HMAC 签名与投递记录。
- 单镜像包含前后端，Compose 运行 Web + worker + PostgreSQL。

**初始没有模拟行情或预设持仓。现金为 100 份，AI 与程序建议默认关闭。**

## 先了解限制

默认采用多源自动切换：A 股按腾讯、东方财富、Yahoo 主备节点依次尝试；港美股使用腾讯与 Yahoo。来源都是公开网站端点，没有持续可用性承诺。2026-10-28 实测中腾讯/东方财富的 A 股报价较新，港股仍有延迟，美股部分图表通过 Yahoo 补充；详见 docs/integration-check.json。
加密资讯有独立频道；CoinDesk / Cointelegraph 提供公开 RSS。加密涨跌幅相对上一 UTC 日收盘，不是滚动 24 小时；USD 和 USDT 分开标识。
系统要求报价在交易时段内且新于五分钟，达不到时只展示数据、不推操作提示。旧缓存不会被标成实时；报价、日线、分时分别标注来源，日线复权序列不会逐行混用。
需要盘中及时提醒，请接入符合授权和时效要求的数据服务，标准协议见 [数据源文档](docs/DATA_SOURCES.md)。

程序规则通过了业务边界测试，**未完成完整策略回测、连续交易日试运行，不代表盈利有效**。AI 与 Webhook 的真实账号联调需要你的配置。未接入自动交易。ETF 重叠分析、场外基金、复杂技术事件通知等后续范围见 [开发计划](docs/PLAN.md)。

## Docker 部署

需要 Docker Engine / Docker Desktop 与 Compose v2。

```powershell
Copy-Item .env.example .env
# 编辑 .env，替换 APP_TOKEN 和 POSTGRES_PASSWORD，使用不同的随机值。
docker compose build
docker compose up -d
docker compose ps
```

打开 <http://localhost:8080>，输入 APP_TOKEN。

默认只监听 127.0.0.1。若在 NAS / 服务器局域网访问，在 `.env` 设置 `BIND_ADDRESS=0.0.0.0`，保留强口令；公网必须通过 HTTPS 反向代理并按 [安全说明](SECURITY.md) 设置出口限制。数据库不映射宿主机端口。

使用已发布镜像可直接：

```powershell
docker compose pull
docker compose up -d --no-build
```

镜像也提供源码提交号标签 `ce5c6f9`。固定版本可在 `.env` 设置 `IMAGE_TAG=0.1.0`；`latest` 会随新版本更新。

三项服务均有健康检查。worker 在浏览器关闭后继续工作；宿主机关机、休眠或网络中断会影响监控。每次监控工作完成后等待 60 秒，数据量与网络延迟影响实际周期，不承诺固定分钟到达。

### 出站网络和 Fake-IP DNS

默认不读取环境代理、拒绝私网和保留地址。服务器使用正常公网 DNS 时无需额外配置。
如本机代理使用 198.18.0.0/15 Fake-IP，可在 `.env` 精确列出信任的公开域名：

```dotenv
TRUSTED_EGRESS_HOSTS=query1.finance.yahoo.com,query2.finance.yahoo.com,qt.gtimg.cn,web.ifzq.gtimg.cn,push2.eastmoney.com,push2his.eastmoney.com,m.cls.cn,www.cls.cn,www.stcn.com,xnews.jin10.com,api-one.wallstcn.com,www.tradingview.com,seekingalpha.com,www.federalreserve.gov,data-api.binance.vision,api.exchange.coinbase.com,www.coindesk.com,cointelegraph.com
```

这只豁免这些域名的 Fake-IP 地址；不放开任意私网。内网 AI 服务需部署者明确开启 `ALLOW_PRIVATE_ENDPOINTS=true`，并自行设置出口隔离。

## 本地开发（无 Docker）

需要 Python 3.12、Node.js 22+，本地默认 SQLite，生产 Compose 使用 PostgreSQL。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

打开 <http://localhost:8000>。开发热更新可在另一个终端进入 frontend 运行 `npm run dev`，其 `/api` 代理到 8000。

独立终端启动后台监控：

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m app.worker
```

Windows 持续试用可在 PowerShell 7 使用以下脚本在后台启动网页与监控，关闭当前终端后仍保持运行：

```powershell
.\scripts\start-local.ps1
# 已有其他虚拟环境时可显式指定：
# .\scripts\start-local.ps1 -Python E:\path\to\.venv\Scripts\python.exe
# 受信 Fake-IP 代理环境另传 -TrustedEgressHosts 'query1.finance.yahoo.com,query2.finance.yahoo.com,www.federalreserve.gov'
```

脚本会等待健康检查、避免重复启动，并将日志和进程状态保存在忽略提交的 data 目录。
首次显式指定的 Python 环境与受信域名会在本地记住，之后运行脚本可复用；不会记录访问口令或 API Key。
主动停止时运行 `.\scripts\stop-local.ps1`。这些是本地后台进程，不是开机自启服务；重启电脑后需再次启动。
如果页面显示“无法连接后端服务”，先运行启动脚本，再点击对应页面的重试按钮。偏好设置和搜索失败会显示原因，不再无限加载。

API 和 worker 的工作目录、DATABASE_URL、DATA_DIR 必须一致。无 APP_TOKEN 的本地模式只接受环回请求。配置令牌时通过当前终端环境变量设置；不将密钥写入命令行参数或提交到 Git。

## 首次使用

1. 搜索并订阅具体代码，点击刷新行情。查看报价来源与时间。
2. 在持仓页配置资产和现金，合计必须为 100 份。允许添加 0 份仓位设置将来加仓上限。
3. 设置关键词和 RSS；获取资讯。
   内置来源已默认启用八个，来源面板显示最近成功时间、条数、失败或访问限制；内置源按 5～10 分钟、RSS 按 30 分钟刷新。发布时间未知的网页标题会明确标注，不进入 AI 的今日新闻证据。
4. 按需开启程序策略。AI 可完全不配置；开启前填写 API/模型/密钥，保存后测试连接。
5. 配置 Webhook，保存后测试；确认后台监控状态正常。
6. 操作后在持仓页手动更新份额并保存。保存持仓仅是记录，不会交易。

标的阈值在自选页面底部“管理订阅与异常阈值”设置。默认 ±5%，10% 是第二档，同方向同档每天一次。分时图为最近交易日，不代表今日仍在开盘。
现金预算在同批程序建议之间共享；不会把尚未执行的减仓当作可用资金。跨次生成的提示仍基于当时持仓快照，操作后需及时更新。

## Webhook 协议

请求为 UTF-8 JSON：

```json
{
  "id": "稳定事件ID",
  "type": "alert",
  "title": "某标的较昨收下跌 5.20%",
  "timestamp": "2026-10-28T02:00:00+00:00",
  "expires_at": "2026-10-28T02:15:00+00:00",
  "data": {"price": 1.0, "change_pct": -5.2}
}
```

示例字段不代表实际行情。消息类型包括 daily、alert、analysis、test。`data` 随类型变化。

请求头：`Idempotency-Key`、`X-InvestWatch-Timestamp`；配置签名密钥时附带 `X-InvestWatch-Signature: sha256=<hex>`，签名输入是 `timestamp + "." + 原始 JSON 字节`，算法为 HMAC-SHA256。接收端需验证时间戳并去重。
通用格式不能直接保证适配每个机器人厂商；使用自己的接收器转换为对应消息格式。

最多重试三次，静默期暂停，15 分钟过期。网络投递是至少一次，不能保证绝对不重复。测试消息立即发送，不受静默期限制。

## 测试与诊断

```powershell
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm test
npm run build
cd ..
python scripts/probe_sources.py
# 扩展来源逐项诊断，只写状态与诊断文件，不修改持仓/自选：
python scripts/check_integrations.py
```

诊断结果写入 `docs/source-probe.json`；不修改用户自选或持仓，不打印密钥。依赖锁文件固定了本次验证版本。
浏览器验收检查了首页、搜索订阅、持仓份额不平衡时禁用保存、设置页面。已验证 Linux 镜像、PostgreSQL / Web / worker、鉴权与重启持久化；ARM 使用仿真验收。PostgreSQL 备份恢复和真实 AI/Webhook 仍需部署环境验收。

## Docker Hub 发布

本机 Docker 可用且已通过 `docker login` 登录目标账号后：

```powershell
.\scripts\publish.ps1 -Tag 0.1.0
```

如果 Windows 没有 docker.exe，但已有 WSL 构建环境（本机为 `wusaqi-build`），可复用 Linux 内已登录的 Docker：

```powershell
.\scripts\publish.ps1 -Tag 0.1.0 -WslDistro wusaqi-build -DockerConfig /run/money-web-docker-auth
```

`-DockerConfig` 只传配置目录，不接收或输出 Token；登录时使用 `docker login --password-stdin`，不要把凭证放进项目或构建参数。`/run` 中的临时登录会随环境重启丢失，发布结束应清除。WSL 属于 Windows 管理员用户，受限账户看不到该发行版时需在该用户下执行。发布期间保持一个 WSL 终端打开，避免发行版空闲退出清除 `/run`。

脚本用 buildx 构建 linux/amd64 和 linux/arm64，推送 `stylle/money-web:0.1.0` 与 `latest`，随后核验 manifest。需要支持多架构的 builder / QEMU。

仓库还包含 `.github/workflows/ci.yml`：推送 main/PR 会测试和构建；发布 v* 标签或手动指定 publish 才推 Docker Hub。需在 GitHub 配置 `DOCKERHUB_TOKEN` Secret，用户名为 stylle。**当前没有创建远程 GitHub 仓库或配置此 Secret。**

## 备份与恢复

PostgreSQL 数据卷与加密密钥卷必须一起备份；`.env` 单独安全保存。避免 PowerShell 文本重定向改变 SQL 编码，先在容器生成文件再复制：

```powershell
New-Item -ItemType Directory backup -Force
docker compose exec -T db pg_dump -U invest -d invest --file=/tmp/invest.sql
docker compose cp db:/tmp/invest.sql ./backup/invest.sql
docker compose cp web:/data/secret.key ./backup/secret.key
```

恢复需在新的空数据库/数据卷验证，不应直接覆盖现有数据。先启动 db 并导入 SQL，再恢复同一 secret.key（UID/GID 10001 可读），最后启动 web/worker。使用 ENCRYPTION_KEY 时改为安全备份该环境变量。恢复命令和路径应按目标环境核实后执行。
SQLite 本地备份先停止 API/worker，再复制 data 目录，避免只拷贝活跃数据库漏掉 WAL。

## 文档

- [开发计划与已实现范围](docs/PLAN.md)
- [开发规范](docs/DEVELOPMENT.md)
- [数据源与自定义协议](docs/DATA_SOURCES.md)
- [安全说明](SECURITY.md)

本工具只聚合信息与提供辅助判断。价格、规则和 AI 都可能出错，任何交易由使用者自行决定。
