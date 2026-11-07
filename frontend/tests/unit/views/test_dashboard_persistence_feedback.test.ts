import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { api } from '@/lib/api'
import DashboardView from '@/views/DashboardView.vue'
import { useDashboardStore } from '@/stores/dashboard'

function dashboard(widgetType = 'quote', config: Record<string, any> = { symbol: 'AAPL' }) {
  return {
    id: 1, user_id: 1, name: 'Main', is_default: true, position: 0, settings: {},
    tabs: [{
      id: 2, dashboard_id: 1, name: 'Main', position: 0, layout_settings: {},
      widgets: [{
        id: 3, tab_id: 2, widget_type: widgetType, title: 'Market', position: 0,
        layout: { x: 0, y: 0, w: 6, h: 4 }, config, style: {},
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      }],
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    }],
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  }
}

const InstrumentSearchStub = defineComponent({
  props: { modelValue: { type: String, default: '' } },
  emits: ['select', 'update:modelValue'],
  template: '<button class="mock-select-symbol" @click="$emit(\'update:modelValue\', \'MSFT\'); $emit(\'select\', \'MSFT\')">Select MSFT</button>',
})

async function flush() {
  await flushPromises()
  await nextTick()
}

function mountView(dashboardResponse: any) {
  setActivePinia(createPinia())
  const store = useDashboardStore()
  store.loadDefaultDashboard = vi.fn(async () => {
    store.dashboards = [dashboardResponse] as any
    store.activeDashboardId = dashboardResponse.id
    store.activeTabId = dashboardResponse.tabs[0].id
    return dashboardResponse
  })
  ;(api.get as ReturnType<typeof vi.fn>).mockImplementation(async (path: string) =>
    path === '/dashboards/default' ? dashboardResponse : [],
  )
  const wrapper = mount(DashboardView, {
    attachTo: document.body,
    global: { stubs: {
      DashboardInstrumentSearch: InstrumentSearchStub,
      DashboardQuoteWidget: true,
      DashboardLineChartWidget: true,
      DashboardAdvancedChartWidget: true,
      DashboardInstrumentDetailsWidget: true,
    } },
  })
  mounted.push(wrapper)
  return wrapper
}

const mounted: Array<{ unmount: () => void }> = []

function bodyButton(text: string) {
  const button = [...document.body.querySelectorAll('button')].find(item => item.textContent?.includes(text))
  if (!button) throw new Error(`Could not find body button: ${text}; body=${document.body.textContent}`)
  return button
}

function viewButton(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find(item => item.text().trim() === text)
  if (!button) throw new Error(`Could not find view button: ${text}`)
  return button
}

describe('dashboard persistence recovery', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    document.body.innerHTML = ''
  })

  afterEach(() => {
    for (const wrapper of mounted.splice(0)) wrapper.unmount()
  })

  it('keeps the old saved symbol after a rejected edit and lets the user retry', async () => {
    ;(api.patch as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('offline'))
      .mockImplementationOnce(async (_path, patch) => ({ ...dashboard().tabs[0].widgets[0], ...(patch as object) }))
    const wrapper = mountView(dashboard())
    await flush()
    await wrapper.get('.header-actions .primary').trigger('click')
    await viewButton(wrapper, 'Configure').trigger('click')
    bodyButton('Select MSFT').click()
    await flush()

    const store = useDashboardStore()
    expect(store.activeTab?.widgets[0].config.symbol).toBe('AAPL')
    expect(document.body.textContent).toContain('The previous saved value was restored.')
    expect(document.body.querySelector('.mock-select-symbol')?.textContent).toBe('Select MSFT')

    bodyButton('Retry save').click()
    await flush()
    expect(store.activeTab?.widgets[0].config.symbol).toBe('MSFT')
    expect(document.body.textContent).not.toContain('The previous saved value was restored.')
    wrapper.unmount()
  })

  it('rolls a rejected comparison target back and shows the same recoverable save error', async () => {
    ;(api.patch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('offline'))
    const response = dashboard('comparison_chart', { targets: [{ symbol: 'AAPL', label: 'AAPL', color: '#fff' }] })
    const wrapper = mountView(response)
    await flush()
    await wrapper.get('.header-actions .primary').trigger('click')
    await viewButton(wrapper, 'Configure').trigger('click')
    bodyButton('Select MSFT').click()
    await flush()

    expect(useDashboardStore().activeTab?.widgets[0].config.targets[0].symbol).toBe('AAPL')
    expect(document.body.textContent).toContain('The previous saved value was restored.')
    wrapper.unmount()
  })

  it('explains a rolled-back layout save and retries the same layout', async () => {
    ;(HTMLElement.prototype as any).setPointerCapture = vi.fn()
    ;(api.patch as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(undefined)
    const wrapper = mountView(dashboard())
    await flush()
    await wrapper.get('.header-actions .primary').trigger('click')
    const header = wrapper.get('.widget-header')
    await header.trigger('pointerdown', { clientX: 0, clientY: 0, pointerId: 1 })
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 124, clientY: 74, bubbles: true }))
    window.dispatchEvent(new MouseEvent('pointerup', { bubbles: true }))
    await flush()

    const store = useDashboardStore()
    expect(api.patch.mock.calls.map(([path]) => path)).toContain('/dashboards/tabs/2/widgets/layout')
    expect(store.activeTab?.widgets[0].layout).toEqual({ x: 0, y: 0, w: 6, h: 4 })
    expect(document.body.textContent).toContain('The previous saved arrangement was restored.')
    bodyButton('Retry layout save').click()
    await flush()
    expect(api.patch).toHaveBeenLastCalledWith('/dashboards/tabs/2/widgets/layout', {
      widgets: [{ id: 3, layout: { x: 2, y: 2, w: 6, h: 4 } }],
    })
    expect(document.body.textContent).not.toContain('The previous saved arrangement was restored.')
    wrapper.unmount()
  })
})
