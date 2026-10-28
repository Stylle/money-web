# 数据源与接口协议

## 当前默认源（多源自动切换）

A 股优先腾讯，失败或延迟时尝试东方财富、Yahoo 主节点、Yahoo 备用节点；港美股使用腾讯和 Yahoo。主备 Yahoo 属于同一家服务，不作为两家独立机构计算。东方财富目前仅启用已验证的 A 股映射；港美股映射未通过完整时效验证。
端点不是厂商授权实时 API，不构成长期稳定性保证。失败会记录、连续网络异常后退避，恢复后自动重试。数据时间失效时暂停信号。
腾讯分钟端点返回的是价格线点，不捏造 OHLC；日线 OHLC 独立来自完整同源复权序列。美股 ETF 的腾讯历史可能不足，使用 Yahoo 整段补充并标注，绝不逐行拼接不同复权口径。

## 内置资讯来源

| 来源 | 接入方式 | 当前边界 |
|---|---|---|
| 财联社 | 公开移动页嵌入的数据 | 只取标题、原文链接、发布时点；页面变化报错 |
| 证券时报 | 公开首页标题索引 | 原文阅读；未知发布时间不参与 AI 今日证据 |
| 金十数据 | xnews 公开市场参考标题索引 | 不含付费/VIP 正文或旧免费快讯接口 |
| 华尔街见闻 | 网站公开快讯端点 | 标题或明确标为摘录的短句，不抓付费内容 |
| 雪球 | 来源目录 / 原站入口 | 当前返回访问验证页，需授权适配器，未启用抓取 |
| TradingView | 公开 RSS 观点流 | 是社区观点，不是经过核实的新闻事实，也不是行情数据 API |
| Seeking Alpha | 官方市场快讯 RSS | 标题、链接、日期；不读取付费文章正文 |

六个可获取的来源默认启用，保留用户 RSS，不覆盖原设置。不同来源并行刷新，单源失败不影响其他来源。重复标题去重；无日期标题按稳定 URL 标识去重，不能把抓取时间当作发布时间。
内置源按 5～10 分钟刷新、RSS 按 30 分钟；状态面板显示实际条数、最近尝试/成功时间和访问限制。公开网页变化或拒绝访问时不显示虚假的“健康”。

