import { flushPromises, mount as vueMount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))

import CodeLibraryTool from '@/components/workstation/CodeLibraryTool.vue'

function mount(component: typeof CodeLibraryTool, options: Record<string, any> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return vueMount(component, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
}

const asset = { id: 4, stable_key: 'streak-study', name: 'Streak study', kind: 'study', is_archived: false, versions: [{ id: 8, version_number: 1, source: "output.scalar('n', 1)", output_contract: 'study', parameter_schema: {}, default_parameters: {} }] }

describe('CodeLibraryTool', () => {
  beforeEach(() => {
    apiGet.mockReset(); apiPost.mockReset(); apiGet.mockResolvedValue([asset])
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: [], output_contracts: ['study', 'scalar'] })
      : Promise.resolve({}))
  })

  it('loads, filters, clones, and archives user-owned assets', async () => {
    apiPost.mockImplementation((path: string, body: Record<string, unknown>) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: [], output_contracts: ['study', 'scalar'] })
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

  it('creates a typed new study asset from the library form', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: [], output_contracts: ['study', 'scalar'] })
      : path === '/code/assets' ? Promise.resolve({ ...asset, id: 9, stable_key: 'breadth-study', name: 'Breadth study' }) : Promise.resolve({}))
    const wrapper = mount(CodeLibraryTool)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === 'New')!.trigger('click')
    await wrapper.find('[aria-label="New Python asset name"]').setValue('Breadth study')
    await wrapper.find('[aria-label="New Python asset key"]').setValue('breadth-study')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({ stable_key: 'breadth-study', kind: 'study', initial_version: expect.objectContaining({ output_contract: 'study' }) }))
    expect(wrapper.text()).toContain('Breadth study')
  })

  it('creates a numeric-series condition asset for isolated breadth targets', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: [], output_contracts: ['series'] })
      : path === '/code/assets' ? Promise.resolve({ ...asset, id: 12, stable_key: 'derived-breadth', name: 'Derived breadth' }) : Promise.resolve({}))
    const wrapper = mount(CodeLibraryTool)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === 'New')!.trigger('click')
    await wrapper.find('[aria-label="New Python asset name"]').setValue('Derived breadth')
    await wrapper.find('[aria-label="New Python asset key"]').setValue('derived-breadth')
    await wrapper.find('[aria-label="New Python asset kind"]').setValue('condition')
    await wrapper.find('[aria-label="New Python condition output contract"]').setValue('series')
    await wrapper.find('[aria-label="New Python asset source"]').setValue("output.series('target', market.close())")
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/code/assets', expect.objectContaining({
      stable_key: 'derived-breadth',
      kind: 'condition',
      initial_version: expect.objectContaining({ output_contract: 'series' }),
    }))
  })

  it('shows source diagnostics and blocks persistence when validation fails', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: false, diagnostics: [{ code: 'forbidden_import', message: 'Imports are not permitted', line: 1, column: 1 }], dependencies: [], output_contracts: [] })
      : Promise.resolve({ ...asset, id: 10 }))
    const wrapper = mount(CodeLibraryTool)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === 'New')!.trigger('click')
    await wrapper.find('[aria-label="New Python asset name"]').setValue('Unsafe study')
    await wrapper.find('[aria-label="New Python asset key"]').setValue('unsafe-study')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Validation errors')
    expect(wrapper.text()).toContain('Imports are not permitted')
    expect(apiPost).not.toHaveBeenCalledWith('/code/assets', expect.anything())
  })

  it('blocks a syntactically valid source whose output contract disagrees with the asset kind', async () => {
    apiPost.mockImplementation((path: string) => path === '/code/validate'
      ? Promise.resolve({ valid: true, diagnostics: [], dependencies: [], output_contracts: ['scalar'] })
      : Promise.resolve({ ...asset, id: 11 }))
    const wrapper = mount(CodeLibraryTool)
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === 'New')!.trigger('click')
    await wrapper.find('[aria-label="New Python asset name"]').setValue('Wrong plot')
    await wrapper.find('[aria-label="New Python asset key"]').setValue('wrong-plot')
    await wrapper.find('[aria-label="New Python asset kind"]').setValue('plot')
    await wrapper.find('[aria-label="New Python asset source"]').setValue("output.scalar('value', 1)")
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Asset declares series')
    expect(apiPost).not.toHaveBeenCalledWith('/code/assets', expect.anything())
  })
})
