<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NAlert, NEmpty } from 'naive-ui'
import TaskTable from '../components/TaskTable.vue'
import { api, errorText, type Row } from '../api'
const router = useRouter(), stats = ref<Row>({}), loading = ref(true), error = ref('')
let timer: ReturnType<typeof setTimeout> | undefined, alive = true
const cards = [{ key: 'bloggers', label: '已采集博主', icon: '♙', color: 'rose' }, { key: 'notes', label: '已采集笔记', icon: '▧', color: 'blue' }, { key: 'comments', label: '已采集评论', icon: '☷', color: 'purple' }, { key: 'tasks', label: '采集任务总数', icon: '▤', color: 'green' }]
async function load() { try { stats.value = (await api.get('/stats')).data; error.value = '' } catch(e) { error.value = errorText(e) } finally { loading.value = false; if (alive) timer = setTimeout(load, 5000) } }
function refreshAfterDelete() { clearTimeout(timer); load() }
onMounted(load); onUnmounted(() => { alive = false; clearTimeout(timer) })
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">OVERVIEW</div><h1>数据概览</h1><p>从采集到整理，让每一条数据清晰可见。</p></div><n-button type="primary" size="large" @click="router.push('/create')">＋ 创建采集任务</n-button></div>
  <n-alert v-if="error" type="error" class="mb">{{ error }}</n-alert>
  <div class="stats-grid"><n-card v-for="card in cards" :key="card.key" :bordered="false"><div class="stat-header"><span>{{ card.label }}</span><span :class="['stat-icon', card.color]">{{ card.icon }}</span></div><div class="stat-number">{{ stats[card.key] ?? '—' }}</div><small class="muted">数据库累计记录</small></n-card></div>
  <div class="activity-banner"><div><span class="live-dot"></span><strong>{{ stats.running ?? 0 }} 个任务正在运行</strong><span class="muted">{{ stats.pending ?? 0 }} 个任务排队中 · 单任务顺序采集</span></div><n-button text @click="router.push('/tasks')">前往任务管理 →</n-button></div>
  <n-card :bordered="false" class="section-card"><template #header>最近采集任务</template><template #header-extra><n-button text type="primary" @click="router.push('/tasks')">查看全部 →</n-button></template><task-table :rows="stats.recent || []" :loading="loading" @deleted="refreshAfterDelete" @changed="refreshAfterDelete" /></n-card>
  <div class="quick-grid"><n-card :bordered="false" title="开始一次采集"><p class="muted">支持博主主页、关键词搜索和指定笔记。图片与视频以链接形式保存。</p><n-button @click="router.push('/create')">选择采集方式 →</n-button></n-card><n-card :bordered="false" title="连接你的登录状态"><p class="muted">使用有效的网页 Cookie，所有平台请求均由本机后端完成。</p><n-button @click="router.push('/login')">管理 Cookie →</n-button></n-card></div>
  <footer class="page-foot">数据来自本机 SQLite 数据库 · 页面每 5 秒刷新 · 所有时间按北京时间展示</footer>
</template>
