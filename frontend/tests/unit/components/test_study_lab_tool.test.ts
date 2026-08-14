import { mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
  })

  function mountTool(props: Record<string, unknown>, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })) {
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

  it('hydrates a persisted run after a virtual-tool remount', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({ id: 77, status: 'completed', artifacts: [{ id: 1, name: 'event_count', artifact_type: 'scalar', payload: { value: 4 } }] })
      : Promise.resolve(undefined))
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { study_run_id: 77, study_run_source: 'output.scalar("event_count", 4)', study_run_contract: 'scalar' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))
    expect(wrapper.text()).toContain('event_count')
    expect(apiGet).toHaveBeenCalledWith('/research/runs/77')
  })

  it('deduplicates concurrent persisted-run hydration across linked roots', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({ id: 77, status: 'completed', artifacts: [] })
      : Promise.resolve(undefined))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const props = { activeSymbol: 'SPY', configuration: { study_run_id: 77 } }
    const first = mountTool(props, queryClient)
    const second = mountTool(props, queryClient)
    await vi.waitFor(() => expect(first.text()).toContain('Run #77'))
    await vi.waitFor(() => expect(second.text()).toContain('Run #77'))
    expect(apiGet).toHaveBeenCalledTimes(1)
    first.unmount()
    second.unmount()
  })

  it('reuses the shared research-run cache populated by another workstation surface', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    queryClient.setQueryData(['workstation', 'research-run', 77], { id: 77, status: 'completed', artifacts: [] })
    apiGet.mockResolvedValue(undefined)
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { study_run_id: 77 } }, queryClient)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))
    expect(apiGet).not.toHaveBeenCalledWith('/research/runs/77')
    wrapper.unmount()
  })

  it('propagates cancel mutations to linked Study Lab roots through the shared run cache', async () => {
    const running = { id: 101, status: 'running', code_version_id: 4, artifacts: [] }
    const canceled = { ...running, status: 'canceled' }
    let canceledRequested = false
    apiGet.mockImplementation((path: string) => path === '/research/runs/101'
      ? Promise.resolve(canceledRequested ? canceled : running)
      : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string) => {
      if (path === '/research/runs/101/cancel') { canceledRequested = true; return Promise.resolve(canceled) }
      return Promise.resolve({})
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const props = { activeSymbol: 'SPY', configuration: { study_run_id: 101 } }
    const first = mountTool(props, queryClient)
    const second = mountTool(props, queryClient)
    await vi.waitFor(() => expect(first.text()).toContain('Run #101'))
    await vi.waitFor(() => expect(second.text()).toContain('Run #101'))

    await first.findAll('button').find(button => button.text() === 'Cancel')!.trigger('click')
    await vi.waitFor(() => expect(second.text()).toContain('canceled'))
    expect(queryClient.getQueryData(['workstation', 'research-run', 101])).toMatchObject({ id: 101, status: 'canceled' })
    first.unmount()
    second.unmount()
  })

  it('does not let late persisted hydration replace a newly started run', async () => {
    let resolvePersisted!: (value: unknown) => void
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs/77') return new Promise(resolve => { resolvePersisted = resolve })
      return Promise.resolve(undefined)
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 78 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 88, status: 'completed', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { study_run_id: 77, study_run_source: 'output.scalar("old", 1)', study_run_contract: 'scalar' } })
    await wrapper.find('[aria-label="Study Python source"]').setValue('output.scalar("new", 2)')
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #88'))

    resolvePersisted({ id: 77, status: 'queued', artifacts: [] })
    await Promise.resolve()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Run #88')
    expect(wrapper.text()).not.toContain('Run #77')
    wrapper.unmount()
  })

  it('uses the shared unified Python editor with SDK suggestions', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    const editor = wrapper.find('[aria-label="Study Python source"]')
    await editor.setValue('market.')
    expect(wrapper.find('.python-source-editor__toolbar').text()).toContain('unified market SDK')
    expect(wrapper.find('[aria-label="Study Python source SDK suggestions"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('market.close()')
    await wrapper.find('[aria-label="Study Python source SDK suggestions"] button').trigger('mousedown')
    expect((editor.element as HTMLTextAreaElement).value).toContain('market.close()')
    expect(wrapper.text()).toContain('SDK reference')
  })

  it('loads editable factory studies and switches back to custom Python on edit', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mountTool({ activeSymbol: 'SPY' }, queryClient)
    const selector = wrapper.find('[aria-label="Factory study"]')
    await selector.setValue('negative_streak')
    expect(wrapper.find('[aria-label="Study name"]').element).toHaveProperty('value', 'Consecutive negative closes')
    expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value).toContain('current_negative_streak')
    await wrapper.find('[aria-label="Study Python source"]').setValue('output.scalar("custom", 1)')
    expect(selector.element).toHaveProperty('value', 'custom')
  })

  it('exposes bounded lookback controls for configurable participation and high-low studies', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    const selector = wrapper.find('[aria-label="Factory study"]')

    await selector.setValue('high_low_breakouts')
    const parameterSchema = wrapper.find('[aria-label="Study parameter schema"]')
    expect((parameterSchema.element as HTMLTextAreaElement).value).toContain('"lookback"')
    const lookback = wrapper.find('[aria-label="Study parameter lookback"]')
    expect(lookback.element).toHaveProperty('value', '20')
    expect(lookback.element.getAttribute('min')).toBe('2')
    expect(lookback.element.getAttribute('max')).toBe('252')
    expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value).toContain('parameters.get')

    await lookback.setValue('50')
    expect(lookback.element).toHaveProperty('value', '50')
    await wrapper.find('[aria-label="Study Python source"]').setValue('output.scalar("custom", 1)')
    expect((parameterSchema.element as HTMLTextAreaElement).value).toBe('')
    await selector.setValue('moving_average_participation')
    expect(wrapper.find('[aria-label="Study parameter lookback"]').exists()).toBe(true)
  })

  it('exposes the required occurrence, distribution, regime, seasonality, and relative-strength study starters', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    const selector = wrapper.find('[aria-label="Factory study"]')
    const options = selector.findAll('option').map(option => ({ value: option.element.getAttribute('value'), label: option.text() }))
    expect(options).toEqual(expect.arrayContaining([
      { value: 'positive_streak', label: 'Consecutive positive closes' },
      { value: 'negative_streak', label: 'Consecutive negative closes' },
      { value: 'forward_return_distribution', label: 'Forward-return distribution' },
      { value: 'event_frequency', label: 'Event frequency and occurrences' },
      { value: 'high_low_breakouts', label: 'Highs and lows' },
      { value: 'volatility_regime', label: 'Volatility regime' },
      { value: 'seasonality', label: 'Month/day seasonality' },
      { value: 'relative_strength_regime', label: 'Relative-strength regime changes' },
      { value: 'cross_sectional_rank', label: 'Cross-sectional ranking' },
      { value: 'breadth_participation', label: 'Breadth participation' },
    ]))

    for (const value of ['forward_return_distribution', 'event_frequency', 'high_low_breakouts', 'volatility_regime', 'seasonality', 'relative_strength_regime']) {
      await selector.setValue(value)
      expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value.length).toBeGreaterThan(80)
    }
    await selector.setValue('seasonality')
    const seasonalitySource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(seasonalitySource).toContain('average_day_of_week_return')
    expect(seasonalitySource).toContain("weekday_names = ['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']")
    expect(seasonalitySource).not.toContain('lambda')
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
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      initial_version: expect.objectContaining({ output_contract: 'study' }),
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
    await wrapper.findAll('button').find(button => button.text() === 'Save plot: trend')!.trigger('click')
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      initial_version: expect.objectContaining({ output_contract: 'series', output_name: 'trend' }),
    }))
    await wrapper.find('.study-lab-tool__events button').trigger('click')
    expect(wrapper.emitted('occurrence')?.[0]).toEqual([{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'positive_close' }])
  })

  it('exposes structured metrics, tables, and occurrences as navigable result regions', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: 1, output_contracts: ['scalar', 'table', 'events'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 51 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 10, status: 'completed', artifacts: [
        { id: 1, name: 'current', artifact_type: 'scalar', payload: { value: 4 } },
        { id: 2, name: 'records', artifact_type: 'table', payload: { value: [{ length: 4 }] } },
        { id: 3, name: 'events', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'streak' }] } },
      ] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue('output.scalar("current", 4)')
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #10'))
    const metric = wrapper.get('[aria-label="Study metrics"] [role="status"]')
    expect(metric.attributes('aria-label')).toBe('current metric')
    expect(metric.attributes('aria-live')).toBe('polite')
    expect(metric.attributes('aria-atomic')).toBe('true')
    expect(wrapper.get('[aria-label="records table result"] caption').text()).toBe('records table')
    expect(wrapper.get('[aria-label="events occurrences"] [role="listitem"]').attributes('aria-label')).toBe('SPY 2026-01-02 streak')
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

  it('cancels a run that is created after the Study Lab tool is destroyed', async () => {
    let resolveRun!: (value: unknown) => void
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 52 }] })
      if (path === '/research/runs') return new Promise(resolve => { resolveRun = resolve })
      if (path === '/research/runs/202/cancel') return Promise.resolve({ id: 202, status: 'canceled', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    wrapper.unmount()

    resolveRun({ id: 202, status: 'queued', artifacts: [] })
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/research/runs/202/cancel', {}))
  })

  it('surfaces an empty polling response instead of caching undefined', async () => {
    apiGet.mockResolvedValue(undefined)
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 102, status: 'running', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #102'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Study run refresh returned no data'))
  })

  it('gives failed runs explicit recovery guidance and preserves both rerun actions', async () => {
    apiGet.mockResolvedValue(undefined)
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 103, status: 'failed', diagnostics: [{ message: 'sandbox limit' }], artifacts: [] })
      if (path === '/research/runs/103/rerun?snapshot=true') return Promise.resolve({ id: 104, status: 'queued', artifacts: [] })
      if (path === '/research/runs/104/rerun?snapshot=false') return Promise.resolve({ id: 105, status: 'queued', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #103'))
    expect(wrapper.get('[data-status="failed"]').text()).toBe('Failed')
    const guidance = wrapper.get('.study-lab-tool__run-guidance')
    expect(guidance.text()).toContain('Inspect diagnostics and execution logs')
    expect(guidance.attributes('aria-atomic')).toBe('true')
    expect(wrapper.findAll('button').some(button => button.text() === 'Rerun snapshot')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Rerun latest')).toBe(true)
  })

  it('labels canceled runs as recoverable rather than leaving a raw terminal token', async () => {
    apiGet.mockResolvedValue(undefined)
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 43 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 106, status: 'canceled', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #106'))
    expect(wrapper.get('[data-status="canceled"]').text()).toBe('Canceled')
    expect(wrapper.get('.study-lab-tool__run-guidance').text()).toContain('configuration is preserved')
  })

  it('promotes a completed boolean study into a reusable scan and alert', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['boolean'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 90, code_version_id: 42, status: 'completed', artifacts: [{ id: 1, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } }] })
      if (path === '/screeners/from-python-condition/42') return Promise.resolve({ id: 77 })
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
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({ kind: 'study', initial_version: expect.objectContaining({ source: "output.boolean('qualifies', True)", output_contract: 'boolean' }) }))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/42', expect.objectContaining({ name: 'Consecutive Positive Closes Scan', universe_type: 'all', timeframe: 'D1' }))

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Promote to alert')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to an active scan alert.'))
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 77, trigger_type: 'entered', repeat: true })
    expect(apiPost.mock.calls.filter(call => String(call[0]).startsWith('/screeners/from-python-condition/'))).toHaveLength(1)

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Strategy signal')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable Strategy Lab signal.'))
    expect(wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Strategy signal')!.attributes('disabled')).toBeUndefined()
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/42', {})
  })

  it('promotes a completed event study without coercing its event contract', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['market', 'output'], lookback_hint: 1, output_contracts: ['events'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 144 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 145, code_version_id: 144, status: 'completed', artifacts: [{ id: 1, name: 'signals', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'signal' }] } }] })
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
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mountTool({ activeSymbol: 'SPY' }, queryClient)
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #90'))

    const rerunSnapshot = wrapper.findAll('button').find(button => button.text() === 'Rerun snapshot')
    expect(rerunSnapshot).toBeDefined()
    await rerunSnapshot!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #91'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/90/rerun?snapshot=true', {})
    expect(queryClient.getQueryData(['workstation', 'research-run', 91])).toMatchObject({ id: 91 })
    let rerunLatest = wrapper.findAll('button').find(button => button.text() === 'Rerun latest')
    await vi.waitFor(() => { rerunLatest = wrapper.findAll('button').find(button => button.text() === 'Rerun latest'); expect(rerunLatest).toBeDefined() })
    await rerunLatest!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #92'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/91/rerun?snapshot=false', {})
  })
})
