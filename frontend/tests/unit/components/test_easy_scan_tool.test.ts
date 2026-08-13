import { flushPromises, mount as vueMount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut } }))

import EasyScanTool from '@/components/workstation/EasyScanTool.vue'
import { CHART_PLOT_DRAG_MIME, createChartPlotDragPayload, writeChartPlotDrag } from '@/lib/workstation/plotDrag'

function mount(component: typeof EasyScanTool, options: Parameters<typeof vueMount>[1] = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return vueMount(component, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }]] } })
}

describe('EasyScanTool', () => {
  it('opens the advanced condition builder with semantic state and restores toggle focus', async () => {
    apiGet.mockResolvedValue([])
    const wrapper = mount(EasyScanTool, { attachTo: document.body })
    await flushPromises()
    const toggle = wrapper.get('button.easy-scan__advanced-toggle')
    await toggle.trigger('click')
    const advanced = wrapper.get('[role="region"][aria-label="Advanced technical condition builder"]')
    expect(wrapper.get('[aria-label="Technical condition tree"]')).toBeTruthy()
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(toggle.attributes('aria-controls')).toBe('easy-scan-advanced-conditions')
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
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
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
    })
    expect(apiPost).toHaveBeenCalledWith('/screeners/7/run', {})
    expect(setQueryData).toHaveBeenCalledWith(['workstation', 'screeners'], expect.any(Function))
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['workstation', 'screeners'] })
    expect(wrapper.text()).toContain('1 matches')
    expect(wrapper.text()).toContain('1/1 evaluated')
    const alertButton = wrapper.findAll('button').find(button => button.text() === 'Alert')
    expect(alertButton).toBeDefined()
    await alertButton!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 7, trigger_type: 'entered', repeat: true })
    expect(wrapper.text()).toContain('Alert active')
    invalidateQueries.mockRestore()
    setQueryData.mockRestore()
  })

  it('exposes cancellation for a queued isolated Python scan', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Queued', versions: [{ id: 43, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/screeners/8/results') return Promise.resolve([{ matched_ids: [], result_data: { _status: 'canceled', _python_research_run_id: 99 }, error: null }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
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
    expect(apiPost).toHaveBeenCalledWith('/research/runs/99/cancel', {})
  })

  it('cancels a queued Python scan when the EasyScan tool is destroyed', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Queued teardown', versions: [{ id: 44, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/screeners/12/results') return Promise.resolve([{ matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 100 }, error: null }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
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
    expect(apiPost).toHaveBeenCalledWith('/research/runs/100/cancel', {})
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
    }))
  })

  it('uses the immutable Python version returned by a visual save for the first scan run', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([])
      if (path === '/code/assets') return Promise.resolve([])
      if (path === '/screeners') return Promise.resolve([])
      if (path === '/screeners/17/results') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiPut.mockResolvedValue({
      stable_key: 'visual-close',
      name: 'Visual close',
      version: 1,
      payload: { condition: {}, python_code_version_id: 77 },
    })
    apiPost.mockImplementation((path: string) => {
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
    })
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
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'close-test', name: 'Close test', version: 1 }])
      if (path === '/code/assets') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => path === '/screeners/from-condition/close-test'
      ? Promise.resolve({ id: 9 })
      : Promise.resolve({ matched_ids: [], result_data: { _status: 'completed' }, error: null }))
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
    })
  })

  it('reconciles a duplicate scan through the shared screeners query', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'duplicate', name: 'Duplicate', version: 1 }])
      if (path === '/screeners') return Promise.resolve([{ id: 12, name: 'Duplicate Scan' }])
      if (path === '/screeners/12/results') return Promise.resolve([{ matched_ids: [], result_data: { _status: 'completed' }, error: null }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
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
    expect(apiPost).toHaveBeenCalledWith('/screeners/12/run', {})
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
      if (path === '/workspaces/library/conditions') return Promise.resolve([{ stable_key: 'history-test', name: 'History test', version: 1 }])
      if (path === '/screeners/10/results') return Promise.resolve([
        { id: 101, run_at: '2026-08-03T16:00:00Z', matched_ids: [1, 2], result_data: { _status: 'completed' }, error: null },
        { id: 100, run_at: '2026-08-02T16:00:00Z', matched_ids: [1], result_data: { _status: 'completed' }, error: null },
      ])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => path === '/screeners/from-condition/history-test'
      ? Promise.resolve({ id: 10 })
      : Promise.resolve({ matched_ids: [1], result_data: { _status: 'completed' }, error: null }))
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
})
