import { flushPromises, mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import MarketGaugeTool from '@/components/workstation/MarketGaugeTool.vue'

function mountTool() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return mount(MarketGaugeTool, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
}

describe('MarketGaugeTool', () => {
  beforeEach(() => apiGet.mockReset())
  afterEach(() => Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }))

  it('loads retained scans, refreshes a selected gauge, and shows freshness lineage', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Above 50 day average' }])
      return Promise.resolve({
        screener_id: 7,
        screener_name: 'Above 50 day average',
        matched_count: 4,
        evaluated_count: 8,
        universe_count: 10,
        percentage: 0.5,
        run_at: '2026-08-03T10:00:00Z',
        freshness: 'stale',
        data_provenance: 'canonical_local_database',
        calculation_version: 'analysis-v1',
        refreshed_at: '2026-08-03T10:01:00Z',
        freshness_detail: { requested: 10, current: 0, stale: 8, other: 2 },
        exclusions: [{ code: 'no_history', message: 'Two symbols have no local history.' }],
      })
    })

    const wrapper = mountTool()
    await flushPromises()
    expect(apiGet).toHaveBeenCalledWith('/screeners')

    await wrapper.find('select').setValue('7')
    await flushPromises()
    expect(apiGet).toHaveBeenCalledWith('/analysis/gauges/7')
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('Stale')
    expect(wrapper.text()).toContain('canonical_local_database')
    expect(wrapper.text()).toContain('Coverage warnings: 1')

    const callsBeforeRefresh = apiGet.mock.calls.length
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(apiGet.mock.calls.length).toBeGreaterThan(callsBeforeRefresh)
    expect(apiGet).toHaveBeenCalledWith('/analysis/gauges/7')
  })

  it('does not fetch a selected gauge while the document is hidden', async () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    apiGet.mockResolvedValue([{ id: 7, name: 'Hidden gauge' }])
    const wrapper = mountTool()
    await flushPromises()

    await wrapper.find('select').setValue('7')
    await flushPromises()
    expect(apiGet).not.toHaveBeenCalledWith('/analysis/gauges/7')
  })

  it('surfaces an empty gauge refresh without caching undefined', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Empty gauge' }])
      return Promise.resolve(undefined)
    })

    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Market gauge refresh returned no data'))
  })
})
