import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SymbolPerformanceBars from '@/components/strategy/SymbolPerformanceBars.vue'

describe('SymbolPerformanceBars', () => {
  it('renders a symbol P&L outcome map and tooltip on hover', async () => {
    const wrapper = mount(SymbolPerformanceBars, {
      attachTo: document.body,
      props: {
        rows: [
          {
            symbol: 'AAPL',
            net_pnl: 1500.45,
            total_pnl: 1500.45,
            realized_pnl: 1250.45,
            unrealized_pnl: 250,
            trade_count: 2,
            closed_trade_count: 2,
            open_position_count: 1,
            win_rate: 50,
            avg_r: 1.1,
          },
          {
            symbol: 'MSFT',
            net_pnl: -630.2,
            total_pnl: -630.2,
            realized_pnl: -630.2,
            unrealized_pnl: 0,
            trade_count: 1,
            closed_trade_count: 1,
            open_position_count: 0,
            win_rate: 0,
            avg_r: -0.82,
          },
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
          {
            ts: '2026-02-09T00:00:00Z',
            position_id: 'AAPL-2',
            event_type: 'open_at_end',
            symbol: 'AAPL',
            pnl: 250,
            pnl_pct: 2.5,
            reason: 'run_end_mark',
          },
        ],
      },
    })

    expect(wrapper.text()).not.toContain('2 symbols')
    expect(wrapper.text()).not.toContain('Best realized AAPL')
    expect(wrapper.text()).not.toContain('Worst realized MSFT')
    expect(wrapper.text()).toContain('LOSSES')
    expect(wrapper.text()).toContain('FLAT')
    expect(wrapper.text()).toContain('GAINS')
    expect(wrapper.findAll('[data-testid="symbol-pnl-point"]')).toHaveLength(2)

    const firstPoint = wrapper.find('[data-testid="symbol-pnl-point"]')
    await firstPoint.trigger('mouseenter')

    expect(document.body.textContent).toContain('50.00% win')
    expect(document.body.textContent).toContain('+15.00% marked')
    expect(document.body.textContent).toContain('+12.50% · +$1,250.45 realized')
    expect(document.body.textContent).toContain('+2.50% · +$250.00 unrealized')
    expect(document.body.textContent).toContain('+$1,500.45 marked value')
    expect(document.body.textContent).toContain('Take Profit')
  })
})
