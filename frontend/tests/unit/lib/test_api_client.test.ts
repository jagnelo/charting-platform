/**
 * Unit tests for the API client — JWT storage, auto-refresh,
 * request construction, and error handling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { setTokens, clearTokens, ApiError } from '@/lib/api'
import { currentAuthSessionEpoch, beginAuthSessionBoundary, AuthSessionChangedError } from '@/lib/authSession'
import { useAuthStore } from '@/stores/auth'
import { router } from '@/router'

// We re-import api after each test to get a fresh module state
// In Vitest we can use vi.resetModules() for this

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  ;(global.fetch as ReturnType<typeof vi.fn>).mockReset()
})

function mockFetchOk(body: unknown, status = 200) {
  ;(global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  })
}

function mockFetchFail(status: number, body = 'Error') {
  ;(global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve({ detail: body }),
    text: () => Promise.resolve(body),
  })
}

describe('setTokens / clearTokens', () => {
  it('setTokens stores both tokens', () => {
    setTokens('access123', 'refresh456')
    expect(localStorage.getItem('access_token')).toBe('access123')
    expect(localStorage.getItem('refresh_token')).toBe('refresh456')
  })

  it('clearTokens removes both tokens', () => {
    setTokens('a', 'r')
    clearTokens()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })
})

describe('api.get', () => {
  it('sends GET request with Authorization header', async () => {
    setTokens('mytoken', 'refresh')
    mockFetchOk({ id: 1 })
    const { api } = await import('@/lib/api')
    await api.get('/test-endpoint')

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/test-endpoint'),
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer mytoken' }),
      })
    )
  })

  it('appends query params to URL', async () => {
    setTokens('tok', 'ref')
    mockFetchOk([])
    const { api } = await import('@/lib/api')
    await api.get('/items', { status: 'active', limit: 10 })

    const [[url]] = (fetch as ReturnType<typeof vi.fn>).mock.calls
    expect(url).toContain('status=active')
    expect(url).toContain('limit=10')
  })

  it('omits null/undefined params', async () => {
    setTokens('tok', 'ref')
    mockFetchOk({})
    const { api } = await import('@/lib/api')
    await api.get('/items', { active: undefined, count: null, name: 'test' })

    const [[url]] = (fetch as ReturnType<typeof vi.fn>).mock.calls
    expect(url).not.toContain('active')
    expect(url).not.toContain('count')
    expect(url).toContain('name=test')
  })

  it('captures the token before logout can clear storage during request preparation', async () => {
    setTokens('session-token', 'refresh')
    let resolveFetch!: (response: unknown) => void
    ;(global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveFetch = resolve }))
    const { api } = await import('@/lib/api')
    const request = api.get('/during-logout')
    clearTokens()
    resolveFetch({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }), text: () => Promise.resolve('') })
    await request

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/during-logout'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer session-token' }) }),
    )
  })

  it('rejects an authenticated response that arrives after the user session changes', async () => {
    setTokens('user-a-access', 'user-a-refresh')
    let resolveFetch!: (response: unknown) => void
    ;(global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveFetch = resolve }))
    const { api } = await import('@/lib/api')
    const request = api.get('/private/results')
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[1]?.headers).toMatchObject({ Authorization: 'Bearer user-a-access' })

    beginAuthSessionBoundary()
    clearTokens()
    setTokens('user-b-access', 'user-b-refresh')
    resolveFetch({ ok: true, status: 200, json: () => Promise.resolve({ owner: 'user-a' }), text: () => Promise.resolve('') })

    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
    expect(localStorage.getItem('access_token')).toBe('user-b-access')

    mockFetchOk({ owner: 'user-b' })
    await expect(api.get('/private/results')).resolves.toEqual({ owner: 'user-b' })
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/private/results'), expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer user-b-access' }),
    }))
  })

  it('normalizes a fetch abort caused by the auth boundary to the typed session-change error', async () => {
    setTokens('user-a-access', 'user-a-refresh')
    let rejectFetch!: (reason: unknown) => void
    ;(global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise((_resolve, reject) => { rejectFetch = reject }))
    const { api } = await import('@/lib/api')
    const request = api.get('/private/results')

    beginAuthSessionBoundary()
    rejectFetch(new DOMException('signal is aborted without reason', 'AbortError'))

    await expect(request).rejects.toBeInstanceOf(AuthSessionChangedError)
    await expect(request).rejects.toMatchObject({ name: 'AbortError', message: 'The authenticated session changed while this request was in flight.' })
  })

  it('preserves the authenticated session generation during token refresh', async () => {
    setTokens('user-a-expiring', 'user-a-refresh')
    mockFetchOk({ access_token: 'user-a-refreshed', refresh_token: 'user-a-refresh-next' })
    const epoch = currentAuthSessionEpoch()
    const { refreshAccessToken } = await import('@/lib/api')

    await expect(refreshAccessToken()).resolves.toBe('user-a-refreshed')
    expect(currentAuthSessionEpoch()).toBe(epoch)
    expect(localStorage.getItem('access_token')).toBe('user-a-refreshed')
  })

  it('throws on non-OK response', async () => {
    setTokens('tok', 'ref')
    mockFetchFail(404, 'Not found')
    const { api } = await import('@/lib/api')
    await expect(api.get('/missing')).rejects.toThrow('404')
  })

  it('exposes structured status and request context for recoverable conflicts', async () => {
    setTokens('tok', 'ref')
    mockFetchFail(409, 'Already exists')
    const { api } = await import('@/lib/api')

    await expect(api.post('/watchlists/1/items', { instrument_id: 2 })).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      method: 'POST',
      path: '/watchlists/1/items',
    } satisfies Partial<ApiError>)
  })
})

describe('api.post', () => {
  it('sends POST with JSON body', async () => {
    setTokens('tok', 'ref')
    mockFetchOk({ id: 42 }, 201)
    const { api } = await import('@/lib/api')
    await api.post('/items', { name: 'test', value: 123 })

    const [, opts] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.body).toBe(JSON.stringify({ name: 'test', value: 123 }))
    expect(opts.headers['Content-Type']).toBe('application/json')
  })

  it('forwards abort signals to fetch for cancellable batch requests', async () => {
    setTokens('tok', 'ref')
    let resolveFetch!: (response: unknown) => void
    ;(global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveFetch = resolve }))
    const controller = new AbortController()
    const { api } = await import('@/lib/api')
    const request = api.post('/items', { name: 'batch' }, { signal: controller.signal })

    const [, opts] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(opts.signal).toBeInstanceOf(AbortSignal)
    expect(opts.signal.aborted).toBe(false)
    controller.abort()
    expect(opts.signal.aborted).toBe(true)
    resolveFetch({ ok: true, status: 201, json: () => Promise.resolve({ id: 42 }), text: () => Promise.resolve('') })
    await expect(request).resolves.toEqual({ id: 42 })
  })
})

describe('api.delete', () => {
  it('returns undefined on 204', async () => {
    setTokens('tok', 'ref')
    ;(global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true, status: 204,
      json: () => Promise.resolve(undefined),
      text: () => Promise.resolve(''),
    })
    const { api } = await import('@/lib/api')
    const result = await api.delete('/items/1')
    expect(result).toBeUndefined()
  })
})

describe('auto-refresh on 401', () => {
  it('retries request after refreshing token', async () => {
    setTokens('expired_token', 'valid_refresh')

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>

    // First call → 401
    fetchMock.mockResolvedValueOnce({
      ok: false, status: 401,
      text: () => Promise.resolve('Unauthorized'),
      json: () => Promise.resolve({}),
    })
    // Refresh call → success with new tokens
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200,
      json: () => Promise.resolve({ access_token: 'new_token', refresh_token: 'new_refresh' }),
      text: () => Promise.resolve(''),
    })
    // Retry with new token → success
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200,
      json: () => Promise.resolve({ data: 'success' }),
      text: () => Promise.resolve(''),
    })

    const { api } = await import('@/lib/api')
    const result = await api.get('/protected')
    expect(result).toEqual({ data: 'success' })
    expect(localStorage.getItem('access_token')).toBe('new_token')
  })

  it('clears tokens and throws when refresh fails', async () => {
    setTokens('expired', 'bad_refresh')

    const fetchMock = global.fetch as ReturnType<typeof vi.fn>
    fetchMock.mockResolvedValueOnce({
      ok: false, status: 401,
      text: () => Promise.resolve('Unauthorized'),
      json: () => Promise.resolve({}),
    })
    fetchMock.mockResolvedValueOnce({
      ok: false, status: 401,
      json: () => Promise.resolve({}),
      text: () => Promise.resolve('Session expired'),
    })

    const { api } = await import('@/lib/api')
    await expect(api.get('/protected')).rejects.toThrow()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('settles auth refs when the API-owned refresh request expires', async () => {
    setActivePinia(createPinia())
    setTokens('expired', 'bad_refresh')
    const auth = useAuthStore()
    auth.user = { id: 41, username: 'user-a', email: 'a@example.test', is_admin: false }
    const redirectToLogin = vi.spyOn(router, 'replace').mockImplementation(() => Promise.resolve(undefined as never))
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>
    fetchMock.mockResolvedValueOnce({
      ok: false, status: 401,
      text: () => Promise.resolve('Unauthorized'),
      json: () => Promise.resolve({ detail: 'Unauthorized' }),
    })
    fetchMock.mockResolvedValueOnce({
      ok: false, status: 401,
      text: () => Promise.resolve('Refresh expired'),
      json: () => Promise.resolve({ detail: 'Refresh expired' }),
    })

    const { api } = await import('@/lib/api')
    await expect(api.get('/private-data')).rejects.toThrow()

    expect(fetch).toHaveBeenCalledTimes(2) // one protected read and one failed refresh
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(auth.accessToken).toBeNull()
    expect(auth.refreshToken).toBeNull()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(redirectToLogin).toHaveBeenCalledWith('/login')
    expect(redirectToLogin).toHaveBeenCalledTimes(1)
    redirectToLogin.mockRestore()
  })
})
