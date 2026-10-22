import { nextTick, ref, watch } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { IndicatorConfig } from '@/types'
import { watchIndicatorStack } from '@/lib/uplot/indicatorLifecycle'

const indicator = (): IndicatorConfig => ({
  type: 'rsi',
  params: { length: 14 },
  style: { color: '#7e57c2', lineWidth: 1 },
  pane: 'separate',
})

describe('uPlot indicator rebuild lifecycle', () => {
  function lifecycleHarness(initial: IndicatorConfig[]) {
    const activeIndicators = ref<IndicatorConfig[]>(initial)
    const charts = [{ destroy: vi.fn() }]
    const rebuild = vi.fn(() => {
      charts.at(-1)?.destroy()
      charts.push({ destroy: vi.fn() })
    })
    const stop = watchIndicatorStack(() => activeIndicators.value, rebuild)
    return { activeIndicators, charts, rebuild, stop }
  }

  async function flushIndicatorWatch() {
    await nextTick()
    await nextTick()
  }

  it('preserves the renderer for equivalent fresh arrays regardless of object key order', async () => {
    const initial = indicator()
    initial.params = { length: 14, source: 'close' }
    const { activeIndicators, charts, rebuild, stop } = lifecycleHarness([initial])
    const legacyDeepRebuild = vi.fn()
    const stopLegacy = watch(() => activeIndicators.value, legacyDeepRebuild, { deep: true })
    const originalChart = charts[0]

    activeIndicators.value = [{
      pane: 'separate',
      style: { lineWidth: 1, color: '#7e57c2' },
      params: { source: 'close', length: 14 },
      type: 'rsi',
    }]
    await flushIndicatorWatch()

    // The old deep watcher rebuilds on this fresh array despite equal config;
    // the semantic watcher must preserve the active renderer instead.
    expect(legacyDeepRebuild).toHaveBeenCalledTimes(1)
    expect(rebuild).not.toHaveBeenCalled()
    expect(charts).toHaveLength(1)
    expect(originalChart.destroy).not.toHaveBeenCalled()
    stop()
    stopLegacy()
  })

  it('rebuilds for in-place nested parameter and style changes', async () => {
    const { activeIndicators, charts, rebuild, stop } = lifecycleHarness([indicator()])
    const originalChart = charts[0]

    activeIndicators.value[0].params.length = 21
    await flushIndicatorWatch()
    expect(rebuild).toHaveBeenCalledTimes(1)
    expect(originalChart.destroy).toHaveBeenCalledTimes(1)

    activeIndicators.value[0].style.color = '#42a5f5'
    await flushIndicatorWatch()
    expect(rebuild).toHaveBeenCalledTimes(2)
    expect(charts).toHaveLength(3)
    stop()
  })

  it('rebuilds for indicator additions, removals, and reorderings', async () => {
    const first = indicator()
    const second: IndicatorConfig = {
      type: 'ema',
      params: { length: 20 },
      style: { color: '#26a69a', lineWidth: 2 },
      pane: 'main',
    }
    const { activeIndicators, charts, rebuild, stop } = lifecycleHarness([first, second])

    activeIndicators.value = [first, second, { ...indicator(), params: { length: 7 } }]
    await flushIndicatorWatch()
    activeIndicators.value = [first, second]
    await flushIndicatorWatch()
    activeIndicators.value = [second, first]
    await flushIndicatorWatch()

    expect(rebuild).toHaveBeenCalledTimes(3)
    expect(charts).toHaveLength(4)
    stop()
  })
})
