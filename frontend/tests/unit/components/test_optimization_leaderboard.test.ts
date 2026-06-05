import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OptimizationLeaderboard from '@/components/strategy/OptimizationLeaderboard.vue'

describe('OptimizationLeaderboard', () => {
  it('renders ranked optimization rows and a detail state', async () => {
    const wrapper = mount(OptimizationLeaderboard, {
      props: {
        rows: [
          { stop_loss_pct: 2, take_profit_rr: 2.5, max_bars_in_trade: 18, trade_count: 6, net_pnl: 1250.45, avg_r: 1.1 },
          { stop_loss_pct: 1.5, take_profit_rr: 3, max_bars_in_trade: 24, trade_count: 5, net_pnl: 980.1, avg_r: 0.9 },
        ],
      },
    })

    expect(wrapper.text()).toContain('2 configs')
    expect(wrapper.text()).toContain('Best')
    expect(wrapper.text()).toContain('1.10R')

    await wrapper.findAll('tbody tr')[0].trigger('click')
    expect(wrapper.text()).toContain('Rank #1')
    expect(wrapper.text()).toContain('Stop 2%')
  })
})
