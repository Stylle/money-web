from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class WatchInput(StrictModel):
    symbol: str = Field(min_length=1, max_length=30, pattern=r'^[A-Z0-9.^=-]+$')
    name: str = Field(min_length=1, max_length=160)
    market: Literal['CN', 'HK', 'US']
    exchange: str = Field(default='', max_length=30)
    kind: Literal['stock', 'etf'] = 'stock'
    threshold: float = Field(default=5, ge=0.5, le=50)

    @model_validator(mode='after')
    def symbol_market(self):
        if self.market == 'CN' and not self.symbol.endswith(('.SS', '.SZ', '.BJ')):
            raise ValueError('A 股代码需要 .SS、.SZ 或 .BJ 后缀')
        if self.market == 'HK' and not self.symbol.endswith('.HK'):
            raise ValueError('港股代码需要 .HK 后缀')
        if self.market == 'US' and self.symbol.endswith(('.SS', '.SZ', '.BJ', '.HK')):
            raise ValueError('代码与市场不匹配')
        return self


class Position(StrictModel):
    watch_id: str = Field(max_length=100)
    shares: Decimal = Field(ge=0, le=100, decimal_places=2)
    target: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    cap: Decimal = Field(default=40, ge=0, le=100, decimal_places=2)


class PortfolioInput(StrictModel):
    revision: int = Field(ge=0)
    positions: list[Position] = Field(max_length=200)
    cash: Decimal = Field(ge=0, le=100, decimal_places=2)
    min_cash: Decimal = Field(default=10, ge=0, le=100, decimal_places=2)
    max_step: Decimal = Field(default=1, gt=0, le=5, decimal_places=2)
    risk: Literal['conservative', 'balanced', 'growth'] = 'balanced'
    horizon: Literal['short', 'medium', 'long'] = 'medium'

    @model_validator(mode='after')
    def validate_total(self):
        if sum((p.shares for p in self.positions), Decimal(0)) + self.cash != 100:
            raise ValueError('持仓和现金必须恰好合计 100 份')
        if len({p.watch_id for p in self.positions}) != len(self.positions):
            raise ValueError('不能重复配置同一标的')
        if any(p.shares > p.cap for p in self.positions):
            raise ValueError('当前份额不能超过设置的仓位上限；请先提高上限')
        return self


class Feed(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2000)


class SettingsInput(StrictModel):
    ai_enabled: bool | None = None
    strategy_enabled: bool | None = None
    ai_base_url: str | None = Field(default=None, max_length=2000)
    ai_key: str | None = Field(default=None, max_length=1000)
    ai_model: str | None = Field(default=None, max_length=100)
    ai_interface: Literal['chat', 'responses'] | None = None
    ai_daily_limit: int | None = Field(default=None, ge=1, le=100)
    webhook_url: str | None = Field(default=None, max_length=2000)
    webhook_secret: str | None = Field(default=None, max_length=1000)
    webhook_authorization: str | None = Field(default=None, max_length=1000)
    notify_daily: bool | None = None
    notify_alerts: bool | None = None
    markets: list[Literal['CN', 'HK', 'US']] | None = Field(default=None, max_length=3)
    quiet_start: str | None = Field(default=None, pattern=r'^$|^([01][0-9]|2[0-3]):[0-5][0-9]$')
    quiet_end: str | None = Field(default=None, pattern=r'^$|^([01][0-9]|2[0-3]):[0-5][0-9]$')
    keywords: list[str] | None = Field(default=None, max_length=50)
    feeds: list[Feed] | None = Field(default=None, max_length=20)
    provider: Literal['yahoo', 'custom'] | None = None
    provider_base_url: str | None = Field(default=None, max_length=2000)
    provider_key: str | None = Field(default=None, max_length=1000)
