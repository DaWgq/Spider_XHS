<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NInput, NButton, NForm, NFormItem, NAlert } from 'naive-ui'
import AppIcon from '../components/AppIcon.vue'
import { api, errorText } from '../api'
import doge from '../assets/doge.png'
import dogecoin from '../assets/dogecoin.png'
const router = useRouter(), route = useRoute()
const form = reactive({ username: '', password: '' }), busy = ref(false), error = ref('')
async function submit() {
  error.value = ''
  if (!form.username.trim() || !form.password) { error.value = '请输入账号和密码'; return }
  busy.value = true
  try {
    await api.post('/auth/login', { username: form.username.trim(), password: form.password })
    form.password = ''
    const redirect = String(route.query.redirect || '/')
    await router.replace(redirect.startsWith('/') && !redirect.startsWith('//') && !redirect.startsWith('/signin') ? redirect : '/')
  } catch(e) { error.value = errorText(e) } finally { busy.value = false }
}
</script>
<template>
  <main class="signin-shell">
    <section class="signin-story">
      <div class="signin-brand"><img class="brand-symbol" :src="dogecoin" alt="Dogecoin" /><div>道格小红书采集<small>DATA COLLECTOR</small></div></div>
      <div class="signin-intro"><span class="signin-eyebrow">YOUR PERSONAL DATA WORKSPACE</span><h1>连接灵感，<br>让数据井然有序。</h1><p>从博主、笔记到评论，<br>在一个工作空间完成采集、整理与导出。</p>
      <div class="signin-art"><div class="doge-halo" aria-hidden="true"></div><img class="signin-doge" :src="doge" alt="金黄色 Doge 柴犬插画" /></div>
      <div class="signin-features"><span><AppIcon name="lock" />本机存储</span><span><AppIcon name="tasks" />任务管理</span><span><AppIcon name="notes" />数据导出</span></div></div>
      <small class="signin-copyright">小红书数据采集系统 · 本机工作空间</small>
    </section>
    <section class="signin-form-side"><div class="signin-form-box"><span class="signin-form-eyebrow">欢迎使用</span><h2>登录工作空间</h2><p>输入账号与密码，继续你的采集工作。</p><n-alert v-if="error" type="error" :bordered="false" class="mb" role="alert">{{ error }}</n-alert>
      <n-form label-placement="top" @submit.prevent="submit"><n-form-item label="账号" required><n-input v-model:value="form.username" size="large" placeholder="请输入账号" autocomplete="username" :disabled="busy"><template #prefix><AppIcon name="user" /></template></n-input></n-form-item><n-form-item label="密码" required><n-input v-model:value="form.password" size="large" type="password" show-password-on="click" placeholder="请输入密码" autocomplete="current-password" :disabled="busy"><template #prefix><AppIcon name="lock" /></template></n-input></n-form-item><n-button attr-type="submit" type="primary" size="large" block :loading="busy">登录<template #icon><AppIcon name="arrow" /></template></n-button></n-form>
      <div class="signin-note"><AppIcon name="lock" /><span>系统登录后，可在“登录配置”中管理小红书 Cookie。</span></div>
    </div><small class="signin-version">LOCAL WORKSPACE / V1.0</small></section>
  </main>
</template>
