import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardAdvancedChartWidget from '@/components/dashboard/DashboardAdvancedChartWidget.vue'
import { usePanelStore } from '@/stores/chart'

const { resolveSymbol } = vi.hoisted(() => ({ resolveSymbol: vi.fn() }))

vi.mock('@/lib/instruments', () => ({
  ensureKnownInstrumentSymbol: resolveSymbol,
}))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

describe('DashboardAdvancedChartWidget lifecycle fencing', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('does not start chart hydration after canonical symbol resolution finishes post-unmount', async () => {
    let resolveTarget!: (symbol: string) => void
    const targetResolved = new Promise<string>(resolve => { resolveTarget = resolve })
    resolveSymbol.mockReturnValueOnce(targetResolved)
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = usePanelStore('dashboard-7')
    const loadBarsSpy = vi.spyOn(store, 'loadBars').mockResolvedValue(undefined)

    const wrapper = mount(DashboardAdvancedChartWidget, {
      props: { widgetId: 7, config: { symbol: 'AAPL' } },
      global: {
        plugins: [pinia],
        stubs: {
          UPlotChart: { template: '<div />' },
          'router-link': { template: '<a><slot /></a>' },
        },
      },
    })

    await Promise.resolve()
    wrapper.unmount()
    resolveTarget('AAPL')
    await Promise.resolve()
    await Promise.resolve()

    expect(loadBarsSpy).not.toHaveBeenCalled()
  })
})
