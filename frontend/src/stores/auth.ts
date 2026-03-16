import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { router } from '@/router'

interface User { id: number; username: string; email: string; display_name?: string; is_admin: boolean }
interface TokenPair { access_token: string; refresh_token: string }

const BASE = '/api/v1'

export const useAuthStore = defineStore('auth', () => {
  const accessToken  = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user         = ref<User | null>(null)
  const isLoading    = ref(false)

  const isAuthenticated = computed(() => !!accessToken.value)

  function setTokens(tokens: TokenPair) {
    accessToken.value  = tokens.access_token
    refreshToken.value = tokens.refresh_token
    localStorage.setItem('access_token',  tokens.access_token)
    localStorage.setItem('refresh_token', tokens.refresh_token)
  }

  function clearTokens() {
    accessToken.value  = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async function register(username: string, email: string, password: string) {
    const res = await fetch(`${BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password }),
    })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Registration failed')
    const tokens: TokenPair = await res.json()
    setTokens(tokens)
    await fetchMe()
  }

  async function login(username: string, password: string) {
    const res = await fetch(`${BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Invalid credentials')
    const tokens: TokenPair = await res.json()
    setTokens(tokens)
    await fetchMe()
  }

  async function logout() {
    clearTokens()
    router.push('/login')
  }

  async function fetchMe() {
    if (!accessToken.value) return
    const res = await fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken.value}` },
    })
    if (res.ok) {
      user.value = await res.json()
    } else if (res.status === 401) {
      await tryRefresh()
    }
  }

  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) { clearTokens(); return false }
    const res = await fetch(`${BASE}/auth/refresh?refresh_token=${refreshToken.value}`, {
      method: 'POST',
    })
    if (res.ok) {
      const tokens: TokenPair = await res.json()
      setTokens(tokens)
      return true
    }
    clearTokens()
    return false
  }

  // Called by the API client on 401
  async function handleUnauthorized(): Promise<string | null> {
    const refreshed = await tryRefresh()
    if (refreshed) return accessToken.value
    router.push('/login')
    return null
  }

  return {
    accessToken, refreshToken, user, isLoading, isAuthenticated,
    register, login, logout, fetchMe, handleUnauthorized,
  }
})
