import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut } }))

import EasyScanTool from '@/components/workstation/EasyScanTool.vue'

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
    await wrapper.get('select[aria-label="Advanced condition operator"]').setValue('OR')
    await wrapper.get('.easy-scan__advanced .tech-cond-card select.form-select').setValue('indicator_threshold')
    await wrapper.findAll('button').find(button => button.text() === 'Save')!.trigger('click')
    await flushPromises()

    expect(apiPut).toHaveBeenCalledWith('/workspaces/library/conditions/rsi-tree', expect.objectContaining({
      name: 'RSI tree',
      condition: expect.objectContaining({ operator: 'OR', conditions: [expect.objectContaining({ type: 'indicator_threshold' })] }),
    }))
  })
})
