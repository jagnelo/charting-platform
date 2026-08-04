import { mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('@/components/workstation/StudySeriesUPlot.vue', () => ({ default: { template: '<div class="series-chart" />', props: ['name', 'timestamps', 'values'] } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))
vi.mock('@/components/workstation/StudyScatterUPlot.vue', () => ({ default: { template: '<div class="scatter-chart" />', props: ['name', 'x', 'y'] } }))
vi.mock('@/components/workstation/StudyHeatmap.vue', () => ({ default: { template: '<div class="heatmap-chart" />', props: ['name', 'rows', 'columns', 'values'] } }))
vi.mock('@/components/workstation/StudyDashboard.vue', () => ({ default: { template: '<div class="dashboard-chart" />', props: ['name', 'panels', 'artifacts'] } }))

import StudyLabTool from '@/components/workstation/StudyLabTool.vue'

describe('StudyLabTool', () => {
  function mountTool(props: Record<string, unknown>) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    return mount(StudyLabTool, { props, global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  }

  it('hydrates serializable dataset controls and normalizes legacy timeframe values', () => {
    const wrapper = mountTool({
      activeSymbol: 'AAPL',
      configuration: { timeframe: 'MN1', benchmark: 'XLK', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01' },
    })

    expect(wrapper.find('[aria-label="Study timeframe"]').element).toHaveProperty('value', 'MN')
    expect(wrapper.find('[aria-label="Study benchmark"]').element).toHaveProperty('value', 'XLK')
    expect(wrapper.find('[aria-label="Study adjustment"]').element).toHaveProperty('value', 'raw')
    expect(wrapper.find('[aria-label="Study session"]').element).toHaveProperty('value', 'all')
  })

  it('offers constrained SDK suggestions while retaining the plain Python editor', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    const editor = wrapper.find('[aria-label="Study Python source"]')
    await editor.setValue('market.')
    expect(wrapper.find('[aria-label="Python SDK suggestions"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('market.close()')
    await wrapper.find('[aria-label="Python SDK suggestions"] button').trigger('mousedown')
    expect((editor.element as HTMLTextAreaElement).value).toContain('market.close()')
    expect(wrapper.text()).toContain('SDK reference')
  })

  it('validates, starts an immutable isolated study run, and renders artifacts', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['stats', 'output'], lookback_hint: 1, output_contracts: ['histogram', 'scatter', 'scalar', 'table'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 9, status: 'completed', reproducibility_hash: 'sha256:test', artifacts: [
        { id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } },
        { id: 9, name: 'shortest_streak', artifact_type: 'scalar', payload: { value: 1 } },
        { id: 7, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } },
        { id: 4, name: 'completed_streaks', artifact_type: 'table', payload: { value: [{ length: 2, end_timestamp: '2026-01-03' }] } },
        { id: 5, name: 'trend', artifact_type: 'series', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], values: [null, 11] } } },
        { id: 6, name: 'signals', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'positive_close' }] } },
        { id: 8, name: 'distribution', artifact_type: 'histogram', payload: { value: { bins: [{ start: 1, end: 2, count: 1 }], sample_size: 1 } } },
        { id: 10, name: 'relationship', artifact_type: 'scatter', payload: { value: { x: [1, 2], y: [2, 4] } } },
        { id: 11, name: 'matrix', artifact_type: 'heatmap', payload: { value: { rows: ['A', 'B'], columns: ['X', 'Y'], values: [[1, 2], [3, 4]] } } },
        { id: 12, name: 'overview', artifact_type: 'dashboard', payload: { value: { panels: [{ artifact: 'current_streak', title: 'Current streak', span: 4 }] } } },
      ] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })

    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.find('[aria-label="Study timeframe"]').setValue('W1')
    await wrapper.find('[aria-label="Study benchmark"]').setValue('QQQ')
    await wrapper.find('[aria-label="Study adjustment"]').setValue('raw')
    await wrapper.find('[aria-label="Study session"]').setValue('all')
    await wrapper.find('[aria-label="Study start date"]').setValue('2024-01-01')
    await wrapper.find('[aria-label="Study end date"]').setValue('2024-02-01')
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01' }))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #9'))

    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({
      code_version_id: 42,
      run_config: { symbol: 'SPY', parameters: {}, timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01' },
      dataset_manifest: expect.objectContaining({ timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01' }),
    }))
    expect(wrapper.text()).toContain('Dataset: SPY · W1 · raw · all session · benchmark QQQ')
    expect(wrapper.text()).toContain('current_streak')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).toContain('qualifies')
    expect(wrapper.text()).toContain('True')
    expect(wrapper.text()).toContain('completed_streaks')
    expect(wrapper.find('table').text()).toContain('end_timestamp')
    expect(wrapper.find('.series-chart').exists()).toBe(true)
    expect(wrapper.find('.histogram-chart').exists()).toBe(true)
    expect(wrapper.find('.scatter-chart').exists()).toBe(true)
    expect(wrapper.find('.heatmap-chart').exists()).toBe(true)
    expect(wrapper.find('.dashboard-chart').exists()).toBe(true)
    await wrapper.find('.study-lab-tool__events button').trigger('click')
    expect(wrapper.emitted('occurrence')?.[0]).toEqual([{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'positive_close' }])
  })

  it('renders schema-defined parameter controls and sends typed values to the immutable run', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 77 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 78, status: 'completed', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study parameter schema"]').setValue(JSON.stringify({ properties: { lookback: { type: 'integer', default: 20, minimum: 1 } } }))
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ parameter_schema: JSON.stringify({ properties: { lookback: { type: 'integer', default: 20, minimum: 1 } } }) }))
    await wrapper.find('[aria-label="Study parameter lookback"]').setValue('30')
    await wrapper.find('[aria-label="Study universe"]').setValue('SPY, XLK')
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #78'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      initial_version: expect.objectContaining({ parameter_schema: { properties: { lookback: { type: 'integer', default: 20, minimum: 1 } } }, default_parameters: { lookback: 30 } }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({ run_config: expect.objectContaining({ symbols: ['SPY', 'XLK'], parameters: { lookback: 30 } }) }))
  })

  it('promotes a completed boolean study into a reusable scan and alert', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['boolean'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: apiPost.mock.calls.filter(call => call[0] === '/code/assets').length === 1 ? 42 : 43 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 90, status: 'completed', artifacts: [{ id: 1, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } }] })
      if (path === '/screeners/from-python-condition/43') return Promise.resolve({ id: 77 })
      if (path === '/alerts/screener') return Promise.resolve({ id: 88 })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.boolean('qualifies', True)")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #90'))

    expect(wrapper.find('[aria-label="Promote study result"]').text()).toContain('Promote to scan')
    await wrapper.get('[aria-label="Promote study result"] button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to a reusable scan.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'condition',
      initial_version: expect.objectContaining({ source: "output.boolean('qualifies', True)", output_contract: 'boolean' }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/43', expect.objectContaining({ name: 'Consecutive Positive Closes Scan', universe_type: 'all', timeframe: 'D1' }))

    await wrapper.get('[aria-label="Promote study result"] button:last-of-type').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to an active scan alert.'))
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 77, trigger_type: 'entered', repeat: true })
  })
})
