<script setup lang="ts">
import { h } from 'vue'
import { useRouter } from 'vue-router'
import { NDataTable, NTag, NButton, NSpace, type DataTableColumns } from 'naive-ui'
import { kinds, states, time, type Row } from '../api'
import { useDeletion } from '../deleteActions'
import { canContinueTask, useTaskContinuation } from '../taskContinuation'
defineProps<{ rows: Row[], loading?: boolean }>()
const emit = defineEmits<{ deleted: [] }>()
const { removeTask } = useDeletion()
const { continueTask } = useTaskContinuation()
const router = useRouter()
const columns: DataTableColumns<Row> = [
  { title: '任务 / 采集目标', key: 'target', minWidth: 240, ellipsis: { tooltip: true }, render: row => h('div', [h('div', { class: 'table-title' }, row.target), h('small', { class: 'muted' }, `${kinds[row.kind]} · ${row.id.slice(0, 12)}`)]) },
  { title: '状态', key: 'status', width: 110, render: row => h(NTag, { type: states[row.status]?.type, bordered: false, size: 'small' }, () => states[row.status]?.label || row.status) },
  { title: '已处理 / 目标', key: 'processed', width: 140, render: row => `${row.processed} / ${row.target_count}` },
  { title: '成功 / 失败', key: 'success_count', width: 120, render: row => `${row.success_count} / ${row.failure_count}` },
  { title: '创建时间（北京时间）', key: 'created_at', width: 190, render: row => time(row.created_at) },
  { title: '操作', key: 'action', width: 210, fixed: 'right', render: row => h(NSpace, { size: 16 }, () => [
    h(NButton, { text: true, type: 'primary', onClick: () => router.push(`/tasks/${row.id}`) }, () => '详情'),
    ...(canContinueTask(row) ? [h(NButton, { text: true, type: 'primary', onClick: () => continueTask(row, async () => { await router.push(`/tasks/${row.id}`) }) }, () => `继续采集（${row.target_count - row.success_count}）`)] : []),
    h(NButton, { text: true, type: 'error', disabled: ['running', 'stopping'].includes(row.status), title: ['running', 'stopping'].includes(row.status) ? '请先停止任务' : '删除任务，保留采集数据', onClick: () => removeTask(row, () => emit('deleted')) }, () => '删除')
  ]) }
]
</script>
<template><n-data-table :columns="columns" :data="rows" :loading="loading" :bordered="false" :scroll-x="880" :row-key="row => row.id" /></template>
