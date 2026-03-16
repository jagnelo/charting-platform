/**
 * Unit tests for the API client — JWT storage, auto-refresh,
 * request construction, and error handling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setTokens, clearTokens } from '@/lib/api'

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

  it('throws on non-OK response', async () => {
    setTokens('tok', 'ref')
    mockFetchFail(404, 'Not found')
    const { api } = await import('@/lib/api')
    await expect(api.get('/missing')).rejects.toThrow('404')
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
})
