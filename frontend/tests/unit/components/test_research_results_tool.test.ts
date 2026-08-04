import { flushPromises, mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))
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
    apiGet.mockResolvedValue([{ id: 9, status: 'completed', reproducibility_hash: 'abc', diagnostics: [], artifacts: [{ id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } }, { id: 4, name: 'distribution', artifact_type: 'histogram', payload: { value: { bins: [{ start: 1, end: 2, count: 1 }] } } }] }])
    const wrapper = mountTool()
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/research/runs', { limit: 25 })
    expect(wrapper.text()).toContain('Run #9')
    expect(wrapper.text()).toContain('current_streak')
    expect(wrapper.find('.histogram-chart').exists()).toBe(true)
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
})
