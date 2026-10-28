from contextlib import contextmanager
from datetime import datetime, timezone
import threading
from sqlalchemy import create_engine, event, String, Text, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATA_DIR


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class Base(DeclarativeBase):
    pass


class Login(Base):
    __tablename__ = 'login_config'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    cookie: Mapped[str] = mapped_column(Text, default='')
    updated_at: Mapped[str] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(default='unchecked')
    account: Mapped[dict] = mapped_column(JSON, default=dict)


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str]
    target: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default='pending', index=True)
    created_at: Mapped[str] = mapped_column(default=now)
    started_at: Mapped[str | None]
    ended_at: Mapped[str | None]
    processed: Mapped[int] = mapped_column(default=0)
    target_count: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)
    failure_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    failures: Mapped[list] = mapped_column(JSON, default=list)


class TaskCompletedNote(Base):
    __tablename__ = 'task_completed_notes'
    __table_args__ = (UniqueConstraint('task_id', 'note_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), index=True)
    note_id: Mapped[str]
    url: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[str] = mapped_column(default=now)


class TaskLog(Base):
    __tablename__ = 'task_logs'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), index=True)
    time: Mapped[str] = mapped_column(default=now)
    level: Mapped[str] = mapped_column(default='info')
    message: Mapped[str] = mapped_column(Text)


class Blogger(Base):
    __tablename__ = 'bloggers'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    nickname: Mapped[str | None]
    url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    fans: Mapped[str | None]
    follows: Mapped[str | None]
    interaction: Mapped[str | None]
    collected_at: Mapped[str] = mapped_column(default=now)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Note(Base):
    __tablename__ = 'notes'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(index=True)
    nickname: Mapped[str | None]
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    note_type: Mapped[str | None] = mapped_column(index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    published_at: Mapped[str | None] = mapped_column(index=True)
    liked_count: Mapped[str | None]
    collected_count: Mapped[str | None]
    platform_comment_count: Mapped[str | None]
    url: Mapped[str | None] = mapped_column(Text)
    media: Mapped[list] = mapped_column(JSON, default=list)
    collected_at: Mapped[str] = mapped_column(default=now)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    note_id: Mapped[str] = mapped_column(index=True)
    root_id: Mapped[str | None]
    parent_id: Mapped[str | None]
    level: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[str | None]
    nickname: Mapped[str | None]
    content: Mapped[str | None] = mapped_column(Text)
    liked_count: Mapped[str | None]
    published_at: Mapped[str | None]
    collected_at: Mapped[str] = mapped_column(default=now)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class TaskData(Base):
    __tablename__ = 'task_data'
    __table_args__ = (UniqueConstraint('task_id', 'entity', 'data_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), index=True)
    entity: Mapped[str]
    data_id: Mapped[str] = mapped_column(index=True)


engine = create_engine(f'sqlite:///{DATA_DIR / "collector.sqlite3"}', connect_args={'check_same_thread': False, 'timeout': 15})


@event.listens_for(engine, 'connect')
def configure_sqlite(connection, _):
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=15000')


Session = sessionmaker(engine, expire_on_commit=False)
DB_LOCK = threading.RLock()


@contextmanager
def session():
    with DB_LOCK, Session.begin() as db:
        yield db


def initialize():
    Base.metadata.create_all(engine)
    with session() as db:
        for task in db.query(Task).filter(Task.status.in_(['running', 'stopping', 'pausing'])).all():
            task.status, task.ended_at, task.reason = 'interrupted', now(), '程序退出或重启，任务已中断'
        if not db.get(Login, 1):
            db.add(Login(id=1))


def as_dict(row, raw=False):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if raw or c.name != 'raw'}
