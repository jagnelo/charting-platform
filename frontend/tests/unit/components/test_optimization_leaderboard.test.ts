import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OptimizationLeaderboard from '@/components/strategy/OptimizationLeaderboard.vue'

describe('OptimizationLeaderboard', () => {
  it('announces an empty leaderboard state to assistive technology', () => {
    const wrapper = mount(OptimizationLeaderboard, {
      props: { rows: [] },
    })

    const emptyState = wrapper.get('.optimization-panel__empty')
    expect(emptyState.text()).toContain('No optimization leaderboard yet.')
    expect(emptyState.attributes('role')).toBe('status')
    expect(emptyState.attributes('aria-live')).toBe('polite')
    expect(emptyState.attributes('aria-atomic')).toBe('true')
  })

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

    const firstRow = wrapper.findAll('tbody tr')[0]
    expect(firstRow.attributes('tabindex')).toBe('0')
    expect(firstRow.attributes('aria-selected')).toBe('false')

    await firstRow.trigger('click')
    expect(wrapper.text()).toContain('Rank #1')
    expect(wrapper.text()).toContain('Stop 2%')
    expect(firstRow.attributes('aria-selected')).toBe('true')

    await firstRow.trigger('keydown', { key: 'Enter' })
    expect(firstRow.attributes('aria-selected')).toBe('false')
    expect(wrapper.find('.optimization-panel__detail').exists()).toBe(false)

    await firstRow.trigger('keydown', { key: ' ' })
    expect(firstRow.attributes('aria-selected')).toBe('true')
    expect(wrapper.find('.optimization-panel__detail').exists()).toBe(true)
  })
})
