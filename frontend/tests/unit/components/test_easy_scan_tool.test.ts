import { flushPromises, mount as vueMount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut } }))

function savedScreener(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    name: `Scan ${id}`,
    universe_type: 'all',
    universe_watchlist_id: null,
    universe_asset_class_id: null,
    universe_basket_id: null,
    universe_instrument_ids: null,
    timeframe: 'D1',
    conditions: { type: 'python_condition', code_version_id: 42 },
    schedule: null,
    is_active: true,
    updated_at: '2026-11-07T10:00:00Z',
    ...overrides,
  }
}

function screenerPreparationResponse(screenerId: number, status: 'ready' | 'unavailable' = 'ready') {
  const now = '2026-11-07T10:00:00Z'
  return {
    request_id: `screener-${screenerId}`,
    status,
    created_at: now,
    updated_at: now,
    version: 1,
    target: { kind: 'screener', screener_id: screenerId },
    dependencies: [],
    completed: 1,
    total: 1,
    last_progress_at: now,
    has_pending_work: false,
  }
}

import EasyScanTool from '@/components/workstation/EasyScanTool.vue'
import { CHART_PLOT_DRAG_MIME, createChartPlotDragPayload, writeChartPlotDrag } from '@/lib/workstation/plotDrag'

function mount(component: typeof EasyScanTool, options: Parameters<typeof vueMount>[1] = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return vueMount(component, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }]] } })
}

