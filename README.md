# 观澜 · Invest Watch

个人自部署投资观察平台：股票与加密现货自选、财经资讯、100 份持仓、确定性程序策略、可选 AI 分析与 Webhook 提醒。

**v0.2.3 已发布：`stylle/money-web:0.2.3` / `latest`，支持 linux/amd64、linux/arm64。新增统一出站代理、NAS 代理部署示例与无密钥网络诊断。[发布核验记录](docs/docker-release.json)。**

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
- MagicPush 自动适配、自定义 JSON/文本模板与请求头、HMAC 签名和投递记录。
- 单容器包含网页、API 和后台监控；SQLite、设置和加密密钥统一保存在持久数据卷。

**初始没有模拟行情或预设持仓。现金为 100 份，AI 与程序建议默认关闭。**

## 先了解限制

默认采用多源自动切换：A 股按腾讯、东方财富、Yahoo 主备节点依次尝试；港美股使用腾讯与 Yahoo。来源都是公开网站端点，没有持续可用性承诺。2026-10-28 实测中腾讯/东方财富的 A 股报价较新，港股仍有延迟，美股部分图表通过 Yahoo 补充；详见 docs/integration-check.json。
加密资讯有独立频道；CoinDesk / Cointelegraph 提供公开 RSS。加密涨跌幅相对上一 UTC 日收盘，不是滚动 24 小时；USD 和 USDT 分开标识。
系统要求报价在交易时段内且新于五分钟，达不到时只展示数据、不推操作提示。旧缓存不会被标成实时；报价、日线、分时分别标注来源，日线复权序列不会逐行混用。
需要盘中及时提醒，请接入符合授权和时效要求的数据服务，标准协议见 [数据源文档](docs/DATA_SOURCES.md)。

程序规则通过了业务边界测试，**未完成完整策略回测、连续交易日试运行，不代表盈利有效**。AI 与 Webhook 的真实账号联调需要你的配置。未接入自动交易。ETF 重叠分析、场外基金、复杂技术事件通知等后续范围见 [开发计划](docs/PLAN.md)。

## Docker Compose 单容器部署

需要 Docker Engine / Docker Desktop 和 Docker Compose v2+。Docker 镜像是应用安装包，容器是运行实例；Compose 用一份 YAML 记录镜像、端口和持久数据，后续升级沿用同一文件。本项目只启动 **1 个容器**，容器内部管理网页和监控两个进程，无需另装数据库或 Redis。

新建空目录，将以下内容保存为 `compose.yaml`（与仓库默认文件一致），替换访问口令：

```yaml
name: money-web
services:
  money-web:
    image: stylle/money-web:0.2.3 # 固定版本；latest 随发布更新
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

- `image`：镜像与版本；固定 `0.2.3` 方便复现，`latest` 随发布更新。
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

始终保留同一个目录和 `name: money-web`，避免换项目名称后挂上一个新的空数据卷。源码构建可用 `docker build -t stylle/money-web:0.2.3 .`，然后运行同一份 Compose。

### 可选参数（按需添加）

下列环境变量需写到服务的 `environment` 下。仅写在 `.env` 不会自动传给容器；若使用 `.env`，还需在 Compose 中写 `APP_TOKEN: ${APP_TOKEN:?Set APP_TOKEN}` 等引用。

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_TOKEN` | 无 | 网页访问口令；最简文件已包含，必须替换 |
| `HTTP_PROXY` / `HTTPS_PROXY` | 空，直连 | HTTP / HTTPS 目标各自的代理；支持 HTTP 或 HTTPS 代理服务器，通常都填 `http://主机:HTTP或Mixed端口` |
| `ALL_PROXY` | 空 | 该协议未设置代理变量时的后备代理；不支持 SOCKS 端口 |
| `NO_PROXY` | 空 | 逗号分隔的直连域名、IP、IP 网段或 `*`；内网 AI、MagicPush 等按需排除 |
| `TRUSTED_EGRESS_HOSTS` | 空 | 受信 Fake-IP DNS 的精确公网域名，逗号分隔；普通公网 DNS 不需要 |
| `ALLOW_PRIVATE_ENDPOINTS` | `false` | 内网 AI/Webhook 必须显式设为 `true`；同时自行配置出口隔离 |
| `ENCRYPTION_KEY` | 自动创建 `/data/secret.key` | 可选 Fernet 密钥；设置后必须独立安全备份，不能随意更换 |
| `DATABASE_URL` | `sqlite:////data/invest.db` | 仅高级部署接外部 PostgreSQL 时使用；普通单容器部署不需要 |
| `PUID` / `PGID` | `10001` / `10001` | 应用运行 UID/GID；NAS 需要沿用指定属主时可设置，必须为非零数字 |
| `DATA_DIR` | `/data` | 数据目录；通常保持默认，与持久卷路径一致 |

