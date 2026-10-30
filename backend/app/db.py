import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATA_DIR = Path(os.getenv('DATA_DIR', 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR / "invest.db"}')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {})
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def sqlite_options(connection, record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=30000')
        cursor.close()
Session = sessionmaker(engine, expire_on_commit=False)


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Config(Base):
    __tablename__ = 'config'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Watch(Base):
    __tablename__ = 'watchlist'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    market: Mapped[str] = mapped_column(String(8))
    exchange: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(20), default='stock')
    threshold: Mapped[float] = mapped_column(Float, default=5)
    quote: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Portfolio(Base):
    __tablename__ = 'portfolio'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)


class Article(Base):
    __tablename__ = 'articles'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(160))
    published: Mapped[str] = mapped_column(String(60))
    collected: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    tags: Mapped[list] = mapped_column(JSON, default=list)


class Event(Base):
    __tablename__ = 'events'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(240))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Delivery(Base):
    __tablename__ = 'deliveries'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(24), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(240), nullable=True)


class Lease(Base):
    __tablename__ = 'leases'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    until: Mapped[float] = mapped_column(Float, default=0)


class SourceHealth(Base):
    __tablename__ = 'source_health'
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


def initialize():
    Base.metadata.create_all(engine)
    with Session.begin() as s:
        if not s.get(Portfolio, 1):
            s.add(Portfolio(id=1, revision=0, payload={'positions': [], 'cash': 100, 'min_cash': 10, 'max_step': 1, 'risk': 'balanced', 'horizon': 'medium', 'updated_at': utcnow().isoformat()}))
        if not s.get(Lease, 'refresh'):
            s.add(Lease(key='refresh', until=0))
        if not s.get(Lease, 'worker'):
            s.add(Lease(key='worker', until=0))
