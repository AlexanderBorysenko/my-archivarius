import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authTelegram, logout as apiLogout } from '../api'

interface UserInfo {
  id: string
  telegram_id: number
  username: string
  display_name: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const isAuthenticated = computed(() => !!localStorage.getItem('access_token'))

  async function loginWithTelegram(authData: Record<string, unknown>) {
    const { data } = await authTelegram(authData)
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    user.value = data.user
  }

  function logout() {
    apiLogout().catch(() => {})
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    user.value = null
  }

  function loadUserFromStorage() {
    const stored = localStorage.getItem('user_info')
    if (stored) {
      user.value = JSON.parse(stored)
    }
  }

  return { user, isAuthenticated, loginWithTelegram, logout, loadUserFromStorage }
})
