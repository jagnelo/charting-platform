import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPatch, apiDelete } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiDelete: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, patch: apiPatch, delete: apiDelete } }))

import AlertsView from '@/views/AlertsView.vue'

describe('AlertsView creation path', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({})
    apiPatch.mockResolvedValue({})
    apiDelete.mockResolvedValue(undefined)
  })

  it('offers the existing chart alert form when a user has no alert definitions', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/legacy/alerts', component: AlertsView },
        { path: '/chart', component: defineComponent({ template: '<main>Chart workspace</main>' }) },
      ],
    })
    await router.push('/legacy/alerts')
    await router.isReady()
    const wrapper = mount(AlertsView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('.alerts-create-path').text()).toContain('Create price or indicator alerts from the chart workspace.')
    const destination = wrapper.get('.alerts-create-path a')
    expect(destination.attributes('href')).toBe('/chart')
    await destination.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/chart')

    wrapper.unmount()
  })
})
