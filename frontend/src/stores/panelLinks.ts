import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type PanelLinkGroup = 'blue' | 'green' | 'yellow' | 'red'

export const PANEL_LINK_GROUPS: Array<{ id: PanelLinkGroup; label: string; color: string }> = [
  { id: 'blue', label: 'Blue', color: '#64b5f6' },
  { id: 'green', label: 'Green', color: '#26a69a' },
  { id: 'yellow', label: 'Yellow', color: '#ffca28' },
  { id: 'red', label: 'Red', color: '#ef5350' },
]

const STORAGE_KEY = 'chart.panelLinks.v1'

function loadInitial(): Record<string, PanelLinkGroup | null> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

export const usePanelLinksStore = defineStore('panelLinks', () => {
  const panelGroups = ref<Record<string, PanelLinkGroup | null>>(loadInitial())

  const groupMeta = computed(() => Object.fromEntries(PANEL_LINK_GROUPS.map(g => [g.id, g])))

  function groupFor(panelId: string): PanelLinkGroup | null {
    if (Object.prototype.hasOwnProperty.call(panelGroups.value, panelId)) {
      return panelGroups.value[panelId] ?? null
    }
    return 'blue'
  }

  function setPanelGroup(panelId: string, group: PanelLinkGroup | null) {
    panelGroups.value = { ...panelGroups.value, [panelId]: group }
  }

  function colorFor(panelId: string): string {
    const group = groupFor(panelId)
    return group ? groupMeta.value[group]?.color ?? '#555' : '#555'
  }

  function linkedPanelIds(sourcePanelId: string, panelIds: string[]): string[] {
    const group = groupFor(sourcePanelId)
    if (!group) return [sourcePanelId]
    return panelIds.filter(id => groupFor(id) === group)
  }

  watch(panelGroups, (value) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  }, { deep: true })

  return {
    panelGroups,
    groupMeta,
    groupFor,
    setPanelGroup,
    colorFor,
    linkedPanelIds,
  }
})
