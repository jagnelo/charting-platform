import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import uPlot from 'uplot'
import StudyBarsUPlot from '@/components/workstation/StudyBarsUPlot.vue'
import StudyHistogramUPlot from '@/components/workstation/StudyHistogramUPlot.vue'

class ResizeObserverMock {
  constructor(_callback: () => void) {}
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

type ChartOptions = {
  scales: {
    x: { range: (self: unknown, min: number, max: number) => [number, number] }
    y: { range?: (self: unknown, min: number, max: number) => [number, number]; min?: number }
  }
  plugins: Array<{ hooks: { draw: Array<(instance: unknown) => void> } }>
}

function lastChartOptions(): ChartOptions {
  return vi.mocked(uPlot).mock.calls.at(-1)![0] as unknown as ChartOptions
}

// Minimal stand-in for the uPlot instance that drawBars receives during a draw hook.
function drawInstance(cursorLeft: number) {
  const ctx = { save: vi.fn(), restore: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fillStyle: '', strokeStyle: '', lineWidth: 1 }
  return {
    ctx,
    cursor: { left: cursorLeft, top: 0, idx: null },
    bbox: { left: 0, top: 0, width: 300, height: 100 },
    valToPos: vi.fn((value: number, scale: 'x' | 'y') => (scale === 'y' ? 100 - value : value * 10)),
  }
}

describe('StudyBarsUPlot', () => {
  beforeEach(() => vi.mocked(uPlot).mockClear())

  it('keeps zero inside the y range so bars start from a zero baseline', async () => {
    mount(StudyBarsUPlot, { props: { name: 'monthly_frequency', labels: ['Jan', 'Feb', 'Mar'], values: [2, 3, 5] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const range = lastChartOptions().scales.y.range!
    expect(range(null, 2, 5)).toEqual([0, 5])
    expect(range(null, -4, -1)).toEqual([-4, 0])
    expect(range(null, 0, 0)).toEqual([0, 1])
  })

  it('keeps the first and last bars inside the plot with half a category of padding', async () => {
    mount(StudyBarsUPlot, { props: { name: 'monthly_frequency', labels: ['Jan', 'Feb', 'Mar'], values: [2, 3, 5] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const range = lastChartOptions().scales.x.range
    expect(range(null, 0, 2)).toEqual([-0.5, 2.5])
  })
})

describe('StudyHistogramUPlot', () => {
  beforeEach(() => vi.mocked(uPlot).mockClear())

  const bins = [{ start: 1, end: 2, count: 4 }, { start: 2, end: 3, count: 1 }]

  it('draws the current-value marker only while the pointer is over the plot', async () => {
    mount(StudyHistogramUPlot, { props: { name: 'streak_distribution', bins, current: 2 } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const draw = lastChartOptions().plugins[0]!.hooks.draw[0]!

    const resting = drawInstance(-10)
    draw(resting)
    expect(resting.ctx.stroke).not.toHaveBeenCalled()

    const hovering = drawInstance(50)
    draw(hovering)
    expect(hovering.ctx.stroke).toHaveBeenCalledTimes(1)
  })

  it('keeps the histogram y axis anchored at zero', async () => {
    mount(StudyHistogramUPlot, { props: { name: 'streak_distribution', bins } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    expect(lastChartOptions().scales.y.min).toBe(0)
    await nextTick()
  })
})
