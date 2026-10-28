# 开发规范

## 边界

`backend/app/providers.py` 行情适配，`news.py` RSS，`strategy.py` 确定性规则，`markets.py` 交易时间，`ai.py` AI 及输出校验，`services.py` 任务/通知，`main.py` API。模块不能绕过统一网络校验读取外部 URL。
前端 React + TypeScript，主要页面由独立组件函数组织。只通过 `/api` 调用后端，密钥不进入 localStorage，访问口令只用 sessionStorage。

## 数据规则

- UTC 存储，市场时区调度，北京时间展示。严禁以服务器当地日期判断美股交易日。
- 份额校验使用 Decimal，最多两位小数，持仓及现金恰好合计 100。
- 持仓是手动快照，不能默默按照行情重估；保存必须带 revision，冲突返回 409。
- 价格必须是有限正数，OHLC/成交量校验，K 线须有序唯一。当前日线不得参与技术建议。
- 报价早于市场开盘、超过五分钟、未来超过 30 秒、数据源错误时，不给份额建议。
- 日线至少 65 根并覆盖上一交易日；未知或过期日历暂停信号，不用工作日猜测替代。
- 修改规则必须增加规则版本并说明行为变化。AI 不能覆盖现金/仓位限制或程序风险禁买。
- 不把技术指标打分包装成上涨概率，不宣称经过回测的收益，除非实际完成相应验证。

## 任务与通知

数据库租约避免同时执行同类任务。事件和通知 outbox 同事务插入；接收端应按 Idempotency-Key 去重。
网络发送最多只能做到“至少一次”：远端收到但本地未记录时可能重发，不宣称 exactly-once。
静默期间暂缓发送，超过 expires_at 丢弃。API 和 worker 使用同一数据库和加密密钥卷。

## 质量检查

```powershell
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm test
npm run build
```

测试应覆盖持仓守恒、并发修改、交易时区、节假日、AI 越界和失效、压缩响应解码、通知重试/过期/去重，避免仅复述实现。
依赖通过 requirements.lock / package-lock.json 固定；增加依赖后更新锁文件并检查 Linux 镜像兼容性。Python 锁中保留跨平台 colorama；无仅 Windows 可用的运行依赖。
在 Docker 中以非 root 运行，只写数据卷和 /tmp。任何真实密钥、数据库、日志、构建依赖目录不得提交或打入源码包。

v0.1 通过建表初始化数据库。后续修改已有表结构前必须引入版本化迁移，先备份，不允许用删库替代迁移。
