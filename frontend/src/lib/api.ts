import { assertAuthSessionCurrent, beginAuthSessionBoundary, captureAuthSession } from '@/lib/authSession'

/**
 * Authenticated API client with automatic token refresh on 401.
 */
const BASE = '/api/v1'
export type ApiRequestOptions = { signal?: AbortSignal }

export class ApiError extends Error {
  readonly status: number
  readonly method: string
  readonly path: string

  constructor(method: string, path: string, status: number, body: string) {
    super(`API ${method} ${path} → ${status}: ${body}`)
    this.name = 'ApiError'
    this.status = status
    this.method = method
    this.path = path
  }
}

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
  const session = captureAuthSession()
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) {
    clearTokens()
    beginAuthSessionBoundary()
    return null
  }

  const controller = new AbortController()
  const abortForSession = () => controller.abort()
  session.signal.addEventListener('abort', abortForSession, { once: true })
  let res: Response
  try {
    res = await fetch(`${BASE}/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    })
    assertAuthSessionCurrent(session)
  } finally {
    session.signal.removeEventListener('abort', abortForSession)
  }

  if (!res.ok) {
    clearTokens()
    beginAuthSessionBoundary()
    return null
  }

  const tokens: TokenPair = await res.json()
  assertAuthSessionCurrent(session)
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
  const session = captureAuthSession()
  let url = `${BASE}${path}`
  if (params && Object.keys(params).length) {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => [k, String(v)])
    ).toString()
    url += `?${qs}`
  }

  // Capture the token synchronously before the first await. Logout can clear
  // storage while a request is being prepared; a request that started while
  // authenticated must retain its authorization header instead of turning
  // into a spurious post-logout 401.
  const token = getToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const controller = new AbortController()
  const abortForSession = () => controller.abort()
  const abortForCaller = () => controller.abort(options?.signal?.reason)
  session.signal.addEventListener('abort', abortForSession, { once: true })
  options?.signal?.addEventListener('abort', abortForCaller, { once: true })
  if (session.signal.aborted) abortForSession()
  if (options?.signal?.aborted) abortForCaller()
  const opts: RequestInit = { method, headers, signal: controller.signal }
  if (body !== undefined) opts.body = JSON.stringify(body)

  try {
    const res = await fetch(url, opts)
    assertAuthSessionCurrent(session)

    if (res.status === 401 && retry && !path.startsWith('/auth/')) {
      const newToken = await refreshAccessToken()
      assertAuthSessionCurrent(session)
      if (newToken) {
        return request<T>(method, path, body, params, false, options)
      }
      throw new Error('Authentication required')
    }

    if (!res.ok) {
      const text = await res.text()
      assertAuthSessionCurrent(session)
      throw new ApiError(method, path, res.status, text)
    }

    if (res.status === 204) return undefined as T
    const payload = await res.json() as T
    assertAuthSessionCurrent(session)
    return payload
  } finally {
    session.signal.removeEventListener('abort', abortForSession)
    options?.signal?.removeEventListener('abort', abortForCaller)
  }
}

export const api = {
  get:    <T>(path: string, params?: Record<string, any>, options?: ApiRequestOptions) => request<T>('GET', path, undefined, params, true, options),
  post:   <T>(path: string, body: unknown, options?: ApiRequestOptions)                => request<T>('POST', path, body, undefined, true, options),
  patch:  <T>(path: string, body: unknown, options?: ApiRequestOptions)                => request<T>('PATCH', path, body, undefined, true, options),
  put:    <T>(path: string, body: unknown, options?: ApiRequestOptions)                => request<T>('PUT', path, body, undefined, true, options),
  delete: <T>(path: string, options?: ApiRequestOptions)                               => request<T>('DELETE', path, undefined, undefined, true, options),
}
