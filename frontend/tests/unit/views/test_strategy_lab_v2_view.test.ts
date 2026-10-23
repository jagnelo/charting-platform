import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import { api } from '@/lib/api'
import StrategyLabV2View from '@/views/StrategyLabV2View.vue'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

function resource(
  id: string,
  attributes: Record<string, unknown> = {},
  type = 'strategies',
) {
  return { type, id, attributes, relationships: {}, meta: { schema_version: 1 } }
}

function studyReference() {
  return {
    research_run_id: 1,
    code_version_id: 1,
    artifact_id: 1,
    artifact_name: 'score',
    artifact_type: 'scalar',
    output_contract: 'study',
    run_reproducibility_hash: 'b'.repeat(64),
    code_version_digest: `sha256:${'c'.repeat(64)}`,
    dataset_manifest_digest: `sha256:${'d'.repeat(64)}`,
    artifact_content_digest: `sha256:${'a'.repeat(64)}`,
  }
}

function mountView() {
  return mount(StrategyLabV2View, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('StrategyLabV2View', () => {
  beforeEach(() => vi.mocked(api.get).mockReset())

  it('lists owner-scoped v2 strategies and re-reads immutable Study lineage on selection', async () => {
    const summary = resource('strategy-1', { strategy_id: 'study-a', version_id: 'v1' })
    const selectedStudy = {
      research_run_id: 1,
      code_version_id: 1,
      artifact_id: 1,
      artifact_name: 'score',
      artifact_type: 'scalar',
      output_contract: 'study',
      run_reproducibility_hash: 'b'.repeat(64),
      code_version_digest: `sha256:${'c'.repeat(64)}`,
      dataset_manifest_digest: `sha256:${'d'.repeat(64)}`,
      artifact_content_digest: `sha256:${'a'.repeat(64)}`,
    }
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: [summary], links: {} })
      .mockResolvedValueOnce({ data: resource('strategy-1', { ...summary.attributes, selected_study_artifact: selectedStudy }) })

    const wrapper = mountView()
    await flushPromises()

    expect(api.get).toHaveBeenNthCalledWith(1, '/strategy-lab/v2/strategies', { limit: 50 })
    expect(wrapper.text()).toContain('study-a')
    expect(wrapper.text()).toContain('Read-only boundary.')

    await wrapper.find('.strategy-lab-v2__item').trigger('click')
    await flushPromises()

    expect(api.get).toHaveBeenNthCalledWith(2, '/strategy-lab/v2/strategies/strategy-1')
    expect(wrapper.get('[aria-label="Pinned Study lineage"]').text()).toContain('artifact_content_digest')
    expect(wrapper.get('[aria-label="Pinned Study lineage"]').text()).toContain('a'.repeat(64))
    expect(wrapper.text()).toContain('not proof of native execution')
  })

  it('keeps server cursor pagination explicit and appends only the next owner-scoped page', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: [resource('strategy-1', { name: 'First' })], links: { next: 'cursor-2' } })
      .mockResolvedValueOnce({ data: [resource('strategy-2', { name: 'Second' })], links: {} })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('button.strategy-lab-v2__next').trigger('click')
    await flushPromises()

    expect(api.get).toHaveBeenNthCalledWith(2, '/strategy-lab/v2/strategies', {
      limit: 50,
      cursor: 'cursor-2',
    })
    expect(wrapper.text()).toContain('First')
    expect(wrapper.text()).toContain('Second')
  })

  it('loads trials and artifacts only when their read-only resource tabs are selected', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: [], links: {} })
      .mockResolvedValueOnce({ data: [resource('trial-1', { name: 'Completed trial' }, 'trials')], links: {} })
      .mockResolvedValueOnce({ data: [resource('artifact-1', { name: 'Persisted output' }, 'artifacts')], links: {} })

    const wrapper = mountView()
    await flushPromises()

    const trialsTab = wrapper.findAll('button').find(button => button.text().includes('Trials'))
    expect(trialsTab).toBeDefined()
    await trialsTab!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenNthCalledWith(2, '/strategy-lab/v2/trials', { limit: 50 })
    expect(wrapper.text()).toContain('Completed trial')

    const artifactsTab = wrapper.findAll('button').find(button => button.text().includes('Artifacts'))
    expect(artifactsTab).toBeDefined()
    await artifactsTab!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenNthCalledWith(3, '/strategy-lab/v2/artifacts', { limit: 50 })
    expect(wrapper.text()).toContain('Persisted output')
    expect(vi.mocked(api.get).mock.calls.every(([path]) => !path.includes('dispatch'))).toBe(true)
  })

  it('previews an immutable Study pin by existing IDs using GET only', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: [], links: {} })
      .mockResolvedValueOnce({
        data: { type: 'study-artifact-references', id: '1:1', attributes: studyReference() },
      })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[aria-label="Research run ID"]').setValue('1')
    await wrapper.get('[aria-label="Artifact ID"]').setValue('1')
    await wrapper.get('.strategy-lab-v2__pin-lookup form').trigger('submit')
    await flushPromises()

    expect(api.get).toHaveBeenNthCalledWith(
      2,
      '/strategy-lab/v2/study-artifact-references/1/1',
    )
    expect(wrapper.get('[aria-label="Resolved Study pin"]').text()).toContain('artifact_content_digest')
    expect(wrapper.text()).toContain('Persisted provenance only')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('rejects incomplete or malformed immutable digests from a Study pin response', async () => {
    const incomplete: Record<string, unknown> = { ...studyReference() }
    delete incomplete.dataset_manifest_digest
    const malformed = { ...studyReference(), artifact_content_digest: 'a'.repeat(64) }
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: [], links: {} })
      .mockResolvedValueOnce({
        data: { type: 'study-artifact-references', id: '1:1', attributes: incomplete },
      })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[aria-label="Research run ID"]').setValue('1')
    await wrapper.get('[aria-label="Artifact ID"]').setValue('1')
    await wrapper.get('.strategy-lab-v2__pin-lookup form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('did not match')
    expect(wrapper.find('[aria-label="Resolved Study pin"]').exists()).toBe(false)

    vi.mocked(api.get).mockReset()
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { type: 'study-artifact-references', id: '1:1', attributes: malformed },
    })
    await wrapper.get('[aria-label="Research run ID"]').setValue('1')
    await wrapper.get('[aria-label="Artifact ID"]').setValue('1')
    await wrapper.get('.strategy-lab-v2__pin-lookup form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('did not match')
    expect(wrapper.find('[aria-label="Resolved Study pin"]').exists()).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('rejects a Study pin response whose returned identity does not match the request', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: [], links: {} })
      .mockResolvedValueOnce({
        data: {
          type: 'study-artifact-references',
          id: '1:2',
          attributes: { research_run_id: 1, artifact_id: 2, output_contract: 'study' },
        },
      })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[aria-label="Research run ID"]').setValue('1')
    await wrapper.get('[aria-label="Artifact ID"]').setValue('1')
    await wrapper.get('.strategy-lab-v2__pin-lookup form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('did not match')
    expect(wrapper.find('[aria-label="Resolved Study pin"]').exists()).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not request a Study pin for non-positive or non-integer identifiers', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: [], links: {} })

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[aria-label="Research run ID"]').setValue('0x1')
    await wrapper.get('[aria-label="Artifact ID"]').setValue('1')
    await wrapper.get('.strategy-lab-v2__pin-lookup form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('positive integer IDs')
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows a failed collection read and allows an explicit retry', async () => {
    vi.mocked(api.get)
      .mockRejectedValueOnce(new Error('owner-scoped read unavailable'))
      .mockResolvedValueOnce({ data: [], links: {} })

    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('owner-scoped read unavailable')

    await wrapper.get('.strategy-lab-v2__list-heading button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('No strategies are available')
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})
