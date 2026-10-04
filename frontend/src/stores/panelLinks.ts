import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { WORKSTATION_LINK_GROUPS, type LinkGroup } from '@/stores/dashboardLinks'

export type PanelLinkGroup = LinkGroup

export const PANEL_LINK_GROUPS = WORKSTATION_LINK_GROUPS

const STORAGE_KEY = 'chart.panelLinks.v1'
const LINK_GROUP_IDS = new Set<string>(WORKSTATION_LINK_GROUPS.map(group => group.id))

function loadInitial(): Record<string, PanelLinkGroup> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(Object.entries(parsed as Record<string, unknown>).flatMap(([panelId, value]) => {
      if (value === null) return [[panelId, 'grey']]
      if (typeof value === 'string' && LINK_GROUP_IDS.has(value)) return [[panelId, value]]
      return []
    })) as Record<string, PanelLinkGroup>
  } catch {
    return {}
  }
}

export const usePanelLinksStore = defineStore('panelLinks', () => {
  const panelGroups = ref<Record<string, PanelLinkGroup>>(loadInitial())

  const groupMeta = computed(() => Object.fromEntries(PANEL_LINK_GROUPS.map(g => [g.id, g])))

  function groupFor(panelId: string): PanelLinkGroup {
    if (Object.prototype.hasOwnProperty.call(panelGroups.value, panelId)) {
      return panelGroups.value[panelId]
    }
    return 'blue'
  }

  function setPanelGroup(panelId: string, group: PanelLinkGroup) {
    panelGroups.value = { ...panelGroups.value, [panelId]: group }
  }

  function colorFor(panelId: string): string {
    const group = groupFor(panelId)
    return group ? groupMeta.value[group]?.color ?? '#555' : '#555'
  }

  function linkedPanelIds(sourcePanelId: string, panelIds: string[]): string[] {
    const group = groupFor(sourcePanelId)
    if (group === 'grey') return [sourcePanelId]
    return panelIds.filter(id => {
      const targetGroup = groupFor(id)
      if (targetGroup === 'grey') return id === sourcePanelId
      return targetGroup === group || (group !== 'yellow' && targetGroup === 'yellow')
    })
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
