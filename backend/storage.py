from datetime import datetime, timezone
from sqlalchemy import select
from .db import session, Blogger, Note, Comment, TaskData, now

SENSITIVE = {'cookie', 'cookies', 'web_session', 'secure_session', 'a1', 'authorization', 'headers', 'id_token', 'mobile_token', 'mobile_token_security'}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k.lower() not in SENSITIVE}
    if isinstance(value, list):
        return [clean(x) for x in value]
    return value


def timestamp(value):
    if value is None:
        return None
    try:
        value = float(value)
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc).isoformat(timespec='milliseconds')
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def text(value):
    return str(value) if value is not None else None


def merge_raw(old, new):
    result = dict(old or {})
    for key, value in (new or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_raw(result[key], value)
        elif value is not None:
            result[key] = value
    return result


def save(model, values, task_id, entity):
    values = clean(values)
    with session() as db:
        obj = db.get(model, values['id'])
        if obj is None:
            obj = model(**values)
            db.add(obj)
        else:
            # Sparse list cards must not erase previously collected detail fields.
            for key, value in values.items():
                if value is not None and (key not in ('media', 'tags', 'raw') or value):
                    setattr(obj, key, merge_raw(obj.raw, value) if key == 'raw' else value)
        if not db.scalar(select(TaskData.id).where(TaskData.task_id == task_id, TaskData.entity == entity, TaskData.data_id == values['id'])):
            db.add(TaskData(task_id=task_id, entity=entity, data_id=values['id']))


def save_blogger(uid, data, task_id):
    basic = data.get('basic_info') or {}
    counts = {x.get('type'): text(x.get('count')) for x in data.get('interactions', [])}
    save(Blogger, dict(id=uid, nickname=basic.get('nickname'), description=basic.get('desc'),
         url=f'https://www.xiaohongshu.com/user/profile/{uid}', fans=counts.get('fans'),
         follows=counts.get('follows'), interaction=counts.get('interaction'), raw=data, collected_at=now()), task_id, 'bloggers')


def save_note(item, url, task_id):
    card = item.get('note_card') or item
    uid = (card.get('user') or {}).get('user_id')
    user = card.get('user') or {}
    nid = item.get('id') or item.get('note_id') or card.get('note_id')
    if not nid:
        raise ValueError('平台笔记缺少 ID')
    if uid:
        save(Blogger, dict(id=str(uid), nickname=user.get('nickname'), url=f'https://www.xiaohongshu.com/user/profile/{uid}', raw=user, collected_at=now()), task_id, 'bloggers')
    media = []
    for image in card.get('image_list') or []:
        image_url = image.get('url_default') or image.get('url') or next((x.get('url') for x in image.get('info_list', []) if x.get('url')), None)
        if image_url:
            media.append({'type': 'image', 'url': image_url})
    streams = ((card.get('video') or {}).get('media') or {}).get('stream') or {}
    for variants in streams.values():
        for stream in variants or []:
            link = stream.get('master_url') or stream.get('url') or next(iter(stream.get('backup_urls') or []), None)
            if link:
                media.append({'type': 'video', 'url': link})
    interact = card.get('interact_info') or {}
    save(Note, dict(id=str(nid), user_id=text(uid), nickname=user.get('nickname'), title=card.get('title', card.get('display_title')),
         content=card.get('desc'), note_type=card.get('type'), tags=[x['name'] for x in card.get('tag_list', []) if x.get('name')],
         published_at=timestamp(card.get('time')), liked_count=text(interact.get('liked_count')),
         collected_count=text(interact.get('collected_count')), platform_comment_count=text(interact.get('comment_count')),
         url=url, media=media, raw=item, collected_at=now()), task_id, 'notes')
    return str(nid)


def save_comment(data, nid, level, root, task_id):
    user = data.get('user_info') or {}
    parent = (data.get('target_comment') or {}).get('id') or data.get('parent_comment_id')
    if not data.get('id'):
        raise ValueError('平台评论缺少 ID')
    save(Comment, dict(id=str(data['id']), note_id=nid, root_id=root, parent_id=text(parent), level=level,
         user_id=text(user.get('user_id')), nickname=user.get('nickname'), content=data.get('content'),
         liked_count=text(data.get('like_count')), published_at=timestamp(data.get('create_time')), raw=data, collected_at=now()), task_id, 'comments')
