<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NButton, NSpace, NAlert, NSelect, NInput, NPagination, NTag, NDescriptions, NDescriptionsItem, NProgress, NEmpty, useMessage, useDialog } from 'naive-ui'
import TaskTable from '../components/TaskTable.vue'
import { useDeletion } from '../deleteActions'
import { canContinueTask, useTaskContinuation } from '../taskContinuation'
const { removeTask } = useDeletion()
const { continueTask } = useTaskContinuation()
import { api, errorText, states, kinds, time, download, type Row } from '../api'
const route = useRoute(), router = useRouter(), message = useMessage(), dialog = useDialog()
const rows = ref<Row[]>([]), task = ref<Row | null>(null), logs = ref<Row[]>([]), total = ref(0), page = ref(1), status = ref(''), q = ref(''), loading = ref(false), error = ref(''), busy = ref(false)
const id = computed(() => String(route.params.id || ''))
const options = [{ label: '全部状态', value: '' }, ...Object.entries(states).map(([value, x]) => ({ label: x.label, value }))]
let cursor = 0, timer: ReturnType<typeof setTimeout> | undefined, alive = true, generation = 0
async function load() {
  const current = generation; loading.value = true
  try {
    if (id.value) {
      const tid = id.value
      const [detail, result] = await Promise.all([api.get(`/tasks/${tid}`), api.get(`/tasks/${tid}/logs`, { params: { after: cursor } })])
      if (current !== generation) return
      task.value = detail.data; logs.value.push(...result.data.items); cursor = result.data.next_cursor
    } else {
      const result = await api.get('/tasks', { params: { page: page.value, status: status.value, q: q.value } })
      if (current !== generation) return
      rows.value = result.data.items; total.value = result.data.total
    }
    error.value = ''
  } catch(e) { if (current === generation) error.value = errorText(e) }
  finally { if (current === generation) { loading.value = false; if (alive) timer = setTimeout(load, 2500) } }
}
async function afterDelete() { if (rows.value.length === 1 && page.value > 1) page.value--; reload() }
function deleteCurrent() { if (task.value) removeTask(task.value, async () => { await router.push('/tasks') }) }
function reload() { clearTimeout(timer); generation++; load() }
watch(() => route.fullPath, () => { task.value = null; logs.value = []; cursor = 0; reload() }, { immediate: true })
onUnmounted(() => { alive = false; generation++; clearTimeout(timer) })
function stop() { dialog.warning({ title: '停止采集任务', content: '当前请求会在超时范围内结束，之后不再发起新请求。已保存的数据会保留。', positiveText: '停止任务', negativeText: '取消', onPositiveClick: async () => { try { await api.post(`/tasks/${id.value}/stop`); reload() } catch(e) { message.error(errorText(e)) } } }) }
async function retry() { busy.value = true; try { const result = await api.post(`/tasks/${id.value}/retry`); await router.push(`/tasks/${result.data.id}`) } catch(e) { message.error(errorText(e)) } finally { busy.value = false } }
async function exportTask() { busy.value = true; try { await download({ fmt: 'xlsx', entity: 'notes', task_id: id.value }) } catch(e) { message.error(errorText(e)) } finally { busy.value = false } }
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">COLLECTION TASKS</div><h1>{{ id ? '任务详情' : '任务管理' }}</h1><p>顺序执行、及时落库，随时查看采集进度。</p></div><n-button v-if="!id" type="primary" @click="router.push('/create')">＋ 创建任务</n-button><n-button v-else @click="router.push('/tasks')">返回任务列表</n-button></div>
  <n-alert v-if="error" type="error" class="mb">{{ error }}</n-alert>
  <template v-if="!id"><n-card :bordered="false"><n-space class="mb"><n-input v-model:value="q" clearable placeholder="搜索采集目标" @keyup.enter="page = 1; reload()" /><n-select v-model:value="status" :options="options" style="width:160px" @update:value="page = 1; reload()" /><n-button @click="page = 1; reload()">查询</n-button></n-space><task-table :rows="rows" :loading="loading" @deleted="afterDelete" /><n-pagination v-model:page="page" :item-count="total" :page-size="20" class="pagination" @update:page="reload" /></n-card></template>
  <template v-else-if="task"><n-card :bordered="false" class="mb"><template #header><n-space align="center">{{ kinds[task.kind] }}<n-tag :type="states[task.status]?.type" :bordered="false">{{ states[task.status]?.label }}</n-tag></n-space></template><template #header-extra><n-space><n-button v-if="canContinueTask(task)" type="primary" @click="continueTask(task, () => { reload() })">继续采集（{{ task.target_count - task.success_count }}）</n-button><n-button type="error" :disabled="['running','stopping'].includes(task.status)" @click="deleteCurrent">删除任务</n-button><n-button v-if="['pending','running','stopping'].includes(task.status)" type="warning" :disabled="task.status === 'stopping'" @click="stop">停止任务</n-button><n-button v-if="['failed','partial_failed'].includes(task.status)" :loading="busy" @click="retry">重试失败项</n-button><n-button :loading="busy" @click="exportTask">导出任务 Excel</n-button><n-button @click="router.push({ path: '/data/notes', query: { task_id: id } })">关联笔记</n-button></n-space></template>
    <n-descriptions :column="2" label-placement="top"><n-descriptions-item label="任务 ID">{{ task.id }}</n-descriptions-item><n-descriptions-item label="采集目标"><span class="wrap">{{ task.target }}</span></n-descriptions-item><n-descriptions-item label="创建时间">{{ time(task.created_at) }}</n-descriptions-item><n-descriptions-item label="开始 / 结束时间">{{ time(task.started_at) }} / {{ time(task.ended_at) }}</n-descriptions-item><n-descriptions-item label="成功 / 失败">{{ task.success_count }} / {{ task.failure_count }}</n-descriptions-item><n-descriptions-item label="已处理 / 目标">{{ task.processed }} / {{ task.target_count }}</n-descriptions-item></n-descriptions>
    <n-progress class="mt" type="line" :percentage="Math.min(100, Math.round(task.processed / Math.max(task.target_count,1) * 100))" :show-indicator="true" />
    <n-alert v-if="task.reason || task.last_error" class="mt" :type="['failed','partial_failed'].includes(task.status) ? 'error' : 'info'">{{ task.reason || task.last_error }}</n-alert>
    <details class="mt"><summary>查看采集参数</summary><pre>{{ JSON.stringify(task.params, null, 2) }}</pre></details>
    <div v-if="task.failures?.length" class="mt"><strong>失败项</strong><div v-for="(failure, i) in task.failures" :key="i" class="failure-row wrap">{{ failure.url || failure.target }}<br>{{ failure.error }}</div></div>
  </n-card><n-card title="增量日志" :bordered="false"><template #header-extra><small class="muted">每 2.5 秒刷新 · 北京时间</small></template><div class="log-panel"><n-empty v-if="!logs.length" description="暂无任务日志" /><div v-for="line in logs" :key="line.id" :class="['log-line', line.level]"><span>{{ time(line.time) }}</span><b>{{ line.level.toUpperCase() }}</b><span>{{ line.message }}</span></div></div></n-card></template>
</template>
