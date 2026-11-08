import { assertAuthSessionCurrent, AuthSessionChangedError, beginAuthSessionBoundary, captureAuthSession } from '@/lib/authSession'

/**
 * Authenticated API client with automatic token refresh on 401.
 */
const BASE = '/api/v1'
export type ApiRequestOptions = { signal?: AbortSignal; priority?: RequestPriority }

// Chromium only admits a small number of same-origin HTTP/1.1 requests at a
// time. Admit work here so queued background reads cannot occupy every slot
// ahead of a visible user action. The spare slot is available to explicit
// high-priority requests; lower-priority local hydration has a smaller cap.
const API_TRANSPORT_LIMIT = 6
const API_NON_HIGH_LIMIT = 5
const API_LOW_PRIORITY_LIMIT = 4
type ApiFetchPriority = NonNullable<ApiRequestOptions['priority']>
interface AdmittedApiResponse { response: Response; release: () => void }

interface QueuedApiFetch {
  input: RequestInfo | URL
  init: RequestInit
  priority: ApiFetchPriority
  resolve: (response: AdmittedApiResponse) => void
  reject: (error: unknown) => void
  abortListener?: () => void
}

const queuedApiFetches: QueuedApiFetch[] = []
let activeApiFetches = 0
let activeNonHighApiFetches = 0
let activeLowApiFetches = 0

function apiAbortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException('The operation was aborted.', 'AbortError')
}

function nextAdmissibleFetchIndex(): number {
  const priorityOrder: ApiFetchPriority[] = ['high', 'auto', 'low']
  for (const priority of priorityOrder) {
    if (priority === 'auto' && activeNonHighApiFetches >= API_NON_HIGH_LIMIT) continue
    if (priority === 'low' && (activeNonHighApiFetches >= API_NON_HIGH_LIMIT || activeLowApiFetches >= API_LOW_PRIORITY_LIMIT)) continue
    const index = queuedApiFetches.findIndex(item => item.priority === priority)
    if (index !== -1) return index
  }
  return -1
}

function drainApiFetchQueue(): void {
  while (activeApiFetches < API_TRANSPORT_LIMIT) {
    const index = nextAdmissibleFetchIndex()
    if (index === -1) return
    const [queued] = queuedApiFetches.splice(index, 1)
    const signal = queued.init.signal
    if (signal?.aborted) {
      if (queued.abortListener) signal.removeEventListener('abort', queued.abortListener)
      queued.reject(apiAbortReason(signal))
      continue
    }
    if (queued.abortListener) signal?.removeEventListener('abort', queued.abortListener)
    activeApiFetches += 1
    if (queued.priority !== 'high') activeNonHighApiFetches += 1
    if (queued.priority === 'low') activeLowApiFetches += 1
    let released = false
    const release = () => {
      if (released) return
      released = true
      activeApiFetches -= 1
      if (queued.priority !== 'high') activeNonHighApiFetches -= 1
      if (queued.priority === 'low') activeLowApiFetches -= 1
      drainApiFetchQueue()
    }
    void Promise.resolve().then(() => fetch(queued.input, queued.init)).then(
      response => queued.resolve({ response, release }),
      error => {
        release()
        queued.reject(error)
      },
    )
  }
}

function admittedApiFetch(input: RequestInfo | URL, init: RequestInit, priority: ApiFetchPriority = 'auto'): Promise<AdmittedApiResponse> {
  const signal = init.signal
  if (signal?.aborted) return Promise.reject(apiAbortReason(signal))
  return new Promise((resolve, reject) => {
    const queued: QueuedApiFetch = { input, init, priority, resolve, reject }
    if (signal) {
      queued.abortListener = () => {
        const index = queuedApiFetches.indexOf(queued)
        if (index < 0) return
        queuedApiFetches.splice(index, 1)
        signal.removeEventListener('abort', queued.abortListener!)
        reject(apiAbortReason(signal))
        drainApiFetchQueue()
      }
      signal.addEventListener('abort', queued.abortListener, { once: true })
    }
    queuedApiFetches.push(queued)
    drainApiFetchQueue()
  })
}

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
  let admitted: AdmittedApiResponse | undefined
  try {
    admitted = await admittedApiFetch(`${BASE}/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    }, 'high')
    assertAuthSessionCurrent(session)
    const res = admitted.response
    if (!res.ok) {
      await res.text()
      clearTokens()
      beginAuthSessionBoundary()
      return null
    }

    const tokens: TokenPair = await res.json()
    assertAuthSessionCurrent(session)
    setTokens(tokens)
    return tokens.access_token
  } finally {
    admitted?.release()
    session.signal.removeEventListener('abort', abortForSession)
  }
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
  if (options?.priority) opts.priority = options.priority
  if (body !== undefined) opts.body = JSON.stringify(body)

  let admitted: AdmittedApiResponse | undefined
  try {
    admitted = await admittedApiFetch(url, opts, options?.priority ?? 'auto')
    const res = admitted.response
    assertAuthSessionCurrent(session)

    if (res.status === 401 && retry && !path.startsWith('/auth/')) {
      await res.text()
      admitted.release()
      admitted = undefined
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
  } catch (error) {
    // Fetch rejects with a browser-native AbortError when logout or another
    // account boundary aborts its session signal. Normalize that expected
    // cancellation at the API boundary so consumers can handle it as the
    // typed auth-session transition rather than logging an opaque fetch error.
    if (session.signal.aborted) throw new AuthSessionChangedError()
    throw error
  } finally {
    admitted?.release()
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
