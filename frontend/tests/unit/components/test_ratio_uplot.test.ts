import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
import RatioUPlot from '@/components/workstation/RatioUPlot.vue'

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

describe('RatioUPlot', () => {
  beforeEach(() => vi.mocked(api.get).mockReset())

  it('requests an aligned local ratio and renders its overlap warning', async () => {
    vi.mocked(api.get).mockResolvedValue({
      coverage: 0.8,
      points: [
        { timestamp: '2026-01-01T00:00:00Z', value: 1.1 },
        { timestamp: '2026-01-02T00:00:00Z', value: 1.2 },
      ],
      warnings: [{ message: 'Only intersecting timestamps were used.' }],
    })
    const wrapper = mount(RatioUPlot, { props: { symbol: 'NVDA', benchmark: 'XLK' } })
    await vi.waitFor(async () => {
      await nextTick()
      expect(wrapper.text()).toContain('80% overlap')
    })

    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'NVDA', benchmark: 'XLK', adjusted: true,
    })
    expect(wrapper.text()).toContain('NVDA/XLK')
    expect(wrapper.text()).toContain('Only intersecting timestamps were used.')
  })
})
