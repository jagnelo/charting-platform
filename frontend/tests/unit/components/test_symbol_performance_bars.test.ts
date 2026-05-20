import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SymbolPerformanceBars from '@/components/strategy/SymbolPerformanceBars.vue'

describe('SymbolPerformanceBars', () => {
  it('renders summary chips and symbol outcome drilldown', async () => {
    const wrapper = mount(SymbolPerformanceBars, {
      props: {
        rows: [
          { symbol: 'AAPL', net_pnl: 1250.45, trade_count: 2, win_rate: 50, avg_r: 1.1 },
          { symbol: 'MSFT', net_pnl: -630.2, trade_count: 1, win_rate: 0, avg_r: -0.82 },
        ],
        events: [
          {
            ts: '2026-02-08T00:00:00Z',
            position_id: 'AAPL-1',
            event_type: 'exit',
            symbol: 'AAPL',
            pnl: 1250.45,
            pnl_pct: 12.5,
            reason: 'take_profit',
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('2 symbols')
    expect(wrapper.text()).toContain('Best AAPL')
    expect(wrapper.text()).toContain('Worst MSFT')

    const firstRow = wrapper.find('.symbol-bars__row-button')
    await firstRow.trigger('click')

    expect(wrapper.text()).toContain('50.00% win')
    expect(wrapper.text()).toContain('Take Profit')
  })
})
