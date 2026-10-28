# 本次验证记录

日期：2026-10-28，Asia/Shanghai。

## 已执行

- Python 3.12 本地依赖安装，版本写入 backend/requirements.lock。
- 后端 43 项测试通过：份额守恒/小数/越界、并发 revision、交易日/午休/节假日/半日市/夏令时、日报窗口、报价时效、完整日线日期、现金预算共享、AI 关闭时不调用与份额/引用校验、设置加密与掩码、提醒去重/分档/过期/重试、压缩响应处理、认证、跨站写入阻止、RSS 链接与去重。
- 依赖自身产生 35 条弃用警告（主要为 exchange_calendars / pandas，另有 Starlette TestClient 提示）；当前测试通过，后续依赖升级需继续验证。
- 前端 TypeScript 检查及 Vite production build 通过；npm 安装审计 0 个已知漏洞（本次安装时）。
- 本地 Uvicorn 启动成功，/api/health 返回 200，实际浏览器打开仪表盘。
- 浏览器实际执行：US 搜索 QQQ、添加订阅、首页计数更新、打开持仓页、将现金临时改成 99 后保存禁用、恢复 100、打开 AI/Webhook/RSS 设置。未输入真实密钥或资产金额，测试订阅在交付前移除。
- 真网络验证三市场报价和历史/分时、在线搜索、官方 RSS 成功，详见 source-probe.json。已发现 A/H 报价延迟，未宣称实时。
- 通过固定公开域名的 Fake-IP 例外完成网络验证；默认的私网限制保留。

## 尚未执行

- Docker 镜像构建、Compose 启动、PostgreSQL 容器集成、amd64/arm64 运行验证、Docker Hub 推送：当前本机没有 Docker，用户要求先写代码。
- GitHub 远端推送和 Actions 执行：未指定远端，CLI 的现有 GitHub 登录无效；当前只做本地 Git 提交。
- 真实 AI 模型调用、真实 Webhook 接收端联调：没有配置用户密钥和目标地址。
- PostgreSQL 备份恢复实操、连续交易日通知验收、策略收益回测：需部署环境和运行时间。

容器和远端发布文件已准备，但不能用静态 YAML 检查代替容器运行成功。当前适合作为个人版基础版本进行部署验证，尚不应当宣称完成生产验收。
