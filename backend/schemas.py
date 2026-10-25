import re
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator, ConfigDict


def validate_target(value, profile=False):
    if profile and re.fullmatch(r'[a-fA-F0-9]{24}', value):
        return value
    parsed = urlparse(value)
    if not profile and parsed.hostname in ('www.xiaohongshu.com', 'xiaohongshu.com') and re.fullmatch(r'/user/profile/[a-fA-F0-9]{24}/?', parsed.path):
        raise ValueError('这是博主主页链接，请选择“博主采集”；“指定笔记”仅支持笔记链接')
    pattern = r'/user/profile/[a-fA-F0-9]{24}/?' if profile else r'/(?:explore|discovery/item)/[a-fA-F0-9]{24}/?'
    if parsed.scheme != 'https' or parsed.hostname not in ('www.xiaohongshu.com', 'xiaohongshu.com') or not re.fullmatch(pattern, parsed.path) or parsed.username or parsed.port:
        raise ValueError('请输入完整的小红书主页/笔记 HTTPS 链接（保留 xsec_token），不支持短链接；博主也可填写 24 位用户 ID')
    return value


class CookieInput(BaseModel):
    cookie: SecretStr = Field(min_length=1, max_length=30000)

    @field_validator('cookie')
    @classmethod
    def cookie_fields(cls, secret):
        value = secret.get_secret_value()
        fields = dict(part.strip().split('=', 1) for part in value.split(';') if '=' in part)
        if not fields.get('a1') or not fields.get('web_session') or '\r' in value or '\n' in value:
            raise ValueError('Cookie 必须含 a1 和 web_session，且不能包含换行')
        return secret


class BatchDeleteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator('ids')
    @classmethod
    def normalized_ids(cls, values):
        values = [value.strip() for value in values]
        if any(not value or len(value) > 128 for value in values):
            raise ValueError('记录 ID 不能为空且不能超过 128 个字符')
        return list(dict.fromkeys(values))


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['blogger', 'keyword', 'notes']
    target: str = Field(min_length=1, max_length=1000000)
    urls: list[str] = Field(default_factory=list, max_length=500)
    max_notes: int = Field(default=20, ge=1, le=1000)
    details: bool = True
    comments: bool = False
    max_comments: int = Field(default=20, ge=0, le=1000)
    replies: bool = False
    max_replies: int = Field(default=50, ge=0, le=2000)
    sort: int = Field(default=0, ge=0, le=4)
    note_type: int = Field(default=0, ge=0, le=2)
    interval_min: float = Field(default=3, ge=0.5, le=60)
    interval_max: float = Field(default=5, ge=0.5, le=60)
    # Accept saved legacy parameters on retry, but never re-export a fixed interval.
    interval: float | None = Field(default=None, ge=0.5, le=60, exclude=True)
    retries: int = Field(default=2, ge=0, le=3)

    @model_validator(mode='after')
    def targets(self):
        if self.interval_min >= self.interval_max:
            raise ValueError('请求间隔上限必须大于下限，使用随机间隔')
        self.target = self.target.strip()
        if not self.target:
            raise ValueError('采集目标不能为空')
        if self.kind == 'keyword' and len(self.target) > 200:
            raise ValueError('关键词不能超过 200 个字符')
        if self.kind == 'blogger':
            validate_target(self.target, True)
        if self.kind == 'notes':
            self.urls = list(dict.fromkeys(x.strip() for x in (self.urls or self.target.splitlines()) if x.strip()))
            if not 1 <= len(self.urls) <= 500:
                raise ValueError('笔记链接数量须为 1–500')
            for url in self.urls:
                if len(url) > 4000:
                    raise ValueError('单条笔记链接不能超过 4000 个字符')
                validate_target(url)
            self.target = self.urls[0] if len(self.urls) == 1 else f'{len(self.urls)} 条指定笔记（首条：{self.urls[0]}）'
            self.max_notes = len(self.urls)
            self.details = True
        return self
