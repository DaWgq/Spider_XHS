import { useDialog, useMessage } from 'naive-ui'
import { api, errorText, type Row } from './api'

export function useDeletion() {
  const dialog = useDialog(), message = useMessage()
  function confirmDelete(url: string, title: string, content: string, after: () => void | Promise<void>, ids?: string[]) {
    dialog.warning({ title, content, positiveText: '确认删除', negativeText: '取消',
      positiveButtonProps: { type: 'error' },
      onPositiveClick: async () => {
        try {
          const result = ids ? await api.post(url, { ids }) : await api.delete(url)
          message.success(result.data.message || '已删除')
          await after()
        } catch(error) { message.error(errorText(error)); return false }
      }
    })
  }
  function removeTask(row: Row, after: () => void | Promise<void>) {
    confirmDelete(`/tasks/${encodeURIComponent(row.id)}`, '删除采集任务',
      '确认删除此任务及其日志？已采集的博主、笔记和评论会保留。待执行任务删除后不会再执行。此操作不可撤销。', after)
  }
  function removeData(entity: string, row: Row, after: () => void | Promise<void>) {
    const names: Record<string, string> = { bloggers: '博主', notes: '笔记', comments: '评论' }
    const effects: Record<string, string> = { bloggers: '仅删除博主记录，保留其笔记和评论。', notes: '同时删除这篇笔记的全部已采集评论。', comments: '同时删除按已知回复关系关联的回复。' }
    confirmDelete(`/data/${entity}/${encodeURIComponent(row.id)}`, `删除${names[entity]}`,
      `确认删除${row.title || row.nickname || names[entity]}？${effects[entity]}该数据在所有任务中的关联也会移除，此操作不可撤销。`, after)
  }
  function removeBatch(entity: string, ids: string[], after: () => void | Promise<void>) {
    if (!ids.length) return
    const label = entity === 'notes' ? '笔记' : '评论'
    const effect = entity === 'notes' ? '所选笔记的全部已采集评论也会删除。' : '按已知回复关系关联的回复也会删除。'
    confirmDelete(`/data/${entity}/batch-delete`, `批量删除${label}`,
      `确认删除选中的 ${ids.length} 条${label}？${effect}所有任务中的相关数据关联同时移除。此操作不可撤销。`, after, [...ids])
  }
  return { removeTask, removeData, removeBatch }
}
