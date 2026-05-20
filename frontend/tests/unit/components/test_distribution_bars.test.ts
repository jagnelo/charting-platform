import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DistributionBars from '@/components/strategy/DistributionBars.vue'

describe('DistributionBars', () => {
  it('renders summary chips and bucket drilldown', async () => {
    const wrapper = mount(DistributionBars, {
      props: {
        rows: [
          { lower: -1, upper: 0, count: 1 },
          { lower: 0, upper: 1, count: 1 },
        ],
        trades: [
          {
            instrument_symbol: 'AAPL',
            pnl: -250.1,
            r_multiple: -0.75,
            exit_reason: 'stop_loss',
            exit_at: '2026-02-08T00:00:00Z',
          },
          {
            instrument_symbol: 'MSFT',
            pnl: 600.2,
            r_multiple: 0.8,
            exit_reason: 'take_profit',
            exit_at: '2026-02-10T00:00:00Z',
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('2 trades')
    expect(wrapper.text()).toContain('Avg 0.03R')
    expect(wrapper.text()).toContain('50% > 0R')

    const firstBucket = wrapper.find('.distribution-bars__row-button')
    await firstBucket.trigger('click')

    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('Stop Loss')
  })
})
