/**
 * Authenticated API client with automatic token refresh on 401.
 */
const BASE = '/api/v1'
export type ApiRequestOptions = { signal?: AbortSignal }

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type?: string
}

export function setTokens(tokens: TokenPair): void
export function setTokens(accessToken: string, refreshToken: string): void
export function setTokens(tokensOrAccess: TokenPair | string, refreshToken?: string): void {
  const access = typeof tokensOrAccess === 'string' ? tokensOrAccess : tokensOrAccess.access_token
  const refresh = typeof tokensOrAccess === 'string' ? refreshToken : tokensOrAccess.refresh_token
  if (!refresh) return
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}

export function clearTokens(): void {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) {
    clearTokens()
    return null
  }

  const res = await fetch(`${BASE}/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })

  if (!res.ok) {
    clearTokens()
    return null
  }

  const tokens: TokenPair = await res.json()
  setTokens(tokens)
  return tokens.access_token
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, any>,
  retry = true,
  options?: ApiRequestOptions,
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

  const opts: RequestInit = { method, headers, signal: options?.signal }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(url, opts)

  if (res.status === 401 && retry && !path.startsWith('/auth/')) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return request<T>(method, path, body, params, false, options)
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
  get:    <T>(path: string, params?: Record<string, any>, options?: ApiRequestOptions) => request<T>('GET', path, undefined, params, true, options),
  post:   <T>(path: string, body: unknown, options?: ApiRequestOptions)                => request<T>('POST', path, body, undefined, true, options),
  patch:  <T>(path: string, body: unknown, options?: ApiRequestOptions)                => request<T>('PATCH', path, body, undefined, true, options),
  put:    <T>(path: string, body: unknown, options?: ApiRequestOptions)                => request<T>('PUT', path, body, undefined, true, options),
  delete: <T>(path: string, options?: ApiRequestOptions)                               => request<T>('DELETE', path, undefined, undefined, true, options),
}
