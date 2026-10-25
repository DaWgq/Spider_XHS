import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Login from './pages/Login.vue'
import Create from './pages/Create.vue'
import Tasks from './pages/Tasks.vue'
import Data from './pages/Data.vue'
import SignIn from './pages/SignIn.vue'
import { api } from './api'
import './style.css'
import './signin.css'

const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/signin', component: SignIn, meta: { title: '系统登录', public: true } },
  { path: '/', component: Dashboard, meta: { title: '数据概览' } },
  { path: '/login', component: Login, meta: { title: '登录配置' } },
  { path: '/create', component: Create, meta: { title: '创建采集任务' } },
  { path: '/tasks', component: Tasks, meta: { title: '任务管理' } },
  { path: '/tasks/:id', component: Tasks, meta: { title: '任务详情' } },
  { path: '/data/:entity(bloggers|notes|comments)', component: Data, meta: { title: '采集数据' } },
  { path: '/:pathMatch(.*)*', redirect: '/' }
] })
router.beforeEach(async to => {
  let authenticated = false
  try { authenticated = (await api.get('/auth/session', { timeout: 5000 })).data.authenticated } catch { /* Login remains reachable when the backend is unavailable. */ }
  if (!authenticated && !to.meta.public) return { path: '/signin', query: { redirect: to.fullPath } }
  if (authenticated && to.path === '/signin') return '/'
})
api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && !String(error.config?.url || '').startsWith('/auth/') && router.currentRoute.value.path !== '/signin') {
    router.replace({ path: '/signin', query: { redirect: router.currentRoute.value.fullPath } })
  }
  return Promise.reject(error)
})
createApp(App).use(createPinia()).use(router).mount('#app')
