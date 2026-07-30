import { describe, expect, it } from 'vitest'

import { normaliseGoldenLayoutConfig } from '@/lib/workstation/layout'

describe('Golden Layout persisted configuration', () => {
  it('converts stale numeric sizes to Golden Layout v2 unit-bearing fractions', () => {
    const layout = normaliseGoldenLayoutConfig({
      root: {
        type: 'row',
        content: [{ type: 'component', size: 1 }, { type: 'component', size: '40%' }],
      },
      dimensions: { defaultMinItemHeight: 10, defaultMinItemWidth: 20 },
    })

    expect(layout).toEqual({
      root: {
        type: 'row',
        content: [{ type: 'component', size: '1fr' }, { type: 'component', size: '40%' }],
      },
      dimensions: { defaultMinItemHeight: '10px', defaultMinItemWidth: '20px' },
    })
  })
})
