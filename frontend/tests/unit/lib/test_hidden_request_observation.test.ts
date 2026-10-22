import { describe, expect, it } from 'vitest'

import { requestsStartedWhileHidden } from '../../e2e/hidden_request_observation'

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
})