describe('EasyScanTool', () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset() })

  it('announces the idle EasyScan state politely', async () => {
    apiGet.mockResolvedValue([])
    const wrapper = mount(EasyScanTool)
    await flushPromises()

    const state = wrapper.get('.easy-scan__state')
    expect(state.text()).toContain('Save a price/volume condition')
    expect(state.attributes('role')).toBe('status')
    expect(state.attributes('aria-live')).toBe('polite')
    expect(state.attributes('aria-atomic')).toBe('true')
    wrapper.unmount()
  })

  it('announces condition-loading failures assertively', async () => {
    apiGet.mockRejectedValueOnce(new Error('Condition library unavailable'))
    const wrapper = mount(EasyScanTool)
    await vi.waitFor(() => expect(wrapper.get('.easy-scan__error').text()).toBe('Condition library unavailable'))

    const error = wrapper.get('.easy-scan__error')
    expect(error.attributes('role')).toBe('alert')
    expect(error.attributes('aria-live')).toBe('assertive')
    expect(error.attributes('aria-atomic')).toBe('true')
    wrapper.unmount()
  })

  it('announces condition-save progress politely', async () => {
    let resolveSave!: (value: unknown) => void
    apiGet.mockResolvedValue([])
    apiPut.mockImplementationOnce(() => new Promise(resolve => { resolveSave = resolve }))
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('input[aria-label="Condition name"]').setValue('Close condition')
    await wrapper.get('input[aria-label="Condition threshold"]').setValue('100')
    await wrapper.findAll('button').find(button => button.text() === 'Save')!.trigger('click')

    const state = wrapper.get('.easy-scan__state')
    expect(state.text()).toContain('Saving condition…')
    expect(state.attributes('role')).toBe('status')
    expect(state.attributes('aria-live')).toBe('polite')
    expect(state.attributes('aria-atomic')).toBe('true')
    resolveSave({ stable_key: 'close-condition', name: 'Close condition', version: 1, payload: { condition: {} } })
    await flushPromises()
    wrapper.unmount()
  })

  it('opens the advanced condition builder with semantic state and restores toggle focus', async () => {
    apiGet.mockResolvedValue([])
    const wrapper = mount(EasyScanTool, { attachTo: document.body })
    await flushPromises()
    const toggle = wrapper.get('button.easy-scan__advanced-toggle')
    await toggle.trigger('click')
    const advanced = wrapper.get('[role="region"][aria-label="Advanced technical condition builder"]')
    expect(wrapper.get('[aria-label="Technical condition tree"]')).toBeTruthy()
    expect(toggle.attributes('aria-expanded')).toBe('true')
    const advancedId = toggle.attributes('aria-controls')
    expect(advancedId).toBeTruthy()
    expect(advanced.attributes('id')).toBe(advancedId)
    expect(document.activeElement).toBe(advanced.find('select, input, button').element)
    await toggle.trigger('click')
    expect(document.activeElement).toBe(toggle.element)
    expect(toggle.attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('creates and runs a saved Python condition through the queued scan API', async () => {
    const invalidateQueries = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    const setQueryData = vi.spyOn(QueryClient.prototype, 'setQueryData')
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') {
        return Promise.resolve([{ kind: 'condition', name: 'Qualifies', versions: [{ id: 42, version_number: 1, output_contract: 'boolean' }] }])
      }
      if (path === '/screeners/7') return Promise.resolve(savedScreener(7, { conditions: { type: 'python_condition', code_version_id: 42 } }))
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-python-condition/42') return Promise.resolve({ id: 7 })
      if (path === '/screeners/7/run') {
        return Promise.resolve({ matched_ids: [11], result_data: { _status: 'completed', _coverage: { evaluated_count: 1, universe_count: 1, excluded: [] } }, error: null })
      }
      if (path === '/alerts/screener') return Promise.resolve({ id: 8 })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Python condition"]').setValue('42')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Qualifies scan')
    const runButton = wrapper.findAll('button').find(button => button.text() === 'Run')
    expect(runButton).toBeDefined()
    await runButton!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/42', {
      name: 'Qualifies scan',
      universe_type: 'all',
      timeframe: 'D1',
    }, expect.objectContaining({ priority: 'high' }))
    expect(apiPost).toHaveBeenCalledWith('/screeners/7/run', {}, expect.objectContaining({ priority: 'high' }))
    expect(setQueryData).toHaveBeenCalledWith(['workstation', 'screeners'], expect.any(Function))
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['workstation', 'screeners'] })
    expect(wrapper.text()).toContain('1 matches')
    expect(wrapper.text()).toContain('1/1 evaluated')
    const alertButton = wrapper.findAll('button').find(button => button.text() === 'Alert')
    expect(alertButton).toBeDefined()
    await alertButton!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 7, trigger_type: 'entered', repeat: true }, expect.objectContaining({ priority: 'high' }))
    expect(wrapper.text()).toContain('Alert active')
    invalidateQueries.mockRestore()
    setQueryData.mockRestore()
  })

  it('starts local scan evaluation without waiting for an unrelated saved-screener list refresh', async () => {
    let finishScreenersInvalidation!: () => void
    const screenersInvalidation = new Promise<void>(resolve => { finishScreenersInvalidation = resolve })
    const invalidateQueries = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
      .mockImplementation(() => screenersInvalidation as any)
    const refetchQueries = vi.spyOn(QueryClient.prototype, 'refetchQueries').mockResolvedValue([] as any)
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{
        stable_key: 'fast-local-run', name: 'Fast local run', version: 1,
        payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } },
      }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/44') return Promise.resolve(savedScreener(44, {
        conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 },
      }))
      if (path === '/screeners/44/results') return Promise.resolve([{
        id: 4401, matched_ids: [11], result_data: { _status: 'completed', _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null,
      }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-condition/fast-local-run') return Promise.resolve({ id: 44 })
      if (path === '/screeners/44/run') return Promise.resolve({
        id: 4401, matched_ids: [11], result_data: { _status: 'completed', _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null,
      })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    try {
      await flushPromises()
      await wrapper.get('select[aria-label="Saved condition"]').setValue('fast-local-run')
      await wrapper.get('input[aria-label="Scan name"]').setValue('Fast local run')
      await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')

      await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/screeners/44/run', {}, expect.objectContaining({ priority: 'high' })))
      await vi.waitFor(() => expect(wrapper.find('.easy-scan__result').exists()).toBe(true))
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['workstation', 'screeners'] })
      expect(refetchQueries).not.toHaveBeenCalled()

      finishScreenersInvalidation()
      await vi.waitFor(() => expect(refetchQueries).toHaveBeenCalledWith({ queryKey: ['workstation', 'screeners'], type: 'all' }))
      await vi.waitFor(() => expect(wrapper.text()).toContain('1 matches'))
    } finally {
      wrapper.unmount()
      invalidateQueries.mockRestore()
      refetchQueries.mockRestore()
    }
  })

  it('runs cached scan coverage immediately while one saved-screener preparation continues', async () => {
    apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset()
    const ensureResolvers = new Map<number, (value: unknown) => void>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'custom-run', name: 'Custom run', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/31') return Promise.resolve(savedScreener(31, {
        universe_type: 'custom', universe_instrument_ids: [11, 12], conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 },
      }))
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') {
        expect(body).toMatchObject({ target: { kind: 'screener', screener_id: 31 }, datasets: ['history'], timeframe: 'D1' })
        return new Promise(resolve => ensureResolvers.set(31, resolve))
      }
      if (path === '/screeners/from-condition/custom-run') return Promise.resolve({ id: 31 })
      if (path === '/screeners/31/run') return Promise.resolve({ matched_ids: [11], result_data: { _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('custom-run')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Custom run')
    await wrapper.get('select[aria-label="Scan universe"]').setValue('custom')
    await wrapper.get('input[aria-label="Scan universe value"]').setValue('11, 12, 11')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')

    await vi.waitFor(() => expect(ensureResolvers.size).toBe(1))
    expect(apiPost).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'screener', screener_id: 31 }, datasets: ['history'], timeframe: 'D1',
    }, expect.any(Object))
    expect(apiPost).toHaveBeenCalledWith('/screeners/31/run', {}, expect.objectContaining({ priority: 'high' }))

    ensureResolvers.forEach(resolve => resolve(screenerPreparationResponse(31)))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Requested data is ready. Scan coverage will report any missing local data.'))
    wrapper.unmount()
  })

  it('refreshes the exact saved scan when a new preparation version arrives', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'partial-run', name: 'Partial run', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/34') return Promise.resolve(savedScreener(34, { conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      if (path.startsWith('/data/requests/')) return Promise.resolve({ ...screenerPreparationResponse(34), version: 2 })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/screeners/from-condition/partial-run') return Promise.resolve({ id: 34 })
      if (path === '/data/ensure') return Promise.resolve({ ...screenerPreparationResponse(34), status: 'queued', completed: 0, total: 1, has_pending_work: true })
      if (path === '/screeners/34/run') return Promise.resolve({ matched_ids: [34], result_data: { _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null })
      return Promise.resolve({})
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('partial-run')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Partial run')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(apiPost.mock.calls.filter(([path]) => path === '/screeners/34/run').length).toBeGreaterThanOrEqual(2), { timeout: 2_500 })
    expect(wrapper.text()).toContain('1 matches')
    expect(apiPost).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'screener', screener_id: 34 }, datasets: ['history'], timeframe: 'D1',
    }, expect.any(Object))
    wrapper.unmount()
  })

  it('cancels saved-screener preparation when the scan tool is closed', async () => {
    apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset()
    let requestSignal: AbortSignal | undefined
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'close-run', name: 'Close run', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/41') return Promise.resolve(savedScreener(41, { universe_type: 'custom', universe_instrument_ids: [41], conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, _body?: any, options?: { signal?: AbortSignal }) => {
      if (path === '/data/ensure') {
        requestSignal = options?.signal
        return new Promise(() => {})
      }
      if (path === '/screeners/from-condition/close-run') return Promise.resolve({ id: 41 })
      if (path === '/screeners/41/run') return Promise.resolve({ matched_ids: [], result_data: { _coverage: { evaluated_count: 0, universe_count: 0, excluded: {} } }, error: null })
      return Promise.resolve({})
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('close-run')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Close run')
    await wrapper.get('select[aria-label="Scan universe"]').setValue('custom')
    await wrapper.get('input[aria-label="Scan universe value"]').setValue('41')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(requestSignal).toBeDefined())

    wrapper.unmount()
    await vi.waitFor(() => expect(requestSignal?.aborted).toBe(true), { timeout: 1_000 })
    expect(apiPost).toHaveBeenCalledWith('/screeners/41/run', {}, expect.objectContaining({ priority: 'high' }))
  })

  it('prepares the saved watchlist scan definition without client-side member fan-out', async () => {
    apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'watch-run', name: 'Watch run', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/32') return Promise.resolve(savedScreener(32, { universe_type: 'watchlist', universe_watchlist_id: 8, conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id, 'unavailable'))
      if (path === '/screeners/from-condition/watch-run') return Promise.resolve({ id: 32 })
      if (path === '/screeners/32/run') return Promise.resolve({ matched_ids: [], result_data: { _coverage: { evaluated_count: 1, universe_count: 2, excluded: { history: 1 } } }, error: null })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('watch-run')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Watch run')
    await wrapper.get('select[aria-label="Scan universe"]').setValue('watchlist')
    await wrapper.get('input[aria-label="Scan universe value"]').setValue('8')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'screener', screener_id: 32 }, datasets: ['history'], timeframe: 'D1',
    }, expect.any(Object))
    expect(apiPost).toHaveBeenCalledWith('/screeners/32/run', {}, expect.objectContaining({ priority: 'high' }))
    expect(wrapper.text()).toContain('Some requested data is unavailable')
    expect(wrapper.text()).toContain('1/2 evaluated')
    wrapper.unmount()
  })

  it('prepares the saved all-instruments definition through one owner-scoped target', async () => {
    apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'all-run', name: 'All run', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/screeners/33') return Promise.resolve(savedScreener(33, { conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-condition/all-run') return Promise.resolve({ id: 33 })
      if (path === '/screeners/33/run') return Promise.resolve({ matched_ids: [], result_data: { _coverage: { evaluated_count: 0, universe_count: 0, excluded: {} } }, error: null })
      return Promise.resolve({})
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('all-run')
    await wrapper.get('input[aria-label="Scan name"]').setValue('All run')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'screener', screener_id: 33 }, datasets: ['history'], timeframe: 'D1',
    }, expect.any(Object))
    expect(wrapper.text()).toContain('Requested data is ready. Scan coverage will report any missing local data.')
    wrapper.unmount()
  })

  it('exposes cancellation for a queued isolated Python scan', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Queued', versions: [{ id: 43, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/screeners/8') return Promise.resolve(savedScreener(8, { conditions: { type: 'python_condition', code_version_id: 43 } }))
      if (path === '/screeners/8/results') return Promise.resolve([{ matched_ids: [], result_data: { _status: 'canceled', _python_research_run_id: 99 }, error: null }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-python-condition/43') return Promise.resolve({ id: 8 })
      if (path === '/screeners/8/run') return Promise.resolve({ matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 99 }, error: null })
      if (path === '/research/runs/99/cancel') return Promise.resolve({ status: 'canceled' })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Python condition"]').setValue('43')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Queued scan')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()

    const cancel = wrapper.findAll('button').find(button => button.text() === 'Cancel')
    expect(cancel).toBeDefined()
    await cancel!.trigger('click')
    expect(apiPost).toHaveBeenCalledWith('/research/runs/99/cancel', {}, expect.objectContaining({ priority: 'high' }))
  })

  it('keeps a queued Python research run alive when the EasyScan tool is unmounted', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Queued teardown', versions: [{ id: 44, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/screeners/12') return Promise.resolve(savedScreener(12, { conditions: { type: 'python_condition', code_version_id: 44 } }))
      if (path === '/screeners/12/results') return Promise.resolve([{ matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 100 }, error: null }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-python-condition/44') return Promise.resolve({ id: 12 })
      if (path === '/screeners/12/run') return Promise.resolve({ matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 100 }, error: null })
      if (path === '/research/runs/100/cancel') return Promise.resolve({ status: 'canceled' })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Python condition"]').setValue('44')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Queued teardown scan')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Cancel'))
    wrapper.unmount()
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs/100/cancel')).toBe(false)
  })

  it('does not cancel a Python run when the tool unmounts after completed results are visible', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Completed', versions: [{ id: 45, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/screeners/14') return Promise.resolve(savedScreener(14, { conditions: { type: 'python_condition', code_version_id: 45 } }))
      if (path === '/screeners/14/results') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-python-condition/45') return Promise.resolve({ id: 14 })
      if (path === '/screeners/14/run') return Promise.resolve({
        matched_ids: [99], result_data: { _status: 'completed', _python_research_run_id: 74, _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null,
      })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Python condition"]').setValue('45')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Completed scan')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.get('.easy-scan__state').text()).toContain('Scan completed.'))
    expect(wrapper.text()).toContain('1 matches')

    wrapper.unmount()
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs/74/cancel')).toBe(false)
  })

  it('saves an advanced technical condition tree through the shared condition contract', async () => {
    apiGet.mockResolvedValue([])
    apiPut.mockResolvedValue({ stable_key: 'rsi-tree', name: 'RSI tree', version: 1, payload: { condition: {} } })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('button.easy-scan__advanced-toggle').trigger('click')
    await wrapper.get('input[aria-label="Condition name"]').setValue('RSI tree')
    await wrapper.get('.easy-scan__advanced header select[aria-label="Condition group operator"]').setValue('OR')
    await wrapper.get('.easy-scan__advanced .tech-cond-card select.form-select').setValue('indicator_threshold')
    await wrapper.findAll('button').find(button => button.text() === 'Save')!.trigger('click')
    await flushPromises()

    expect(apiPut).toHaveBeenCalledWith('/workspaces/library/conditions/rsi-tree', expect.objectContaining({
      name: 'RSI tree',
      condition: expect.objectContaining({ operator: 'OR', conditions: [expect.objectContaining({ type: 'indicator_threshold' })] }),
    }), expect.objectContaining({ priority: 'high' }))
  })

  it('uses the immutable Python version returned by a visual save for the first scan run', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners') return Promise.resolve([])
      if (path === '/screeners/17') return Promise.resolve(savedScreener(17, { conditions: { type: 'python_condition', code_version_id: 77 } }))
      if (path === '/screeners/17/results') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiPut.mockResolvedValue({
      stable_key: 'visual-close',
      name: 'Visual close',
      version: 1,
      payload: { condition: {}, python_code_version_id: 77 },
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-python-condition/77') return Promise.resolve({ id: 17 })
      if (path === '/screeners/17/run') return Promise.resolve({ matched_ids: [], result_data: { _status: 'completed', _coverage: { evaluated_count: 0, universe_count: 0, excluded: [] } }, error: null })
      return Promise.resolve({})
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('input[aria-label="Condition name"]').setValue('Visual close')
    await wrapper.get('input[aria-label="Condition threshold"]').setValue('100')
    await wrapper.findAll('button').find(button => button.text() === 'Save')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/77', {
      name: 'Visual close Scan', universe_type: 'all', timeframe: 'D1',
    }, expect.objectContaining({ priority: 'high' }))
  })

  it('follows a queued visual-condition run and keeps the last completed result until completion', async () => {
    let runCount = 0
    let replacementQueued = false
    let resolveQueuedPoll!: (value: unknown) => void
    const queuedPoll = new Promise(resolve => { resolveQueuedPoll = resolve })
    apiGet.mockImplementation((path: string, options?: { limit?: number }) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{
        stable_key: 'visual-saved', name: 'Visual saved', version: 1,
        payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 }, python_code_version_id: 77 },
      }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/6') return Promise.resolve(savedScreener(6, { conditions: { type: 'python_condition', code_version_id: 77 } }))
      if (path === '/screeners/6/results' && options?.limit === 20) return replacementQueued
        ? queuedPoll
        : Promise.resolve([{ id: 70, matched_ids: [3], result_data: { _status: 'completed', _python_research_run_id: 71, _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null }])
      if (path === '/screeners/6/results') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/screeners/from-condition/visual-saved') return Promise.resolve({ id: 6 })
      if (path === '/screeners/6/run') {
        runCount += 1
        if (runCount === 1) return Promise.resolve({ matched_ids: [3], result_data: { _status: 'completed', _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null })
        replacementQueued = true
        return Promise.resolve({ matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 72 }, error: null })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('visual-saved')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Visual saved scan')
    expect((wrapper.get('select[aria-label="Python condition"]').element as HTMLSelectElement).value).toBe('')

    const runButton = () => wrapper.findAll('button').find(button => button.text() === 'Run')!
    await runButton().trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('1 matches'))
    expect(wrapper.text()).toContain('1/1 evaluated')
    await vi.waitFor(() => expect((runButton().element as HTMLButtonElement).disabled).toBe(false))
    await runButton().trigger('click')
    await vi.waitFor(() => expect(apiPost.mock.calls.filter(([path]) => path === '/screeners/6/run')).toHaveLength(2))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Scan queued; waiting for results…'))
    expect(wrapper.text()).toContain('1 matches')
    expect(wrapper.text()).toContain('1/1 evaluated')
    expect(wrapper.text()).not.toContain('0 matches')

    resolveQueuedPoll([{ matched_ids: [11], result_data: { _status: 'completed', _python_research_run_id: 72, _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null }])
    await vi.waitFor(() => expect(wrapper.text()).toContain('Scan completed.'))
    expect(wrapper.text()).toContain('1 matches')
    expect(apiPost).toHaveBeenCalledWith('/screeners/6/run', {}, expect.objectContaining({ priority: 'high' }))
    wrapper.unmount()
  })

  it('follows a preparation-triggered replacement run and preserves the completed result until its matching coverage arrives', async () => {
    let runCount = 0
    let replacementSubmitted = false
    let replacementPolls = 0
    let resolveReplacement!: (value: unknown) => void
    const replacementCompletion = new Promise(resolve => { resolveReplacement = resolve })
    const originalCompleted = {
      id: 70, matched_ids: [3], result_data: { _status: 'completed', _python_research_run_id: 71, _coverage: { evaluated_count: 1, universe_count: 1, excluded: {} } }, error: null,
    }
    const replacementQueued = {
      id: 72, matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 73 }, error: null,
    }
    const replacementCompleted = {
      id: 72, matched_ids: [3, 4], result_data: { _status: 'completed', _python_research_run_id: 73, _coverage: { evaluated_count: 2, universe_count: 2, excluded: {} } }, error: null,
    }
    apiGet.mockImplementation((path: string, options?: { limit?: number }) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{
        stable_key: 'visual-saved', name: 'Visual saved', version: 1,
        payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 }, python_code_version_id: 77 },
      }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/6') return Promise.resolve(savedScreener(6, { conditions: { type: 'python_condition', code_version_id: 77 } }))
      if (path.startsWith('/data/requests/')) return Promise.resolve({ ...screenerPreparationResponse(6), status: 'partial', version: 2, has_pending_work: false })
      if (path === '/screeners/6/results' && options?.limit === 20) {
        if (!replacementSubmitted) return Promise.resolve([originalCompleted])
        replacementPolls += 1
        return replacementPolls === 1 ? Promise.resolve([replacementQueued, originalCompleted]) : replacementCompletion
      }
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/screeners/from-condition/visual-saved') return Promise.resolve({ id: 6 })
      if (path === '/data/ensure') return Promise.resolve({ ...screenerPreparationResponse(6), status: 'queued', completed: 0, total: 1, has_pending_work: true })
      if (path === '/screeners/6/run') {
        runCount += 1
        if (runCount === 1) return Promise.resolve(originalCompleted)
        replacementSubmitted = true
        return Promise.resolve(replacementQueued)
      }
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('visual-saved')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Visual saved scan')
    const runButton = () => wrapper.findAll('button').find(button => button.text() === 'Run')!
    await runButton().trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('1/1 evaluated'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Scan queued; waiting for results…'), { timeout: 3_000 })
    expect(wrapper.text()).toContain('1 matches')
    expect(wrapper.text()).toContain('1/1 evaluated')
    expect(wrapper.text()).not.toContain('0 matches')

    const completedHistory = [replacementCompleted, originalCompleted]
    await vi.waitFor(() => expect(replacementPolls).toBeGreaterThanOrEqual(2))
    resolveReplacement(completedHistory)
    await vi.waitFor(() => expect(wrapper.text()).toContain('2/2 evaluated'))
    expect(wrapper.text()).toContain('2 matches')
    expect(wrapper.text()).toContain('Scan completed.')
    wrapper.unmount()
  })

  it('keeps a queued visual-condition run alive while fencing its unmounted observer', async () => {
    let resolvePoll!: (value: unknown) => void
    const pendingPoll = new Promise(resolve => { resolvePoll = resolve })
    apiGet.mockImplementation((path: string, options?: { limit?: number }) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{
        stable_key: 'visual-pending', name: 'Visual pending', version: 1,
        payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 }, python_code_version_id: 78 },
      }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/7') return Promise.resolve(savedScreener(7, { conditions: { type: 'python_condition', code_version_id: 78 } }))
      if (path === '/screeners/7/results' && options?.limit === 20) return pendingPoll
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/screeners/from-condition/visual-pending') return Promise.resolve({ id: 7 })
      if (path === '/screeners/7/run') return Promise.resolve({ matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 73 }, error: null })
      return Promise.resolve({})
    })

    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('visual-pending')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Visual pending scan')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/screeners/7/results', { limit: 20 }, expect.objectContaining({
      priority: 'high', queueKey: 'easy-scan:poll:7', signal: expect.any(AbortSignal),
    })))

    wrapper.unmount()
    resolvePoll([{ matched_ids: [99], result_data: { _status: 'completed', _python_research_run_id: 73 }, error: null }])
    await flushPromises()
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs/73/cancel')).toBe(false)
    expect(apiPost.mock.calls.filter(([path]) => path === '/screeners/7/run')).toHaveLength(1)
  })

  it('accepts a chart plot drop into the technical condition editor', async () => {
    apiGet.mockResolvedValue([])
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    const values = new Map<string, string>()
    const dataTransfer = {
      types: ['application/x-charting-platform-plot'],
      setData: (type: string, value: string) => values.set(type, value),
      getData: (type: string) => values.get(type) ?? '',
      effectAllowed: '',
    } as unknown as DataTransfer
    writeChartPlotDrag(dataTransfer, createChartPlotDragPayload({ type: 'rsi', params: { period: 14 }, style: { color: '#fff', lineWidth: 1 }, pane: 'separate' }, 'D1', 'chart-source'))

    await wrapper.get('.easy-scan').trigger('drop', { dataTransfer })
    await flushPromises()

    expect(wrapper.text()).toContain('Added RSI(14) to technical conditions')
    expect(wrapper.find('.easy-scan__advanced').exists()).toBe(true)
    expect(wrapper.findAll('.tech-cond-card')).toHaveLength(2)
  })

  it('refuses an ambiguous multi-output chart plot drop', async () => {
    apiGet.mockResolvedValue([])
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    const values = new Map<string, string>()
    const dataTransfer = {
      types: ['application/x-charting-platform-plot'],
      setData: (type: string, value: string) => values.set(type, value),
      getData: (type: string) => values.get(type) ?? '',
      effectAllowed: '',
    } as unknown as DataTransfer
    writeChartPlotDrag(dataTransfer, createChartPlotDragPayload({ type: 'bb', params: { period: 20, std_dev: 2 }, style: { color: '#fff', lineWidth: 1 }, pane: 'main' }, 'D1', 'chart-source'))

    await wrapper.get('.easy-scan').trigger('drop', { dataTransfer })
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('multi-output')
    expect(wrapper.find('.easy-scan__advanced').exists()).toBe(false)
  })

  it('exposes the editable condition tree as a bounded drag source', async () => {
    apiGet.mockResolvedValue([])
    const wrapper = mount(EasyScanTool, { props: { sourceWindowKey: 'scan-source' } })
    await flushPromises()
    await wrapper.get('button.easy-scan__advanced-toggle').trigger('click')
    const values = new Map<string, string>()
    const dataTransfer = {
      setData: (type: string, value: string) => values.set(type, value),
      getData: (type: string) => values.get(type) ?? '',
      effectAllowed: '',
    } as unknown as DataTransfer
    await wrapper.get('.easy-scan__advanced-drag-source').trigger('dragstart', { dataTransfer })
    expect(JSON.parse(values.get(CHART_PLOT_DRAG_MIME) ?? '')).toMatchObject({ kind: 'technical-condition', sourceWindowKey: 'scan-source', timeframe: 'D1' })
  })

  it('passes the selected universe and timeframe to the canonical scan definition', async () => {
    apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'close-test', name: 'Close test', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners/9') return Promise.resolve(savedScreener(9, { universe_type: 'basket', universe_basket_id: 44, timeframe: 'W1', schedule: '0 16 * * 1-5', conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-condition/close-test') return Promise.resolve({ id: 9 })
      if (path === '/screeners/9/run') return Promise.resolve({ matched_ids: [], result_data: { _status: 'completed' }, error: null })
      return Promise.resolve({})
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('close-test')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Basket scan')
    await wrapper.get('select[aria-label="Scan universe"]').setValue('basket')
    await wrapper.get('input[aria-label="Scan universe value"]').setValue('44')
    await wrapper.get('select[aria-label="Scan timeframe"]').setValue('W1')
    await wrapper.get('select[aria-label="Scan schedule"]').setValue('daily_close')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/screeners/from-condition/close-test', {
      name: 'Basket scan', universe_type: 'basket', universe_basket_id: 44, timeframe: 'W1', schedule: '0 16 * * 1-5',
    }, expect.objectContaining({ priority: 'high' }))
  })

  it('reconciles a duplicate scan through the shared screeners query', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'duplicate', name: 'Duplicate', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/screeners') return Promise.resolve([{ id: 12, name: 'Duplicate Scan' }])
      if (path === '/screeners/12') return Promise.resolve(savedScreener(12, { conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      if (path === '/screeners/12/results') return Promise.resolve([{ matched_ids: [], result_data: { _status: 'completed' }, error: null }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-condition/duplicate') return Promise.reject(new Error('duplicate → 409: already exists'))
      if (path === '/screeners/12/run') return Promise.resolve({ matched_ids: [], result_data: { _status: 'completed' }, error: null })
      return Promise.resolve({})
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('duplicate')
    await wrapper.get('input[aria-label="Scan name"]').setValue('Duplicate Scan')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()
    // One fresh lookup reconciles the 409 and the second is the intentional
    // post-create refresh shared with Market Gauge roots.
    expect(apiGet.mock.calls.filter(([path]) => path === '/screeners')).toHaveLength(2)
    expect(apiPost).toHaveBeenCalledWith('/screeners/12/run', {}, expect.objectContaining({ priority: 'high' }))
    expect(wrapper.text()).toContain('0 matches')
  })

  it('deduplicates saved-condition hydration across linked EasyScan windows', async () => {
    apiGet.mockReset()
    apiGet.mockResolvedValue([])
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const first = vueMount(EasyScanTool, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
    const second = vueMount(EasyScanTool, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
    await flushPromises()
    expect(apiGet.mock.calls.filter(([path]) => path === '/workspaces/library/conditions')).toHaveLength(1)
    expect(first.find('.easy-scan').exists()).toBe(true)
    expect(second.find('.easy-scan').exists()).toBe(true)
  })

  it('retains and exposes recent scan results for review', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'history-test', name: 'History test', version: 1, payload: { condition: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } } }])
      if (path === '/screeners/10') return Promise.resolve(savedScreener(10, { conditions: { type: 'price_threshold', field: 'close', op: 'gt', value: 50 } }))
      if (path === '/screeners/10/results') return Promise.resolve([
        { id: 101, run_at: '2026-08-03T16:00:00Z', matched_ids: [1, 2], result_data: { _status: 'completed' }, error: null },
        { id: 100, run_at: '2026-08-02T16:00:00Z', matched_ids: [1], result_data: { _status: 'completed' }, error: null },
      ])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: any) => {
      if (path === '/data/ensure') return Promise.resolve(screenerPreparationResponse(body.target.screener_id))
      if (path === '/screeners/from-condition/history-test') return Promise.resolve({ id: 10 })
      return Promise.resolve({ matched_ids: [1], result_data: { _status: 'completed' }, error: null })
    })
    const wrapper = mount(EasyScanTool)
    await flushPromises()
    await wrapper.get('select[aria-label="Saved condition"]').setValue('history-test')
    await wrapper.get('input[aria-label="Scan name"]').setValue('History scan')
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await flushPromises()

    const history = wrapper.get('select[aria-label="Scan result history"]')
    expect(history.findAll('option')).toHaveLength(3)
    expect(wrapper.text()).toContain('2 matches')
    await history.setValue('100')
    expect(wrapper.text()).toContain('1 matches')
  })

  it('does not publish late library hydration after the tool unmounts', async () => {
    let resolveConditions!: (value: any[]) => void
    apiGet.mockImplementation((path: string) => path === '/workspaces/library/conditions'
      ? new Promise(resolve => { resolveConditions = resolve })
      : Promise.resolve([]))
    const wrapper = mount(EasyScanTool)
    await Promise.resolve()
    expect(apiGet).toHaveBeenCalledWith('/workspaces/library/conditions', undefined, expect.objectContaining({
      priority: 'auto', queueKey: 'easy-scan:conditions', signal: expect.any(AbortSignal),
    }))

    wrapper.unmount()
    resolveConditions([{ stable_key: 'late', name: 'Late condition', version: 1 }])
    await flushPromises()

    expect((wrapper.vm as any).conditions).toEqual([])
  })
})
