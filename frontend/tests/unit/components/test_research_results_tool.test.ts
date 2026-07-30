import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import ResearchResultsTool from '@/components/workstation/ResearchResultsTool.vue'

describe('ResearchResultsTool', () => {
  beforeEach(() => apiGet.mockReset())

  it('loads persisted runs and exposes selected structured artifacts', async () => {
    apiGet.mockResolvedValue([{ id: 9, status: 'completed', reproducibility_hash: 'abc', diagnostics: [], artifacts: [{ id: 3, name: 'current_streak', artifact_type: 'scalar' }] }])
    const wrapper = mount(ResearchResultsTool)
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/research/runs', { limit: 25 })
    expect(wrapper.text()).toContain('Run #9')
    expect(wrapper.text()).toContain('current_streak')
  })
})