可选服务参数（与 `image` 同级）：

```yaml
    # 可选加固；/data 和 /tmp 仍可写
    read_only: true
    tmpfs:
      - /tmp:size=64M,mode=1777
    cap_drop: [ALL]
    # 初始化数据卷及降权需要；运行进程降权后不保留这些能力
    cap_add: [CHOWN, FOWNER, DAC_OVERRIDE, SETUID, SETGID]
    security_opt: ["no-new-privileges:true"]
    # 可选限制，按订阅量和宿主机资源调整
    mem_limit: 1g
    cpus: 2
```

### 容器使用 NAS / 本机代理

v0.2.3 起，行情、搜索、资讯、AI 和 Webhook 统一读取上述代理变量；未配置时直连。旧版显式忽略环境代理，只有添加变量不会生效，需要升级镜像。支持对应小写变量；大小写同时存在时小写优先，显式空值禁用该协议代理且不再回退 `ALL_PROXY`。兼容 NAS 中误写的 `http-proxy` / `https-proxy` 等连字符名称，建议统一改为下划线标准名称。

容器里的 `localhost` / `127.0.0.1` 是容器自身。代理运行在 NAS 宿主机时，在原 Compose 服务中合并如下内容，保留原口令和数据卷；`7890` 替换为代理实际的 **HTTP / Mixed 端口**：

```yaml
    environment:
      APP_TOKEN: "保留你的原口令"
      HTTP_PROXY: "http://host.docker.internal:7890"
      HTTPS_PROXY: "http://host.docker.internal:7890" # HTTPS 目标通常也使用 http:// 代理，通过 CONNECT 隧道访问
      NO_PROXY: "localhost,127.0.0.1,::1,host.docker.internal" # 自建 AI/MagicPush 的域名或 IP 也加在这里
    extra_hosts:
      - "host.docker.internal:host-gateway" # Linux/NAS 将此名称映射到 Docker 宿主机网关
```

