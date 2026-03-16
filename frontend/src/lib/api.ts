/**
 * Authenticated API client with automatic token refresh on 401.
 */
const BASE = '/api/v1'

async function getToken(): Promise<string | null> {
  return localStorage.getItem('access_token')
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, any>,
  retry = true,
): Promise<T> {
  let url = `${BASE}${path}`
  if (params && Object.keys(params).length) {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => [k, String(v)])
    ).toString()
    url += `?${qs}`
  }

  const token = await getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const opts: RequestInit = { method, headers }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(url, opts)

  if (res.status === 401 && retry) {
    // Attempt silent token refresh
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    const newToken = await authStore.handleUnauthorized()
    if (newToken) {
      return request<T>(method, path, body, params, false)
    }
    throw new Error('Authentication required')
  }

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${method} ${path} → ${res.status}: ${text}`)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get:    <T>(path: string, params?: Record<string, any>) => request<T>('GET', path, undefined, params),
  post:   <T>(path: string, body: unknown)                => request<T>('POST', path, body),
  patch:  <T>(path: string, body: unknown)                => request<T>('PATCH', path, body),
  delete: <T>(path: string)                               => request<T>('DELETE', path),
}