官方说明：[Seeking Alpha RSS 目录](https://about.seekingalpha.com/feeds)、[TradingView 不提供用户数据提取 API 的说明](https://www.tradingview.com/support/solutions/43000474413-i-need-access-to-your-api-in-order-to-get-data-or-indicator-values/)、[金十引用服务说明](https://south.jin10.com/example/websiteiframe.html)。
请按来源条款在个人空间内使用标题索引；付费、授权、登录或访问验证内容没有被绕过，也不能因为公开端点能访问就声称取得转载/分发授权。

## Yahoo 与外部 RSS

- 行情/搜索：Yahoo Finance 实验性非官方接口。并非获授权实时行情服务，不保证长期可用，可能限流、延迟、拒绝请求；部署者需自行确认使用条款和适用授权。
- 日线取最近六个月，OHLC 按上游 adjclose 比例调整，成交量保留上游值。用于观察指标，不是完整回测或券商成交核算数据。
- 分时图取最近交易日五分钟 K 线，仅展示取得的点，不填造缺失行情。
- RSS 默认使用 [美联储官方公告](https://www.federalreserve.gov/feeds/press_all.xml)，可在设置中添加自己有权使用的公开 RSS / Atom。
- [官方 RSS 说明](https://www.federalreserve.gov/feeds/feeds.htm)。存储标题、时间、链接、来源和关键词标签，不抓取新闻全文。

早期单源真网络结果见 `source-probe.json`。扩展后的逐来源结果见 `integration-check.json`，A 股新源的时效较好，港股仍可能延迟；**未达五分钟要求时不会生成盘中操作建议或阈值推送**。单次验证不是持续可用性或授权实时能力验收。

运行 `python scripts/probe_sources.py` 重新验证，结果不含 API Key，不写入用户自选和行情库。
本机使用 Fake-IP DNS，诊断时显式信任了既定公开域名；见部署文档的 TRUSTED_EGRESS_HOSTS。默认不放开私网。

## 自定义行情适配器

此处不是直接填任意厂商 API 地址；需要一个实现下列标准协议的适配服务。厂商凭证保存在服务端，按其授权与数据口径转换。
配置的 `provider_key` 以 `Authorization: Bearer ...` 请求头发送。

### GET /search?q=QQQ&market=US

```json
{"items":[{"symbol":"QQQ","name":"Invesco 纳斯达克100 ETF","market":"US","exchange":"NASDAQ","kind":"etf"}]}
```

市场为 CN/HK/US，kind 为 stock/etf；CN 使用 .SS/.SZ/.BJ 后缀，HK 使用 .HK。
A 股日历当前按沪市共享假日日历处理，深市、北交所特有临时安排需数据源或后续交易所级日历适配，不声称覆盖所有临时停市。

### GET /quote?symbol=QQQ&market=US

```json
{
  "price": 100.0,
  "previous_close": 99.0,
  "as_of": "2026-10-28T14:00:00+00:00",
  "currency": "USD",
  "delay_note": "说明来源、延迟与授权",
  "history": [
    {"time":"2026-10-27T13:30:00+00:00","open":98.0,"high":100.0,"low":97.0,"close":99.0,"volume":100000}
  ],
  "intraday": [
    {"time":"2026-10-28T13:30:00+00:00","open":99.0,"high":100.0,"low":98.5,"close":99.8,"volume":1000}
  ]
}
```

以上仅为字段示例，不是真实行情。

- `as_of` 必须带时区；`previous_close` 为该证券市场上一交易日收盘价，不是六个月区间首日价格。
- history 至少 65 根完整、连续的日线，覆盖上一交易日，不包含当日未完成日线。OHLC 必须采用一致复权口径。
- 两种 K 线时间必须递增、唯一；每组最多 2000 条；体积不超过 4MB。
- 适配服务遇到延迟、停牌、无授权时不能把“现在”写成行情时间；应保留真实报价时间或返回错误。
- 一份仓位不是一股/一手，不计算券商最小交易单位、手续费、税费和汇兑成本；实际交易需自行换算。

## AI 接口

只使用用户配置的兼容 API。支持 `/chat/completions` 的 `messages` / JSON object / `max_completion_tokens`，或 `/responses` 的 instructions/input / JSON object / max_output_tokens，均发送 `store:false`。
部分兼容服务不支持这些参数，会明确报错，不暗中切换接口或重复计费重试。连接测试需保存配置并开启 AI。
没有工具调用、自动联网或自动交易。新闻标题作为不可信证据，不允许其指示模型执行操作。
调用上限按 UTC 日计算，包含连接测试及失败请求；请求成功不等于建议通过约束校验。

接口依据：[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[Responses 迁移说明](https://developers.openai.com/api/docs/guides/migrate-to-responses)。


## 加密现货与资讯

CRYPTO 独立市场，支持 BASE-USDT / BASE-USD，展示计价币和交易所。USDT 默认 Binance 公开市场数据接口，失败尝试 Coinbase 的完全相同交易对；USD 直接 Coinbase，不用稳定币代替美元。自定义模式继续使用部署者的标准协议。当前选择腾讯/东方财富/Yahoo 只影响股票，内置加密市场独立路由。

- Binance：[官方公开行情域名说明](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)，仅无需密钥的现货目录、成交和 K 线。目录过滤 SPOT / TRADING 并不表示每个标的适合投资。
- Coinbase：[官方成交快照](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker)、[日线文档](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)。保留最近成交时间；低流动性交易对可能过期，缺少上一完整 UTC 日线时不给涨跌提醒。
- [CoinDesk RSS](https://www.coindesk.com/arc/outboundfeeds/rss)、[Cointelegraph RSS](https://cointelegraph.com/rss)，仅公开标题、时间和原文链接；已默认启用。加密频道还匹配其他来源中的比特币、以太坊、稳定币等关键词，不使用 AI 分类。

加密市场全年 7×24 小时，UTC 每日 00:00 为日线边界（北京时间 08:00）。涨跌幅是现价与上一完整 UTC 日线收盘之比，不使用滚动 24 小时统计。日报 UTC 00:30（北京时间 08:30），静默/去重/过期和五分钟时效约束仍生效。现货可以加入 100 份持仓，但不会自动为用户订阅或分配仓位。未接合约、杠杆、链上钱包、自动交易。
