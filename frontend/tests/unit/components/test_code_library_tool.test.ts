import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))

import CodeLibraryTool from '@/components/workstation/CodeLibraryTool.vue'

const asset = { id: 4, stable_key: 'streak-study', name: 'Streak study', kind: 'study', is_archived: false, versions: [{ id: 8, version_number: 1, source: "output.scalar('n', 1)", output_contract: 'study', parameter_schema: {}, default_parameters: {} }] }

describe('CodeLibraryTool', () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiGet.mockResolvedValue([asset]) })

  it('loads, filters, clones, and archives user-owned assets', async () => {
    apiPost.mockImplementation((path: string, body: Record<string, unknown>) => {
      if (path.endsWith('/clone')) return Promise.resolve({ ...asset, id: 5, stable_key: body.stable_key, name: body.name })
      if (path.endsWith('/archive')) return Promise.resolve({ ...asset, is_archived: body.is_archived })
      return Promise.resolve({})
    })
    const wrapper = mount(CodeLibraryTool)
    await flushPromises()
    expect(wrapper.text()).toContain('Streak study')
    await wrapper.find('[aria-label="Filter Python assets"]').setValue('missing')
    expect(wrapper.text()).toContain('No matching Python assets')
    await wrapper.find('[aria-label="Filter Python assets"]').setValue('streak')
    await wrapper.findAll('button').find(button => button.text() === 'Clone')!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/code/assets/4/clone', expect.objectContaining({ name: 'Streak study copy' }))
    await wrapper.find('summary').trigger('click')
    await wrapper.find('[aria-label="Python source for Streak study"]').setValue("output.scalar('n', 2)")
    await wrapper.findAll('button').find(button => button.text() === 'Save as new version')!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/code/assets/4/versions', expect.objectContaining({ source: "output.scalar('n', 2)", output_contract: 'study' }))
    await wrapper.findAll('button').find(button => button.text() === 'Archive')!.trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/code/assets/4/archive', { is_archived: true })
  })
})
