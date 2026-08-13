import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import ExcursionBars from '@/components/strategy/ExcursionBars.vue'
import uPlot from 'uplot'

describe('ExcursionBars', () => {
  it('renders MAE/MFE summary and uses uPlot for the numerical surface', async () => {
    vi.mocked(uPlot).mockClear()
    const wrapper = mount(ExcursionBars, {
      props: {
        rows: [
          { instrument_symbol: 'AAPL', entry_at: '2026-01-01T00:00:00Z', exit_at: '2026-01-03T00:00:00Z', mae_pct: -2, mfe_pct: 6, bars_available: 3 },
          { instrument_symbol: 'MSFT', entry_at: '2026-01-02T00:00:00Z', exit_at: '2026-01-04T00:00:00Z', mae_pct: -1, mfe_pct: 3, bars_available: 3 },
        ],
      },
    })
    await nextTick()
    expect(wrapper.text()).toContain('2 trades with intratrade bars')
    expect(wrapper.text()).toContain('average MAE -1.50%')
    expect(wrapper.text()).toContain('average MFE +4.50%')
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.excursion-bars__plot').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not create a chart when no trade has materialized bars', async () => {
    vi.mocked(uPlot).mockClear()
    const wrapper = mount(ExcursionBars, { props: { rows: [{ mae_pct: -2, mfe_pct: 4, bars_available: 0 }] } })
    await nextTick()
    expect(wrapper.text()).toContain('No intratrade excursion data yet.')
    expect(vi.mocked(uPlot)).not.toHaveBeenCalled()
  })
})
