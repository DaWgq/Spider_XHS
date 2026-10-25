import { defineStore } from 'pinia'
import { api, type Row } from './api'
export const useApp = defineStore('app', {
  state: () => ({ login: null as Row | null }),
  actions: { async refreshLogin() { this.login = (await api.get('/login')).data } }
})
