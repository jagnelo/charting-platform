import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { sparkTf, useSparklines } from '@/composables/useSparklines'

describe('useSparklines', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    sparkTf.value = '1M'
  })

  it('loads sparkline points and caches them', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { close: 10 },
      { close: 12 },
      { close: 14 },
    ])

    const { load } = useSparklines()
    const first = await load('NVDA')
    const second = await load('NVDA')

    expect(first).toEqual([10, 12, 14])
    expect(second).toEqual([10, 12, 14])
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('loadMany resolves without throwing when some symbols fail', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ close: 1 }, { close: 2 }])
      .mockRejectedValueOnce(new Error('boom'))

    const { loadMany } = useSparklines()
    await expect(loadMany(['AAPL', 'MSFT'])).resolves.toBeUndefined()
  })

  it('converts points into svg coordinates', () => {
    const { pointsToSvg } = useSparklines()
    const svg = pointsToSvg([10, 15, 20])
    expect(svg.split(' ')).toHaveLength(3)
    expect(svg).toContain(',')
  })
})
