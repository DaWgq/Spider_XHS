<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NCard, NInput, NButton, NSpace, NAlert, NDescriptions, NDescriptionsItem, NTag, NModal, NSpin, useMessage, useDialog } from 'naive-ui'
import { api, errorText, time, type Row } from '../api'
import { useApp } from '../store'
const store = useApp(), message = useMessage(), cookie = ref(''), busy = ref(false), error = ref('')
const dialog = useDialog()
const qrShow = ref(false), qrBusy = ref(false), qr = ref<Row | null>(null), qrError = ref('')
const qrTerminal = computed(() => !!qr.value && ['succeeded', 'expired', 'failed', 'cancelled'].includes(qr.value.state))
let qrTimer: ReturnType<typeof setTimeout> | undefined, qrGeneration = 0
async function pollQr(generation: number) {
  if (!qr.value || generation !== qrGeneration || !qrShow.value) return
  try {
    const result = (await api.get(`/login/qrcode/${qr.value.id}`, { timeout: 10000 })).data
    if (generation !== qrGeneration || !qrShow.value) return
    qr.value = result
    if (result.state === 'succeeded') { await store.refreshLogin(); message.success('扫码登录成功，Cookie 已自动保存'); return }
    if (!qrTerminal.value) qrTimer = setTimeout(() => pollQr(generation), 1500)
  } catch(e) { if (generation === qrGeneration) { qrError.value = errorText(e); qr.value = qr.value ? { ...qr.value, state: 'failed' } : null } }
}
async function openQr() {
  clearTimeout(qrTimer)
  const generation = ++qrGeneration
  qrShow.value = true; qrBusy.value = true; qr.value = null; qrError.value = ''
  try {
    const result = (await api.post('/login/qrcode', undefined, { timeout: 10000 })).data
    if (generation !== qrGeneration || !qrShow.value) { api.delete(`/login/qrcode/${result.id}`).catch(() => {}); return }
    qr.value = result
    await pollQr(generation)
  } catch(e) { if (generation === qrGeneration) qrError.value = errorText(e) }
  finally { if (generation === qrGeneration) qrBusy.value = false }
}
function closeQr() {
  clearTimeout(qrTimer); qrGeneration++; qrShow.value = false; qrBusy.value = false
  if (qr.value && !qrTerminal.value) api.delete(`/login/qrcode/${qr.value.id}`).catch(() => {})
}
async function save() { busy.value = true; error.value = ''; try { store.login = (await api.put('/login', { cookie: cookie.value })).data; cookie.value = ''; message.success('Cookie 已保存，请检测登录状态') } catch(e) { error.value = errorText(e) } finally { busy.value = false } }
async function check() { busy.value = true; error.value = ''; try { store.login = (await api.post('/login/check')).data; message.success('登录有效') } catch(e) { error.value = errorText(e); await store.refreshLogin().catch(() => {}) } finally { busy.value = false } }
function clearCookie() {
  dialog.warning({ title: '清除现有 Cookie',
    content: '确认清除当前小红书账号的 Cookie、账号信息和登录状态？未完成的二维码登录也会取消。已采集数据会保留，之后可以扫码登录其他账号。',
    positiveText: '确认清除', negativeText: '取消', positiveButtonProps: { type: 'error' },
    onPositiveClick: async () => {
      busy.value = true; error.value = ''
      try {
        store.login = (await api.delete('/login')).data
        closeQr(); qr.value = null; qrError.value = ''; cookie.value = ''
        message.success('Cookie 已清除，可以扫码登录其他账号')
      } catch(e) { error.value = errorText(e); return false }
      finally { busy.value = false }
    }
  })
}
onMounted(() => store.refreshLogin().catch(e => { error.value = errorText(e) }))
onUnmounted(closeQr)
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">CONNECTION</div><h1>登录配置</h1><p>手机扫码自动登录，或手动配置小红书网页 Cookie。</p></div><n-button type="primary" size="large" :disabled="busy || qrBusy" @click="openQr">扫码登录小红书</n-button></div>
  <n-alert v-if="error" type="error" class="mb">{{ error }}</n-alert>
  <div class="form-grid"><n-card title="Cookie 登录" :bordered="false"><n-alert type="info" :bordered="false" class="mb">从已登录的小红书网页请求中复制完整 Cookie（包含 a1 与 web_session）。仅保存于后端本机数据库，不回显完整内容。</n-alert><label class="field-label">更新 Cookie</label><n-input v-model:value="cookie" type="password" show-password-on="click" autocomplete="off" placeholder="粘贴完整请求 Cookie" :disabled="busy" /><n-space class="mt"><n-button type="primary" :loading="busy" :disabled="!cookie.trim()" @click="save">保存 Cookie</n-button><n-button :loading="busy" :disabled="!store.login?.configured" @click="check">检测当前登录</n-button><n-button type="error" secondary :disabled="busy || !store.login?.configured" @click="clearCookie">清除 Cookie</n-button></n-space></n-card>
  <n-card title="配置状态" :bordered="false"><n-descriptions :column="1" label-placement="left"><n-descriptions-item label="Cookie">{{ store.login?.masked || '未配置' }}</n-descriptions-item><n-descriptions-item label="登录状态"><n-tag :bordered="false" :type="store.login?.status === 'valid' ? 'success' : 'warning'">{{ !store.login?.configured ? '未配置' : ({ valid: '登录有效', invalid: '检测失败，请更新 Cookie', unchecked: '尚未检测' } as Record<string,string>)[store.login?.status] || '未配置' }}</n-tag></n-descriptions-item><n-descriptions-item label="更新于">{{ time(store.login?.updated_at) }}</n-descriptions-item><n-descriptions-item label="用户 ID">{{ store.login?.account?.user_id || '—' }}</n-descriptions-item><n-descriptions-item label="昵称">{{ store.login?.account?.nickname || '—' }}</n-descriptions-item></n-descriptions></n-card></div>
  <n-modal :show="qrShow" preset="card" title="扫码登录小红书" style="width:440px;max-width:94vw" :mask-closable="false" @update:show="value => { if (!value) closeQr() }">
    <n-alert v-if="qrError || qr?.state === 'failed'" type="error" :bordered="false" class="mb">{{ qrError || qr?.message }}</n-alert>
    <div style="text-align:center;padding:12px 0">
      <img v-if="qr?.image && !qrTerminal" :src="qr.image" alt="小红书登录二维码" style="display:block;width:240px;max-width:100%;height:240px;margin:0 auto;background:#fff" />
      <n-spin v-else-if="qrBusy || (qr && !qrTerminal)" size="large" />
      <n-alert v-if="qr?.state === 'succeeded'" type="success" :bordered="false">登录成功，Cookie 已自动保存</n-alert>
      <p v-if="qr && qr.state !== 'failed'">{{ qr.message }}</p>
      <p v-if="qr?.stage_label && !qrTerminal" class="muted" style="font-size:12px">{{ qr.stage_label }} · 已用 {{ qr.elapsed_seconds ?? 0 }} 秒 · 本阶段剩余约 {{ qr.remaining_seconds ?? 0 }} 秒</p>
      <details v-if="qr?.request" class="muted" style="font-size:11px;text-align:left;overflow-wrap:anywhere;margin:12px 0"><summary>查看诊断信息</summary><p>阶段：{{ qr.stage_label }}<br>请求：{{ qr.request }}<br>已发起 {{ qr.request_count }} 次请求</p></details>
      <p v-if="qr?.state === 'succeeded'" class="muted">{{ qr.account?.nickname || '账号已连接' }}</p>
      <small class="muted">初始化最长 120 秒，二维码生成后最多等待 3 分钟。请使用小红书 App 扫码并确认。原 Cookie 在成功前不会被替换。</small>
    </div>
    <template #footer><n-space justify="end"><n-button @click="closeQr">{{ qr?.state === 'succeeded' ? '完成' : '关闭' }}</n-button><n-button v-if="qrError || (qrTerminal && qr?.state !== 'succeeded')" type="primary" :loading="qrBusy" @click="openQr">重新生成二维码</n-button></n-space></template>
  </n-modal>
</template>
