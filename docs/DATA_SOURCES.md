# 数据源与接口协议

## 当前默认源

- 行情/搜索：Yahoo Finance 实验性非官方接口。并非获授权实时行情服务，不保证长期可用，可能限流、延迟、拒绝请求；部署者需自行确认使用条款和适用授权。
- 日线取最近六个月，OHLC 按上游 adjclose 比例调整，成交量保留上游值。用于观察指标，不是完整回测或券商成交核算数据。
- 分时图取最近交易日五分钟 K 线，仅展示取得的点，不填造缺失行情。
- RSS 默认使用 [美联储官方公告](https://www.federalreserve.gov/feeds/press_all.xml)，可在设置中添加自己有权使用的公开 RSS / Atom。
- [官方 RSS 说明](https://www.federalreserve.gov/feeds/feeds.htm)。存储标题、时间、链接、来源和关键词标签，不抓取新闻全文。

2026-10-28 的真网络结果见 `source-probe.json`：三市场各一标的、在线搜索、官方 RSS 均取得响应。A/H 报价约延迟 15 分钟，因此当时**不满足五分钟内报价要求，不会生成盘中操作建议或阈值推送**。这不是实时能力验收。

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
