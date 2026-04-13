import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/lib/api'
import type {
  Dashboard,
  DashboardTab,
  DashboardWidget,
  DashboardWidgetLayout,
  DashboardWidgetType,
} from '@/types'

export interface WidgetDraft {
  widget_type: DashboardWidgetType
  title?: string | null
  layout: DashboardWidgetLayout
  config?: Record<string, any>
  style?: Record<string, any>
}

export const useDashboardStore = defineStore('dashboard', () => {
  const dashboards = ref<Dashboard[]>([])
  const activeDashboardId = ref<number | null>(null)
  const activeTabId = ref<number | null>(null)
  const isLoading = ref(false)
  const editMode = ref(false)
  const error = ref<string | null>(null)

  const activeDashboard = computed(() =>
    dashboards.value.find(d => d.id === activeDashboardId.value) ?? dashboards.value[0] ?? null
  )

  const activeTab = computed(() => {
    const dashboard = activeDashboard.value
    if (!dashboard) return null
    return dashboard.tabs.find(t => t.id === activeTabId.value) ?? dashboard.tabs[0] ?? null
  })

  async function loadDefaultDashboard() {
    isLoading.value = true
    error.value = null
    try {
      const dashboard = await api.get<Dashboard>('/dashboards/default')
      upsertDashboard(dashboard)
      activeDashboardId.value = dashboard.id
      activeTabId.value = dashboard.tabs[0]?.id ?? null
      return dashboard
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load dashboard'
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function createTab(name = 'New Tab') {
    const dashboard = activeDashboard.value
    if (!dashboard) return null
    const tab = await api.post<DashboardTab>(`/dashboards/${dashboard.id}/tabs`, {
      name,
      position: dashboard.tabs.length,
      layout_settings: {},
    })
    dashboard.tabs.push(tab)
    activeTabId.value = tab.id
    return tab
  }

  async function renameTab(tabId: number, name: string) {
    const tab = findTab(tabId)
    if (!tab) return null
    const updated = await api.patch<DashboardTab>(`/dashboards/tabs/${tabId}`, { name })
    Object.assign(tab, updated)
    return updated
  }

  async function deleteTab(tabId: number) {
    const dashboard = activeDashboard.value
    if (!dashboard || dashboard.tabs.length <= 1) return
    await api.delete(`/dashboards/tabs/${tabId}`)
    dashboard.tabs = dashboard.tabs.filter(t => t.id !== tabId)
    if (activeTabId.value === tabId) activeTabId.value = dashboard.tabs[0]?.id ?? null
  }

  async function addWidget(draft: WidgetDraft) {
    const tab = activeTab.value
    if (!tab) return null
    const widget = await api.post<DashboardWidget>(`/dashboards/tabs/${tab.id}/widgets`, {
      title: draft.title,
      widget_type: draft.widget_type,
      layout: draft.layout,
      config: draft.config ?? {},
      style: draft.style ?? {},
      position: tab.widgets.length,
    })
    tab.widgets.push(widget)
    return widget
  }

  async function updateWidget(widgetId: number, patch: Partial<DashboardWidget>) {
    const local = findWidget(widgetId)
    if (local) Object.assign(local, patch)
    const updated = await api.patch<DashboardWidget>(`/dashboards/widgets/${widgetId}`, patch)
    if (local) Object.assign(local, updated)
    return updated
  }

  async function deleteWidget(widgetId: number) {
    await api.delete(`/dashboards/widgets/${widgetId}`)
    const tab = activeTab.value
    if (tab) tab.widgets = tab.widgets.filter(w => w.id !== widgetId)
  }

  async function saveWidgetLayout(widgetId: number, layout: DashboardWidgetLayout) {
    const widget = findWidget(widgetId)
    if (!widget) return
    widget.layout = { ...layout }
    await api.patch(`/dashboards/tabs/${widget.tab_id}/widgets/layout`, {
      widgets: [{ id: widgetId, layout }],
    })
  }

  function setActiveTab(tabId: number) {
    activeTabId.value = tabId
  }

  function setEditMode(value: boolean) {
    editMode.value = value
  }

  function upsertDashboard(dashboard: Dashboard) {
    const idx = dashboards.value.findIndex(d => d.id === dashboard.id)
    if (idx === -1) dashboards.value.push(dashboard)
    else dashboards.value[idx] = dashboard
  }

  function findTab(tabId: number) {
    return dashboards.value.flatMap(d => d.tabs).find(t => t.id === tabId) ?? null
  }

  function findWidget(widgetId: number) {
    return dashboards.value
      .flatMap(d => d.tabs)
      .flatMap(t => t.widgets)
      .find(w => w.id === widgetId) ?? null
  }

  return {
    dashboards,
    activeDashboardId,
    activeTabId,
    activeDashboard,
    activeTab,
    isLoading,
    editMode,
    error,
    loadDefaultDashboard,
    createTab,
    renameTab,
    deleteTab,
    addWidget,
    updateWidget,
    deleteWidget,
    saveWidgetLayout,
    setActiveTab,
    setEditMode,
  }
})
