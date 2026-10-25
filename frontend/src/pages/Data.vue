<script setup lang="ts">
import { ref, reactive, computed, h, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NButton, NSpace, NInput, NSelect, NDataTable, NPagination, NAlert, NDrawer, NDrawerContent, NDescriptions, NDescriptionsItem, NTag, NEmpty, NDatePicker, useMessage, type DataTableColumns } from 'naive-ui'
import { api, errorText, time, download, type Row } from '../api'
import { useDeletion } from '../deleteActions'
const { removeData, removeBatch } = useDeletion()
const route = useRoute(), router = useRouter(), message = useMessage()
const entity = computed(() => String(route.params.entity)), names: Record<string,string> = { bloggers: '博主', notes: '笔记', comments: '评论' }
const rows = ref<Row[]>([]), total = ref(0), page = ref(1), size = ref(20), loading = ref(false), error = ref(''), exporting = ref(false)
const selected = ref<Row | null>(null), drawer = ref(false), comments = ref<Row[]>([]), commentPage = ref(1), commentTotal = ref(0), commentLoading = ref(false)
const dates = ref<[number,number] | null>(null)
const checkedKeys = ref<Array<string | number>>([])
const batchEnabled = computed(() => entity.value === 'notes' || entity.value === 'comments')
const filters = reactive({ q: '', user_id: '', note_id: '', keyword: '', note_type: '', level: null as number | null, task_id: '' })
let generation = 0
const typeOptions = [{ label: '全部笔记类型', value: '' }, { label: '图文', value: 'normal' }, { label: '视频', value: 'video' }]
const levelOptions = [{ label: '一级评论', value: 1 }, { label: '二级评论', value: 2 }]
function params() { return { ...filters, ...(dates.value ? { published_from: new Date(dates.value[0]).toISOString(), published_to: new Date(dates.value[1]).toISOString() } : {}) } }
async function load() { const current = ++generation; loading.value = true; error.value = ''; try { const response = await api.get(`/data/${entity.value}`, { params: { ...params(), page: page.value, page_size: size.value } }); if (current === generation) { rows.value = response.data.items; total.value = response.data.total } } catch(e) { if (current === generation) error.value = errorText(e) } finally { if (current === generation) loading.value = false } }
function search() { checkedKeys.value = []; page.value = 1; load() }
watch([page, size], () => { checkedKeys.value = [] }, { flush: 'sync' })
watch(() => route.fullPath, () => { Object.assign(filters, { q: '', user_id: String(route.query.user_id || ''), note_id: String(route.query.note_id || ''), keyword: '', note_type: '', level: null, task_id: String(route.query.task_id || '') }); dates.value = null; selected.value = null; drawer.value = false; rows.value = []; search() }, { immediate: true })
onUnmounted(() => { generation++ })
async function exportData(fmt: string) { exporting.value = true; try { await download({ ...params(), fmt, entity: entity.value }) } catch(e) { message.error(errorText(e)) } finally { exporting.value = false } }
async function loadComments() { if (!selected.value) return; commentLoading.value = true; try { const result = await api.get('/data/comments', { params: { note_id: selected.value.id, page: commentPage.value, page_size: 20 } }); comments.value = result.data.items; commentTotal.value = result.data.total } catch(e) { message.error(errorText(e)) } finally { commentLoading.value = false } }
async function open(row: Row) { selected.value = row; drawer.value = true; commentPage.value = 1; comments.value = []; if (entity.value === 'notes') await loadComments() }
function remove(row: Row) {
  removeData(entity.value, row, async () => {
    checkedKeys.value = []
    if (selected.value?.id === row.id) { drawer.value = false; selected.value = null }
    if (rows.value.length === 1 && page.value > 1) page.value--
    await load()
    const lastPage = Math.max(1, Math.ceil(total.value / size.value))
    if (page.value > lastPage) { page.value = lastPage; await load() }
  })
}
function bulkRemove() {
  const currentEntity = entity.value
  removeBatch(currentEntity, checkedKeys.value.map(String), async () => {
    if (entity.value !== currentEntity) return
    checkedKeys.value = []; drawer.value = false; selected.value = null
    await load()
    const lastPage = Math.max(1, Math.ceil(total.value / size.value))
    if (page.value > lastPage) { page.value = lastPage; await load() }
  })
}
const short = (title: string, key: string, width=150) => ({ title, key, width, ellipsis: { tooltip: true }, render: (row: Row) => row[key] ?? '—' })
const date = (title: string, key: string) => ({ title, key, width: 180, render: (row: Row) => time(row[key]) })
const columns = computed<DataTableColumns<Row>>(() => {
  const selection: DataTableColumns<Row> = [{ type: 'selection', fixed: 'left', width: 44 }]
  const action = { title: '操作', key: 'action', width: 150, fixed: 'right' as const, render: (row: Row) => h(NSpace, { size: 16 }, () => [h(NButton, { text: true, type: 'primary', onClick: () => open(row) }, () => '查看详情'), h(NButton, { text: true, type: 'error', onClick: () => remove(row) }, () => '删除')]) }
  if (entity.value === 'bloggers') return [short('昵称', 'nickname'), short('简介', 'description', 230), short('粉丝', 'fans', 100), short('关注', 'follows', 100), short('获赞与收藏', 'interaction', 120), date('最近采集时间', 'collected_at'), action]
  if (entity.value === 'notes') return [...selection, short('标题', 'title', 220), short('博主昵称', 'nickname'), short('正文', 'content', 220), short('类型', 'note_type', 90), short('点赞', 'liked_count', 80), short('收藏', 'collected_count', 80), short('平台评论数', 'platform_comment_count', 110), short('已采集评论', 'collected_comment_count', 110), date('发布时间', 'published_at'), date('采集时间', 'collected_at'), action]
  return [...selection, short('昵称', 'nickname'), short('内容', 'content', 280), short('层级', 'level', 80), short('点赞', 'liked_count', 90), date('发布时间', 'published_at'), date('采集时间', 'collected_at'), action]
})
function safeLink(value: unknown) { return typeof value === 'string' && /^https?:\/\//i.test(value) ? value : undefined }
const labels: Record<string,string> = { nickname: '昵称', title: '标题', content: '正文 / 评论内容', description: '简介', fans: '粉丝数', follows: '关注数', interaction: '获赞与收藏', note_type: '笔记类型', tags: '标签', published_at: '发布时间', liked_count: '点赞数', collected_count: '收藏数', platform_comment_count: '平台评论数', collected_comment_count: '已采集评论数', collected_at: '采集时间', level: '评论层级' }
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">COLLECTED DATA</div><h1>{{ names[entity] }}数据</h1><p>共 {{ total }} 条记录 · 未返回的字段显示为空 · 时间为北京时间</p></div><n-space><n-button :loading="exporting" @click="exportData('csv')">导出 CSV</n-button><n-button type="primary" :loading="exporting" @click="exportData('xlsx')">导出 Excel</n-button></n-space></div>
  <n-alert v-if="error" type="error" class="mb">{{ error }}</n-alert>
  <n-card :bordered="false"><div class="filters"><n-input v-model:value="filters.q" clearable placeholder="搜索昵称、标题或内容" @keyup.enter="search" /><n-input v-if="entity === 'notes'" v-model:value="filters.user_id" clearable placeholder="博主 ID" /><n-input v-if="entity === 'notes'" v-model:value="filters.keyword" clearable placeholder="采集来源关键词" /><n-select v-if="entity === 'notes'" v-model:value="filters.note_type" :options="typeOptions" /><n-date-picker v-if="entity === 'notes'" v-model:value="dates" type="datetimerange" clearable start-placeholder="发布开始时间" end-placeholder="发布结束时间" /><n-input v-if="entity === 'comments'" v-model:value="filters.note_id" clearable placeholder="笔记 ID" /><n-select v-if="entity === 'comments'" v-model:value="filters.level" :options="levelOptions" clearable placeholder="全部评论层级" /><n-input v-model:value="filters.task_id" clearable placeholder="关联任务 ID（可选）" /><n-button type="primary" @click="search">查询</n-button></div>
    <n-space v-if="batchEnabled" align="center" class="mb"><n-button type="error" :disabled="!checkedKeys.length || loading" @click="bulkRemove">批量删除（{{ checkedKeys.length }}）</n-button><span class="muted">已选 {{ checkedKeys.length }} 条 · 表头可全选当前页，翻页或查询会清空选择</span><n-button v-if="checkedKeys.length" text @click="checkedKeys = []">取消选择</n-button></n-space>
    <n-data-table v-model:checked-row-keys="checkedKeys" :data="rows" :columns="columns" :bordered="false" :loading="loading" :scroll-x="entity === 'bloggers' ? 970 : entity === 'notes' ? 1610 : 1050" :row-key="row => row.id" />
    <div class="table-footer"><small class="muted">Excel 包含博主、笔记、评论三个工作表；当前筛选作用于当前表，任务筛选作用于所有表。</small><n-pagination v-model:page="page" v-model:page-size="size" :item-count="total" show-size-picker :page-sizes="[20,50,100]" @update:page="load" @update:page-size="search" /></div>
  </n-card>
  <n-drawer v-model:show="drawer" :width="760" style="max-width:96vw"><n-drawer-content :title="`${names[entity]}详情`" closable><template v-if="selected"><n-descriptions :column="1" label-placement="top"><n-descriptions-item v-for="(label,key) in labels" v-show="key in selected" :key="key" :label="label"><span class="detail-text">{{ key.endsWith('_at') ? time(selected[key]) : Array.isArray(selected[key]) ? selected[key].join('、') : selected[key] ?? '—' }}</span></n-descriptions-item><n-descriptions-item v-if="selected.url" label="原始链接"><a :href="safeLink(selected.url)" target="_blank" rel="noopener noreferrer" class="wrap">{{ selected.url }}</a></n-descriptions-item></n-descriptions>
    <n-button v-if="entity === 'bloggers'" class="mt" @click="router.push({ path: '/data/notes', query: { user_id: selected.id } })">查看该博主的笔记 →</n-button>
    <template v-if="entity === 'notes'"><h3 class="mt">媒体链接</h3><n-empty v-if="!selected.media?.length" description="平台尚未返回媒体链接" /><div v-for="(media,i) in selected.media" :key="i" class="media-link"><n-tag size="small">{{ media.type === 'video' ? '视频' : '图片' }}</n-tag><a :href="safeLink(media.url)" target="_blank" rel="noopener noreferrer" class="wrap">{{ media.url }}</a></div><h3>已采集评论（{{ commentTotal }}）</h3><n-empty v-if="!comments.length && !commentLoading" description="暂无已采集评论" /><div v-for="comment in comments" :key="comment.id" class="comment-card"><div><strong>{{ comment.nickname || '未返回昵称' }}</strong><n-tag size="small" :bordered="false">{{ comment.level }} 级</n-tag></div><p class="detail-text">{{ comment.content }}</p><small class="muted">{{ time(comment.published_at) }} · 点赞 {{ comment.liked_count ?? '—' }}</small></div><n-pagination v-model:page="commentPage" :item-count="commentTotal" :page-size="20" class="mt" @update:page="loadComments" /></template>
  </template></n-drawer-content></n-drawer>
</template>