- 代理必须监听容器可达的宿主机网卡/网关地址并开启「允许局域网连接」，同时在防火墙允许 Docker 网段。仅监听宿主机 `127.0.0.1` 的代理无法通过网关访问。不要为了使用代理设置容器 `network_mode: host` 或 `privileged`。
- 如果代理运行在另一台电脑，把两项代理地址都换为那台电脑的局域网 IP，例如 `http://192.168.1.20:7890`，不需要 `extra_hosts`；电脑关机或休眠时代理不可用。NAS 虚拟机内的 Docker，宿主机指 Docker 引擎所在虚拟机，可能仍需使用实际代理机器的局域网 IP。
- `HTTPS_PROXY` 表示用于 HTTPS **目标**，不意味着代理本身必须是 `https://`。只有代理端口确实提供 TLS 时才用 `https://`；SOCKS 专用端口会给出配置错误，请改用 HTTP/Mixed 端口。[HTTPX 说明](https://www.python-httpx.org/advanced/proxies/)、[Docker 网关说明](https://docs.docker.com/compose/how-tos/networking/)。
- `NO_PROXY=example.com` 匹配该域名及其子域名，不匹配 `badexample.com`；支持 `example.com:8443`、`https://example.com`、IPv4/IPv6 和 CIDR。网段只匹配 URL 中的 IP 字面量，不会解析域名来匹配网段；内网域名请显式添加。`*` 使全部直连。
- 内网 HTTP AI/MagicPush 还需 `ALLOW_PRIVATE_ENDPOINTS: "true"`；`NO_PROXY` 仅控制路由，不放宽目标地址安全校验。代理自身可以使用私网地址，无需为代理开启此选项。
- 代理认证可按需使用 URL 中的账号密码（特殊字符做 URL 编码，Compose 中字面 `$` 写成 `$$`）。环境变量可被 NAS 管理员查看；不要把含密码的配置上传 Git。错误和诊断命令不输出代理 URL、账号、密码。

修改环境变量后重建容器，单纯 `docker compose restart` 不会更新环境：

```sh
docker compose pull
docker compose up -d --force-recreate
docker compose exec money-web python -m app.networkcheck
```

诊断命令显示 HTTP/HTTPS 使用的变量名、代理/直连、NO_PROXY 是否匹配、代理是否误指向环回，并通过同一出站链路访问固定公共测试站点。不会读取 AI/Webhook 设置或发送通知；HTTP 只检查路由，HTTPS 执行十秒超时测试，失败返回非零退出码。测试站点连通不代表所有行情源可用，仍需查看网页来源状态。失败会区分代理认证、握手、连接及超时；不会在代理失败后悄悄切换直连。容器自身健康检查始终直连，不依赖代理可用性。

仍保留 HTTPS 证书验证、目标域名 DNS 预检查、私网限制、禁止重定向与 4MB 响应限制。代理不绕过本地 DNS 检查；域名无法解析时需修复容器 DNS。若受信 DNS 采用 198.18.0.0/15 Fake-IP，可添加以下设置；只对列出的精确域名豁免 Fake-IP，不放开任意私网：

```yaml
    environment:
      APP_TOKEN: "替换为你的随机口令"
      TRUSTED_EGRESS_HOSTS: "query1.finance.yahoo.com,query2.finance.yahoo.com,qt.gtimg.cn,web.ifzq.gtimg.cn,push2.eastmoney.com,push2his.eastmoney.com,m.cls.cn,www.cls.cn,www.stcn.com,xnews.jin10.com,api-one.wallstcn.com,www.tradingview.com,seekingalpha.com,www.federalreserve.gov,data-api.binance.vision,api.exchange.coinbase.com,www.coindesk.com,cointelegraph.com"
```

### NAS 权限与启动报错

v0.2.1 启动时先准备应用数据目录和数据库/密钥文件，再降权运行网页与监控。无需手动匹配默认 UID 10001；保留文件内容，只处理应用自身文件，不递归修改其他目录，不跟随符号链接或硬链接。运行进程不保留 root 权限。

NAS 若需沿用本机用户和组，在 `environment` 中按实际数字添加 `PUID: "1026"`、`PGID: "100"`（仅示例）。不要设置 `user: root` 来长期运行服务。显式 `user: "1026:100"` 会跳过初始化，此时目录须已允许该用户访问。

`ERROR:root` 是日志名称，不代表进程身份。新版启动日志会报告失败阶段：`data-volume-initialization`（NAS ACL、只读挂载或初始化能力）、`sqlite-lock-file`、`sqlite-advisory-lock`、`database-initialization`、`encryption-key`、`runtime-state-in-tmp`。

从 0.2.0 更新：修改 Compose 的镜像为 `stylle/money-web:0.2.3`，保留原数据卷，运行 `docker compose pull` 和 `docker compose up -d`。开启 `read_only` 时必须保留可写 `/tmp`；使用 `cap_drop: [ALL]` 时需补上上方 `cap_add`。NAS ACL、只读存储或 NFS root_squash 无法由应用绕过，遇到这种情况需按明确的失败阶段调整 NAS 挂载设置或配置对应 PUID/PGID。

### 从 v0.1 三容器部署继续使用

**原 PostgreSQL 数据卷不能直接作为 SQLite 使用。** 已有部署先保留原目录、数据卷和 `.env`，使用 [compose.legacy.yaml](compose.legacy.yaml) 继续运行固定的 `0.1.0`：`docker compose -f compose.legacy.yaml up -d`。该文件仅用于旧部署兼容。

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

## Webhook 与 MagicPush

### MagicPush 配置

参照 [电影项目的模板实现](https://github.com/Stylle/today-random-movie-web/blob/main/server/notify.go)，并按 [MagicPush 官方推送接口](https://github.com/magiccode1412/magicpush/blob/main/apps/website/guide/dev/api-reference.md) 适配。MagicPush 需要 `content` 正文，消息 `type` 使用 `text/markdown/html`；观澜事件的 `alert/daily/analysis` 不是它的消息格式。

1. 在偏好设置中填写 MagicPush 的 `https://你的域名/api/push/接口令牌`，推送格式选 **MagicPush**，请求方法选 **POST**。
2. 也可填写 `https://你的域名/api/push`，在 Authorization 中填写 `Bearer 接口令牌`。这里使用 MagicPush「接口管理」的推送令牌，不是登录密码或观澜的 HMAC 签名密钥。
3. 点击 **保存并测试推送**。此按钮只保存推送设置，保留其他未提交的偏好。测试消息和后台日报/异常提醒使用相同适配器。
4. 自动模式可识别标准 `/api/push` 路径；反向代理重写路径时请显式选择 MagicPush。旧通用接收器如也使用该路径，可选「观澜原始事件 JSON」保持原格式。

请求会转换为以下结构，正文由真实事件生成，不调用 AI：

```json
{"title":"观澜通知连接测试","content":"观澜通知连接测试\n时间：事件时间\nWebhook 已成功连接","type":"text"}
```

MagicPush 的 `/api/inbound/接口令牌` 是另一种入站映射接口，需要在 MagicPush 中启用并配置字段映射。普通推送建议使用 `/api/push/接口令牌`。NAS 内网 HTTP 地址还需按上文显式设置 `ALLOW_PRIVATE_ENDPOINTS=true`，不会自动放宽网络访问限制。

400 也可能来自无效令牌、接口禁用、未绑定渠道、关键词过滤或下游渠道失败。已知原因显示固定诊断，不回显上游正文、URL 或密钥；未知错误显示 HTTP 状态并引导查看 MagicPush 推送记录。HTTP 200 中 `success=false` 或部分渠道失败也会记作失败，不冒充成功。

### 自定义 Webhook（与电影项目类似）

选择「自定义正文模板」，可配置 POST / PUT / GET、JSON / 纯文本、自定义请求头。GET 仅支持 JSON 对象，会把字段编码到查询参数，保留 URL 已有查询参数；发送正文建议使用 POST。自定义请求头采用 JSON 字符串对象；签名、去重及 HTTP 传输头不可覆盖。Authorization 专用字段优先于自定义头中的同名字段。

模板示例：

```json
{"title":"{{title}}","content":"{{text}}","type":"text"}
```

变量包括 `{{title}}`、`{{text}}` / `{{content}}`、`{{event}}`、`{{id}}`、`{{timestamp}}`、`{{fields}}` / `{{data}}`、`{{payload}}`。`event` 保留 alert/daily/analysis/test 事件类型；不要把 `{{event}}` 填入 MagicPush 的消息 `type`。`fields` 是事件数据对象，`payload` 是完整事件；JSON 中不加引号可保留结构，例如 `{"data":{{fields}}}`。字符串变量自动处理引号、反斜杠与换行；不执行表达式。保存时校验模板和请求头，非法配置不覆盖原设置。

请求头和模板可能含 Token，保存在加密设置中，不在配置读取接口回显；未修改保留，填写完整内容替换，使用清除按钮可删除。模板选项只在自定义模式生效。纯文本留空模板时发送可读通知正文。

### 保留原始事件 JSON

选择「观澜原始事件 JSON」继续发送原格式：

```json
{"id":"稳定事件ID","type":"alert","title":"提醒标题","timestamp":"事件时间","expires_at":"过期时间","data":{"price":1.0,"change_pct":-5.2}}
```

示例不代表实际行情。消息类型为 daily、alert、analysis、test，`data` 随类型变化。Idempotency-Key 在格式转换后仍保持事件 ID。可选 `X-InvestWatch-Signature: sha256=<hex>` 使用 HMAC-SHA256，输入为 `X-InvestWatch-Timestamp + "." + 实际发送的正文原始字节`；GET 的正文为空。接收端需校验时间戳并去重。

最多重试三次，静默期暂停，15 分钟过期。至少一次投递不能保证绝不重复；MagicPush 部分渠道成功后重试可能导致该渠道重复，请结合其推送记录核对。测试消息立即发送，不受静默期限制。协议模拟测试不等同于你的真实 MagicPush 账号/渠道已完成联调。

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
.\scripts\publish.ps1 -Tag 0.2.3
```

如果 Windows 没有 docker.exe，但已有 WSL 构建环境（本机为 `wusaqi-build`），可复用 Linux 内已登录的 Docker：

```powershell
.\scripts\publish.ps1 -Tag 0.2.3 -WslDistro wusaqi-build -DockerConfig /run/money-web-docker-auth
```

`-DockerConfig` 只传配置目录，不接收或输出 Token；登录时使用 `docker login --password-stdin`，不要把凭证放进项目或构建参数。`/run` 中的临时登录会随环境重启丢失，发布结束应清除。WSL 属于 Windows 管理员用户，受限账户看不到该发行版时需在该用户下执行。发布期间保持一个 WSL 终端打开，避免发行版空闲退出清除 `/run`。

脚本用 buildx 构建 linux/amd64 和 linux/arm64，推送 `stylle/money-web:0.2.3` 与 `latest`，随后核验 manifest。需要支持多架构的 builder / QEMU。

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

- [开发计划与已实现范围](docs/PLAN.md)
- [开发规范](docs/DEVELOPMENT.md)
- [数据源与自定义协议](docs/DATA_SOURCES.md)
- [安全说明](SECURITY.md)

本工具只聚合信息与提供辅助判断。价格、规则和 AI 都可能出错，任何交易由使用者自行决定。
