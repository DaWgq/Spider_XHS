<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NRadioGroup, NRadioButton, NForm, NFormItem, NInput, NInputNumber, NSwitch, NSelect, NButton, NSpace, NAlert } from 'naive-ui'
import { api, errorText } from '../api'
const router = useRouter(), busy = ref(false), error = ref('')
const form = reactive({ kind: 'blogger', target: '', max_notes: 20, details: true, comments: false, max_comments: 20, replies: false, max_replies: 50, sort: 0, note_type: 0, interval_min: 3, interval_max: 5, retries: 2 })
const sortOptions = ['综合', '最新', '最多点赞', '最多评论', '最多收藏'].map((label, value) => ({ label, value }))
const typeOptions = ['不限', '视频笔记', '图文笔记'].map((label, value) => ({ label, value }))
function linkedKind(value: string): 'blogger' | 'notes' | null {
  try {
    const url = new URL(value.trim())
    if (url.protocol !== 'https:' || !['www.xiaohongshu.com', 'xiaohongshu.com'].includes(url.hostname) || url.username || url.port) return null
    if (/^\/user\/profile\/[a-f\d]{24}\/?$/i.test(url.pathname)) return 'blogger'
    if (/^\/(?:explore|discovery\/item)\/[a-f\d]{24}\/?$/i.test(url.pathname)) return 'notes'
  } catch { /* Keywords and incomplete URLs are left for normal input validation. */ }
  return null
}
const detectedKind = computed(() => linkedKind(form.target))
watch(() => form.target, value => {
  error.value = ''
  const kind = linkedKind(value)
  if (kind) form.kind = kind
})
watch(() => form.kind, () => { error.value = '' })
async function submit() { error.value = ''; if (!form.target.trim()) { error.value = '请填写采集目标'; return } const kind = linkedKind(form.target); if (kind) form.kind = kind; busy.value = true; try { const body = { ...form, target: form.target.trim(), urls: form.kind === 'notes' ? form.target.split('\n').map(x => x.trim()).filter(Boolean) : [] }; const task = (await api.post('/tasks', body)).data; await router.push(`/tasks/${task.id}`) } catch(e) { error.value = errorText(e) } finally { busy.value = false } }
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">NEW COLLECTION</div><h1>创建采集任务</h1><p>选择数据来源，设置采集范围。新任务会进入本机执行队列。</p></div></div>
  <n-alert v-if="error" type="error" class="mb">{{ error }}</n-alert>
  <n-card :bordered="false" class="create-card"><label class="field-label">采集方式</label><n-radio-group v-model:value="form.kind" name="collection-kind" size="large" aria-label="采集方式"><n-radio-button value="blogger">博主采集</n-radio-button><n-radio-button value="keyword">关键词采集</n-radio-button><n-radio-button value="notes">指定笔记</n-radio-button></n-radio-group>
  <p class="muted">直接粘贴博主主页或笔记链接，系统会自动识别采集方式。</p>
  <n-form label-placement="top" class="mt" @submit.prevent="submit">
    <n-form-item :label="form.kind === 'notes' ? '笔记链接（每行一个，最多 500 条）' : form.kind === 'blogger' ? '博主主页链接或用户 ID' : '搜索关键词'" required><n-input v-model:value="form.target" :type="form.kind === 'notes' ? 'textarea' : 'text'" :rows="5" :placeholder="form.kind === 'notes' ? 'https://www.xiaohongshu.com/explore/…?xsec_token=…\n请粘贴完整链接，保留签名参数' : form.kind === 'blogger' ? 'https://www.xiaohongshu.com/user/profile/… 或 24 位 ID' : '输入关键词'" /></n-form-item>
    <n-alert v-if="detectedKind" type="success" :bordered="false" class="mb">{{ detectedKind === 'blogger' ? '已识别为博主主页，将采集博主资料及其发布的笔记。' : '已识别为笔记链接，将采集该篇笔记。' }}链接中的 xsec_token 等参数会保留。</n-alert>
    <div class="fields-grid"><n-form-item v-if="form.kind !== 'notes'" label="最多采集笔记数"><n-input-number v-model:value="form.max_notes" :min="1" :max="1000" /></n-form-item><n-form-item v-if="form.kind === 'keyword'" label="排序方式"><n-select v-model:value="form.sort" :options="sortOptions" /></n-form-item><n-form-item v-if="form.kind === 'keyword'" label="笔记类型"><n-select v-model:value="form.note_type" :options="typeOptions" /></n-form-item></div>
    <div class="option-row"><div><strong>采集笔记详情</strong><p>保存正文、标签与媒体链接</p></div><n-switch v-model:value="form.details" :disabled="form.kind === 'notes'" /></div>
    <div class="option-row"><div><strong>采集评论</strong><p>区分平台评论总数与本机实际采集数</p></div><n-switch v-model:value="form.comments" /></div>
    <div v-if="form.comments" class="fields-grid mt"><n-form-item label="每篇最多一级评论数"><n-input-number v-model:value="form.max_comments" :min="0" :max="1000" /></n-form-item><n-form-item label="采集二级评论"><n-switch v-model:value="form.replies" /></n-form-item><n-form-item v-if="form.replies" label="每篇最多二级评论总数"><n-input-number v-model:value="form.max_replies" :min="0" :max="2000" /></n-form-item></div>
    <div class="fields-grid mt"><n-form-item label="随机间隔下限（秒）"><n-input-number v-model:value="form.interval_min" :min="0.5" :max="59.5" :step="0.5" /></n-form-item><n-form-item label="随机间隔上限（秒）"><n-input-number v-model:value="form.interval_max" :min="1" :max="60" :step="0.5" /></n-form-item><n-form-item label="网络失败最多重试次数"><n-input-number v-model:value="form.retries" :min="0" :max="3" /></n-form-item></div>
    <p class="muted">每次请求单独随机取值，默认在上次请求结束后等待 3～5 秒；停止任务时可立即中断等待。</p>
    <n-alert type="info" :bordered="false">图片与视频仅保存链接，不下载文件。达到数量上限、平台无下一页或收到停止指令时结束；实际数量可能少于目标数量。遇到登录失效或访问限制立即停止。</n-alert>
    <n-space class="mt"><n-button type="primary" size="large" :loading="busy" @click="submit">创建并查看任务 →</n-button><n-button size="large" @click="router.push('/tasks')">查看已有任务</n-button></n-space>
  </n-form></n-card>
</template>
