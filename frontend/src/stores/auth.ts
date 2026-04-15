import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { router } from '@/router'
import { api, clearTokens as clearStoredTokens, refreshAccessToken, setTokens as storeTokens } from '@/lib/api'
import type { TokenPair } from '@/lib/api'

interface User { id: number; username: string; email: string; display_name?: string; is_admin: boolean }

export const useAuthStore = defineStore('auth', () => {
  const accessToken  = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user         = ref<User | null>(null)
  const isLoading    = ref(false)

  const isAuthenticated = computed(() => !!accessToken.value)
  const isLoggedIn       = computed(() => !!accessToken.value)
  const loading          = isLoading

  function setTokens(tokens: TokenPair) {
    accessToken.value  = tokens.access_token
    refreshToken.value = tokens.refresh_token
    storeTokens(tokens.access_token, tokens.refresh_token)
  }

  function clearTokens() {
    accessToken.value  = null
    refreshToken.value = null
    user.value = null
    clearStoredTokens()
  }

  async function register(username: string, email: string, password: string) {
    const tokens = await api.post<Partial<TokenPair>>('/auth/register', { username, email, password })
    if (tokens.access_token && tokens.refresh_token) {
      setTokens(tokens as TokenPair)
    } else {
      await login(username, password)
      return
    }
    await fetchMe()
  }

  async function login(username: string, password: string) {
    const tokens = await api.post<TokenPair>('/auth/login', { username, password })
    setTokens(tokens)
    await fetchMe()
  }

  async function logout() {
    clearTokens()
    router.push('/login')
  }

  async function fetchMe() {
    try {
      user.value = await api.get<User>('/auth/me')
      _syncTokensFromStorage(true)
    } catch {
      user.value = null
    }
  }
  const loadMe = fetchMe

  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) { clearTokens(); return false }
    const token = await refreshAccessToken()
    _syncTokensFromStorage(true)
    if (token) {
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

  function _syncTokensFromStorage(preserveCurrent = false) {
    const storedAccess = localStorage.getItem('access_token')
    const storedRefresh = localStorage.getItem('refresh_token')
    accessToken.value = storedAccess ?? (preserveCurrent ? accessToken.value : null)
    refreshToken.value = storedRefresh ?? (preserveCurrent ? refreshToken.value : null)
  }

  return {
    accessToken, refreshToken, user, isLoading, loading, isAuthenticated, isLoggedIn,
    register, login, logout, fetchMe, loadMe, handleUnauthorized,
  }
})
