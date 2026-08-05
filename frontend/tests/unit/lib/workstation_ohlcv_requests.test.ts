import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearOhlcvRequestCache, dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'

afterEach(() => clearOhlcvRequestCache())

describe('OHLCV request coordinator', () => {
  it('coalesces simultaneous identical requests and reuses the short-lived result', async () => {
    let resolve: ((value: string[]) => void) | undefined
    const request = vi.fn(() => new Promise<string[]>(done => { resolve = done }))
    const first = dedupeOhlcvRequest('SPY:D1:500', request)
    const second = dedupeOhlcvRequest('SPY:D1:500', request)
    expect(request).toHaveBeenCalledTimes(1)
    resolve?.(['bar'])
    await expect(Promise.all([first, second])).resolves.toEqual([['bar'], ['bar']])
    await expect(dedupeOhlcvRequest('SPY:D1:500', request)).resolves.toEqual(['bar'])
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('does not retain rejected requests or leak a stale in-flight entry', async () => {
    const request = vi.fn()
      .mockRejectedValueOnce(new Error('temporary'))
      .mockResolvedValueOnce(['recovered'])
    await expect(dedupeOhlcvRequest('XLK:D1:500', request)).rejects.toThrow('temporary')
    await expect(dedupeOhlcvRequest('XLK:D1:500', request)).resolves.toEqual(['recovered'])
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('expires successful entries so a later refresh can observe new bars', async () => {
    vi.useFakeTimers()
    try {
      const request = vi.fn()
        .mockResolvedValueOnce(['old'])
        .mockResolvedValueOnce(['new'])
      await expect(dedupeOhlcvRequest('XLE:D1:500', request, 100)).resolves.toEqual(['old'])
      vi.advanceTimersByTime(101)
      await expect(dedupeOhlcvRequest('XLE:D1:500', request, 100)).resolves.toEqual(['new'])
      expect(request).toHaveBeenCalledTimes(2)
    } finally { vi.useRealTimers() }
  })
})
