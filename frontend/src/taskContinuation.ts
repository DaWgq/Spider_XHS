import { useDialog, useMessage } from 'naive-ui'
import { api, errorText, type Row } from './api'

export function canContinueTask(row: Row) {
  return ['partial_failed', 'failed', 'stopped', 'interrupted', 'paused'].includes(row.status) && row.success_count < row.target_count
}

export function useTaskContinuation() {
  const dialog = useDialog(), message = useMessage()
  function continueTask(row: Row, after: () => void | Promise<void>) {
    const remaining = Math.max(0, row.target_count - row.success_count)
    dialog.info({ title: '继续采集剩余笔记',
      content: `已成功 ${row.success_count} / ${row.target_count} 篇。继续此任务，补采剩余 ${remaining} 篇；已成功笔记会跳过。列表会重新遍历以获取最新链接参数。若此前登录失效或受到访问限制，请先在登录配置页处理并检测。`,
      positiveText: '继续采集', negativeText: '取消',
      onPositiveClick: async () => {
        try { await api.post(`/tasks/${row.id}/resume`); message.success(`已重新排队，继续采集剩余 ${remaining} 篇`); await after() }
        catch(error) { message.error(errorText(error)); return false }
      }
    })
  }
  function pauseTask(row: Row, after: () => void | Promise<void>) {
    dialog.warning({ title: '暂停采集',
      content: '暂停后保留已完成进度，当前请求结束后不再发起新请求。之后可点击“继续采集”补采剩余笔记。',
      positiveText: '暂停采集', negativeText: '取消',
      onPositiveClick: async () => {
        try { await api.post(`/tasks/${row.id}/pause`); message.success('已提交暂停请求'); await after() }
        catch(error) { message.error(errorText(error)); return false }
      }
    })
  }
  return { continueTask, pauseTask }
}
