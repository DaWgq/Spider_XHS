import axios from 'axios'
export const api = axios.create({ baseURL: '/api', timeout: 120000 })
export function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (Array.isArray(detail)) return detail.map(x => `${x.loc?.slice(1).join('.')}: ${x.msg}`).join('；')
    return typeof detail === 'string' ? detail : error.code === 'ECONNABORTED' ? '请求超时，请稍后检查任务状态' : '无法连接后端，请检查服务是否启动'
  }
  return error instanceof Error ? error.message : '操作失败，请重试'
}
export function time(value?: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'medium', hour12: false }).format(new Date(value)) : '—'
}
export const kinds: Record<string, string> = { blogger: '博主采集', keyword: '关键词采集', notes: '指定笔记' }
export const states: Record<string, { label: string, type: 'default' | 'info' | 'success' | 'warning' | 'error' }> = {
  pending: { label: '待执行', type: 'default' }, running: { label: '运行中', type: 'info' }, stopping: { label: '停止中', type: 'warning' },
  stopped: { label: '已停止', type: 'default' }, completed: { label: '已完成', type: 'success' }, partial_failed: { label: '部分失败', type: 'warning' },
  failed: { label: '失败', type: 'error' }, interrupted: { label: '已中断', type: 'warning' }
}
export type Row = Record<string, any>
export async function download(params: Row) {
  let response
  try { response = await api.get('/export', { params, responseType: 'blob' }) }
  catch (error) {
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      try { error.response.data = JSON.parse(await error.response.data.text()) } catch { /* Keep the original HTTP error. */ }
    }
    throw error
  }
  const url = URL.createObjectURL(response.data)
  const a = document.createElement('a')
  let filename = `小红书-${params.entity || '任务数据'}.${params.fmt}`
  if (params.fmt === 'xlsx') {
    const disposition = String(response.headers['content-disposition'] || '')
    const encoded = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)
    const plain = disposition.match(/filename\s*=\s*"([^"]+)"/i)
    try { filename = encoded ? decodeURIComponent(encoded[1]) : plain?.[1] || filename } catch { /* Keep a usable fallback filename. */ }
  }
  a.href = url; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
