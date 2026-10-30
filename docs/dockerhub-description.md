# 观澜 · Invest Watch

个人自部署投资观察平台：股票与加密现货自选、财经资讯、100 份持仓、确定性程序策略、可选 AI 分析与 Webhook 提醒。

**v0.2.0 已发布：`stylle/money-web:0.2.0` / `latest`，支持 linux/amd64、linux/arm64，默认单容器部署。[发布核验记录](https://github.com/Stylle/money-web/blob/main/docs/docker-release.json)。**

代码仓库：[Stylle/money-web](https://github.com/Stylle/money-web) · 镜像：[Docker Hub](https://hub.docker.com/r/stylle/money-web)。

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
- 单容器包含网页、API 和后台监控；SQLite、设置和加密密钥统一保存在持久数据卷。

**初始没有模拟行情或预设持仓。现金为 100 份，AI 与程序建议默认关闭。**

## 先了解限制

默认采用多源自动切换：A 股按腾讯、东方财富、Yahoo 主备节点依次尝试；港美股使用腾讯与 Yahoo。来源都是公开网站端点，没有持续可用性承诺。2026-10-28 实测中腾讯/东方财富的 A 股报价较新，港股仍有延迟，美股部分图表通过 Yahoo 补充；详见 docs/integration-check.json。
加密资讯有独立频道；CoinDesk / Cointelegraph 提供公开 RSS。加密涨跌幅相对上一 UTC 日收盘，不是滚动 24 小时；USD 和 USDT 分开标识。
系统要求报价在交易时段内且新于五分钟，达不到时只展示数据、不推操作提示。旧缓存不会被标成实时；报价、日线、分时分别标注来源，日线复权序列不会逐行混用。
需要盘中及时提醒，请接入符合授权和时效要求的数据服务，标准协议见 [数据源文档](https://github.com/Stylle/money-web/blob/main/docs/DATA_SOURCES.md)。

程序规则通过了业务边界测试，**未完成完整策略回测、连续交易日试运行，不代表盈利有效**。AI 与 Webhook 的真实账号联调需要你的配置。未接入自动交易。ETF 重叠分析、场外基金、复杂技术事件通知等后续范围见 [开发计划](https://github.com/Stylle/money-web/blob/main/docs/PLAN.md)。

## Docker Compose 单容器部署

需要 Docker Engine / Docker Desktop 和 Docker Compose v2+。Docker 镜像是应用安装包，容器是运行实例；Compose 用一份 YAML 记录镜像、端口和持久数据，后续升级沿用同一文件。本项目只启动 **1 个容器**，容器内部管理网页和监控两个进程，无需另装数据库或 Redis。

新建空目录，将以下内容保存为 `compose.yaml`（与仓库默认文件一致），替换访问口令：

```yaml
name: money-web
services:
  money-web:
    image: stylle/money-web:0.2.0 # 固定版本；latest 随发布更新
    restart: unless-stopped # 异常退出和宿主机重启后自动启动，手动停止除外
    ports:
      - "127.0.0.1:8080:8000" # 宿主机地址:网页端口:容器端口；局域网访问改为 8080:8000
    environment:
      APP_TOKEN: "replace_with_at_least_32_random_characters" # 必改：网页口令，至少 32 位随机字符
    volumes:
      - money-data:/data # SQLite、持仓、自选、设置和自动生成的加密密钥
volumes:
  money-data: # Docker 管理的持久卷，更新/重建容器仍保留
```

在该目录执行，无需克隆代码、构建镜像或准备 `.env`：

```sh
docker compose up -d
docker compose ps
```

本机打开 <http://localhost:8080>，输入 `APP_TOKEN`。局域网/NAS 访问把端口改为 `"8080:8000"`，再打开 `http://服务器IP:8080`；公网访问应使用 HTTPS 反向代理。共享访问口令需保密。

- `image`：镜像与版本；固定 `0.2.0` 方便复现，`latest` 随发布更新。
- `restart`：进程异常退出会由容器管理器退出整个容器，Docker 自动重启；网页或监控子进程不会默默消失。Docker 的 `unhealthy` 状态本身不会触发重启，需要监控平台介入。
- `ports`：左侧是宿主机端口，右侧固定为容器的 `8000`。默认只接受本机访问。
- `environment.APP_TOKEN`：网页访问口令，必须替换为至少 32 位随机字符。AI Key、Webhook 等在网页偏好设置里配置。
- `volumes`：`money-data` 保存 SQLite 数据库、自选、100 份持仓、资讯、通知记录、加密设置及 `secret.key`。重建容器不丢数据；**不要执行 `docker compose down -v`**，它会删除数据卷。

这是个人单实例部署，不支持通过 `--scale` 共享同一 SQLite 数据库；数据卷应使用本地磁盘。

网页和监控均被健康检查覆盖。浏览器关闭后监控继续运行；宿主机关机、休眠或断网会影响监控。每轮工作后等待 60 秒，网络延迟会影响实际周期。

### 更新、查看日志与停止

```sh
# 固定版本升级时先修改 image 标签，并先备份数据
docker compose pull
docker compose up -d
docker compose logs --tail=100 -f
docker compose stop
# 恢复运行
docker compose up -d
```

始终保留同一个目录和 `name: money-web`，避免换项目名称后挂上一个新的空数据卷。源码构建可用 `docker build -t stylle/money-web:0.2.0 .`，然后运行同一份 Compose。

### 可选参数（按需添加）

下列环境变量需写到服务的 `environment` 下。仅写在 `.env` 不会自动传给容器；若使用 `.env`，还需在 Compose 中写 `APP_TOKEN: ${APP_TOKEN:?Set APP_TOKEN}` 等引用。

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_TOKEN` | 无 | 网页访问口令；最简文件已包含，必须替换 |
| `TRUSTED_EGRESS_HOSTS` | 空 | 受信 Fake-IP DNS 的精确公网域名，逗号分隔；普通公网 DNS 不需要 |
| `ALLOW_PRIVATE_ENDPOINTS` | `false` | 内网 AI/Webhook 必须显式设为 `true`；同时自行配置出口隔离 |
| `ENCRYPTION_KEY` | 自动创建 `/data/secret.key` | 可选 Fernet 密钥；设置后必须独立安全备份，不能随意更换 |
| `DATABASE_URL` | `sqlite:////data/invest.db` | 仅高级部署接外部 PostgreSQL 时使用；普通单容器部署不需要 |
| `DATA_DIR` | `/data` | 数据目录；通常保持默认，与持久卷路径一致 |

可选服务参数（与 `image` 同级）：

```yaml
    # 可选加固；/data 和 /tmp 仍可写
    read_only: true
    tmpfs:
      - /tmp:size=64M,mode=1777
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    # 可选限制，按订阅量和宿主机资源调整
    mem_limit: 1g
    cpus: 2
```

默认不读取环境代理，拒绝私网和保留地址。若代理采用 198.18.0.0/15 Fake-IP，可添加以下设置；只对列出的精确域名豁免 Fake-IP，不放开任意私网：

```yaml
    environment:
      APP_TOKEN: "替换为你的随机口令"
      TRUSTED_EGRESS_HOSTS: "query1.finance.yahoo.com,query2.finance.yahoo.com,qt.gtimg.cn,web.ifzq.gtimg.cn,push2.eastmoney.com,push2his.eastmoney.com,m.cls.cn,www.cls.cn,www.stcn.com,xnews.jin10.com,api-one.wallstcn.com,www.tradingview.com,seekingalpha.com,www.federalreserve.gov,data-api.binance.vision,api.exchange.coinbase.com,www.coindesk.com,cointelegraph.com"
```

### 从 v0.1 三容器部署继续使用

**原 PostgreSQL 数据卷不能直接作为 SQLite 使用。** 已有部署先保留原目录、数据卷和 `.env`，使用 [compose.legacy.yaml](https://github.com/Stylle/money-web/blob/main/compose.legacy.yaml) 继续运行固定的 `0.1.0`：`docker compose -f compose.legacy.yaml up -d`。该文件仅用于旧部署兼容。

新建空目录使用 v0.2 单容器会创建新 SQLite 数据，不能自动继承旧持仓；目前没有 PostgreSQL → SQLite 自动迁移工具。若需保留旧库并升级应用，可将 v0.2 单容器的 `DATABASE_URL` 指向原 PostgreSQL、挂载原加密密钥，并继续保留数据库服务。迁移前必须备份；不要删除旧卷，也不要把旧数据库目录挂到 `/data`。

## 本地开发（无 Docker）

需要 Python 3.12、Node.js 22+，本地与默认 Compose 均使用 SQLite。

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
浏览器验收检查了首页、搜索订阅、持仓份额不平衡时禁用保存、设置页面。容器验收覆盖单容器数量、网页与监控、鉴权、进程故障恢复和重启持久化；ARM 为仿真环境。真实 AI/Webhook 仍需你的配置。

## Docker Hub 发布

本机 Docker 可用且已通过 `docker login` 登录目标账号后：

```powershell
.\scripts\publish.ps1 -Tag 0.2.0
```

如果 Windows 没有 docker.exe，但已有 WSL 构建环境（本机为 `wusaqi-build`），可复用 Linux 内已登录的 Docker：

```powershell
.\scripts\publish.ps1 -Tag 0.2.0 -WslDistro wusaqi-build -DockerConfig /run/money-web-docker-auth
```

`-DockerConfig` 只传配置目录，不接收或输出 Token；登录时使用 `docker login --password-stdin`，不要把凭证放进项目或构建参数。`/run` 中的临时登录会随环境重启丢失，发布结束应清除。WSL 属于 Windows 管理员用户，受限账户看不到该发行版时需在该用户下执行。发布期间保持一个 WSL 终端打开，避免发行版空闲退出清除 `/run`。

脚本用 buildx 构建 linux/amd64 和 linux/arm64，推送 `stylle/money-web:0.2.0` 与 `latest`，随后核验 manifest。需要支持多架构的 builder / QEMU。

仓库还包含 `.github/workflows/ci.yml`：推送 main/PR 会测试和构建；发布 v* 标签或手动指定 publish 才推 Docker Hub。需在 GitHub 配置 `DOCKERHUB_TOKEN` Secret，用户名为 stylle。**公开 GitHub 仓库已建立；DOCKERHUB_TOKEN Secret 尚未配置，当前由本机授权发布。**

## 备份与恢复

默认 SQLite：先停容器，再复制整个 `/data`，包含数据库、WAL（若有）和加密密钥。以下命令在 Compose 所在目录执行，备份目录应为空：

```sh
mkdir backup
docker compose stop
docker compose cp money-web:/data/. ./backup/
docker compose up -d
```

备份包含敏感信息，需安全保存。用新目录和独立 Compose 项目验证恢复，先 `docker compose create` 创建停止状态容器，再 `docker compose cp ./backup/. money-web:/data/`，再执行 `docker compose run --rm --no-deps --user 0 --entrypoint chown money-web -R 10001:10001 /data` 修正文件归属，最后 `docker compose up -d`。恢复到原部署前也必须先停止并另做备份，不能直接覆盖运行中的数据库。使用 `ENCRYPTION_KEY` 时另行备份同一个环境变量。

旧 PostgreSQL 部署需同时备份 `pg_dump`、原密钥和 `.env`，不要用 SQLite 的目录复制替代数据库备份。

## 文档

- [开发计划与已实现范围](https://github.com/Stylle/money-web/blob/main/docs/PLAN.md)
- [开发规范](https://github.com/Stylle/money-web/blob/main/docs/DEVELOPMENT.md)
- [数据源与自定义协议](https://github.com/Stylle/money-web/blob/main/docs/DATA_SOURCES.md)
- [安全说明](https://github.com/Stylle/money-web/blob/main/SECURITY.md)

本工具只聚合信息与提供辅助判断。价格、规则和 AI 都可能出错，任何交易由使用者自行决定。
