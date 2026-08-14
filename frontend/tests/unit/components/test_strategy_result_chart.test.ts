import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

interface MockChartInstance {
  opts: any
  data: any
  target: HTMLElement
  cursor: { idx: number | null; left: number | null; top: number | null }
  destroyed: boolean
  scales: Record<string, any>
  triggerCursor: (idx: number | null, left?: number, top?: number) => void
  setScale: (key: string, value: any) => void
  setSize: (value: any) => void
  destroy: () => void
  valToPos: (value: number) => number
}

const { MockUPlot, instances } = vi.hoisted(() => {
  const created: MockChartInstance[] = []
  class MockUPlot {
    opts: any
    data: any
    target: HTMLElement
    cursor = { idx: null as number | null, left: null as number | null, top: null as number | null }
    destroyed = false
    scales: Record<string, any> = {}
    constructor(opts: any, data: any, target: HTMLElement) {
      this.opts = opts
      this.data = data
      this.target = target
      target.innerHTML = '<canvas class="uplot-canvas"></canvas>'
      created.push(this as unknown as MockChartInstance)
    }
    triggerCursor(idx: number | null, left = 100, top = 40) {
      this.cursor = { idx, left, top }
      for (const callback of this.opts.hooks?.setCursor ?? []) callback(this)
    }
    setScale(key: string, value: any) { this.scales[key] = value }
    setSize(_value: any) {}
    destroy() { this.destroyed = true }
    valToPos(value: number) { return value }
  }
  return { MockUPlot, instances: created }
})

vi.mock('uplot', () => ({ default: MockUPlot }))

import StrategyResultChart from '@/components/strategy/StrategyResultChart.vue'

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}

describe('StrategyResultChart', () => {
  beforeEach(() => {
    instances.splice(0)
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the empty state without creating a numerical chart', () => {
    const wrapper = mount(StrategyResultChart, {
      props: { series: [], label: 'Performance', emptyLabel: 'Nothing here yet' },
    })

    expect(wrapper.text()).toContain('Nothing here yet')
    expect(instances).toHaveLength(0)
  })

  it('renders numerical data through uPlot and preserves dense hover details', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Position evolution',
        focusNearestSeries: true,
        currency: true,
        series: [
          { label: 'AAPL #1', color: '#64b5f6', points: [
            { ts: '2026-01-01T00:00:00Z', value: 0, detail: 'Entry · AAPL', marker: 'entry' },
            { ts: '2026-01-02T00:00:00Z', value: 125.55 },
          ] },
          { label: 'MSFT #1', color: '#e0b35b', points: [
            { ts: '2026-01-01T00:00:00Z', value: 0, detail: 'Entry · MSFT', marker: 'entry' },
            { ts: '2026-01-02T00:00:00Z', value: 250.1 },
          ] },
        ],
      },
      attachTo: document.body,
    })
    await nextTick()
    expect(instances).toHaveLength(1)
    instances[0].triggerCursor(1, 310, 125)
    await nextTick()

    expect(wrapper.text()).toContain('AAPL #1')
    expect(wrapper.text()).toContain('MSFT #1')
    expect(wrapper.find('.result-chart__hovercard--overlay').exists()).toBe(true)
    wrapper.unmount()
    expect(instances[0].destroyed).toBe(true)
  })

  it('passes real elapsed timestamps to uPlot instead of equal point indexes', async () => {
    mount(StrategyResultChart, {
      props: {
        label: 'Performance',
        currency: true,
        series: [{ label: 'Strategy', color: '#64b5f6', points: [
          { ts: '2026-01-01T00:00:00Z', value: 100 },
          { ts: '2026-01-02T00:00:00Z', value: 105 },
          { ts: '2026-01-10T00:00:00Z', value: 120 },
        ] }],
      },
    })
    await nextTick()
    const x = instances[0].data[0] as number[]
    expect(x).toHaveLength(3)
    expect(x[1] - x[0]).toBeLessThan(x[2] - x[1])
  })

  it('does not expose a future point when the cursor is on the first point', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Performance',
        currency: true,
        series: [{ label: 'Strategy', color: '#64b5f6', points: [
          { ts: '2026-01-01T00:00:00Z', value: 100, detail: 'First' },
          { ts: '2026-01-10T00:00:00Z', value: 120, detail: 'Second' },
        ] }],
      },
    })
    await nextTick()
    instances[0].triggerCursor(0)
    await nextTick()
    expect(wrapper.text()).toContain('First')
    expect(wrapper.text()).not.toContain('Second')
  })

  it('changes the uPlot x scale when narrowing to a shorter visible range', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Performance',
        percent: true,
        series: [{ label: 'Strategy', color: '#64b5f6', points: [
          { ts: '2025-01-01T00:00:00Z', value: 0 },
          { ts: '2025-04-01T00:00:00Z', value: 2.5 },
          { ts: '2025-07-01T00:00:00Z', value: 5.1 },
          { ts: '2025-10-01T00:00:00Z', value: 7.8 },
          { ts: '2026-01-01T00:00:00Z', value: 10.2 },
        ] }],
      },
    })
    await nextTick()
    const fullRange = instances[0].opts.scales.x
    const rangeButtons = wrapper.findAll('.result-chart__range-button')
    const threeMonthButton = rangeButtons.find(button => button.text() === '3M')
    expect(threeMonthButton).toBeDefined()
    await threeMonthButton!.trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('→')
    expect(instances[0].scales.x.max - instances[0].scales.x.min)
      .toBeLessThan(fullRange.max - fullRange.min)
  })

  it('formats integer-only y-axis values through the uPlot axis formatter', async () => {
    mount(StrategyResultChart, {
      props: {
        label: 'Open positions',
        integerAxis: true,
        series: [{ label: 'Open positions', color: '#e0b35b', points: [
          { ts: '2026-01-01T00:00:00Z', value: 0 },
          { ts: '2026-01-02T00:00:00Z', value: 1 },
          { ts: '2026-01-03T00:00:00Z', value: 2 },
        ] }],
      },
    })
    await nextTick()
    const values = instances[0].opts.axes[1].values(null, [0, 2, 2.4])
    expect(values).toEqual(['0', '2', '2'])
  })

  it('does not create a numerical chart when every runtime value is malformed', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Malformed result',
        series: [{ label: 'Strategy', color: '#64b5f6', points: [
          { ts: '2026-01-01T00:00:00Z', value: Number.NaN },
          { ts: '2026-01-02T00:00:00Z', value: Number.POSITIVE_INFINITY },
        ] }],
      },
    })
    await nextTick()

    expect(instances).toHaveLength(0)
    expect(wrapper.text()).toContain('No chart data available.')
  })

  it('preserves explicit null values as gaps instead of coercing them to zero', async () => {
    mount(StrategyResultChart, {
      props: {
        label: 'Partial result',
        series: [{ label: 'Strategy', color: '#64b5f6', points: [
          { ts: '2026-01-01T00:00:00Z', value: null as unknown as number },
          { ts: '2026-01-02T00:00:00Z', value: 2 },
        ] }],
      },
    })
    await nextTick()

    expect(instances).toHaveLength(1)
    expect(instances[0].data[1]).toEqual([null, 2])
  })
})
