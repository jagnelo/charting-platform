import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardEconomicCalendarWidget from '@/components/dashboard/DashboardEconomicCalendarWidget.vue'
import DashboardSeasonalityWidget from '@/components/dashboard/DashboardSeasonalityWidget.vue'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

import { api } from '@/lib/api'

describe('dashboard analytics widget lifecycle fencing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('does not publish a late economic-calendar response after unmount', async () => {
    let resolveEvents!: (events: any[]) => void
    const eventsLoaded = new Promise<any[]>(resolve => { resolveEvents = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce(eventsLoaded)
    const wrapper = mount(DashboardEconomicCalendarWidget, {
      props: { config: { symbol: 'AAPL' } },
    })

    await Promise.resolve()
    const vm = wrapper.vm as unknown as { events: any[]; loading: boolean }
    wrapper.unmount()
    resolveEvents([{ date: '2026-05-01', event_type: 'earnings', symbol: 'AAPL', title: 'Results', is_estimate: false }])
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.events).toEqual([])
    expect(vm.loading).toBe(true)
  })

  it('does not publish a late seasonality response after unmount', async () => {
    let resolveSeasonality!: (response: any) => void
    const seasonalityLoaded = new Promise(resolve => { resolveSeasonality = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce(seasonalityLoaded)
    const wrapper = mount(DashboardSeasonalityWidget, {
      props: { config: { symbol: 'AAPL' } },
    })

    await Promise.resolve()
    const vm = wrapper.vm as unknown as { months: any[]; loading: boolean; selectedMonth: unknown }
    wrapper.unmount()
    resolveSeasonality({ symbol: 'AAPL', months: [{ month: 1, label: 'Jan', sample_count: 1, records: [] }] })
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.months).toEqual([])
    expect(vm.selectedMonth).toBe(null)
    expect(vm.loading).toBe(true)
  })
})
