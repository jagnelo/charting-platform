import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import DistributionBars from '@/components/strategy/DistributionBars.vue'
import uPlot from 'uplot'

describe('DistributionBars', () => {
  it('renders an R outcome map with trade dots and hover detail', async () => {
    vi.mocked(uPlot).mockClear()
    const wrapper = mount(DistributionBars, {
      attachTo: document.body,
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
    await nextTick()

    expect(wrapper.text()).not.toContain('2 trades')
    expect(wrapper.text()).not.toContain('Avg 0.03R')
    expect(wrapper.text()).not.toContain('50% > 0R')
    expect(wrapper.text()).toContain('LOSSES')
    expect(wrapper.text()).toContain('BREAKEVEN')
    expect(wrapper.text()).toContain('WINS')
    expect(vi.mocked(uPlot)).toHaveBeenCalled()
    expect(vi.mocked(uPlot).mock.calls.at(-1)?.[0].plugins).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="r-outcome-point"]')).toHaveLength(2)

    const firstPoint = wrapper.find('[data-testid="r-outcome-point"]')
    await firstPoint.trigger('mouseenter')

    expect(document.body.textContent).toContain('AAPL')
    expect(document.body.textContent).toContain('-0.75R')
    expect(document.body.textContent).toContain('Stop Loss')
  })
})
