# 观澜 · Invest Watch

行情、资讯与提醒，集中观察。

自部署的股票与加密现货观察平台，适合 NAS、本机电脑和小型 VPS。单容器包含网页、API、后台监控与 SQLite，无需额外数据库或 Redis。

## 核心功能

- A 股、港股、美股与加密现货自选，报价、来源状态和历史图表。
- RSS / Atom 资讯与关键词订阅；100 份持仓模型，不保存总资金金额。
- 确定性程序观察与可选 AI 分析，支持时效、现金与仓位校验。
- MagicPush / 自定义 Webhook，日报、异常提醒与投递记录。
- 密钥加密、数据备份、容器健康检查与监控状态。

**不自动交易。公开数据可能延迟或不可用；规则未经完整收益回测，不承诺盈利。**初始没有模拟行情或预设持仓，AI 与程序建议默认关闭。

## 最简 Docker Compose

支持 `linux/amd64` / `linux/arm64`。保存为 `compose.yaml`，替换口令；NAS Compose 页面也可直接粘贴。无需源码或 `.env`：

```yaml
name: money-web
services:
  money-web:
    image: stylle/money-web:0.2.4 # 固定版本；latest 随发布更新
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

```sh
docker compose up -d
```

打开 <http://localhost:8080>，输入 `APP_TOKEN`。需要局域网访问时，将端口改成 `"8080:8000"`，访问 `http://服务器IP:8080`。公网入口使用 HTTPS 并保护访问口令。

## 可选参数与详细指南

其余参数均按需配置，AI / Webhook 在网页中设置；不配置即可使用基础行情与资讯。

| 内容 | 文档 |
| --- | --- |
| 全部参数、代理、卷权限、旧版迁移 | [部署指南](docs/guide.md#docker-compose-单容器部署) · [Compose 文件](compose.yaml) |
| 搜索、自选、持仓与通知使用流程 | [首次使用](docs/guide.md#首次使用) |
| MagicPush、模板、签名、推送测试 | [Webhook 指南](docs/guide.md#webhook-与-magicpush) |
| 停机备份、恢复与密钥保管 | [备份与恢复](docs/guide.md#备份与恢复) |
| 数据源、延迟和授权边界 | [数据源说明](docs/DATA_SOURCES.md) |
| 计划、开发与验证范围 | [开发计划](docs/PLAN.md) · [开发规范](docs/DEVELOPMENT.md) · [验证说明](docs/VERIFICATION.md) |
| 网络限制与凭据保护 | [安全说明](SECURITY.md) |

## 更新与备份

先备份整个数据卷和加密密钥，再修改固定版本标签，执行：

```sh
docker compose pull
docker compose up -d
docker compose logs --tail=100
```

保留原项目名称与数据卷，**不要使用 `docker compose down -v`**。默认 SQLite 为单实例；旧 PostgreSQL 部署按指南单独备份数据库，不要直接转换。

## 使用范围

价格、资讯、程序规则和 AI 都可能出错。缺失或过期数据不会被包装成实时操作建议；任何交易由使用者自行决定。软件不构成投资建议。

[代码仓库](https://github.com/Stylle/money-web) · [Docker Hub](https://hub.docker.com/r/stylle/money-web)
