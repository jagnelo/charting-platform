import { mount as baseMount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiDelete, apiGet, apiPatch, apiPost, apiPut } = vi.hoisted(() => ({ apiDelete: vi.fn(), apiGet: vi.fn(), apiPatch: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { delete: apiDelete, get: apiGet, patch: apiPatch, post: apiPost, put: apiPut } }))

import InstrumentNoteTool from '@/components/workstation/InstrumentNoteTool.vue'
import InstrumentAlertsTool from '@/components/workstation/InstrumentAlertsTool.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}

beforeEach(() => {
  apiGet.mockReset()
  apiDelete.mockReset()
  apiPatch.mockReset()
  apiPost.mockReset()
  apiPut.mockReset()
})

function mount(component: any, options: Record<string, any> = {}) { return baseMount(component, options) }
function mountNote(options: Record<string, any>, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })) {
  return baseMount(InstrumentNoteTool, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
}
function mountAlerts(options: Record<string, any>, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })) {
  return baseMount(InstrumentAlertsTool, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
}

describe('linked instrument tool stale-response guards', () => {
  it('does not let an older note load overwrite the newly selected instrument', async () => {
    const first = deferred<{ content: string; updated_at: string } | null>()
    apiGet.mockImplementation((path: string) => path.endsWith('/1') ? first.promise : Promise.resolve({ content: 'XLK note', updated_at: '2026-08-03T00:00:00Z' }))
    const wrapper = mountNote({ props: { instrumentId: 1, symbol: 'SPY' } })
    expect(wrapper.find('[role="region"][aria-label="SPY notes"]').exists()).toBe(true)
    expect(wrapper.find('.note-tool__status[role="status"]').exists()).toBe(true)
    await wrapper.setProps({ instrumentId: 2, symbol: 'XLK' })
    await vi.waitFor(() => expect(wrapper.get('textarea').element).toHaveProperty('value', 'XLK note'))

    first.resolve({ content: 'stale SPY note', updated_at: '2026-08-02T00:00:00Z' })
    await wrapper.vm.$nextTick()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('XLK note')
  })

  it('does not let an older alerts load overwrite the newly selected instrument', async () => {
    const first = deferred<unknown[]>()
    apiGet.mockImplementation((_path: string, params?: { instrument_id?: number }) => {
      if (params?.instrument_id === 1) return first.promise
      if (_path === '/alerts/price') return Promise.resolve([{ id: 2, condition: 'touches', threshold_price: 9, status: 'active', repeat: false }])
      return Promise.resolve([])
    })
    const wrapper = mountAlerts({ props: { instrumentId: 1, symbol: 'SPY' } })
    await wrapper.setProps({ instrumentId: 2, symbol: 'XLK' })
    await vi.waitFor(() => expect(wrapper.text()).toContain('touches'))

    first.resolve([])
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('touches')
    expect(wrapper.text()).not.toContain('No alerts for XLK.')
  })

  it('does not leave the alerts tool busy when an older mutation completes after relinking', async () => {
    const mutation = deferred<{ id: number; condition: string; threshold_price: number; status: string; repeat: boolean }>()
    apiGet.mockImplementation((_path: string, params?: { instrument_id?: number }) => {
      if (_path === '/alerts/price') return Promise.resolve([{ id: params?.instrument_id ?? 1, condition: 'touches', threshold_price: 9, status: 'active', repeat: false }])
      return Promise.resolve([])
    })
    apiPatch.mockReturnValue(mutation.promise)
    const wrapper = mountAlerts({ props: { instrumentId: 1, symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.get('button[aria-label="Enable repeat for price alert"]')).toBeTruthy())
    await wrapper.get('button[aria-label="Enable repeat for price alert"]').trigger('click')
    await wrapper.setProps({ instrumentId: 2, symbol: 'XLK' })
    expect((wrapper.vm as unknown as { busy: boolean }).busy).toBe(false)

    mutation.resolve({ id: 1, condition: 'touches', threshold_price: 9, status: 'active', repeat: true })
    await wrapper.vm.$nextTick()
    expect((wrapper.vm as unknown as { busy: boolean }).busy).toBe(false)
  })

  it('renders and manages saved EasyScan alerts alongside instrument alerts', async () => {
    apiGet.mockImplementation((_path: string) => {
      if (_path === '/alerts/screener') return Promise.resolve([{ id: 9, screener_id: 4, screener_name: 'Momentum', trigger_type: 'entered', status: 'active', repeat: true }])
      return Promise.resolve([])
    })
    apiPatch.mockResolvedValue({ id: 9, screener_id: 4, screener_name: 'Momentum', trigger_type: 'entered', status: 'paused', repeat: true })
    const wrapper = mountAlerts({ props: { instrumentId: 1, symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Momentum'))
    await wrapper.get('button[aria-label="Pause scan alert"]').trigger('click')
    expect(apiPatch).toHaveBeenCalledWith('/alerts/screener/9', { status: 'paused' })
  })

  it('creates an indicator alert from the primary Alerts tool', async () => {
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({ id: 41, instrument_id: 7, indicator_a_type: 'rsi', condition: 'crosses_below', threshold_value: 30, status: 'active', repeat: true })
    const wrapper = mountAlerts({ props: { instrumentId: 7, symbol: 'SPY', timeframe: 'W1' } })
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Alert type"]')).toBeTruthy())
    await wrapper.get('[aria-label="Alert type"]').setValue('indicator')
    await wrapper.get('[aria-label="Alert indicator"]').setValue('rsi')
    expect(wrapper.get('[aria-label="Alert Period"]').element).toHaveProperty('value', '14')
    expect(wrapper.get('[aria-label="Alert timeframe"]').element).toHaveProperty('value', 'W1')
    await wrapper.get('[aria-label="Indicator threshold"]').setValue('30')
    await wrapper.get('.alerts-tool__repeat input').setValue(true)
    await wrapper.get('form[aria-label="Create instrument alert"]').trigger('submit')
    expect(apiPost).toHaveBeenCalledWith('/alerts/indicator', expect.objectContaining({
      instrument_id: 7,
      timeframe: 'W1',
      indicator_a_type: 'rsi',
      condition: 'crosses_above',
      threshold_value: 30,
      repeat: true,
    }))
  })

  it('supports fixed-value indicator comparison operators', async () => {
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({ id: 42, instrument_id: 7, indicator_a_type: 'rsi', condition: 'lte', threshold_value: 30, status: 'active', repeat: false })
    const wrapper = mountAlerts({ props: { instrumentId: 7, symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Alert type"]')).toBeTruthy())
    await wrapper.get('[aria-label="Alert type"]').setValue('indicator')
    await wrapper.get('select[aria-label="Indicator condition"]').setValue('lte')
    await wrapper.get('[aria-label="Indicator threshold"]').setValue('30')
    await wrapper.get('form[aria-label="Create instrument alert"]').trigger('submit')
    expect(apiPost).toHaveBeenCalledWith('/alerts/indicator', expect.objectContaining({ condition: 'lte', threshold_value: 30 }))
  })

  it('creates an indicator-versus-indicator alert without a fixed threshold', async () => {
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({ id: 43, instrument_id: 7, indicator_a_type: 'ema', indicator_b_type: 'sma', condition: 'crosses_above', status: 'active', repeat: false })
    const wrapper = mountAlerts({ props: { instrumentId: 7, symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Alert type"]')).toBeTruthy())
    await wrapper.get('[aria-label="Alert type"]').setValue('indicator')
    await wrapper.get('[aria-label="Alert indicator"]').setValue('ema')
    await wrapper.get('[aria-label="Indicator target"]').setValue('indicator')
    await wrapper.get('[aria-label="Comparison indicator"]').setValue('sma')
    expect(wrapper.get('[aria-label="Alert comparison Period"]').element).toHaveProperty('value', '20')
    await wrapper.get('[aria-label="Alert comparison Period"]').setValue('50')
    await wrapper.get('form[aria-label="Create instrument alert"]').trigger('submit')
    expect(apiPost).toHaveBeenCalledWith('/alerts/indicator', expect.objectContaining({
      indicator_a_type: 'ema', indicator_b_type: 'sma', condition: 'crosses_above',
      indicator_b_params: { period: 50 },
    }))
    expect(apiPost.mock.calls.at(-1)?.[1]).not.toHaveProperty('threshold_value')
  })

  it('loads global EasyScan alerts before a canonical instrument is selected', async () => {
    apiGet.mockImplementation((_path: string) => {
      if (_path === '/alerts/screener') return Promise.resolve([{ id: 10, screener_id: 5, screener_name: 'Breadth', trigger_type: 'both', status: 'active', repeat: false }])
      return Promise.resolve([])
    })
    const wrapper = mountAlerts({ props: { instrumentId: null, symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Breadth'))
    expect(apiGet).toHaveBeenCalledWith('/alerts/screener')
  })

  it('deduplicates the shared alert bundle across linked tool windows', async () => {
    apiGet.mockImplementation(() => Promise.resolve([]))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const first = mountAlerts({ props: { instrumentId: 7, symbol: 'SPY' } }, queryClient)
    const second = mountAlerts({ props: { instrumentId: 7, symbol: 'SPY' } }, queryClient)
    await vi.waitFor(() => expect(first.text()).toContain('No alerts for SPY.'))
    await vi.waitFor(() => expect(second.text()).toContain('No alerts for SPY.'))
    expect(first.find('[role="region"][aria-label="SPY alerts"]').exists()).toBe(true)
    expect(first.find('.alerts-tool__state[role="status"]').text()).toContain('No alerts for SPY.')
    expect(apiGet.mock.calls.filter(([path]) => path === '/alerts/price')).toHaveLength(1)
    expect(apiGet.mock.calls.filter(([path]) => path === '/alerts/indicator')).toHaveLength(1)
    expect(apiGet.mock.calls.filter(([path]) => path === '/alerts/screener')).toHaveLength(1)
    expect(apiGet.mock.calls.filter(([path]) => String(path).includes('/alerts/history/instrument/7'))).toHaveLength(1)
  })

  it('deduplicates instrument-note hydration across linked tool windows', async () => {
    apiGet.mockResolvedValue({ content: 'Shared note', updated_at: '2026-08-03T00:00:00Z' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const first = mountNote({ props: { instrumentId: 7, symbol: 'SPY' } }, queryClient)
    const second = mountNote({ props: { instrumentId: 7, symbol: 'SPY' } }, queryClient)
    await vi.waitFor(() => expect((first.get('textarea').element as HTMLTextAreaElement).value).toBe('Shared note'))
    await vi.waitFor(() => expect((second.get('textarea').element as HTMLTextAreaElement).value).toBe('Shared note'))
    expect(apiGet).toHaveBeenCalledTimes(1)
  })
})
