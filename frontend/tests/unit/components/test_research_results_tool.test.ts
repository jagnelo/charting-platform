import { flushPromises, mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('@/components/workstation/StudyBarsUPlot.vue', () => ({ default: { template: '<div class="bars-chart" />', props: ['name', 'labels', 'values'] } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))
vi.mock('@/components/workstation/StudyRangeUPlot.vue', () => ({ default: { template: '<div class="range-chart" />', props: ['name', 'timestamps', 'lower', 'upper', 'center'] } }))
vi.mock('@/components/workstation/StudyScatterUPlot.vue', () => ({ default: { template: '<div class="scatter-chart" />', props: ['name', 'x', 'y'] } }))
vi.mock('@/components/workstation/StudyHeatmap.vue', () => ({ default: { template: '<div class="heatmap-chart" />', props: ['name', 'rows', 'columns', 'values'] } }))
vi.mock('@/components/workstation/StudyDashboard.vue', () => ({ default: { template: '<div class="dashboard-chart" />', props: ['name', 'panels', 'artifacts'] } }))

import ResearchResultsTool from '@/components/workstation/ResearchResultsTool.vue'

describe('ResearchResultsTool', () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset() })

  function mountTool() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    return mount(ResearchResultsTool, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  }

  it('loads persisted runs and exposes selected structured artifacts', async () => {
    apiGet.mockResolvedValue([{ id: 9, status: 'completed', reproducibility_hash: 'abc', diagnostics: [], artifacts: [{ id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } }, { id: 4, name: 'distribution', artifact_type: 'histogram', payload: { value: { bins: [{ start: 1, end: 2, count: 1 }] } } }, { id: 5, name: 'ranking', artifact_type: 'bar', payload: { value: { labels: ['XLK'], values: [12] } } }, { id: 6, name: 'confidence', artifact_type: 'range', payload: { value: { timestamps: ['2026-01-01'], lower: [1], upper: [3], center: [2] } } }] }])
    const wrapper = mountTool()
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/research/runs', { limit: 25, include_artifacts: false })
    expect(wrapper.text()).toContain('Run #9')
    expect(wrapper.text()).toContain('current_streak')
    expect(wrapper.find('.histogram-chart').exists()).toBe(true)
    expect(wrapper.find('.bars-chart').exists()).toBe(true)
    expect(wrapper.find('.range-chart').exists()).toBe(true)
  })

  it('exposes selected-run and loading/error states as navigable live regions', async () => {
    let resolveDetail!: (value: unknown) => void
    const detail = new Promise(resolve => { resolveDetail = resolve })
    apiGet.mockImplementation((path: string) => path === '/research/runs'
      ? Promise.resolve([{ id: 10, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 1, artifacts: [] }])
      : detail)
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.find('[role="region"][aria-label="Study Lab research results"]').exists()).toBe(true)
    expect(wrapper.find('[role="list"][aria-label="Persisted research runs"]').exists()).toBe(true)
    expect(wrapper.find('.research-results-tool__run').attributes('aria-current')).toBe('true')
    const loadingNotice = wrapper.find('.research-results-tool__notice[role="status"]')
    expect(loadingNotice.text()).toContain('Loading selected run details')
    expect(loadingNotice.attributes('aria-live')).toBe('polite')
    expect(loadingNotice.attributes('aria-atomic')).toBe('true')

    resolveDetail({ id: 10, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 1, artifacts: [{ id: 1, name: 'sample', artifact_type: 'scalar', payload: { value: 1 } }] })
    await flushPromises()
    expect(wrapper.find('[aria-label="sample scalar result"]').exists()).toBe(true)
  })

  it('shows a bounded detail-loading state while compact run artifacts hydrate', async () => {
    let resolveDetail!: (value: unknown) => void
    const detail = new Promise(resolve => { resolveDetail = resolve })
    apiGet.mockImplementation((path: string) => path === '/research/runs'
      ? Promise.resolve([{ id: 10, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 1, artifacts: [] }])
      : detail)
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.text()).toContain('Loading selected run details…')
    resolveDetail({ id: 10, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 1, artifacts: [{ id: 1, name: 'sample', artifact_type: 'scalar', payload: { value: 1 } }] })
    await flushPromises()

    expect(wrapper.text()).toContain('sample')
    expect(wrapper.text()).not.toContain('Loading selected run details…')
  })

  it('shows detail-load failure and allows an explicit retry', async () => {
    let detailAttempt = 0
    let resolveRetry!: (value: unknown) => void
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs') return Promise.resolve([{ id: 11, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 1, artifacts: [] }])
      detailAttempt += 1
      return detailAttempt === 1
        ? Promise.reject(new Error('detail endpoint unavailable'))
        : new Promise(resolve => { resolveRetry = resolve })
    })
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.text()).toContain('detail endpoint unavailable')
    expect(wrapper.text()).not.toContain('No structured artifacts have been produced yet.')
    const retry = wrapper.findAll('button').find(button => button.text() === 'Retry')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Loading selected run details…')

    resolveRetry({ id: 11, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifact_count: 1, artifacts: [{ id: 2, name: 'retried', artifact_type: 'scalar', payload: { value: 2 } }] })
    await flushPromises()
    expect(wrapper.text()).toContain('retried')
    expect(wrapper.text()).not.toContain('detail endpoint unavailable')
  })

  it('cancels a queued persisted research run', async () => {
    apiGet.mockResolvedValue([{ id: 12, status: 'running', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [], artifacts: [] }])
    apiPost.mockResolvedValue({ id: 12, status: 'canceled' })
    const wrapper = mountTool()
    await flushPromises()

    const cancel = wrapper.findAll('button').find(button => button.text() === 'Cancel')
    expect(cancel).toBeDefined()
    await cancel!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/research/runs/12/cancel', {})
    expect(wrapper.text()).toContain('canceled')
  })

  it('propagates rerun and cancel mutations through the shared results cache', async () => {
    const running = { id: 16, status: 'running', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [], artifacts: [] }
    const canceled = { ...running, status: 'canceled' }
    let reads = 0
    apiGet.mockImplementation(() => Promise.resolve(reads++ === 0 ? [running] : [canceled]))
    apiPost.mockResolvedValue(canceled)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const plugin = [VueQueryPlugin, { queryClient }] as const
    const first = mount(ResearchResultsTool, { global: { plugins: [plugin] } })
    const second = mount(ResearchResultsTool, { global: { plugins: [plugin] } })
    await flushPromises()

    const cancel = first.findAll('button').find(button => button.text() === 'Cancel')
    expect(cancel).toBeDefined()
    await cancel!.trigger('click')
    await flushPromises()

    expect(second.text()).toContain('canceled')
    expect(queryClient.getQueryData(['workstation', 'research-runs'])).toEqual([canceled])
  })

  it('renders persisted scatter and heatmap artifacts with native result surfaces', async () => {
    apiGet.mockResolvedValue([{ id: 13, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [], artifacts: [
      { id: 5, name: 'relationship', artifact_type: 'scatter', payload: { value: { x: [1, 2], y: [3, 4] } } },
      { id: 6, name: 'matrix', artifact_type: 'heatmap', payload: { value: { rows: ['A'], columns: ['B'], values: [[1]] } } },
    ] }])
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.find('.scatter-chart').exists()).toBe(true)
    expect(wrapper.find('.heatmap-chart').exists()).toBe(true)
  })

  it('renders persisted dashboard artifacts as structured panels', async () => {
    apiGet.mockResolvedValue([{ id: 14, status: 'completed', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [], artifacts: [
      { id: 7, name: 'sample_size', artifact_type: 'scalar', payload: { value: 4 } },
      { id: 8, name: 'overview', artifact_type: 'dashboard', payload: { value: { panels: [{ artifact: 'sample_size', title: 'Sample size', span: 12 }] } } },
    ] }])
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.find('.dashboard-chart').exists()).toBe(true)
  })

  it('renders structured diagnostics, warnings, logs, and resource usage for a persisted run', async () => {
    apiGet.mockResolvedValue([{ id: 15, status: 'failed', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [{ code: 'coverage', message: 'missing bars' }], warnings: [{ code: 'partial', message: 'one symbol excluded' }], logs: 'runner completed with exclusions', resource_usage: { wall_ms: 12 }, artifacts: [] }])
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.text()).toContain('Diagnostics (1)')
    expect(wrapper.text()).toContain('missing bars')
    expect(wrapper.text()).toContain('Warnings (1)')
    expect(wrapper.text()).toContain('one symbol excluded')
    expect(wrapper.text()).toContain('runner completed with exclusions')
    expect(wrapper.text()).toContain('Resource usage')
    expect(wrapper.text()).toContain('wall_ms')
  })

  it('labels terminal and in-flight states with recovery guidance', async () => {
    apiGet.mockResolvedValue([
      { id: 16, status: 'failed', code_version_id: 4, run_config: {}, dataset_manifest: {}, diagnostics: [{ message: 'sandbox limit' }], artifacts: [] },
      { id: 17, status: 'canceled', code_version_id: 4, run_config: {}, dataset_manifest: {}, artifacts: [] },
    ])
    const wrapper = mountTool()
    await flushPromises()

    expect(wrapper.get('[data-status="failed"]').text()).toBe('Failed')
    expect(wrapper.get('[aria-label="Run 16 status: Failed"]').exists()).toBe(true)
    const guidance = wrapper.get('.research-results-tool__run-guidance')
    expect(guidance.text()).toContain('Inspect diagnostics')
    expect(guidance.attributes('aria-atomic')).toBe('true')
    expect(wrapper.text()).toContain('Rerun snapshot')
    expect(wrapper.text()).toContain('Rerun latest')

    await wrapper.findAll('button.research-results-tool__run')[1].trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-status="canceled"]').text()).toBe('Canceled')
    expect(wrapper.get('.research-results-tool__run-guidance').text()).toContain('saved configuration is preserved')
  })
})
