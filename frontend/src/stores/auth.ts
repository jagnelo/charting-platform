import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { router } from '@/router'
import { assertAuthSessionCurrent, beginAuthSessionBoundary, captureAuthSession, onAuthSessionBoundary } from '@/lib/authSession'
import { api, clearTokens as clearStoredTokens, refreshAccessToken, setTokens as storeTokens } from '@/lib/api'
import type { TokenPair } from '@/lib/api'

interface User { id: number; username: string; email: string; display_name?: string; is_admin: boolean }

const SESSION_CHANNEL_NAME = 'charting-platform-session'
const SESSION_LOGOUT_KEY = `${SESSION_CHANNEL_NAME}:logout`
let installedStorageLogoutHandler: ((event: StorageEvent) => void) | null = null
let sessionChannel: BroadcastChannel | null = null
let installedBoundaryCleanup: (() => void) | null = null

function accessTokenSubject(token: string | null): string | null {
  if (!token) return null
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as { sub?: unknown }
    return typeof decoded.sub === 'string' || typeof decoded.sub === 'number' ? String(decoded.sub) : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken  = ref<string | null>(localStorage.getItem('access_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user         = ref<User | null>(null)
  const isLoading    = ref(false)
  const sessionSubject = ref(accessTokenSubject(accessToken.value))

  const isAuthenticated = computed(() => !!accessToken.value)
  const isLoggedIn       = computed(() => !!accessToken.value)
  const loading          = isLoading

  function applyRemoteLogout() {
    clearTokens()
    if (router.currentRoute.value.path !== '/login') void router.push('/login')
  }

  function applyRemoteTokenChange() {
    const storedAccess = localStorage.getItem('access_token')
    const nextSubject = accessTokenSubject(storedAccess)
    if (!storedAccess) {
      if (!accessToken.value && !user.value) return
      beginAuthSessionBoundary()
      if (router.currentRoute.value.path !== '/login') void router.push('/login')
      return
    }

    const currentSubject = sessionSubject.value ?? accessTokenSubject(accessToken.value)
    if (storedAccess === accessToken.value || (nextSubject && currentSubject === nextSubject)) {
      _syncTokensFromStorage()
      if (nextSubject) sessionSubject.value = nextSubject
      return
    }

    // A different JWT subject means another same-origin window authenticated as
    // another user. Cancel the old private requests before the next /auth/me.
    // Unknown/opaque tokens fail closed; the platform's access tokens carry a
    // stable JWT `sub`, so same-user refreshes take the branch above.
    beginAuthSessionBoundary()
    _syncTokensFromStorage()
    user.value = null
    sessionSubject.value = nextSubject
    void fetchMe().then(() => {
      if (user.value && router.currentRoute.value.path === '/login') void router.push('/chart')
    })
  }

  // Browser pop-outs are separate Vue/Pinia instances. BroadcastChannel is the
  // primary same-origin transport and storage is the portable fallback.
  function installSessionSync() {
    if (typeof window === 'undefined') return
    if (installedStorageLogoutHandler) window.removeEventListener('storage', installedStorageLogoutHandler)
    installedStorageLogoutHandler = event => {
      if (event.key === SESSION_LOGOUT_KEY && event.newValue) applyRemoteLogout()
      else if (event.key === 'access_token') applyRemoteTokenChange()
    }
    window.addEventListener('storage', installedStorageLogoutHandler)
    if (typeof BroadcastChannel !== 'undefined') {
      sessionChannel?.close()
      sessionChannel = new BroadcastChannel(SESSION_CHANNEL_NAME)
      sessionChannel.addEventListener('message', event => {
        if (event.data?.type === 'logout') applyRemoteLogout()
        else if (event.data?.type === 'session-token-changed') applyRemoteTokenChange()
      })
    }
    installedBoundaryCleanup?.()
    installedBoundaryCleanup = onAuthSessionBoundary(() => {
      _syncTokensFromStorage()
      sessionSubject.value = accessTokenSubject(accessToken.value)
      user.value = null
      // API-owned refresh can discover expiry outside handleUnauthorized().
      // Settle the current view at the public login route as part of the same
      // boundary, rather than leaving an unauthenticated private shell mounted.
      if (!accessToken.value && router.currentRoute.value.path !== '/login') {
        void router.replace('/login')
      }
    })
  }

  function publishLogout() {
    sessionChannel?.postMessage({ type: 'logout' })
    try {
      localStorage.setItem(SESSION_LOGOUT_KEY, `${Date.now()}-${Math.random().toString(36).slice(2)}`)
    } catch {
      // BroadcastChannel remains sufficient where storage is unavailable.
    }
  }

  installSessionSync()

  function setTokens(tokens: TokenPair) {
    accessToken.value  = tokens.access_token
    refreshToken.value = tokens.refresh_token
    sessionSubject.value = accessTokenSubject(tokens.access_token)
    storeTokens(tokens.access_token, tokens.refresh_token)
    sessionChannel?.postMessage({ type: 'session-token-changed' })
  }

  function clearTokens() {
    clearStoredTokens()
    beginAuthSessionBoundary()
    accessToken.value  = null
    refreshToken.value = null
    user.value = null
  }

  function beginNewLoginAttempt() {
    clearStoredTokens()
    beginAuthSessionBoundary()
    accessToken.value = null
    refreshToken.value = null
    user.value = null
  }

  async function register(username: string, email: string, password: string) {
    beginNewLoginAttempt()
    const session = captureAuthSession()
    const tokens = await api.post<Partial<TokenPair>>('/auth/register', { username, email, password })
    assertAuthSessionCurrent(session)
    if (tokens.access_token && tokens.refresh_token) {
      setTokens(tokens as TokenPair)
    } else {
      await login(username, password)
      return
    }
    await fetchMe()
  }

  async function login(username: string, password: string) {
    beginNewLoginAttempt()
    const session = captureAuthSession()
    const tokens = await api.post<TokenPair>('/auth/login', { username, password })
    assertAuthSessionCurrent(session)
    setTokens(tokens)
    await fetchMe()
  }

  async function logout() {
    publishLogout()
    clearTokens()
    router.push('/login')
  }

  async function fetchMe() {
    const session = captureAuthSession()
    try {
      const resolvedUser = await api.get<User>('/auth/me')
      assertAuthSessionCurrent(session)
      user.value = resolvedUser
      sessionSubject.value = accessTokenSubject(accessToken.value) ?? String(resolvedUser.id)
      _syncTokensFromStorage(true)
    } catch {
      if (session.epoch === captureAuthSession().epoch) user.value = null
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
    if (storedAccess) sessionSubject.value = accessTokenSubject(storedAccess)
    else if (!preserveCurrent) sessionSubject.value = null
  }

  function syncTokensFromSessionBoundary() {
    _syncTokensFromStorage()
    if (!accessToken.value) user.value = null
  }

  return {
    accessToken, refreshToken, user, isLoading, loading, isAuthenticated, isLoggedIn,
    register, login, logout, fetchMe, loadMe, handleUnauthorized,
    syncTokensFromSessionBoundary,
  }
})
