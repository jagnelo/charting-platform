import { mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('@/components/workstation/StudyBarsUPlot.vue', () => ({ default: { template: '<div class="bars-chart" />', props: ['name', 'labels', 'values'] } }))
vi.mock('@/components/workstation/StudySeriesUPlot.vue', () => ({ default: { template: '<div class="series-chart" />', props: ['name', 'timestamps', 'values'] } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))
vi.mock('@/components/workstation/StudyRangeUPlot.vue', () => ({ default: { template: '<div class="range-chart" />', props: ['name', 'timestamps', 'lower', 'upper', 'center'] } }))
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
      configuration: { timeframe: 'MN1', benchmark: 'XLK', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01', as_of: '2024-02-01T15:30:00Z' },
    })

    expect(wrapper.find('[aria-label="Study timeframe"]').element).toHaveProperty('value', 'MN')
    expect(wrapper.find('[aria-label="Study benchmark"]').element).toHaveProperty('value', 'XLK')
    expect(wrapper.find('[aria-label="Study adjustment"]').element).toHaveProperty('value', 'raw')
    expect(wrapper.find('[aria-label="Study session"]').element).toHaveProperty('value', 'all')
    expect(wrapper.find('[aria-label="Study as of"]').element).toHaveProperty('value', '2024-02-01T15:30')
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

  it('loads editable factory studies and switches back to custom Python on edit', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    const selector = wrapper.find('[aria-label="Factory study"]')
    await selector.setValue('negative_streak')
    expect(wrapper.find('[aria-label="Study name"]').element).toHaveProperty('value', 'Consecutive negative closes')
    expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value).toContain('current_negative_streak')
    await wrapper.find('[aria-label="Study Python source"]').setValue('output.scalar("custom", 1)')
    expect(selector.element).toHaveProperty('value', 'custom')
  })

  it('exposes the required occurrence, distribution, regime, seasonality, and relative-strength study starters', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    const selector = wrapper.find('[aria-label="Factory study"]')
    const options = selector.findAll('option').map(option => ({ value: option.element.getAttribute('value'), label: option.text() }))
    expect(options).toEqual(expect.arrayContaining([
      { value: 'positive_streak', label: 'Consecutive positive closes' },
      { value: 'negative_streak', label: 'Consecutive negative closes' },
      { value: 'forward_return_distribution', label: 'Forward-return distribution' },
      { value: 'high_low_breakouts', label: 'Highs and lows' },
      { value: 'volatility_regime', label: 'Volatility regime' },
      { value: 'seasonality', label: 'Monthly seasonality' },
      { value: 'relative_strength_regime', label: 'Relative-strength regime changes' },
      { value: 'cross_sectional_rank', label: 'Cross-sectional ranking' },
      { value: 'breadth_participation', label: 'Breadth participation' },
    ]))

    for (const value of ['forward_return_distribution', 'high_low_breakouts', 'volatility_regime', 'seasonality', 'relative_strength_regime']) {
      await selector.setValue(value)
      expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value.length).toBeGreaterThan(80)
    }
  })

  it('requires an explicit universe before running aggregate factory studies', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['research', 'output'], lookback_hint: 20, output_contracts: ['bar', 'boolean', 'scalar', 'table'] })
      : Promise.resolve({}))
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Factory study"]').setValue('cross_sectional_rank')
    expect(wrapper.find('[role="status"]').text()).toContain('declared comma-separated universe')
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    expect(wrapper.text()).toContain('requires a declared comma-separated universe')
    expect(apiPost).not.toHaveBeenCalledWith('/research/runs', expect.anything())
  })

  it('validates, starts an immutable isolated study run, and renders artifacts', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['stats', 'output'], lookback_hint: 1, output_contracts: ['bar', 'histogram', 'range', 'scatter', 'scalar', 'table'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 9, status: 'completed', reproducibility_hash: 'sha256:test', artifacts: [
        { id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } },
        { id: 9, name: 'shortest_streak', artifact_type: 'scalar', payload: { value: 1 } },
        { id: 7, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } },
        { id: 4, name: 'completed_streaks', artifact_type: 'table', payload: { value: [{ length: 2, end_timestamp: '2026-01-03' }] } },
        { id: 5, name: 'trend', artifact_type: 'series', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], values: [null, 11] } } },
        { id: 13, name: 'ranking', artifact_type: 'bar', payload: { value: { labels: ['XLK', 'XLE'], values: [12, -3] } } },
        { id: 14, name: 'confidence', artifact_type: 'range', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [3, 4], center: [2, 3] } } },
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
    expect(wrapper.find('.bars-chart').exists()).toBe(true)
    expect(wrapper.find('.histogram-chart').exists()).toBe(true)
    expect(wrapper.find('.range-chart').exists()).toBe(true)
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

  it('cancels an active study run when the Study Lab tool is destroyed', async () => {
    apiGet.mockResolvedValue({ id: 101, status: 'running', artifacts: [] })
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 101, status: 'running', artifacts: [] })
      if (path === '/research/runs/101/cancel') return Promise.resolve({ id: 101, status: 'canceled', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #101'))
    wrapper.unmount()
    expect(apiPost).toHaveBeenCalledWith('/research/runs/101/cancel', {})
  })

  it('promotes a completed boolean study into a reusable scan and alert', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['boolean'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: apiPost.mock.calls.filter(call => call[0] === '/code/assets').length === 1 ? 42 : 43 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 90, status: 'completed', artifacts: [{ id: 1, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } }] })
      if (path === '/screeners/from-python-condition/43') return Promise.resolve({ id: 77 })
      if (path === '/alerts/screener') return Promise.resolve({ id: 88 })
      if (path.startsWith('/strategy-lab/signals/from-code/')) return Promise.resolve({ id: 91 })
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

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Promote to alert')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to an active scan alert.'))
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 77, trigger_type: 'entered', repeat: true })

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Strategy signal')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable Strategy Lab signal.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({ kind: 'signal', initial_version: expect.objectContaining({ output_contract: 'boolean' }) }))
  })

  it('promotes a completed event study without coercing its event contract', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['market', 'output'], lookback_hint: 1, output_contracts: ['events'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 144 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 145, status: 'completed', artifacts: [{ id: 1, name: 'signals', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'signal' }] } }] })
      if (path.startsWith('/strategy-lab/signals/from-code/')) return Promise.resolve({ id: 146 })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.events('signals', [{'timestamp': '2026-01-02', 'kind': 'signal'}])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #145'))
    const signalButton = wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Strategy signal')
    expect(signalButton).toBeTruthy()
    await signalButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable Strategy Lab signal.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({ kind: 'signal', initial_version: expect.objectContaining({ output_contract: 'events' }) }))
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/144', {})
  })

  it('reruns a completed study against its snapshot or latest canonical data', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/91' ? Promise.resolve({ id: 91, status: 'completed', artifacts: [] }) : Promise.resolve([]))
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 90, status: 'completed', artifacts: [] })
      if (path === '/research/runs/90/rerun?snapshot=true') return Promise.resolve({ id: 91, status: 'queued', artifacts: [] })
      if (path === '/research/runs/91/rerun?snapshot=false') return Promise.resolve({ id: 92, status: 'queued', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #90'))

    const rerunSnapshot = wrapper.findAll('button').find(button => button.text() === 'Rerun snapshot')
    expect(rerunSnapshot).toBeDefined()
    await rerunSnapshot!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #91'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/90/rerun?snapshot=true', {})
    let rerunLatest = wrapper.findAll('button').find(button => button.text() === 'Rerun latest')
    await vi.waitFor(() => { rerunLatest = wrapper.findAll('button').find(button => button.text() === 'Rerun latest'); expect(rerunLatest).toBeDefined() })
    await rerunLatest!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #92'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/91/rerun?snapshot=false', {})
  })
})
