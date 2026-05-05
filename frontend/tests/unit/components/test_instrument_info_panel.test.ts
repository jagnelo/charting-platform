import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import InstrumentInfoPanel from '@/components/chart/InstrumentInfoPanel.vue'

describe('InstrumentInfoPanel', () => {
  it('shows intraday time for day-range and date-only timestamps for 52-week range endpoints', async () => {
    const wrapper = mount(InstrumentInfoPanel, {
      attachTo: document.body,
      props: {
        instrument: {
          id: 1,
          symbol: 'TSLA',
          name: 'Tesla',
          currency: 'USD',
          is_active: true,
          stats: {
            week52_high: 488.4,
            week52_low: 138.8,
            field_provenance: {
              week52_high: { source: 'internal_ohlcv_52w', observed_at: '2026-03-05T00:00:00Z' },
              week52_low: { source: 'internal_ohlcv_52w', observed_at: '2025-06-11T00:00:00Z' },
            },
          },
        },
        currentPrice: 320.5,
        sessionHigh: 325.2,
        sessionLow: 312.4,
        sessionHighTime: '2026-05-05T14:30:00Z',
        sessionLowTime: '2026-05-05T10:15:00Z',
      },
      global: {
        stubs: {
          ProvenanceHint: { template: '<span class="prov-hint-stub">i</span>' },
        },
      },
    })

    const rangeRows = wrapper.findAll('.range-row')
    expect(rangeRows).toHaveLength(2)

    const tooltipAnchors = wrapper.findAll('.hover-tooltip-anchor')
    await tooltipAnchors[0].trigger('mouseenter')
    await nextTick()
    await nextTick()

    expect(document.body.textContent).toContain('Day low occurred on 2026-05-05 at 10:15 UTC')

    await tooltipAnchors[3].trigger('mouseenter')
    await nextTick()
    await nextTick()

    expect(document.body.textContent).toContain('52-week high occurred on 2026-03-05')
    expect(document.body.textContent).not.toContain('2026-03-05 at')
    wrapper.unmount()
  })
})
