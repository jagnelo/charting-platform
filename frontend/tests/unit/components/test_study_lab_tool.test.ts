import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))

import StudyLabTool from '@/components/workstation/StudyLabTool.vue'

describe('StudyLabTool', () => {
  it('validates, starts an immutable isolated study run, and renders artifacts', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['stats', 'output'], lookback_hint: 1 })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 9, status: 'completed', reproducibility_hash: 'sha256:test', artifacts: [
        { id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } },
        { id: 4, name: 'completed_streaks', artifact_type: 'table', payload: { value: [{ length: 2, end_timestamp: '2026-01-03' }] } },
      ] })
      return Promise.resolve({})
    })
    const wrapper = mount(StudyLabTool, { props: { activeSymbol: 'SPY' } })

    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #9'))

    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({ code_version_id: 42, run_config: { symbol: 'SPY' } }))
    expect(wrapper.text()).toContain('current_streak')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).toContain('completed_streaks')
    expect(wrapper.find('table').text()).toContain('end_timestamp')
  })
})
