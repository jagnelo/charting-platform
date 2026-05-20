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

    expect(wrapper.text()).toContain('-2.50%')
    expect(wrapper.text()).toContain('+2.50%')
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

    expect(wrapper.text()).toContain('No closed positions or run-end marks were recorded in this period.')
  })
})
