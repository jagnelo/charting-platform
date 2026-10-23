import { afterEach, describe, expect, it, vi } from 'vitest'

import { installBrowserRequestObservation, requireObservedRequestCoverage, requestsStartedWhileHidden } from '../../e2e/hidden_request_observation'

const observed = () => (globalThis as typeof globalThis & {
  __analysisRequestStarts: { path: string; startTime: number }[]
}).__analysisRequestStarts

afterEach(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(globalThis, '__analysisRequestStarts')
})

function prepareCollector(now: () => number, fetchImpl: typeof fetch = vi.fn(() => new Promise<Response>(() => {}))) {
  vi.stubGlobal('performance', { timeOrigin: 1_000, now })
  vi.stubGlobal('fetch', fetchImpl)
  vi.stubGlobal('XMLHttpRequest', class {
    open() {}
    send() {}
  })
  installBrowserRequestObservation()
  return fetchImpl
}

describe('hidden request observation', () => {
  it('does not count a pre-hidden request delivered after the browser transition', () => {
    expect(
      requestsStartedWhileHidden(
        [{ path: '/api/v1/analysis/market-map', startTime: 999 }],
        1_000,
      ),
    ).toEqual([])
  })

  it('counts a request whose browser initiation starts at the hidden boundary', () => {
    expect(
      requestsStartedWhileHidden(
        [{ path: '/api/v1/market-groups/us-benchmarks', startTime: 1_000 }],
        1_000,
      ),
    ).toEqual(['/api/v1/market-groups/us-benchmarks'])
  })

  it('fails closed when the request timing is unavailable', () => {
    expect(() =>
      requestsStartedWhileHidden(
        [{ path: '/api/v1/analysis/market-map', startTime: undefined }],
        1_000,
      ),
    ).toThrow('Request start time unavailable')
  })

  it('records a pending fetch before any response or native timing exists', () => {
    const nativeFetch = prepareCollector(() => 99)
    void fetch('/api/v1/analysis/benchmark-families/readiness')
    expect(nativeFetch).toHaveBeenCalledOnce()
    expect(observed()).toEqual([{ path: '/api/v1/analysis/benchmark-families/readiness', startTime: 1_099 }])
    expect(requestsStartedWhileHidden(observed(), 1_100)).toEqual([])
  })

  it('keeps pre-hidden initiation evidence after a fetch is aborted', async () => {
    const controller = new AbortController()
    const nativeFetch = vi.fn((_input?: unknown, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    prepareCollector(() => 99, nativeFetch)
    const pending = fetch('/api/v1/analysis/benchmark-families/readiness', { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toThrow('Aborted')
    expect(requestsStartedWhileHidden(observed(), 1_100)).toEqual([])
    expect(observed()).toHaveLength(1)
  })

  it('still detects fetch initiation at the hidden boundary', () => {
    prepareCollector(() => 100)
    void fetch('/api/v1/analysis/benchmark-families/readiness')
    expect(requestsStartedWhileHidden(observed(), 1_100)).toEqual(['/api/v1/analysis/benchmark-families/readiness'])
  })

  it('timestamps XHR send, not an earlier open', () => {
    let now = 99
    prepareCollector(() => now)
    const xhr = new XMLHttpRequest()
    xhr.open('GET', '/api/v1/market-groups/us-benchmarks')
    expect(observed()).toEqual([])
    now = 100
    xhr.send()
    expect(requestsStartedWhileHidden(observed(), 1_100)).toEqual(['/api/v1/market-groups/us-benchmarks'])
  })

  it('does not collect unrelated endpoints or credential-bearing query data', () => {
    prepareCollector(() => 99)
    void fetch('/api/v1/auth/refresh?refresh_token=synthetic-only')
    void fetch('/api/v1/analysis/market-map?synthetic=not-recorded')
    expect(observed()).toEqual([{ path: '/api/v1/analysis/market-map', startTime: 1_099 }])
  })

  it('fails closed for a native request without matching browser observation', () => {
    expect(() => requireObservedRequestCoverage([], ['/api/v1/analysis/market-map'])).toThrow('Unobserved request')
    expect(() => requireObservedRequestCoverage(
      [{ path: '/api/v1/analysis/market-map', startTime: 999 }],
      ['/api/v1/analysis/market-map', '/api/v1/analysis/market-map'],
    )).toThrow('Unobserved request')
  })
})
