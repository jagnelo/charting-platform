import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import StrategyResultChart from '@/components/strategy/StrategyResultChart.vue'

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}

describe('StrategyResultChart', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the empty state when no series exist', () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        series: [],
        label: 'Performance',
        emptyLabel: 'Nothing here yet',
      },
    })

    expect(wrapper.text()).toContain('Nothing here yet')
  })

  it('shows all hovered dense-series items inside the chart, ordered by proximity', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Position evolution',
        focusNearestSeries: true,
        currency: true,
        series: [
          {
            label: 'AAPL #1',
            color: '#64b5f6',
            points: [
              { ts: '2026-01-01T00:00:00Z', value: 0, detail: 'Entry · AAPL', marker: 'entry' },
              { ts: '2026-01-02T00:00:00Z', value: 125.55 },
            ],
          },
          {
            label: 'MSFT #1',
            color: '#e0b35b',
            points: [
              { ts: '2026-01-01T00:00:00Z', value: 0, detail: 'Entry · MSFT', marker: 'entry' },
              { ts: '2026-01-02T00:00:00Z', value: 250.1 },
            ],
          },
        ],
      },
      attachTo: document.body,
    })

    Object.defineProperty(wrapper.find('svg').element, 'getBoundingClientRect', {
      value: () => ({
        left: 0,
        top: 0,
        width: 320,
        height: 164,
        right: 320,
        bottom: 164,
      }),
    })

    await wrapper.find('svg').trigger('mousemove', {
      clientX: 310,
      clientY: 125,
    })

    expect(wrapper.text()).toContain('AAPL #1')
    expect(wrapper.text()).toContain('MSFT #1')
    expect(wrapper.find('.result-chart__hovercard--overlay').exists()).toBe(true)
  })

  it('spaces chart points by real elapsed time instead of equal point count', () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Performance',
        currency: true,
        series: [
          {
            label: 'Strategy',
            color: '#64b5f6',
            points: [
              { ts: '2026-01-01T00:00:00Z', value: 100 },
              { ts: '2026-01-02T00:00:00Z', value: 105 },
              { ts: '2026-01-10T00:00:00Z', value: 120 },
            ],
          },
        ],
      },
    })

    const polyline = wrapper.find('.result-chart__line')
    const points = String(polyline.attributes('points'))
      .split(' ')
      .map(point => point.split(',').map(Number))

    expect(points).toHaveLength(3)
    const firstX = points[0][0]
    const secondX = points[1][0]
    const thirdX = points[2][0]

    expect(secondX - firstX).toBeLessThan(thirdX - secondX)
  })

  it('does not snap hover selection to a future point to the right of the cursor', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Performance',
        currency: true,
        series: [
          {
            label: 'Strategy',
            color: '#64b5f6',
            points: [
              { ts: '2026-01-01T00:00:00Z', value: 100, detail: 'First' },
              { ts: '2026-01-10T00:00:00Z', value: 120, detail: 'Second' },
            ],
          },
        ],
      },
      attachTo: document.body,
    })

    Object.defineProperty(wrapper.find('svg').element, 'getBoundingClientRect', {
      value: () => ({
        left: 0,
        top: 0,
        width: 320,
        height: 164,
        right: 320,
        bottom: 164,
      }),
    })

    await wrapper.find('svg').trigger('mousemove', {
      clientX: 120,
      clientY: 80,
    })

    expect(wrapper.text()).toContain('First')
    expect(wrapper.text()).not.toContain('Second')
  })

  it('supports narrowing a long chart to a shorter visible period', async () => {
    const wrapper = mount(StrategyResultChart, {
      props: {
        label: 'Performance',
        percent: true,
        series: [
          {
            label: 'Strategy',
            color: '#64b5f6',
            points: [
              { ts: '2025-01-01T00:00:00Z', value: 0 },
              { ts: '2025-04-01T00:00:00Z', value: 2.5 },
              { ts: '2025-07-01T00:00:00Z', value: 5.1 },
              { ts: '2025-10-01T00:00:00Z', value: 7.8 },
              { ts: '2026-01-01T00:00:00Z', value: 10.2 },
            ],
          },
        ],
      },
    })

    const fullPoints = String(wrapper.find('.result-chart__line').attributes('points'))
      .split(' ')
      .filter(Boolean)

    expect(wrapper.text()).toContain('All')
    expect(wrapper.findAll('.result-chart__range-button').length).toBeGreaterThan(1)

    const rangeButtons = wrapper.findAll('.result-chart__range-button')
    const threeMonthButton = rangeButtons.find(button => button.text() === '3M')

    expect(threeMonthButton).toBeDefined()
    await threeMonthButton!.trigger('click')

    const zoomedPoints = String(wrapper.find('.result-chart__line').attributes('points'))
      .split(' ')
      .filter(Boolean)

    expect(zoomedPoints.length).toBeLessThan(fullPoints.length)
    expect(wrapper.text()).toContain('→')
  })
})
