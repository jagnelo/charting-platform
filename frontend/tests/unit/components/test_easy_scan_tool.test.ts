import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut } }))

import EasyScanTool from '@/components/workstation/EasyScanTool.vue'
import { CHART_PLOT_DRAG_MIME, createChartPlotDragPayload, writeChartPlotDrag } from '@/lib/workstation/plotDrag'

describe('EasyScanTool', () => {
  it('creates and runs a saved Python condition through the queued scan API', async () => {
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
    expect(wrapper.text()).toContain('1 matches')
    expect(wrapper.text()).toContain('1/1 evaluated')
    const alertButton = wrapper.findAll('button').find(button => button.text() === 'Alert')
    expect(alertButton).toBeDefined()
    await alertButton!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 7, trigger_type: 'entered', repeat: true })
    expect(wrapper.text()).toContain('Alert active')
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
