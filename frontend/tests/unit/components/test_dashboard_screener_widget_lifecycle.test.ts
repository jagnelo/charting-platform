import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardScreenerWidget from '@/components/dashboard/DashboardScreenerWidget.vue'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

import { api } from '@/lib/api'

describe('DashboardScreenerWidget lifecycle fencing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('does not publish a late screener list after the widget unmounts', async () => {
    let resolveScreeners!: (screeners: any[]) => void
    const screenersLoaded = new Promise<any[]>(resolve => { resolveScreeners = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementationOnce(() => screenersLoaded)
    const wrapper = mount(DashboardScreenerWidget, {
      props: { config: {} },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })

    await Promise.resolve()
    const vm = wrapper.vm as unknown as { screeners: any[]; loading: boolean }
    wrapper.unmount()
    resolveScreeners([{ id: 1, name: 'Late', timeframe: 'D1' }])
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.screeners).toEqual([])
    expect(vm.loading).toBe(true)
  })

  it('does not publish late instrument metadata after a result request is superseded', async () => {
    let resolveInfo!: (response: any) => void
    const infoLoaded = new Promise(resolve => { resolveInfo = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url === '/screeners') return Promise.resolve([{ id: 1, name: 'Screen', timeframe: 'D1' }])
      if (url === '/screeners/1/results') return Promise.resolve([{ id: 3, screener_id: 1, result_data: {}, matched_ids: [7], run_at: '2026-05-01T00:00:00Z' }])
      if (url === '/instruments/browse') return infoLoaded
      return Promise.resolve([])
    })
    const wrapper = mount(DashboardScreenerWidget, {
      props: { config: { screenerId: 1 } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/instruments/browse', expect.anything()))
    const vm = wrapper.vm as unknown as { instrumentMap: Record<number, unknown> }
    wrapper.setProps({ config: { screenerId: 1, revision: 2 } })
    wrapper.unmount()
    resolveInfo({ items: [{ id: 7, symbol: 'AAPL', name: 'Apple' }] })
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.instrumentMap).toEqual({})
  })
})
