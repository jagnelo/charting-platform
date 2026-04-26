import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useDashboardStore } from '@/stores/dashboard'

function widget(id: number, tabId: number) {
  return {
    id,
    tab_id: tabId,
    widget_type: 'quote',
    title: 'Widget',
    layout: { x: 0, y: 0, w: 4, h: 3 },
    config: {},
    style: {},
    position: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function tab(id: number, dashboardId: number, widgets = [widget(id * 10, id)]) {
  return {
    id,
    dashboard_id: dashboardId,
    name: `Tab ${id}`,
    position: id - 1,
    layout_settings: {},
    widgets,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function dashboard(id = 1) {
  return {
    id,
    user_id: 1,
    name: 'Main',
    is_default: true,
    position: 0,
    settings: {},
    tabs: [tab(1, id), tab(2, id)],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('useDashboardStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('loads the default dashboard and preserves the previous tab when possible', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce(dashboard())
    const store = useDashboardStore()
    store.activeTabId = 2

    await store.loadDefaultDashboard()

    expect(store.activeDashboardId).toBe(1)
    expect(store.activeTabId).toBe(2)
    expect(store.activeDashboard?.tabs).toHaveLength(2)
  })

  it('creates, renames, and deletes tabs', async () => {
    const store = useDashboardStore()
    store.dashboards = [dashboard()] as any
    store.activeDashboardId = 1
    store.activeTabId = 1

    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(tab(3, 1, []))
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ...tab(3, 1, []), name: 'Renamed' })
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    await store.createTab('New Tab')
    expect(store.activeTabId).toBe(3)

    await store.renameTab(3, 'Renamed')
    expect(store.activeDashboard?.tabs.find(t => t.id === 3)?.name).toBe('Renamed')

    await store.deleteTab(3)
    expect(store.activeDashboard?.tabs.some(t => t.id === 3)).toBe(false)
  })

  it('adds and deletes widgets on the active tab', async () => {
    const store = useDashboardStore()
    store.dashboards = [dashboard()] as any
    store.activeDashboardId = 1
    store.activeTabId = 1

    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(widget(99, 1))
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    await store.addWidget({
      widget_type: 'quote',
      title: 'Added',
      layout: { x: 1, y: 1, w: 4, h: 4 },
      config: {},
      style: {},
    })

    expect(store.activeTab?.widgets.some(w => w.id === 99)).toBe(true)

    await store.deleteWidget(99)
    expect(store.activeTab?.widgets.some(w => w.id === 99)).toBe(false)
  })

  it('reverts optimistic widget updates on failure', async () => {
    const store = useDashboardStore()
    store.dashboards = [dashboard()] as any
    store.activeDashboardId = 1
    store.activeTabId = 1
    const originalTitle = store.activeTab!.widgets[0].title

    ;(api.patch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'))

    await expect(store.updateWidget(10, { title: 'Broken' } as any)).rejects.toThrow('boom')
    expect(store.activeTab!.widgets[0].title).toBe(originalTitle)
  })

  it('reverts widget layout changes when persistence fails', async () => {
    const store = useDashboardStore()
    store.dashboards = [dashboard()] as any
    store.activeDashboardId = 1
    store.activeTabId = 1
    const original = { ...store.activeTab!.widgets[0].layout }

    ;(api.patch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('layout'))

    await expect(store.saveWidgetLayout(10, { x: 9, y: 9, w: 6, h: 6 })).rejects.toThrow('layout')
    expect(store.activeTab!.widgets[0].layout).toEqual(original)
  })
})
