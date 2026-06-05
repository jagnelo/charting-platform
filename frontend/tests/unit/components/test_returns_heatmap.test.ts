import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import ReturnsHeatmap from '@/components/strategy/ReturnsHeatmap.vue'

async function flushPromises() {
  await Promise.resolve()
  await nextTick()
}

describe('ReturnsHeatmap', () => {
  it('shows the actual color-scale endpoint percentages in the legend', () => {
    const wrapper = mount(ReturnsHeatmap, {
      props: {
        mode: 'monthly',
        rows: [
          { period: '2026-03', return_pct: 2.5 },
          { period: '2026-04', return_pct: -0.1 },
        ],
      },
    })

    expect(wrapper.text()).toContain('-2.5%')
    expect(wrapper.text()).toContain('+2.5%')
  })

  it('uses the same precision for legend endpoints and visible cells', () => {
    const wrapper = mount(ReturnsHeatmap, {
      props: {
        mode: 'monthly',
        rows: [
          { period: '2026-04', return_pct: -0.065 },
          { period: '2026-05', return_pct: -0.065 },
        ],
      },
    })

    expect(wrapper.text()).toContain('-0.07%')
    expect(wrapper.text()).not.toContain('-0.1%')
  })

  it('shows execution details for a return cell on click', async () => {
    const wrapper = mount(ReturnsHeatmap, {
      props: {
        mode: 'monthly',
        rows: [
          { period: '2026-04', return_pct: -0.1 },
        ],
        cellDetails: {
          '2026-04': [
            {
              ts: '2026-04-20T05:00:00Z',
              event_type: 'exit',
              position_id: 'AAPL-2026-04-15T05:00:00Z',
              symbol: 'AAPL',
              side: 'long',
              quantity: 1,
              price: 294.95,
              pnl: -9.53,
              pnl_pct: -3.23,
              reason: 'stop_loss',
            },
          ],
        },
      },
      attachTo: document.body,
    })

    await wrapper.findAll('.returns-heatmap__cell')[3].trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.returns-heatmap__cell')[3].attributes('title')).toBeUndefined()
    expect(wrapper.text()).toContain('2026-04')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('Exit')
    expect(wrapper.text()).toContain('Stop Loss')
    expect(wrapper.text()).toContain('-$9.53')
    expect(wrapper.text()).toContain('-3.23%')
  })

  it('keeps unrealized marks separate from realized cell value in the tooltip', async () => {
    const wrapper = mount(ReturnsHeatmap, {
      props: {
        mode: 'monthly',
        rows: [
          { period: '2026-05', return_pct: -0.06 },
        ],
        cellDetails: {
          '2026-05': [
            {
              ts: '2026-05-12T05:00:00Z',
              event_type: 'exit',
              position_id: 'MSFT-2026-05-11T05:00:00Z',
              symbol: 'MSFT',
              side: 'long',
              quantity: 1,
              price: 407.57,
              pnl: -6.3,
              pnl_pct: -0.82,
              reason: 'take_profit',
            },
            {
              ts: '2026-05-13T05:00:00Z',
              event_type: 'open_at_end',
              position_id: 'AAPL-2026-05-12T05:00:00Z',
              symbol: 'AAPL',
              side: 'long',
              quantity: 1,
              price: 298.72,
              pnl: 2.77,
              pnl_pct: 0.36,
              reason: 'run_end_mark',
            },
          ],
        },
      },
      attachTo: document.body,
    })

    await wrapper.findAll('.returns-heatmap__cell')[4].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('-0.06% realized')
    expect(wrapper.text()).toContain('Resolved in period')
    expect(wrapper.text()).toContain('Unrealized marks')
    expect(wrapper.text()).toContain('1 open · +0.36% · +$2.77')
    expect(wrapper.text()).toContain('AAPL')
  })

  it('uses a scrollable popover body for dense periods', async () => {
    const denseDetails = Array.from({ length: 14 }, (_, index) => ({
      ts: `2026-05-${String(index + 1).padStart(2, '0')}T05:00:00Z`,
      event_type: 'exit',
      position_id: `SYM${index}-2026-05`,
      symbol: `SYM${index}`,
      side: 'long',
      quantity: 1,
      price: 100 + index,
      pnl: index % 2 === 0 ? 5 : -3,
      pnl_pct: index % 2 === 0 ? 1.2 : -0.7,
      reason: index % 2 === 0 ? 'take_profit' : 'stop_loss',
    }))
    const wrapper = mount(ReturnsHeatmap, {
      props: {
        mode: 'monthly',
        rows: [
          { period: '2026-05', return_pct: 0.3 },
        ],
        cellDetails: {
          '2026-05': denseDetails,
        },
      },
      attachTo: document.body,
    })

    await wrapper.findAll('.returns-heatmap__cell')[4].trigger('mouseenter')
    await flushPromises()

    const popover = wrapper.find('.returns-heatmap__popover')
    const scrollBody = wrapper.find('.returns-heatmap__popover-scroll')
    expect(popover.exists()).toBe(true)
    expect(popover.attributes('style')).toContain('max-block-size')
    expect(scrollBody.exists()).toBe(true)
    expect(wrapper.text()).toContain('SYM13')
  })

  it('shows a no-data message when a period has no closed-position detail', async () => {
    const wrapper = mount(ReturnsHeatmap, {
      props: {
        mode: 'monthly',
        rows: [
          { period: '2026-04', return_pct: 0 },
        ],
      },
      attachTo: document.body,
    })

    await wrapper.findAll('.returns-heatmap__cell')[3].trigger('mouseenter')
    await flushPromises()

    expect(wrapper.text()).toContain('No closed positions were recorded in this period.')
  })
})
