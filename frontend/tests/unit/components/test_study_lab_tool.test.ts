import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, reactive, nextTick } from 'vue'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, ensurePreparation, resolveWatchlistSource, watchlistSourceState } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), ensurePreparation: vi.fn(), resolveWatchlistSource: vi.fn(), watchlistSourceState: { sources: [] as unknown[] } }))
vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    constructor(readonly method: string, readonly path: string, readonly status: number, body: string) {
      super(`API ${method} ${path} → ${status}: ${body}`)
      this.name = 'ApiError'
    }
  },
  api: { get: apiGet, post: apiPost },
}))
vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: ensurePreparation },
  preparationStatusMessage: (response: { status: string }) => response.status === 'ready' ? 'Requested data is ready.' : 'Requested data is unavailable.',
}))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ watchlistSources: watchlistSourceState.sources, resolveWatchlistSource }) }))
vi.mock('@/components/workstation/StudyBarsUPlot.vue', () => ({ default: { template: '<div class="bars-chart" />', props: ['name', 'labels', 'values'] } }))
vi.mock('@/components/workstation/StudySeriesUPlot.vue', () => ({ default: { template: '<div class="series-chart" :data-values="JSON.stringify(values)" />', props: ['name', 'timestamps', 'values'] } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))
vi.mock('@/components/workstation/StudyRangeUPlot.vue', () => ({ default: { template: '<div class="range-chart" />', props: ['name', 'timestamps', 'lower', 'upper', 'center'] } }))
vi.mock('@/components/workstation/StudyScatterUPlot.vue', () => ({ default: { template: '<div class="scatter-chart" />', props: ['name', 'x', 'y'] } }))
vi.mock('@/components/workstation/StudyHeatmap.vue', () => ({ default: { template: '<div class="heatmap-chart" />', props: ['name', 'rows', 'columns', 'values'] } }))
vi.mock('@/components/workstation/StudyDashboard.vue', () => ({ default: { template: '<div class="dashboard-chart" />', props: ['name', 'panels', 'artifacts'] } }))

import StudyLabTool from '@/components/workstation/StudyLabTool.vue'
import ResearchResultsTool from '@/components/workstation/ResearchResultsTool.vue'
import { ApiError } from '@/lib/api'
import type { WatchlistSource } from '@/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}

function terminalCancelConflict(runId: number, status: 'completed' | 'failed' | 'canceled' = 'completed') {
  const path = `/research/runs/${runId}/cancel`
  return new ApiError('POST', path, 409, JSON.stringify({ detail: { code: 'research_run_terminal', status } }))
}

describe('StudyLabTool', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    ensurePreparation.mockReset().mockResolvedValue({ status: 'ready' })
    resolveWatchlistSource.mockReset()
    watchlistSourceState.sources = []
  })

  function mountTool(props: Record<string, unknown>, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }), sources: WatchlistSource[] = []) {
    watchlistSourceState.sources = sources
    return mount(StudyLabTool, { props, global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  }

  it('offers canonical watchlist sources while retaining custom source IDs', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} }, undefined, [
      { source_id: 'watchlist:7', source_kind: 'personal', name: 'Growth leaders', locked: false, can_follow: false, can_clone: true, can_edit_membership: true, provenance: {} },
      { source_id: 'market-group:sp500', source_kind: 'market_group', name: 'S&P 500', locked: true, can_follow: true, can_clone: false, can_edit_membership: false, provenance: {} },
    ])
    const sourceInput = wrapper.get('[aria-label="Study universe source"]')
    const sourceListId = sourceInput.attributes('list')
    const sources = wrapper.findAll(`#${sourceListId} option`)

    expect(sources).toHaveLength(2)
    expect(sources[0].attributes('value')).toBe('market-group:sp500')
    expect(sources[0].attributes('label')).toBe('Market groups · S&P 500')
    expect(sources[1].attributes('value')).toBe('watchlist:7')
    expect(sources[1].attributes('label')).toBe('Personal watchlists · Growth leaders')

    await sourceInput.setValue('market-group:sp500')
    expect(wrapper.find('[aria-label="Study universe"]').attributes('disabled')).toBeDefined()

    await sourceInput.setValue('unpublished:alpha')
    expect(sourceInput.element).toHaveProperty('value', 'unpublished:alpha')
    wrapper.unmount()
  })

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

  it('restores an explicit draft symbol ahead of linked context and applies later saved configuration updates', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { symbol: 'XLB' } })
    const symbol = wrapper.get('[aria-label="Study symbol"]')

    expect(symbol.element).toHaveProperty('value', 'XLB')

    await wrapper.setProps({ activeSymbol: 'XLK' })
    expect(symbol.element).toHaveProperty('value', 'XLB')

    await wrapper.setProps({ configuration: { symbol: 'QQQ' } })
    expect(symbol.element).toHaveProperty('value', 'QQQ')
    wrapper.unmount()
  })

  it('applies a completed parent configuration update without recursive intermediate emissions', async () => {
    const configuration = reactive<Record<string, unknown>>({
      symbol: 'SPY',
      benchmark: 'QQQ',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      session: 'regular',
      symbols: 'SPY,XLK',
    })
    const onConfiguration = vi.fn((next: Record<string, unknown>) => {
      // Match WorkstationView.updateToolConfiguration: keep the reactive config
      // object, but apply the replacement as a synchronous delete/assign batch.
      for (const key of Object.keys(configuration)) delete configuration[key]
      Object.assign(configuration, next)
    })
    const Parent = defineComponent({
      setup: () => () => h(StudyLabTool, { activeSymbol: 'SPY', configuration, onConfiguration }),
    })
    const wrapper = mount(Parent, {
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) }]] },
    })

    configuration.timeframe = 'W1'
    await nextTick()
    await flushPromises()

    expect(wrapper.get('[aria-label="Study timeframe"]').element).toHaveProperty('value', 'W1')
    expect(configuration.timeframe).toBe('W1')
    expect(onConfiguration.mock.calls.length).toBeLessThanOrEqual(2)
    wrapper.unmount()
  })

  it('preserves saved-run identity when a draft update is applied as a complete parent replacement and remounted', async () => {
    const savedRun = {
      id: 77,
      status: 'completed',
      run_config: { symbol: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', session: 'regular' },
      dataset_manifest: { symbol: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', session: 'regular' },
      artifacts: [{ id: 1, name: 'saved_close', artifact_type: 'scalar', payload: { value: 501 } }],
    }
    apiGet.mockImplementation((path: string) => path === '/research/runs/77' ? Promise.resolve(savedRun) : Promise.resolve([]))
    const configuration = reactive<Record<string, unknown>>({
      symbol: 'SPY',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      session: 'regular',
      study_run_id: 77,
      study_run_source: "output.scalar('saved_close', 501)",
      study_run_contract: 'scalar',
      study_run_name: 'Saved SPY run',
      study_run_parameter_schema: { properties: {} },
    })
    const Parent = defineComponent({
      setup: () => () => h(StudyLabTool, {
        activeSymbol: 'SPY',
        configuration,
        onConfiguration: (next: Record<string, unknown>) => {
          // Match WorkstationView's complete replacement semantics exactly.
          for (const key of Object.keys(configuration)) delete configuration[key]
          Object.assign(configuration, next)
        },
      }),
    })
    const wrapper = mount(Parent, {
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) }]] },
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))

    await wrapper.get('[aria-label="Study symbol"]').setValue('XLB')
    await nextTick()
    await flushPromises()

    expect(configuration).toMatchObject({
      symbol: 'XLB',
      study_run_id: 77,
      study_run_source: "output.scalar('saved_close', 501)",
      study_run_contract: 'scalar',
      study_run_name: 'Saved SPY run',
    })
    expect(wrapper.text()).toContain('Current draft dataset: XLB')
    expect(wrapper.text()).toContain('Saved run #77 dataset: symbol SPY')
    wrapper.unmount()

    const remounted = mountTool({ activeSymbol: 'SPY', configuration })
    await vi.waitFor(() => expect(remounted.text()).toContain('Run #77'))
    expect(remounted.text()).toContain('Current draft dataset: XLB')
    expect(remounted.text()).toContain('Saved run #77 dataset: symbol SPY')
    expect(remounted.text()).toContain('saved_close scalar result: 501.')
    remounted.unmount()
  })

  it('keeps a restored XLB draft through async saved-run loading, linked context updates, and complete parent echoes', async () => {
    const savedRunResponse = deferred<any>()
    apiGet.mockImplementation((path: string) => path === '/research/runs/88' ? savedRunResponse.promise : Promise.resolve([]))
    const configuration = reactive<Record<string, unknown>>({
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      session: 'regular',
      study_run_id: 88,
      study_run_source: "output.scalar('saved_close', 501)",
      study_run_contract: 'scalar',
      study_run_name: 'Saved SPY run',
      study_run_parameter_schema: { properties: {} },
    })
    const parent = reactive({ activeSymbol: 'SPY' })
    const Parent = defineComponent({
      setup: () => () => h(StudyLabTool, {
        activeSymbol: parent.activeSymbol,
        configuration,
        onConfiguration: (next: Record<string, unknown>) => {
          // WorkstationView applies complete snapshots with a synchronous
          // delete/assign batch; the draft symbol and saved-run lineage must
          // both survive that real parent behavior.
          for (const key of Object.keys(configuration)) delete configuration[key]
          Object.assign(configuration, next)
        },
      }),
    })
    const wrapper = mount(Parent, {
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) }]] },
    })
    expect(wrapper.get('[aria-label="Study symbol"]').element).toHaveProperty('value', 'SPY')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/research/runs/88', undefined, expect.objectContaining({ priority: 'high' })))

    // The host can deliver the persisted workspace draft after the virtual
    // tool mounts and starts loading its saved run. Apply that full snapshot
    // through the same delete/assign semantics used for later echoes.
    for (const key of Object.keys(configuration)) delete configuration[key]
    Object.assign(configuration, {
      symbol: 'XLB',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      session: 'regular',
      study_run_id: 88,
      study_run_source: "output.scalar('saved_close', 501)",
      study_run_contract: 'scalar',
      study_run_name: 'Saved SPY run',
      study_run_parameter_schema: { properties: {} },
    })
    await nextTick()
    expect(wrapper.get('[aria-label="Study symbol"]').element).toHaveProperty('value', 'XLB')

    savedRunResponse.resolve({
      id: 88,
      status: 'completed',
      run_config: { symbol: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', session: 'regular' },
      dataset_manifest: { symbol: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', session: 'regular' },
      artifacts: [{ id: 1, name: 'saved_close', artifact_type: 'scalar', payload: { value: 501 } }],
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #88'))

    // A parent-linked symbol change must not replace an independently saved
    // draft, even after asynchronous run details have populated the view.
    parent.activeSymbol = 'XLK'
    await nextTick()
    parent.activeSymbol = 'SPY'
    await nextTick()
    await wrapper.get('[aria-label="Study timeframe"]').setValue('W1')
    await flushPromises()

    expect(configuration).toMatchObject({ symbol: 'XLB', timeframe: 'W1', study_run_id: 88 })
    expect(wrapper.get('[aria-label="Study symbol"]').element).toHaveProperty('value', 'XLB')
    expect(wrapper.text()).toContain('Current draft dataset: XLB')
    expect(wrapper.text()).toContain('Saved run #88 dataset: symbol SPY')
    wrapper.unmount()

    apiGet.mockImplementation((path: string) => path === '/research/runs/88' ? Promise.resolve({
      id: 88,
      status: 'completed',
      run_config: { symbol: 'SPY', timeframe: 'D1' },
      dataset_manifest: { symbol: 'SPY', timeframe: 'D1' },
      artifacts: [{ id: 1, name: 'saved_close', artifact_type: 'scalar', payload: { value: 501 } }],
    }) : Promise.resolve([]))
    const remounted = mountTool({ activeSymbol: 'SPY', configuration })
    await vi.waitFor(() => expect(remounted.text()).toContain('Run #88'))
    expect(remounted.get('[aria-label="Study symbol"]').element).toHaveProperty('value', 'XLB')
    expect(remounted.text()).toContain('Current draft dataset: XLB')
    expect(remounted.text()).toContain('Saved run #88 dataset: symbol SPY')
    await remounted.get('[aria-label="Study symbol"]').setValue('')
    await remounted.setProps({ activeSymbol: 'QQQ' })
    expect(remounted.get('[aria-label="Study symbol"]').element).toHaveProperty('value', 'QQQ')
    remounted.unmount()
  })

  it('associates parameter schema errors with the invalid schema field', async () => {
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
    const schema = wrapper.get('[aria-label="Study parameter schema"]')

    expect(schema.attributes('aria-invalid')).toBeUndefined()
    expect(schema.attributes('aria-describedby')).toBeUndefined()

    await schema.setValue('{')

    const errorId = schema.attributes('aria-describedby')
    expect(schema.attributes('aria-invalid')).toBe('true')
    expect(errorId).toMatch(/^study-parameter-schema-error-/)
    expect(wrapper.get(`#${errorId}`).text()).toBe('Parameter schema must be a JSON object.')

    await schema.setValue(JSON.stringify({ properties: { lookback: { type: 'integer', default: 20 } } }))
    expect(schema.attributes('aria-invalid')).toBeUndefined()
    expect(schema.attributes('aria-describedby')).toBeUndefined()
    wrapper.unmount()
  })

  it('associates current Python validation diagnostics with the source editor', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: false, diagnostics: ['line 1: unsupported expression'], dependencies: [], lookback_hint: null, output_contracts: [] })
      : Promise.resolve({}))
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
    const source = wrapper.get('[aria-label="Study Python source"]')

    expect(source.attributes('aria-invalid')).toBeUndefined()
    expect(source.attributes('aria-describedby')).toBeUndefined()

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(source.attributes('aria-invalid')).toBe('true'))

    const describedBy = source.attributes('aria-describedby')?.split(' ')
    expect(describedBy).toHaveLength(1)
    expect(wrapper.get(`#${describedBy?.[0]}`).text()).toContain('line 1: unsupported expression')

    await source.setValue("output.scalar('corrected', 1)")
    expect(source.attributes('aria-invalid')).toBeUndefined()
    expect(wrapper.get(`#${describedBy?.[0]}`).text()).toContain('Study source changed since validation')
    wrapper.unmount()
  })

  it('gives study lifecycle controls stable accessible names', () => {
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })

    expect(wrapper.get('button[aria-label="Validate study"]').text()).toBe('Validate')
    expect(wrapper.get('button[aria-label="Run study"]').text()).toBe('Run')
  })

  it('requires the current source to match the latest validation before running', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 77 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 78, status: 'completed', artifacts: [] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
    const source = wrapper.find('[aria-label="Study Python source"]')
    const validate = wrapper.get('button[aria-label="Validate study"]')
    const run = wrapper.get('button[aria-label="Run study"]')

    await validate.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    expect(run.attributes('disabled')).toBeUndefined()

    await source.setValue("output.scalar('changed', 1)")
    expect(run.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Study source changed since validation. Validate the current source before running.')
    await run.trigger('click')
    expect(apiPost).not.toHaveBeenCalledWith('/code/assets', expect.anything())
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)

    await validate.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    expect(run.attributes('disabled')).toBeUndefined()
    await run.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #78'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      initial_version: expect.objectContaining({ source: "output.scalar('changed', 1)" }),
    }))
    const preparationOrder = ensurePreparation.mock.invocationCallOrder.at(-1)!
    const assetOrder = apiPost.mock.invocationCallOrder[apiPost.mock.calls.findIndex(([path]) => path === '/code/assets')]
    const runOrder = apiPost.mock.invocationCallOrder[apiPost.mock.calls.findIndex(([path]) => path === '/research/runs')]
    expect(preparationOrder).toBeLessThan(assetOrder)
    expect(preparationOrder).toBeLessThan(runOrder)
    wrapper.unmount()
  })

  it('prepares the selected primary and benchmark history with bounded date intent before validating', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    const wrapper = mountTool({
      activeSymbol: 'SPY',
      configuration: { timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', start_date: '2024-01-02', end_date: '2024-02-29', as_of: '2024-02-15T15:30:00Z' },
    })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/code/validate', expect.anything(), expect.objectContaining({ priority: 'high' })))

    expect(ensurePreparation).toHaveBeenNthCalledWith(1, {
      target: { kind: 'instrument', symbol: 'SPY' },
      datasets: ['history'],
      timeframe: 'W1',
      adjusted: false,
      start_at: '2024-01-02T00:00:00.000Z',
      end_at: '2024-02-15T15:30:00.000Z',
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(ensurePreparation).toHaveBeenNthCalledWith(2, expect.objectContaining({
      target: { kind: 'instrument', symbol: 'QQQ' },
      timeframe: 'W1',
      start_at: '2024-01-02T00:00:00.000Z',
      end_at: '2024-02-15T15:30:00.000Z',
    }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(ensurePreparation.mock.invocationCallOrder[0]).toBeLessThan(apiPost.mock.invocationCallOrder[0])
    expect(wrapper.get('[aria-label="Study data preparation"]').text()).toContain('Selected Study data and benchmark are ready.')
    wrapper.unmount()
  })

  it('submits every independent member and benchmark before waiting for a held target', async () => {
    const heldPrimary = deferred<{ status: string }>()
    ensurePreparation.mockImplementation((request: { target: { symbol?: string } }) => {
      if (request.target.symbol === 'SPY') return heldPrimary.promise
      return Promise.resolve({ status: 'ready' })
    })
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    const wrapper = mountTool({
      activeSymbol: 'XLB',
      configuration: { symbols: 'SPY,XLK', benchmark: 'QQQ' },
    })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(ensurePreparation).toHaveBeenCalledTimes(3))
    expect(ensurePreparation.mock.calls.map(([request]) => request.target)).toEqual([
      { kind: 'instrument', symbol: 'SPY' },
      { kind: 'instrument', symbol: 'XLK' },
      { kind: 'instrument', symbol: 'QQQ' },
    ])
    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('XLK: Requested data is ready.'))
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('QQQ: Requested data is ready.'))

    heldPrimary.resolve({ status: 'unavailable' })
    await flushPromises()
    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)
    expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('SPY: Requested data is unavailable.')
    expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('XLK: Requested data is ready.')
    expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('QQQ: Requested data is ready.')
    expect(wrapper.get('[aria-label="Study data preparation"]').text()).toContain('Some selected Study data is not ready')
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    wrapper.unmount()
  })

  it('submits later targets before closing while the first preparation is still held', async () => {
    const heldPrimary = deferred<{ status: string }>()
    ensurePreparation.mockImplementation((request: { target: { symbol?: string } }) => {
      if (request.target.symbol === 'SPY') return heldPrimary.promise
      return Promise.resolve({ status: 'ready' })
    })
    const wrapper = mountTool({
      activeSymbol: 'XLB',
      configuration: { symbols: 'SPY,XLK', benchmark: 'QQQ' },
    })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(ensurePreparation).toHaveBeenCalledTimes(3))
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('QQQ: Requested data is ready.'))
    const signals = ensurePreparation.mock.calls.map(([, options]) => options.signal as AbortSignal)

    wrapper.unmount()
    expect(signals.every(signal => signal.aborted)).toBe(true)
    heldPrimary.resolve({ status: 'unavailable' })
    await flushPromises()
    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    expect(apiPost).not.toHaveBeenCalledWith(expect.stringContaining('/cancel'), expect.anything())
  })

  it('keeps later preparation outcomes when one target request rejects', async () => {
    ensurePreparation.mockImplementation((request: { target: { symbol?: string } }) => {
      if (request.target.symbol === 'SPY') return Promise.reject(new Error('Preparation request timed out.'))
      return Promise.resolve({ status: 'ready' })
    })
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    const wrapper = mountTool({
      activeSymbol: 'XLB',
      configuration: { symbols: 'SPY,XLK', benchmark: 'QQQ' },
    })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(ensurePreparation).toHaveBeenCalledTimes(3))
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study data preparation outcomes"]').text()).toContain('QQQ: Requested data is ready.'))
    await flushPromises()
    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)

    const outcomes = wrapper.get('[aria-label="Study data preparation outcomes"]').text()
    expect(outcomes).toContain('SPY: Preparation request timed out.')
    expect(outcomes).toContain('XLK: Requested data is ready.')
    expect(outcomes).toContain('QQQ: Requested data is ready.')
    expect(wrapper.get('[aria-label="Study data preparation"]').text()).toContain('Some selected Study data is not ready')
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    wrapper.unmount()
  })

  it('aborts all obsolete preparation subscriptions when the benchmark context changes', async () => {
    const heldPrimary = deferred<{ status: string }>()
    ensurePreparation.mockImplementation((request: { target: { symbol?: string } }) => {
      if (request.target.symbol === 'SPY') return heldPrimary.promise
      return Promise.resolve({ status: 'ready' })
    })
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    const wrapper = mountTool({
      activeSymbol: 'XLB',
      configuration: { symbols: 'SPY,XLK', benchmark: 'QQQ' },
    })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(ensurePreparation).toHaveBeenCalledTimes(3))
    const signals = ensurePreparation.mock.calls.map(([, options]) => options.signal as AbortSignal)
    await wrapper.get('[aria-label="Study benchmark"]').setValue('DIA')
    expect(signals.every(signal => signal.aborted)).toBe(true)

    heldPrimary.resolve({ status: 'ready' })
    await flushPromises()
    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    expect(apiPost).not.toHaveBeenCalledWith(expect.stringContaining('/cancel'), expect.anything())
    wrapper.unmount()
  })

  it('resolves a watchlist membership snapshot before preparing its instrument history', async () => {
    resolveWatchlistSource.mockResolvedValue({
      source: { source_id: 'watchlist:7', membership_version: 'watchlist:7:v2' },
      members: [
        { instrument_id: 7, position: 0, relationship_type: 'member' },
        { instrument_id: 8, position: 1, relationship_type: 'member' },
      ],
      exclusions: [],
    })
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { universe_source_id: 'watchlist:7', as_of: '2024-02-15T15:30:00Z' } })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/code/validate', expect.anything(), expect.objectContaining({ priority: 'high' })))

    expect(resolveWatchlistSource).toHaveBeenCalledWith('watchlist:7', '2024-02-15T15:30:00.000Z')
    expect(ensurePreparation).toHaveBeenNthCalledWith(1, expect.objectContaining({ target: { kind: 'instrument', instrument_id: 7 } }), expect.anything())
    expect(ensurePreparation).toHaveBeenNthCalledWith(2, expect.objectContaining({ target: { kind: 'instrument', instrument_id: 8 } }), expect.anything())
    wrapper.unmount()
  })

  it('keeps a saved result visible and does not create a run when selected data preparation is unavailable', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({ id: 77, status: 'completed', run_config: { symbol: 'SPY', timeframe: 'D1' }, dataset_manifest: { symbol: 'SPY', timeframe: 'D1' }, artifacts: [{ id: 1, name: 'saved', artifact_type: 'scalar', payload: { value: 4 } }] })
      : Promise.resolve([]))
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    ensurePreparation.mockResolvedValueOnce({ status: 'ready' }).mockResolvedValueOnce({ status: 'unavailable' })
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { study_run_id: 77, study_run_name: 'Saved study' } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))
    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.get('button[aria-label="Run study"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Requested data is unavailable.'))

    expect(wrapper.text()).toContain('Run #77')
    expect(apiPost).not.toHaveBeenCalledWith('/code/assets', expect.anything())
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    wrapper.unmount()
  })

  it('does not certify a draft for execution when preparation is unavailable during validation', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({ id: 77, status: 'completed', run_config: { symbol: 'SPY', timeframe: 'D1' }, dataset_manifest: { symbol: 'SPY', timeframe: 'D1' }, artifacts: [{ id: 1, name: 'saved', artifact_type: 'scalar', payload: { value: 4 } }] })
      : Promise.resolve([]))
    ensurePreparation.mockResolvedValue({ status: 'unavailable' })
    const wrapper = mountTool({ activeSymbol: 'XLB', configuration: { study_run_id: 77, study_run_name: 'Saved study' } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))
    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study data preparation"]').text()).toContain('Some selected Study data is not ready'))

    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    expect(wrapper.text()).toContain('Run #77')
    expect(wrapper.text()).toContain('saved scalar result: 4')
    wrapper.unmount()
  })

  it('aborts stale preparation when the selected symbol changes during validation', async () => {
    const pending = deferred<{ status: string }>()
    ensurePreparation.mockReturnValueOnce(pending.promise)
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : Promise.resolve({}))
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })

    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    const [, options] = ensurePreparation.mock.calls[0]
    await wrapper.get('[aria-label="Study symbol"]').setValue('XLB')
    expect(options.signal.aborted).toBe(true)
    pending.resolve({ status: 'ready' })
    await flushPromises()
    expect(apiPost.mock.calls.some(([path]) => path === '/code/validate')).toBe(false)
    wrapper.unmount()
  })

  it('invalidates the persisted-run list when a new Study run is submitted', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 222, code_version_id: 42, status: 'queued', artifacts: [] })
      return Promise.resolve({})
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = mountTool({ activeSymbol: 'XLB', configuration: {} }, queryClient)
    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.get('button[aria-label="Run study"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #222'))

    expect(invalidateQueries).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['workstation', 'research-runs'] }))
    wrapper.unmount()
  })

  it('shows a newly completed Study run and its artifact count in the adjacent Results list without manual refresh', async () => {
    let listReads = 0
    const staleQueuedRun = {
      id: 222,
      code_version_id: 42,
      status: 'queued',
      artifact_count: 0,
      run_config: {},
      dataset_manifest: {},
      artifacts: [],
    }
    const completedRun = {
      id: 222,
      code_version_id: 42,
      status: 'completed',
      artifact_count: 8,
      run_config: { symbol: 'XLB', timeframe: 'D1' },
      dataset_manifest: { symbol: 'XLB', datasets: [{ symbol: 'XLB' }] },
      artifacts: Array.from({ length: 8 }, (_, index) => ({
        id: index + 1,
        name: `output-${index + 1}`,
        artifact_type: 'scalar',
        payload: { value: index + 1 },
      })),
    }
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs') {
        listReads += 1
        return Promise.resolve(listReads === 1
          ? [{ id: 6, status: 'completed', code_version_id: 41, artifact_count: 0, artifacts: [] }]
          : [staleQueuedRun, { id: 6, status: 'completed', code_version_id: 41, artifact_count: 0, artifacts: [] }])
      }
      if (path === '/research/runs/222') return Promise.resolve(completedRun)
      return Promise.resolve(undefined)
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 222, code_version_id: 42, status: 'queued', artifacts: [] })
      return Promise.resolve({})
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const results = mount(ResearchResultsTool, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } },
      },
    })
    const study = mountTool({ activeSymbol: 'XLB', configuration: {} }, queryClient)
    await vi.waitFor(() => expect(results.find('[aria-label="Run 6, completed, 0 artifacts"]').exists()).toBe(true))

    await study.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(study.text()).toContain('Validated for isolated execution'))
    await study.get('button[aria-label="Run study"]').trigger('click')
    await vi.waitFor(() => expect(results.find('[aria-label="Run 222, completed, 8 artifacts"]').exists()).toBe(true))

    expect(results.text()).toContain('Run #222')
    expect(listReads).toBeGreaterThanOrEqual(2)
    study.unmount()
    results.unmount()
  })

  it('does not let a late validation response bless source edited while it was pending', async () => {
    const pendingValidation = deferred<unknown>()
    apiPost.mockImplementation((path: string) => path === '/code/validate' ? pendingValidation.promise : Promise.resolve({}))
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
    const source = wrapper.find('[aria-label="Study Python source"]')
    const validate = wrapper.get('button[aria-label="Validate study"]')
    const run = wrapper.get('button[aria-label="Run study"]')

    await validate.trigger('click')
    expect(validate.attributes('disabled')).toBeDefined()
    await source.setValue("output.scalar('edited-during-validation', 1)")
    pendingValidation.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
    await flushPromises()

    expect(run.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Study source changed since validation. Validate the current source before running.')
    expect(apiPost).not.toHaveBeenCalledWith('/code/assets', expect.anything())
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
    wrapper.unmount()
  })

  it('discloses selected Market Map source lineage without replacing the canonical source ID', () => {
    const wrapper = mountTool({
      activeSymbol: 'SPY',
      configuration: {
        source_id: 'watchlist:7',
        analysis_source_id: 'explicit:4,2,4',
        analysis_scope: 'selection',
        selected_member_ids: [4, 2, 4],
        universe_source_id: 'explicit:4,2',
      },
    })

    const lineage = wrapper.find('[aria-label="Study source lineage"]')
    expect(lineage.exists()).toBe(true)
    expect(lineage.text()).toContain('Selected members · 2 · Locked explicit source')
    expect(lineage.text()).toContain('Parent source watchlist:7')
    expect(lineage.attributes('data-source-id')).toBe('explicit:4,2,4')
    expect(wrapper.find('[aria-label="Study universe source"]').element).toHaveProperty('value', 'explicit:4,2')
  })

  it('hydrates a persisted run after a virtual-tool remount', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({ id: 77, status: 'completed', run_config: { symbol: 'SPY', timeframe: 'D1' }, dataset_manifest: { symbol: 'SPY', timeframe: 'D1', datasets: [{ symbol: 'SPY' }] }, artifacts: [{ id: 1, name: 'event_count', artifact_type: 'scalar', payload: { value: 4 } }] })
      : Promise.resolve(undefined))
    const wrapper = mountTool({ activeSymbol: 'XLB', configuration: { study_run_id: 77, study_run_source: 'output.scalar("event_count", 4)', study_run_contract: 'scalar', study_run_name: 'Saved SPY result' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))
    expect(wrapper.text()).toContain('event_count')
    expect(wrapper.get('[aria-label="Saved run dataset"]').text()).toContain('Saved run #77 dataset: symbol SPY')
    const summaryId = wrapper.find('[aria-label="event_count metric"]').attributes('aria-describedby')
    expect(summaryId).toMatch(/-study-artifact-1-summary$/)
    expect(wrapper.find(`#${summaryId}`).text()).toContain('event_count scalar result: 4.')
    expect(apiGet).toHaveBeenCalledWith('/research/runs/77', undefined, expect.objectContaining({ priority: 'high' }))
  })

  it('distinguishes a saved deferred evaluation from a completed Study result', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({
          id: 77,
          status: 'completed',
          evaluation_status: 'deferred',
          run_config: { symbol: 'SPY', timeframe: 'D1' },
          dataset_manifest: { symbol: 'SPY', timeframe: 'D1' },
          diagnostics: [{ code: 'coverage_preflight_blocked' }],
          artifact_count: 0,
          artifacts: [],
        })
      : Promise.resolve(undefined))
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { study_run_id: 77 } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #77'))

    expect(wrapper.get('[aria-label="Study run status: Evaluation deferred"]').attributes('data-status')).toBe('completed')
    expect(wrapper.get('.study-lab-tool__run-guidance').text()).toContain('No artifacts were produced')
    expect(wrapper.find('.study-lab-tool__metrics').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps a saved run tied to its recorded dataset while the current draft changes', async () => {
    const savedRun = {
      id: 6,
      status: 'completed',
      code_version_id: 42,
      run_config: { symbol: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', session: 'regular', benchmark: 'SPY', parameters: { lookback: 20 } },
      dataset_manifest: { symbol: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', session: 'regular', benchmark: 'SPY', datasets: [{ symbol: 'SPY' }] },
      artifacts: [{ id: 1, name: 'last_close', artifact_type: 'scalar', payload: { value: 763.96 } }],
    }
    apiGet.mockImplementation((path: string) => path === '/research/runs/6' ? Promise.resolve(savedRun) : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      : path === '/code/assets'
        ? Promise.resolve({ versions: [{ id: 777 }] })
        : Promise.resolve({}))
    const wrapper = mountTool({
      activeSymbol: 'XLB',
      configuration: {
        study_run_id: 6,
        study_run_source: "output.scalar('last_close', 763.96)",
        study_run_contract: 'scalar',
        study_run_name: 'Saved SPY study',
        study_run_parameter_schema: { properties: { lookback: { type: 'integer' } } },
      },
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #6'))

    expect(wrapper.text()).toContain('Current draft dataset: XLB')
    expect(wrapper.get('[aria-label="Saved run dataset"]').text()).toContain('Saved run #6 dataset: symbol SPY')
    expect(wrapper.get('[aria-label="Saved run dataset"]').text()).not.toContain('symbol XLB')
    expect(wrapper.text()).toContain('last_close')

    await wrapper.get('[aria-label="Study name"]').setValue('Draft XLB study')
    await wrapper.get('[aria-label="Study timeframe"]').setValue('MN')
    await wrapper.get('[aria-label="Study Python source"]').setValue("output.scalar('draft_metric', 1)")
    await wrapper.get('button[aria-label="Validate study"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))

    expect(wrapper.get('[aria-label="Saved run dataset"]').text()).toContain('symbol SPY')
    expect(wrapper.text()).toContain('last_close')
    await wrapper.findAll('button').find(button => button.text() === 'Save as column')!.trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.anything()))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      name: 'Saved SPY study column',
      initial_version: expect.objectContaining({
        source: "output.scalar('last_close', 763.96)",
        parameter_schema: { properties: { lookback: { type: 'integer' } } },
        default_parameters: { lookback: 20 },
        lineage: expect.objectContaining({
          source_run_id: 6,
          source_run_config: expect.objectContaining({ symbol: 'SPY', timeframe: 'D1' }),
          source_dataset_manifest: expect.objectContaining({ symbol: 'SPY' }),
        }),
      }),
    }))
    wrapper.unmount()
  })

  it('keeps an in-flight promotion bound to the selected run when the selection changes', async () => {
    const promotion = deferred<{ versions: Array<{ id: number }> }>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs/6') return Promise.resolve({
        id: 6,
        status: 'completed',
        code_version_id: 42,
        run_config: { symbol: 'SPY', parameters: { lookback: 20 } },
        dataset_manifest: { symbol: 'SPY', datasets: [{ symbol: 'SPY' }] },
        artifacts: [{ id: 1, name: 'spy_close', artifact_type: 'scalar', payload: { value: 101 } }],
      })
      if (path === '/research/runs/7') return Promise.resolve({
        id: 7,
        status: 'completed',
        code_version_id: 84,
        run_config: { symbol: 'XLB', parameters: { lookback: 5 } },
        dataset_manifest: { symbol: 'XLB', datasets: [{ symbol: 'XLB' }] },
        artifacts: [{ id: 2, name: 'xlb_close', artifact_type: 'scalar', payload: { value: 202 } }],
      })
      return Promise.resolve(undefined)
    })
    apiPost.mockImplementation((path: string) => path === '/code/assets' ? promotion.promise : Promise.resolve({}))
    const wrapper = mountTool({
      activeSymbol: 'XLB',
      configuration: {
        study_run_id: 6,
        study_run_source: "output.scalar('spy_close', 101)",
        study_run_contract: 'scalar',
        study_run_name: 'Saved SPY run',
        study_run_parameter_schema: { properties: { lookback: { type: 'integer', minimum: 10 } } },
      },
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #6'))

    await wrapper.findAll('button').find(button => button.text() === 'Save as column')!.trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.any(Object)))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      name: 'Saved SPY run column',
      initial_version: expect.objectContaining({
        source: "output.scalar('spy_close', 101)",
        parameter_schema: { properties: { lookback: { type: 'integer', minimum: 10 } } },
        default_parameters: { lookback: 20 },
        lineage: expect.objectContaining({
          source_run_id: 6,
          source_run_config: expect.objectContaining({ symbol: 'SPY' }),
          source_dataset_manifest: expect.objectContaining({ symbol: 'SPY' }),
        }),
      }),
    }))

    await wrapper.setProps({ configuration: { study_run_id: 7, study_run_source: "output.scalar('xlb_close', 202)", study_run_contract: 'scalar', study_run_name: 'Saved XLB run', study_run_parameter_schema: { properties: { lookback: { type: 'integer', maximum: 5 } } } } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #7'))
    promotion.resolve({ versions: [{ id: 777 }] })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(apiPost.mock.calls[0][1]).toEqual(expect.objectContaining({
      name: 'Saved SPY run column',
      initial_version: expect.objectContaining({ lineage: expect.objectContaining({ source_run_id: 6 }) }),
    }))
    wrapper.unmount()
  })

  it('switches the displayed result identity when the persisted run selection changes', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs/6') return Promise.resolve({ id: 6, status: 'completed', run_config: { symbol: 'SPY' }, dataset_manifest: { datasets: [{ symbol: 'SPY' }] }, artifacts: [{ id: 1, name: 'spy_result', artifact_type: 'scalar', payload: { value: 1 } }] })
      if (path === '/research/runs/7') return Promise.resolve({ id: 7, status: 'completed', run_config: { symbol: 'XLB' }, dataset_manifest: { datasets: [{ symbol: 'XLB' }] }, artifacts: [{ id: 2, name: 'xlb_result', artifact_type: 'scalar', payload: { value: 2 } }] })
      return Promise.resolve(undefined)
    })
    const wrapper = mountTool({ activeSymbol: 'XLB', configuration: { study_run_id: 6 } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #6'))
    await wrapper.setProps({ configuration: { study_run_id: 7 } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #7'))
    expect(wrapper.get('[aria-label="Saved run dataset"]').text()).toContain('symbol XLB')
    expect(wrapper.text()).toContain('xlb_result')
    expect(wrapper.text()).not.toContain('spy_result')
  })

  it('shows a retryable error when a persisted result cannot be restored', async () => {
    let attempts = 0
    apiGet.mockImplementation((path: string) => {
      if (path !== '/research/runs/6') return Promise.resolve(undefined)
      attempts += 1
      return attempts === 1
        ? Promise.reject(new Error('temporary read failure'))
        : Promise.resolve({ id: 6, status: 'completed', run_config: { symbol: 'SPY' }, artifacts: [] })
    })
    const wrapper = mountTool({ activeSymbol: 'XLB', configuration: { study_run_id: 6 } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved Study run #6 could not be loaded'))
    const retry = wrapper.findAll('button').find(button => button.text().includes('Retry loading saved run'))!
    expect(retry.exists()).toBe(true)
    await retry.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #6'))
    expect(attempts).toBe(2)
  })

  it('keeps artifact summary relationships unique across linked Study Lab panes', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/77'
      ? Promise.resolve({ id: 77, status: 'completed', artifacts: [{ id: 1, name: 'event_count', artifact_type: 'scalar', payload: { value: 4 } }] })
      : Promise.resolve(undefined))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const props = { activeSymbol: 'SPY', configuration: { study_run_id: 77 } }
    const first = mountTool(props, queryClient)
    const second = mountTool(props, queryClient)
    await vi.waitFor(() => expect(first.text()).toContain('Run #77'))
    await vi.waitFor(() => expect(second.text()).toContain('Run #77'))

    const firstSummaryId = first.find('[aria-label="event_count metric"]').attributes('aria-describedby')
    const secondSummaryId = second.find('[aria-label="event_count metric"]').attributes('aria-describedby')
    expect(firstSummaryId).toMatch(/-study-artifact-1-summary$/)
    expect(secondSummaryId).toMatch(/-study-artifact-1-summary$/)
    expect(firstSummaryId).not.toBe(secondSummaryId)
    expect(first.find(`#${firstSummaryId}`).text()).toContain('event_count scalar result: 4.')
    expect(second.find(`#${secondSummaryId}`).text()).toContain('event_count scalar result: 4.')
  })

  it('keeps an invalid single-output structured series view/export only', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/78'
      ? Promise.resolve({ id: 78, status: 'completed', artifacts: [{ id: 2, name: 'invalid_history', artifact_type: 'series', payload: { value: { timestamps: ['not-a-date'], values: [0.4] } } }] })
      : Promise.resolve(undefined))
    const wrapper = mountTool({
      activeSymbol: 'SPY',
      configuration: { study_run_id: 78, study_run_source: "output.series('invalid_history', {'timestamps': ['not-a-date'], 'values': [0.4]})", study_run_contract: 'series' },
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #78'))

    expect(wrapper.find('[aria-label="Promote study result"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Export invalid_history"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('View/export only: this series needs valid aligned timestamps and at least one finite observation before it can be plotted or promoted.')
    expect(wrapper.find('.series-chart').exists()).toBe(false)
  })

  it('keeps an unaligned value series eligible for latest-value promotion but not chart plots', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/79'
      ? Promise.resolve({ id: 79, status: 'completed', artifacts: [{ id: 3, name: 'unaligned_history', artifact_type: 'series', payload: { value: [0.4, 0.5] } }] })
      : Promise.resolve(undefined))
    const wrapper = mountTool({
      activeSymbol: 'SPY',
      configuration: { study_run_id: 79, study_run_source: "output.series('unaligned_history', [0.4, 0.5])", study_run_contract: 'series' },
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #79'))

    const promotions = wrapper.find('[aria-label="Promote study result"]')
    expect(promotions.exists()).toBe(true)
    expect(promotions.text()).not.toContain('Save as chart plot')
    expect(promotions.text()).toContain('Save latest column')
    expect(wrapper.text()).toContain('Chart plot unavailable: this series has no aligned timestamp axis.')
    expect(wrapper.find('.series-chart').exists()).toBe(false)
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
    expect(apiGet.mock.calls.some(([path]) => path === '/research/runs/77')).toBe(false)
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

  it('reads the canonical Study run when completion wins a cancel race', async () => {
    const running = { id: 102, status: 'running', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [], artifacts: [] }
    const completed = { ...running, status: 'completed' }
    let cancelAttempted = false
    apiGet.mockImplementation((path: string) => path === '/research/runs/102'
      ? Promise.resolve(cancelAttempted ? completed : running)
      : Promise.resolve(undefined))
    apiPost.mockImplementationOnce(() => {
      cancelAttempted = true
      return Promise.reject(terminalCancelConflict(102))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: { study_run_id: 102 } }, queryClient)
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study run status: Running"]').exists()).toBe(true))
    const readsBeforeCancel = apiGet.mock.calls.filter(([path]) => path === '/research/runs/102').length

    await wrapper.get('[aria-label="Cancel study run"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[aria-label="Study run status: Completed"]').exists()).toBe(true))

    expect(apiPost).toHaveBeenCalledWith('/research/runs/102/cancel', {}, expect.objectContaining({ priority: 'high' }))
    expect(apiGet.mock.calls.filter(([path]) => path === '/research/runs/102').length).toBeGreaterThan(readsBeforeCancel)
    expect(wrapper.text()).not.toContain('Study canceled.')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(queryClient.getQueryData(['workstation', 'research-run', 102])).toMatchObject({ id: 102, status: 'completed' })
    wrapper.unmount()
    queryClient.clear()
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
    const statsReferenceRows = wrapper.findAll('.study-lab-tool__sdk-reference > span').filter(row => row.text().startsWith('stats:'))
    expect(statsReferenceRows).toHaveLength(1)
    expect(wrapper.text()).toContain('positive_close_streaks')
    expect(wrapper.text()).toContain('stats: positive_close_streaks, streaks')
    expect(wrapper.text()).toContain('percentile')
    expect(wrapper.text()).toContain('distribution')
    expect(wrapper.text()).toContain('cross_sectional_rank')
    expect(wrapper.text()).toContain('conditional_outcomes')
    expect(wrapper.text()).toContain('regimes')
    expect(wrapper.text()).toContain('historical_comparison')
    expect(wrapper.text()).not.toContain('historical comparisons')
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
      { value: 'breadth_thrust_90_90', label: '90/90 breadth thrust' },
      { value: 'breadth_thrust_history_90_90', label: 'Historical 90/90 breadth thrust' },
      { value: 'generic_breadth_cross_sectional_percentile', label: 'Cross-sectional percentile breadth' },
      { value: 'current_history_comparison', label: 'Current versus history' },
    ]))

    for (const value of ['forward_return_distribution', 'event_frequency', 'high_low_breakouts', 'volatility_regime', 'seasonality', 'relative_strength_regime', 'current_history_comparison']) {
      await selector.setValue(value)
      expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value.length).toBeGreaterThan(80)
    }
    await selector.setValue('negative_streak')
    expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value).toContain("stats.streaks(closes, 'negative')")
    await selector.setValue('current_history_comparison')
    const currentHistorySource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(currentHistorySource).toContain('research.historical_comparison')
    expect(currentHistorySource).toContain('history = returns[:-1]')
    expect(currentHistorySource).toContain('current = returns[-1] if returns else None')
    expect(currentHistorySource).toContain('research.historical_comparison(history, current)')
    expect(currentHistorySource).toContain("output.histogram('historical_return_distribution'")
    expect(currentHistorySource).toContain("output.histogram('historical_return_distribution', history, 12, comparison['current'])")
    expect(currentHistorySource).toContain("output.scalar('historical_sample_size'")
    await selector.setValue('breadth_thrust_90_90')
    const breadthThrustSource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(breadthThrustSource).toContain('research.breadth_thrust(dataset, 90)')
    expect(breadthThrustSource).toContain("output.boolean('qualifies_90_90'")
    await selector.setValue('breadth_thrust_history_90_90')
    const breadthHistorySource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(breadthHistorySource).toContain('research.breadth_thrust_history(dataset, 90)')
    expect(breadthHistorySource).toContain("output.series('percent_price_advancing_history'")
    expect(breadthHistorySource).toContain("output.histogram('price_participation_distribution'")
    expect(breadthHistorySource).toContain("output.histogram('volume_participation_distribution'")
    expect(breadthHistorySource).toContain("price_history[-1] if price_history else None")
    expect(breadthHistorySource).toContain("output.events('breadth_thrust_occurrences'")
    await selector.setValue('generic_breadth_cross_sectional_percentile')
    const crossSectionalBreadthSource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(crossSectionalBreadthSource).toContain("'target_scope': 'cross_sectional'")
    expect(crossSectionalBreadthSource).toContain('research.breadth_condition(dataset, condition, True)')
    expect(wrapper.find('[aria-label="Study parameter field"]').element).toHaveProperty('value', 'close')
    expect(wrapper.find('[aria-label="Study parameter percentile"]').element).toHaveProperty('value', '0.5')
    await selector.setValue('seasonality')
    const seasonalitySource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(seasonalitySource).toContain('average_day_of_week_return')
    expect(seasonalitySource).toContain("weekday_names = ['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']")
    expect(seasonalitySource).not.toContain('lambda')
    await selector.setValue('forward_return_distribution')
    const forwardSource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(forwardSource).toContain('research.conditional_outcomes')
    expect(forwardSource).not.toContain('research.forward_returns')
    await selector.setValue('volatility_regime')
    const volatilitySource = (wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value
    expect(volatilitySource).toContain("stats.rolling(returns, 20, 'std')")
    expect(volatilitySource).toContain('stats.median(valid_volatility)')
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
    expect(apiPost.mock.calls.some(([path]) => path === '/research/runs')).toBe(false)
  })

  it('validates, starts an immutable isolated study run, and renders artifacts', async () => {
    apiGet.mockImplementation((path: string) => path === '/code/assets'
      ? Promise.resolve([{ versions: [{ id: 42, source: 'output.events("signals", [])', parameter_schema: {}, default_parameters: {} }] }])
      : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['stats', 'output'], lookback_hint: 1, output_contracts: ['bar', 'histogram', 'range', 'scatter', 'scalar', 'table'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 9, code_version_id: 42, status: 'completed', reproducibility_hash: 'sha256:test', run_config: { universe_source_id: 'market-group:sp500', parameters: {}, timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01' }, dataset_manifest: { universe_source_id: 'market-group:sp500', universe_membership_version: 'market-group:sp500:v1', timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', session: 'all', start_date: '2024-01-01', end_date: '2024-02-01', datasets: [{ instrument_id: 7, symbol: 'SPY' }] }, artifacts: [
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
      if (path === '/research/runs/9/promote-event-filter') return Promise.resolve({ id: 88, name: 'signals Filter' })
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
    }), expect.objectContaining({ priority: 'high' }))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      initial_version: expect.objectContaining({ output_contract: 'study' }),
    }))
    expect(wrapper.text()).toContain('Current draft dataset: SPY · W1 · raw · all session · benchmark QQQ')
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
    const createObjectURL = vi.fn(() => 'blob:study-artifact')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    await wrapper.find('[aria-label="Export current_streak"]').trigger('click')
    await wrapper.find('[aria-label="Export trend"]').trigger('click')
    expect(createObjectURL).toHaveBeenCalledTimes(2)
    expect(anchorClick).toHaveBeenCalledTimes(2)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:study-artifact')
    Reflect.deleteProperty(URL, 'createObjectURL')
    Reflect.deleteProperty(URL, 'revokeObjectURL')
    anchorClick.mockRestore()
    await wrapper.findAll('button').find(button => button.text() === 'Save plot: trend')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable chart plot.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      initial_version: expect.objectContaining({ output_contract: 'series', output_name: 'trend' }),
    }))
    const latestColumnButton = wrapper.findAll('button').find(button => button.text() === 'Save latest column: trend')
    expect(latestColumnButton).toBeDefined()
    await latestColumnButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'scalar',
        output_name: 'trend',
        lineage: expect.objectContaining({
          source_run_id: 9,
          source_output_name: 'trend',
          output_adapter: 'latest_series_to_scalar',
          semantics: 'study_series_latest_result_as_watchlist_column',
        }),
      }),
    }))
    const rangeCenterButton = wrapper.findAll('button').find(button => button.text() === 'Save center plot: confidence')
    expect(rangeCenterButton).toBeDefined()
    await rangeCenterButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable chart plot.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'plot',
      initial_version: expect.objectContaining({
        output_contract: 'series',
        output_name: 'confidence',
        lineage: expect.objectContaining({
          source_run_id: 9,
          source_output_name: 'confidence',
          output_adapter: 'range_center_to_series',
          semantics: 'study_range_center_result_as_chart_plot',
        }),
      }),
    }))
    const rangeCenterColumnButton = wrapper.findAll('button').find(button => button.text() === 'Save latest center column: confidence')
    expect(rangeCenterColumnButton).toBeDefined()
    await rangeCenterColumnButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'scalar',
        output_name: 'confidence',
        lineage: expect.objectContaining({
          source_run_id: 9,
          source_output_name: 'confidence',
          target: 'column',
          output_adapter: 'range_center_to_scalar',
          semantics: 'study_range_center_result_as_latest_watchlist_column',
        }),
      }),
    }))
    await wrapper.findAll('button').find(button => button.text() === 'Save column: qualifies')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'qualifies',
        lineage: expect.objectContaining({
          source_run_id: 9,
          source_code_version_id: 42,
          source_reproducibility_hash: 'sha256:test',
          target: 'column',
          semantics: 'study_boolean_result_as_typed_watchlist_column',
        }),
      }),
    }))
    expect(wrapper.findAll('button').some(button => button.text() === 'Save filter: qualifies')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Save column: qualifies')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Promote scan: qualifies')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Use Gauge: qualifies')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Promote alert: qualifies')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Save signal: qualifies')).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === 'Save filter: qualifies')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist filter through EasyScan.'))
    await wrapper.findAll('button').find(button => button.text() === 'Promote scan: qualifies')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to a reusable scan.'))
    await wrapper.findAll('button').find(button => button.text() === 'Use Gauge: qualifies')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Available as a Market Gauge from the saved EasyScan.'))
    await wrapper.findAll('button').find(button => button.text() === 'Promote alert: qualifies')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to an active scan alert.'))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/42', expect.any(Object))
    await wrapper.findAll('button').find(button => button.text() === 'Save signal: qualifies')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable Strategy Lab signal.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'signal',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'qualifies',
        lineage: expect.objectContaining({
          source_run_id: 9,
          source_output_name: 'qualifies',
          target: 'signal',
          semantics: 'study_result_promotion',
        }),
      }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/42', {})
    expect(wrapper.findAll('button').some(button => button.text() === 'Save filter: signals')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Promote alert: signals')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === 'Save signal: signals')).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === 'Save signal: signals')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved event artifact “signals” as a reusable Strategy Lab signal.'))
    expect(apiGet).toHaveBeenCalledWith('/code/assets', undefined, expect.objectContaining({ priority: 'high' }))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'signal',
      initial_version: expect.objectContaining({
        output_contract: 'events',
        output_name: 'signals',
        lineage: expect.objectContaining({
          source_run_id: 9,
          source_code_version_id: 42,
          source_reproducibility_hash: 'sha256:test',
          source_output_name: 'signals',
          target: 'signal',
          output_adapter: 'events_to_signal',
          semantics: 'study_event_result_as_strategy_signal',
        }),
      }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/42', {})
    await wrapper.findAll('button').find(button => button.text() === 'Save filter: signals')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved event artifact “signals” as a reusable watchlist filter.'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/9/promote-event-filter', { artifact_name: 'signals' })
    await wrapper.findAll('button').find(button => button.text() === 'Promote alert: signals')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted event artifact “signals” to an active alert.'))
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 88, trigger_type: 'both', repeat: true, notes: 'Created from event study run 9' })
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
    const eventListItem = wrapper.get('[aria-label="events occurrences"] [role="listitem"]')
    const eventButton = eventListItem.get('button')
    expect(eventButton.attributes('aria-label')).toBe('SPY 2026-01-02 streak')
    expect(eventButton.attributes('type')).toBe('button')
  })

  it('offers threshold fan-out for a finite named scalar in a structured Study run', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: 1, output_contracts: ['scalar', 'table'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 201 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 202,
        code_version_id: 201,
        status: 'completed',
        run_config: { universe_source_id: 'watchlist:7', timeframe: 'D1' },
        dataset_manifest: { universe_source_id: 'watchlist:7', universe_membership_version: 'watchlist:7:v2', timeframe: 'D1', datasets: [{ instrument_id: 7, symbol: 'SPY' }] },
        artifacts: [
          { id: 1, name: 'score', artifact_type: 'scalar', payload: { value: 12 } },
          { id: 2, name: 'records', artifact_type: 'table', payload: { value: [{ score: 12 }] } },
        ],
      })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.scalar('score', market.close()[-1])\noutput.table('records', [])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #202'))

    const threshold = wrapper.get('[aria-label="score threshold condition"]')
    expect(threshold.exists()).toBe(true)
    await threshold.get('[aria-label="Structured scalar condition operator: score"]').setValue('gt')
    await threshold.get('[aria-label="Structured scalar condition threshold: score"]').setValue('10')
    await threshold.get('[aria-label="Save Boolean column: score"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved scalar artifact “score” as a thresholded Boolean column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'score',
        lineage: expect.objectContaining({
          source_run_id: 202,
          source_output_name: 'score',
          output_adapter: 'scalar_target_to_boolean',
          series_target: { operator: 'gt', threshold: 10 },
          semantics: 'study_scalar_threshold_as_boolean',
        }),
      }),
    }))
  })

  it('keeps structured output threshold drafts independent per artifact', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: 1, output_contracts: ['scalar', 'series'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 301 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 302,
        code_version_id: 301,
        status: 'completed',
        run_config: { symbol: 'SPY', timeframe: 'D1' },
        dataset_manifest: { datasets: [{ instrument_id: 7, symbol: 'SPY' }] },
        artifacts: [
          { id: 1, name: 'score', artifact_type: 'scalar', payload: { value: 12 } },
          { id: 2, name: 'trend', artifact_type: 'series', payload: { value: { timestamps: ['2026-01-01'], values: [0.7] } } },
        ],
      })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.scalar('score', market.close()[-1])\noutput.series('trend', market.close())")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #302'))

    const scoreCondition = wrapper.get('[aria-label="score threshold condition"]')
    const trendCondition = wrapper.get('[aria-label="trend threshold condition"]')
    await scoreCondition.get('[aria-label="Structured scalar condition operator: score"]').setValue('gt')
    await scoreCondition.get('[aria-label="Structured scalar condition threshold: score"]').setValue('10')
    await trendCondition.get('[aria-label="Structured series condition operator: trend"]').setValue('lt')
    await trendCondition.get('[aria-label="Structured series condition threshold: trend"]').setValue('0.5')

    expect(scoreCondition.get('[aria-label="Structured scalar condition operator: score"]').element).toHaveProperty('value', 'gt')
    expect(scoreCondition.get('[aria-label="Structured scalar condition threshold: score"]').element).toHaveProperty('value', '10')
    expect(trendCondition.get('[aria-label="Structured series condition operator: trend"]').element).toHaveProperty('value', 'lt')
    expect(trendCondition.get('[aria-label="Structured series condition threshold: trend"]').element).toHaveProperty('value', '0.5')

    await scoreCondition.get('[aria-label="Save Boolean column: score"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved scalar artifact “score” as a thresholded Boolean column.'))
    await trendCondition.get('[aria-label="Save Boolean column: trend"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved series artifact “trend” as a thresholded Boolean column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_name: 'score',
        lineage: expect.objectContaining({ series_target: { operator: 'gt', threshold: 10 } }),
      }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_name: 'trend',
        lineage: expect.objectContaining({ series_target: { operator: 'lt', threshold: 0.5 } }),
      }),
    }))
    wrapper.unmount()
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
    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({ run_config: expect.objectContaining({ symbols: ['SPY', 'XLK'], parameters: { lookback: 30 } }) }), expect.objectContaining({ priority: 'high' }))
  })

  it('reuses an opened immutable Study definition version without creating a duplicate asset', async () => {
    const source = "condition = parameters.get('condition', {'kind': 'above_moving_average'})\noutput.scalar('current_percentage', 0.5)"
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['parameters', 'output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/research/runs') return Promise.resolve({ id: 314, code_version_id: 91, status: 'completed', artifacts: [{ id: 1, name: 'current_percentage', artifact_type: 'scalar', payload: { value: 0.5 } }] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({
      activeSymbol: 'SPY',
      configuration: {
        study_asset_version_id: 91,
        study_name: 'Saved breadth definition',
        study_source: source,
        study_output_contract: 'study',
        study_default_parameters: { condition: { kind: 'above_moving_average' }, source_id: 'explicit:4,2' },
        parameter_schema: JSON.stringify({ properties: { condition: { type: 'object' }, source_id: { type: 'string' } } }),
        universe_source_id: 'explicit:4,2',
      },
    })

    expect(wrapper.find('[aria-label="Study name"]').element).toHaveProperty('value', 'Saved breadth definition')
    expect((wrapper.find('[aria-label="Study Python source"]').element as HTMLTextAreaElement).value).toBe(source)
    await wrapper.findAll('button').find(button => button.text() === 'Validate')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #314'))

    expect(apiPost).not.toHaveBeenCalledWith('/code/assets', expect.anything())
    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({
      code_version_id: 91,
      run_config: expect.objectContaining({
        universe_source_id: 'explicit:4,2',
        parameters: { condition: { kind: 'above_moving_average' }, source_id: 'explicit:4,2' },
      }),
    }), expect.objectContaining({ priority: 'high' }))
  })

  it('preserves a durable active run when its Study Lab pane is closed', async () => {
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
    expect(apiPost.mock.calls.some(([requestPath]) => requestPath === '/research/runs/101/cancel')).toBe(false)
  })

  it('keeps a late-created run durable and publishes it to the open Results surface after Study Lab closes', async () => {
    let resolveRun!: (value: unknown) => void
    const createdRun = { id: 202, code_version_id: 52, status: 'queued', run_config: { symbol: 'SPY' }, dataset_manifest: { symbol: 'SPY' }, artifact_count: 0, artifacts: [] }
    let listReads = 0
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs') return Promise.resolve(listReads++ === 0 ? [] : [createdRun])
      if (path === '/research/runs/202') return Promise.resolve(createdRun)
      return Promise.resolve({})
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 52 }] })
      if (path === '/research/runs') return new Promise(resolve => { resolveRun = resolve })
      return Promise.resolve({})
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const results = mount(ResearchResultsTool, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } },
      },
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' }, queryClient)
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button').find(button => button.text() === 'Run')!.trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.anything(), expect.objectContaining({ priority: 'high' })))
    wrapper.unmount()

    resolveRun(createdRun)
    await vi.waitFor(() => expect(results.find('[aria-label="Run 202, queued, 0 artifacts"]').exists()).toBe(true))
    expect(queryClient.getQueryData(['workstation', 'research-run', 202])).toMatchObject(createdRun)
    expect(apiPost.mock.calls.some(([requestPath]) => requestPath === '/research/runs/202/cancel')).toBe(false)
    results.unmount()
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
      if (path === '/research/runs') return Promise.resolve({ id: 90, code_version_id: 42, status: 'completed', run_config: { universe_source_id: 'market-group:sp500', parameters: {}, timeframe: 'D1' }, dataset_manifest: { universe_source_id: 'market-group:sp500', universe_membership_version: 'market-group:sp500:v1', timeframe: 'D1', datasets: [{ instrument_id: 7, symbol: 'SPY' }] }, artifacts: [{ id: 1, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } }] })
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

    expect(wrapper.find('[aria-label="Promote study result"]').text()).toContain('Save as watchlist filter')
    expect(wrapper.find('[aria-label="Promote study result"]').text()).toContain('Use as Market Gauge')
    expect(wrapper.find('[aria-label="Promote study result"]').text()).toContain('Save as Boolean column')
    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Boolean column')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        lineage: expect.objectContaining({
          source_run_id: 90,
          source_code_version_id: 42,
          target: 'column',
          semantics: 'study_boolean_result_as_typed_watchlist_column',
        }),
      }),
    }))
    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as watchlist filter')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist filter through EasyScan.'))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/42', expect.objectContaining({ name: 'Consecutive Positive Closes Scan', universe_type: 'custom', universe_instrument_ids: [7], timeframe: 'D1', provenance: expect.objectContaining({ source_run_id: 90, source_universe_source_id: 'market-group:sp500', source_membership_version: 'market-group:sp500:v1', point_in_time_source_preserved: false }) }))

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Promote to scan')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to a reusable scan.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({ kind: 'study', initial_version: expect.objectContaining({ source: "output.boolean('qualifies', True)", output_contract: 'boolean' }) }))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/42', expect.objectContaining({ name: 'Consecutive Positive Closes Scan', universe_type: 'custom', universe_instrument_ids: [7], timeframe: 'D1' }))

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Promote to alert')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted to an active scan alert.'))
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 77, trigger_type: 'entered', repeat: true })
    expect(apiPost.mock.calls.filter(call => String(call[0]).startsWith('/screeners/from-python-condition/'))).toHaveLength(1)

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Use as Market Gauge')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Available as a Market Gauge from the saved EasyScan.'))
    expect(apiPost.mock.calls.filter(call => String(call[0]).startsWith('/screeners/from-python-condition/'))).toHaveLength(1)

    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Strategy signal')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable Strategy Lab signal.'))
    expect(wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as Strategy signal')!.attributes('disabled')).toBeUndefined()
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/42', {})
  })

  it('refuses to promote a study when no canonical dataset members are declared', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['boolean'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 94, code_version_id: 42, status: 'completed', artifacts: [{ id: 1, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } }] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.boolean('qualifies', True)")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #94'))
    await wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Promote to scan')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('refusing to widen the promoted scan universe'))
    expect(apiPost.mock.calls.filter(call => String(call[0]).startsWith('/screeners/from-python-condition/'))).toHaveLength(0)
  })

  it('offers the latest-value column for a single-output raw numeric series', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['series'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 146 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 147, code_version_id: 146, status: 'completed', artifacts: [{ id: 1, name: 'trend', artifact_type: 'series', payload: { value: [null, 4, 6] } }] })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.series('trend', [None, 4, 6])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #147'))
    const latestColumn = wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save latest column')
    expect(latestColumn).toBeDefined()
    await latestColumn!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'scalar',
        output_name: 'trend',
        lineage: expect.objectContaining({ output_adapter: 'latest_series_to_scalar', semantics: 'study_series_latest_result_as_watchlist_column' }),
      }),
    }))
  })

  it('promotes a declared cross-sectional Study series only through the aggregate chart adapter', async () => {
    const source = "output.scalar('current_percentage', 0.5)\noutput.series('percentage_history', {'timestamps': ['2026-01-01', '2026-01-02'], 'values': [0.5, None]})"
    apiGet.mockImplementation((path: string) => path === '/code/assets'
      ? Promise.resolve([{ versions: [{ id: 151, source, output_contract: 'study', parameter_schema: {}, default_parameters: {} }] }])
      : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string, body: any) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['research', 'output'], lookback_hint: null, output_contracts: ['scalar', 'series', 'table'] })
      if (path === '/code/assets' && body?.kind === 'study') return Promise.resolve({ versions: [{ id: 151 }] })
      if (path === '/code/assets' && body?.kind === 'plot') return Promise.resolve({ id: 152, name: 'Aggregate percentage plot', versions: [{ id: 152 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 153,
        code_version_id: 151,
        status: 'completed',
        run_config: { symbols: ['SPY', 'XLK'], result_scope: 'cross_sectional' },
        dataset_manifest: { datasets: [{ instrument_id: 7, symbol: 'SPY' }, { instrument_id: 8, symbol: 'XLK' }] },
        artifacts: [
          { id: 1, name: 'current_percentage', artifact_type: 'scalar', payload: { value: 0.5 } },
          { id: 2, name: 'percentage_history', artifact_type: 'series', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], values: [0.5, null] } } },
          { id: 3, name: 'members', artifact_type: 'table', payload: { value: [] } },
        ],
      })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Factory study"]').setValue('generic_breadth_cross_sectional_percentile')
    await wrapper.find('[aria-label="Study universe"]').setValue('SPY, XLK')
    await wrapper.findAll('button')[0].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #153'))

    expect(wrapper.findAll('[aria-label="Promote study result"] button').map(button => button.text())).toEqual(['Save aggregate chart plot: percentage_history'])
    expect(wrapper.find('.series-chart').attributes('data-values')).toBe('[0.5,null]')
    await wrapper.get('[aria-label="Promote study result"] button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable chart plot.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'plot',
      initial_version: expect.objectContaining({
        output_contract: 'series',
        output_name: 'percentage_history',
        lineage: expect.objectContaining({
          output_adapter: 'study_series_to_series',
          semantics: 'study_cross_sectional_aggregate_series_as_chart_plot',
        }),
      }),
    }))
  })

  it.each([
    { label: 'misaligned aggregate axes', value: { timestamps: ['2026-01-01'], values: [0.4, 0.5] }, resultScope: 'cross_sectional' },
    { label: 'invalid aggregate timestamp', value: { timestamps: ['not-a-date'], values: [0.4] }, resultScope: 'cross_sectional' },
    { label: 'aggregate series with no finite observations', value: { timestamps: ['2026-01-01'], values: [null] }, resultScope: 'cross_sectional' },
    { label: 'invalid single-symbol timestamp', value: { timestamps: ['not-a-date'], values: [0.4] }, resultScope: 'per_symbol' },
  ])('keeps malformed Study series view/export only: $label', async ({ value, resultScope }) => {
    const source = "output.series('invalid_history', {'timestamps': ['not-a-date'], 'values': [0.4]})"
    apiGet.mockImplementation((path: string) => path === '/code/assets'
      ? Promise.resolve([{ versions: [{ id: 161, source, output_contract: 'study', parameter_schema: {}, default_parameters: {} }] }])
      : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string, body: any) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['series'] })
      if (path === '/code/assets' && body?.kind === 'study') return Promise.resolve({ versions: [{ id: 161 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 162,
        code_version_id: 161,
        status: 'completed',
        run_config: { symbols: ['SPY', 'XLK'], result_scope: resultScope },
        dataset_manifest: { datasets: [{ instrument_id: 7, symbol: 'SPY' }, { instrument_id: 8, symbol: 'XLK' }] },
        artifacts: [{ id: 1, name: 'invalid_history', artifact_type: 'series', payload: { value } }],
      })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Factory study"]').setValue('generic_breadth_cross_sectional_percentile')
    await wrapper.find('[aria-label="Study universe"]').setValue('SPY, XLK')
    await wrapper.findAll('button')[0].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #162'))

    expect(wrapper.find('[aria-label="Promote study result"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Export invalid_history"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('View/export only: this series needs valid aligned timestamps and at least one finite observation before it can be plotted or promoted.')
    expect(wrapper.find('.series-chart').exists()).toBe(false)
  })

  it('promotes a direct Study Lab series through one explicit threshold condition', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['series'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 148 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 149,
        code_version_id: 148,
        status: 'completed',
        run_config: { universe_source_id: 'watchlist:7', timeframe: 'W1' },
        dataset_manifest: { universe_source_id: 'watchlist:7', universe_membership_version: 'watchlist:7:v2', timeframe: 'W1', datasets: [{ instrument_id: 7, symbol: 'SPY' }] },
        artifacts: [{ id: 1, name: 'trend', artifact_type: 'series', payload: { value: [null, 4, 6] } }],
      })
      if (path === '/screeners/from-python-condition/148') return Promise.resolve({ id: 150 })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.series('trend', [None, 4, 6])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #149'))
    expect(wrapper.find('[aria-label="Study series threshold condition"]').exists()).toBe(true)
    await wrapper.find('[aria-label="Study series condition operator"]').setValue('gt')
    await wrapper.find('[aria-label="Study series condition threshold"]').setValue('5')
    await wrapper.findAll('[aria-label="Study series threshold condition"] button').find(button => button.text() === 'Save Boolean column')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved series artifact “trend” as a thresholded Boolean column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'trend',
        lineage: expect.objectContaining({
          source_run_id: 149,
          source_instrument_ids: [7],
          source_universe_source_id: 'watchlist:7',
          source_membership_version: 'watchlist:7:v2',
          output_adapter: 'series_target_to_boolean',
          series_target: { operator: 'gt', threshold: 5 },
          semantics: 'study_series_threshold_as_boolean',
        }),
      }),
    }))
    await wrapper.findAll('[aria-label="Study series threshold condition"] button').find(button => button.text() === 'Save watchlist filter')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved series artifact “trend” as a thresholded watchlist filter.'))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/148', expect.objectContaining({
      universe_type: 'custom',
      universe_instrument_ids: [7],
      timeframe: 'W1',
      provenance: expect.objectContaining({ output_adapter: 'series_target_to_boolean', series_target: { operator: 'gt', threshold: 5 } }),
    }))
    await wrapper.findAll('[aria-label="Study series threshold condition"] button').find(button => button.text() === 'Promote scan')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted series artifact “trend” to a thresholded scan.'))
    await wrapper.findAll('[aria-label="Study series threshold condition"] button').find(button => button.text() === 'Use as Market Gauge')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Series artifact “trend” is available as a thresholded Market Gauge.'))
    await wrapper.findAll('[aria-label="Study series threshold condition"] button').find(button => button.text() === 'Promote alert')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted series artifact “trend” to a thresholded scan alert.'))
    expect(apiPost.mock.calls.filter(call => String(call[0]).startsWith('/screeners/from-python-condition/'))).toHaveLength(1)
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 150, trigger_type: 'entered', repeat: true, notes: 'Created from Study Lab series run 149 (trend)' })
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 154 }] })
      if (path === '/strategy-lab/signals/from-code/154') return Promise.resolve({ id: 155, name: 'trend Strategy signal' })
      return Promise.resolve({})
    })
    await wrapper.findAll('[aria-label="Study series threshold condition"] button').find(button => button.text() === 'Save as Strategy signal')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved thresholded series “trend” as Strategy signal “trend Strategy signal” (#155).'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'signal',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'trend',
        lineage: expect.objectContaining({
          target: 'signal',
          output_adapter: 'series_target_to_boolean',
          series_target: { operator: 'gt', threshold: 5 },
          semantics: 'study_series_threshold_as_strategy_signal',
          source_instrument_ids: [7],
          source_universe_source_id: 'watchlist:7',
          source_membership_version: 'watchlist:7:v2',
        }),
      }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/154', {})
  })

  it('promotes a direct Study Lab scalar through an explicit threshold condition', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 159 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 160,
        code_version_id: 159,
        status: 'completed',
        run_config: { universe_source_id: 'watchlist:7', timeframe: 'D1' },
        dataset_manifest: { universe_source_id: 'watchlist:7', universe_membership_version: 'watchlist:7:v2', timeframe: 'D1', datasets: [{ instrument_id: 7, symbol: 'SPY' }] },
        artifacts: [{ id: 1, name: 'score', artifact_type: 'scalar', payload: { value: 12 } }],
      })
      if (path === '/screeners/from-python-condition/159') return Promise.resolve({ id: 161 })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.scalar('score', market.close()[-1])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #160'))
    expect(wrapper.find('[aria-label="Study scalar threshold condition"]').exists()).toBe(true)
    await wrapper.find('[aria-label="Study scalar condition operator"]').setValue('gte')
    await wrapper.find('[aria-label="Study scalar condition threshold"]').setValue('10')
    await wrapper.findAll('[aria-label="Study scalar threshold condition"] button').find(button => button.text() === 'Save Boolean column')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved scalar artifact “score” as a thresholded Boolean column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'score',
        lineage: expect.objectContaining({
          source_run_id: 160,
          source_instrument_ids: [7],
          output_adapter: 'scalar_target_to_boolean',
          series_target: { operator: 'gte', threshold: 10 },
          semantics: 'study_scalar_threshold_as_boolean',
        }),
      }),
    }))
  })

  it('promotes a direct Study Lab range center through an explicit threshold condition', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['range'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 151 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 152,
        code_version_id: 151,
        status: 'completed',
        run_config: { universe_source_id: 'watchlist:7', timeframe: 'D1' },
        dataset_manifest: { universe_source_id: 'watchlist:7', universe_membership_version: 'watchlist:7:v2', timeframe: 'D1', datasets: [{ instrument_id: 7, symbol: 'SPY' }] },
        artifacts: [{ id: 2, name: 'confidence', artifact_type: 'range', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [3, 4], center: [2, 3] } } }],
      })
      if (path === '/screeners/from-python-condition/151') return Promise.resolve({ id: 153 })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.range('confidence', [1, 2], [3, 4], [2, 3])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #152'))
    expect(wrapper.find('[aria-label="Study range center threshold condition"]').exists()).toBe(true)
    await wrapper.find('[aria-label="Study range center condition operator"]').setValue('gt')
    await wrapper.find('[aria-label="Study range center condition threshold"]').setValue('2.5')
    await wrapper.findAll('[aria-label="Study range center threshold condition"] button').find(button => button.text() === 'Save Boolean column')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved range center “confidence” as a thresholded Boolean column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'confidence',
        lineage: expect.objectContaining({
          output_adapter: 'range_center_target_to_boolean',
          series_target: { operator: 'gt', threshold: 2.5 },
          semantics: 'study_range_center_threshold_as_boolean',
        }),
      }),
    }))
    await wrapper.findAll('[aria-label="Study range center threshold condition"] button').find(button => button.text() === 'Save watchlist filter')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved range center “confidence” as a thresholded watchlist filter.'))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-python-condition/151', expect.objectContaining({
      provenance: expect.objectContaining({ output_adapter: 'range_center_target_to_boolean', series_target: { operator: 'gt', threshold: 2.5 } }),
    }))
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 156 }] })
      if (path === '/strategy-lab/signals/from-code/156') return Promise.resolve({ id: 157, name: 'confidence Strategy signal' })
      return Promise.resolve({})
    })
    await wrapper.findAll('[aria-label="Study range center threshold condition"] button').find(button => button.text() === 'Save as Strategy signal')!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved thresholded range center “confidence” as Strategy signal “confidence Strategy signal” (#157).'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'signal',
      initial_version: expect.objectContaining({
        output_contract: 'boolean',
        output_name: 'confidence',
        lineage: expect.objectContaining({
          target: 'signal',
          output_adapter: 'range_center_target_to_boolean',
          series_target: { operator: 'gt', threshold: 2.5 },
          semantics: 'study_range_center_threshold_as_strategy_signal',
        }),
      }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/156', {})
  })

  it('promotes direct single-output range centers as chart plots and latest columns', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['range'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 161 }] })
      if (path === '/research/runs') return Promise.resolve({
        id: 162,
        code_version_id: 160,
        status: 'completed',
        run_config: { universe_source_id: 'watchlist:7', timeframe: 'D1' },
        dataset_manifest: { universe_source_id: 'watchlist:7', universe_membership_version: 'watchlist:7:v2', timeframe: 'D1', datasets: [{ instrument_id: 7, symbol: 'SPY' }] },
        artifacts: [{ id: 4, name: 'confidence', artifact_type: 'range', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [3, 4], center: [2, 3] } } }],
      })
      return Promise.resolve({})
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' })
    await wrapper.find('[aria-label="Study Python source"]').setValue("output.range('confidence', [1, 2], [3, 4], [2, 3])")
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #162'))

    const plotButton = wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save center as chart plot')
    expect(plotButton).toBeDefined()
    await plotButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable chart plot.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'plot',
      initial_version: expect.objectContaining({
        output_contract: 'series',
        output_name: 'confidence',
        lineage: expect.objectContaining({
          source_run_id: 162,
          source_output_name: 'confidence',
          output_adapter: 'range_center_to_series',
          semantics: 'study_range_center_result_as_chart_plot',
        }),
      }),
    }))

    const columnButton = wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save latest center column')
    expect(columnButton).toBeDefined()
    await columnButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved as a reusable watchlist column.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'column',
      initial_version: expect.objectContaining({
        output_contract: 'scalar',
        output_name: 'confidence',
        lineage: expect.objectContaining({
          source_run_id: 162,
          source_output_name: 'confidence',
          output_adapter: 'range_center_to_scalar',
          semantics: 'study_range_center_result_as_latest_watchlist_column',
        }),
      }),
    }))
  })

  it('keeps a range without a finite aligned center view/export only', async () => {
    apiGet.mockImplementation((path: string) => path === '/research/runs/163'
      ? Promise.resolve({
        id: 163,
        status: 'completed',
        artifacts: [{ id: 5, name: 'uncertain_range', artifact_type: 'range', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [3, 4], center: [null, 3] } } }],
      })
      : Promise.resolve(undefined))
    const wrapper = mountTool({
      activeSymbol: 'SPY',
      configuration: { study_run_id: 163, study_run_source: "output.range('uncertain_range', [1, 2], [3, 4], [None, 3])", study_run_contract: 'range' },
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #163'))

    expect(wrapper.find('[aria-label="Promote study result"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Export uncertain_range"]').exists()).toBe(true)
    expect(wrapper.find('.range-chart').exists()).toBe(true)
  })

  it('promotes a completed event study without coercing its event contract', async () => {
    apiGet.mockImplementation((path: string) => path === '/code/assets'
      ? Promise.resolve([{ versions: [{ id: 144, source: "output.events('signals', [])", parameter_schema: {}, default_parameters: {} }] }])
      : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['market', 'output'], lookback_hint: 1, output_contracts: ['events'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 144 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 145, code_version_id: 144, status: 'completed', artifacts: [{ id: 1, name: 'signals', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'signal' }] } }] })
      if (path === '/research/runs/145/promote-event-filter') return Promise.resolve({ id: 147, name: 'signals Filter' })
      if (path.startsWith('/strategy-lab/signals/from-code/')) return Promise.resolve({ id: 146 })
      if (path === '/alerts/screener') return Promise.resolve({ id: 148 })
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
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved event artifact “signals” as a reusable Strategy Lab signal.'))
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      kind: 'signal',
      initial_version: expect.objectContaining({
        output_contract: 'events',
        output_name: 'signals',
        lineage: expect.objectContaining({
          source_run_id: 145,
          source_code_version_id: 144,
          source_output_name: 'signals',
          target: 'signal',
          output_adapter: 'events_to_signal',
          semantics: 'study_event_result_as_strategy_signal',
        }),
      }),
    }))
    expect(apiPost).toHaveBeenCalledWith('/strategy-lab/signals/from-code/144', {})
    const filterButton = wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Save as watchlist filter')
    expect(filterButton).toBeTruthy()
    await filterButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved event artifact “signals” as a reusable watchlist filter.'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/145/promote-event-filter', { artifact_name: 'signals' })
    const alertButton = wrapper.findAll('[aria-label="Promote study result"] button').find(button => button.text() === 'Promote events to alert')
    expect(alertButton).toBeTruthy()
    await alertButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Promoted event artifact “signals” to an active alert.'))
    expect(apiPost).toHaveBeenCalledWith('/alerts/screener', { screener_id: 147, trigger_type: 'both', repeat: true, notes: 'Created from event study run 145' })
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
    // Keep cache entries alive so the getQueryData assertion below cannot race garbage collection on a slow runner.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
    const wrapper = mountTool({ activeSymbol: 'SPY' }, queryClient)
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #90'))

    const rerunSnapshot = wrapper.findAll('button').find(button => button.text() === 'Rerun snapshot')
    expect(rerunSnapshot).toBeDefined()
    await rerunSnapshot!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #91'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/90/rerun?snapshot=true', {}, expect.objectContaining({ priority: 'high' }))
    expect(queryClient.getQueryData(['workstation', 'research-run', 91])).toMatchObject({ id: 91 })
    let rerunLatest = wrapper.findAll('button').find(button => button.text() === 'Rerun latest')
    await vi.waitFor(() => { rerunLatest = wrapper.findAll('button').find(button => button.text() === 'Rerun latest'); expect(rerunLatest).toBeDefined() })
    await rerunLatest!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #92'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs/91/rerun?snapshot=false', {}, expect.objectContaining({ priority: 'high' }))
  })

  it('publishes a late durable Study rerun to Results after the Study Lab tool unmounts', async () => {
    const run = { id: 150, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 0, artifacts: [] }
    const rerun = deferred<typeof run>()
    apiGet.mockImplementation((path: string) => path === '/research/runs' ? Promise.resolve([run]) : Promise.resolve(undefined))
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve(run)
      if (path === '/research/runs/150/rerun?snapshot=true') return rerun.promise
      return Promise.resolve({})
    })
    // Keep cache entries alive so the getQueryData assertion below cannot race garbage collection on a slow runner.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
    const results = mount(ResearchResultsTool, {
      global: { plugins: [[VueQueryPlugin, { queryClient }]], stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } } },
    })
    const wrapper = mountTool({ activeSymbol: 'SPY' }, queryClient)
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #150'))
    const rerunButton = wrapper.findAll('button').find(button => button.text() === 'Rerun snapshot')
    expect(rerunButton).toBeDefined()
    await rerunButton!.trigger('click')
    wrapper.unmount()
    rerun.resolve({ ...run, id: 151, status: 'queued' })
    await flushPromises()

    expect((wrapper.vm as unknown as { run: typeof run | null }).run).toEqual(run)
    await vi.waitFor(() => expect(results.find('[aria-label="Run 151, queued, 0 artifacts"]').exists()).toBe(true))
    expect(queryClient.getQueryData(['workstation', 'research-run', 151])).toMatchObject({ id: 151, status: 'queued' })
    results.unmount()
  })

    it('sizes the Python source editor to show the whole default factory source', () => {
      const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
      const editor = wrapper.get('[aria-label="Study Python source"]').element as HTMLTextAreaElement
      // Ten default factory lines at 14px each plus padding, so no line is cut off by default.
      expect(editor.style.minHeight).toBe('156px')
    })

    it('lists validation diagnostics with their location and keeps the raw JSON behind Details', async () => {
      const diagnostic = { message: 'Unknown name dataset2', line: 3, column: 5 }
      apiPost.mockImplementation((path: string) => {
        if (path === '/code/validate') return Promise.resolve({ valid: false, diagnostics: [diagnostic], dependencies: [], lookback_hint: null, output_contracts: [] })
        return Promise.resolve({})
      })
      const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
      await wrapper.get('button[aria-label="Validate study"]').trigger('click')
      await vi.waitFor(() => expect(wrapper.text()).toContain('Validation errors'))

      const items = wrapper.findAll('.study-lab-tool__diagnostics li')
      expect(items).toHaveLength(1)
      expect(items[0]!.text()).toBe('Unknown name dataset2 (line 3, column 5)')
      expect(wrapper.get('.study-lab-tool__raw pre').text()).toContain('"message": "Unknown name dataset2"')
    })

    it('separates the validated status from its dependency summary', async () => {
      apiPost.mockImplementation((path: string) => {
        if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] })
        return Promise.resolve({})
      })
      const wrapper = mountTool({ activeSymbol: 'SPY', configuration: {} })
      await wrapper.get('button[aria-label="Validate study"]').trigger('click')
      await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
      expect(wrapper.text()).toContain('Validated for isolated execution · Dependencies: output')
    })
})
