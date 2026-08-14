import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import SymbolPerformanceBars from '@/components/strategy/SymbolPerformanceBars.vue'
import uPlot from 'uplot'

class ResizeObserverMock {
  static instances: ResizeObserverMock[] = []
  observed: Element | null = null
  constructor(private readonly callback: ResizeObserverCallback) {
    ResizeObserverMock.instances.push(this)
  }
  observe(element: Element) { this.observed = element }
  disconnect() { this.observed = null }
  trigger() { this.callback([], this as unknown as ResizeObserver) }
}

describe('SymbolPerformanceBars', () => {
  it('renders a symbol P&L outcome map and tooltip on hover', async () => {
    vi.mocked(uPlot).mockClear()
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
          {
            symbol: 'ARM',
            net_pnl: 250,
            total_pnl: 250,
            realized_pnl: 0,
            unrealized_pnl: 250,
            trade_count: 0,
            closed_trade_count: 0,
            open_position_count: 1,
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
          {
            ts: '2026-02-09T00:00:00Z',
            position_id: 'ARM-1',
            event_type: 'open_at_end',
            symbol: 'ARM',
            pnl: 250,
            pnl_pct: 2.5,
            reason: 'run_end_mark',
          },
        ],
      },
    })
    await nextTick()

    expect(wrapper.text()).not.toContain('2 symbols')
    expect(wrapper.text()).not.toContain('Best realized AAPL')
    expect(wrapper.text()).not.toContain('Worst realized MSFT')
    expect(wrapper.text()).toContain('LOSSES')
    expect(wrapper.text()).toContain('BREAKEVEN')
    expect(wrapper.text()).toContain('WINS')
    expect(vi.mocked(uPlot)).toHaveBeenCalled()
    expect(vi.mocked(uPlot).mock.calls.at(-1)?.[0].plugins).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="symbol-pnl-point"]')).toHaveLength(3)
    const unrealizedPoint = wrapper
      .findAll('[data-testid="symbol-pnl-point"]')
      .find(point => point.attributes('aria-label')?.startsWith('ARM '))
    expect(unrealizedPoint?.attributes('fill-opacity')).toBe('0.46')
    expect(unrealizedPoint?.attributes('stroke-dasharray')).toBeUndefined()

    const firstPoint = wrapper.find('[data-testid="symbol-pnl-point"]')
    await firstPoint.trigger('mouseenter')

    expect(document.body.textContent).toContain('50.00% win')
    expect(document.body.textContent).toContain('+15.00% marked')
    expect(document.body.textContent).toContain('+12.50% · +$1,250.45 realized')
    expect(document.body.textContent).toContain('+2.50% · +$250.00 unrealized')
    expect(document.body.textContent).toContain('+$1,500.45 marked value')
    expect(document.body.textContent).toContain('Take Profit')
  })

  it('attaches resize handling when data changes from empty to valid', async () => {
    vi.mocked(uPlot).mockClear()
    ResizeObserverMock.instances.splice(0)
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
    const wrapper = mount(SymbolPerformanceBars, { props: { rows: [] } })
    expect(ResizeObserverMock.instances.at(-1)?.observed).toBeNull()

    await wrapper.setProps({ rows: [{ symbol: 'AAPL', net_pnl: 12, realized_pnl: 12 }] })
    await nextTick()
    await nextTick()

    const observer = ResizeObserverMock.instances.at(-1)
    const chart = vi.mocked(uPlot).mock.results.at(-1)?.value as { setSize: ReturnType<typeof vi.fn> }
    expect(observer?.observed).toBeInstanceOf(HTMLElement)
    chart.setSize.mockClear()
    observer?.trigger()
    expect(chart.setSize).toHaveBeenCalledWith({ width: 640, height: 220 })

    await wrapper.setProps({ rows: [] })
    await nextTick()
    await nextTick()
    expect(observer?.observed).toBeNull()

    await wrapper.setProps({ rows: [{ symbol: 'MSFT', net_pnl: -8, realized_pnl: -8 }] })
    await nextTick()
    await nextTick()
    expect(observer?.observed).toBeInstanceOf(HTMLElement)
    wrapper.unmount()
    vi.unstubAllGlobals()
  })
})
