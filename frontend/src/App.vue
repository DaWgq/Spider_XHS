<script setup lang="ts">
import { computed, h, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider, NDialogProvider, NLayout, NLayoutSider, NLayoutContent, NMenu, NTag, NButton, zhCN, dateZhCN } from 'naive-ui'
import { useApp } from './store'
import AppIcon from './components/AppIcon.vue'
import { api } from './api'
import dogecoin from './assets/dogecoin.png'
const route = useRoute(), router = useRouter(), store = useApp()
const theme = { common: { primaryColor: '#956708', primaryColorHover: '#805707', primaryColorPressed: '#684606', primaryColorSuppl: '#a47717', bodyColor: '#faf8f0', cardColor: '#ffffff', borderColor: '#e8e1d2', textColorBase: '#443c2b', textColor1: '#44351d', textColor2: '#70634e', textColor3: '#948875', borderRadius: '8px', fontFamily: 'Inter, "Microsoft YaHei", sans-serif' } }
const menu = [
  ['/', '数据概览', 'overview'], ['/create', '创建采集任务', 'create'], ['/tasks', '任务管理', 'tasks'],
  ['/data/bloggers', '博主数据', 'user'], ['/data/notes', '笔记数据', 'notes'], ['/data/comments', '评论数据', 'comments'], ['/login', '登录配置', 'settings']
].map(([key, label, icon]) => ({ key, label, icon: () => h(AppIcon, { name: icon }) }))
const selected = computed(() => route.path.startsWith('/tasks/') ? '/tasks' : route.path)
watch(() => route.meta.public, value => { if (!value && route.matched.length) store.refreshLogin().catch(() => {}) }, { immediate: true })
async function logout() { await api.post('/auth/logout'); store.login = null; await router.replace('/signin') }
</script>
<template>
  <n-config-provider :theme-overrides="theme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider><n-dialog-provider>
      <router-view v-if="route.meta.public" />
      <n-layout v-else has-sider class="shell">
        <n-layout-sider bordered :width="220" class="sidebar" collapse-mode="width" :collapsed-width="68" show-trigger="bar" :native-scrollbar="false">
          <div class="brand"><img class="brand-symbol" :src="dogecoin" alt="Dogecoin" /><div>道格小红书采集<span>DATA COLLECTOR</span></div></div>
          <div class="menu-caption">工作空间</div><n-menu :value="selected" :options="menu" @update:value="key => router.push(key)" />
          <div class="sidebar-foot"><span class="live-dot"></span> 本机单用户模式<small>数据保存在本机 · v1.0</small></div>
        </n-layout-sider>
        <n-layout>
          <header class="topbar"><span>工作空间 <span class="breadcrumb">/ {{ route.meta.title }}</span></span><div class="top-actions"><span class="timezone">北京时间 UTC+8</span><n-tag size="small" :type="store.login?.status === 'valid' ? 'success' : 'warning'" :bordered="false">{{ store.login?.status === 'valid' ? '小红书登录已验证' : store.login?.configured ? 'Cookie 待检测' : '未配置 Cookie' }}</n-tag><span class="avatar">D</span><span class="account-name">dawg</span><n-button text title="退出登录" aria-label="退出登录" @click="logout"><AppIcon name="logout" /></n-button></div></header>
          <n-layout-content class="workspace" :native-scrollbar="false"><router-view /></n-layout-content>
        </n-layout>
      </n-layout>
    </n-dialog-provider></n-message-provider>
  </n-config-provider>
</template>
