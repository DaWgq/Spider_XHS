import csv
import io
import json
import re
from sqlalchemy import select, func
from .db import Blogger, Note, Task
from urllib.parse import urlparse
from openpyxl import Workbook
from .queries import query_data, records, MODELS

# One authoritative mapping for Excel and CSV.
FIELDS = {
    'bloggers': [('id', '用户ID'), ('nickname', '昵称'), ('url', '主页链接'), ('description', '简介'),
                 ('fans', '粉丝数'), ('follows', '关注数'), ('interaction', '获赞与收藏数'), ('collected_at', '采集时间UTC')],
    'notes': [('id', '笔记ID'), ('user_id', '博主ID'), ('nickname', '博主昵称'), ('title', '标题'), ('content', '正文'),
              ('note_type', '笔记类型'), ('tags', '标签'), ('published_at', '发布时间UTC'), ('liked_count', '点赞数'),
              ('collected_count', '收藏数'), ('platform_comment_count', '平台评论数'), ('collected_comment_count', '已采集评论数'),
              ('url', '笔记链接'), ('media', '媒体链接'), ('collected_at', '采集时间UTC')],
    'comments': [('id', '评论ID'), ('note_id', '笔记ID'), ('root_id', '根评论ID'), ('parent_id', '父评论ID'),
                 ('level', '评论层级'), ('user_id', '评论用户ID'), ('nickname', '评论用户昵称'), ('content', '评论内容'),
                 ('liked_count', '点赞数'), ('published_at', '发布时间UTC'), ('collected_at', '采集时间UTC')],
}
SHEETS = {'bloggers': '博主', 'notes': '笔记', 'comments': '评论'}
# Internal IDs stay in storage and CSV for machine processing; Excel is for reading.
EXCEL_FIELDS = {name: [(key, label) for key, label in columns if key != 'id' and not key.endswith('_id')]
                for name, columns in FIELDS.items()}


def export_filename(db, fmt, entity, filters):
    if fmt != 'xlsx':
        return f'xhs-{entity}.{fmt}'
    data = query_data(entity, **filters).subquery()
    if entity == 'bloggers':
        stmt = select(data.c.id, data.c.nickname).select_from(data)
    elif entity == 'notes':
        stmt = select(func.coalesce(data.c.user_id, data.c.id), func.coalesce(Blogger.nickname, data.c.nickname)).select_from(data).outerjoin(Blogger, Blogger.id == data.c.user_id)
    else:
        # Name comment exports by the note's author, never by the commenter.
        stmt = select(func.coalesce(Note.user_id, data.c.note_id), func.coalesce(Blogger.nickname, Note.nickname)).select_from(data).outerjoin(Note, Note.id == data.c.note_id).outerjoin(Blogger, Blogger.id == Note.user_id)
    authors = db.execute(stmt.distinct().limit(2)).all()
    if len(authors) > 1:
        name = '多博主数据'
    elif authors:
        name = authors[0][1] or '未命名博主'
    else:
        uid = filters.get('user_id')
        task = db.get(Task, filters['task_id']) if filters.get('task_id') else None
        if task and task.kind == 'blogger':
            uid = urlparse(task.target).path.rstrip('/').split('/')[-1]
        blogger = db.get(Blogger, uid) if uid else None
        name = blogger.nickname if blogger and blogger.nickname else '小红书数据'
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', str(name)).strip(' .')[:80].rstrip(' .') or '小红书数据'
    if re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I):
        name = '_' + name
    return name + '.xlsx'


def safe_text(value):
    if value is None:
        return ''
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    value = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', str(value))
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        value = "'" + value
    return value


def csv_value(key, value):
    result = safe_text(value)
    # CSV carries no cell types: prefix identifiers for Excel's automatic import.
    if result and (key == 'id' or key.endswith('_id')) and not result.startswith("'"):
        result = "'" + result
    return result


def export_file(db, fmt, entity, filters):
    entities = list(FIELDS) if fmt == 'xlsx' else [entity]
    if fmt == 'xlsx':
        book = Workbook(write_only=True)
    else:
        output = io.StringIO(newline='')
        writer = csv.writer(output)
    for name in entities:
        columns = EXCEL_FIELDS[name] if fmt == 'xlsx' else FIELDS[name]
        # Current tab filters apply to that entity. Task filter applies to all sheets.
        current = filters if name == entity else {'task_id': filters.get('task_id', '')}
        stmt = query_data(name, **current).order_by(MODELS[name].collected_at.desc())
        rows = records(db, name, stmt)
        if fmt == 'xlsx':
            sheet = book.create_sheet(SHEETS[name])
            sheet.append([title for _, title in columns])
            from openpyxl.cell import WriteOnlyCell
            for row in rows:
                cells = []
                for key, _ in columns:
                    cell = WriteOnlyCell(sheet, value=safe_text(row.get(key))[:32767])
                    cell.data_type, cell.number_format = 's', '@'
                    cells.append(cell)
                sheet.append(cells)
        else:
            writer.writerow([title for _, title in columns])
            writer.writerows([[csv_value(key, row.get(key)) for key, _ in columns] for row in rows])
    if fmt == 'xlsx':
        output = io.BytesIO()
        book.save(output)
        return output.getvalue()
    return output.getvalue().encode('utf-8-sig')
