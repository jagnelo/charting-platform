import { defineStore } from 'pinia'
import { ref } from 'vue'

export const LINK_GROUP_COLORS = [
  '#64b5f6',
  '#81c784',
  '#ffb74d',
  '#ef5350',
  '#ba68c8',
  '#4dd0e1',
  '#f06292',
  '#aed581',
  '#7986cb',
  '#ffd54f',
  '#4db6ac',
  '#e57373',
]

const LEGACY_LINK_GROUPS: Record<string, { color: string; label: string }> = {
  blue: { color: '#64b5f6', label: 'Blue' },
  green: { color: '#81c784', label: 'Green' },
  yellow: { color: '#ffb74d', label: 'Yellow' },
  red: { color: '#ef5350', label: 'Red' },
}

function groupIndex(group: string): number {
  const match = group.match(/^group-(\d+)$/)
  if (match) return Math.max(0, Number(match[1]) - 1)

  let hash = 0
  for (const char of group) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return hash
}

export function dashboardLinkGroupColor(group: string | undefined | null): string {
  if (!group) return 'transparent'
  const legacy = LEGACY_LINK_GROUPS[group]
  if (legacy) return legacy.color
  const index = groupIndex(group)
  if (index < LINK_GROUP_COLORS.length) return LINK_GROUP_COLORS[index]
  const hue = Math.round((210 + index * 137.508) % 360)
  return `hsl(${hue} 62% 64%)`
}

export function dashboardLinkGroupLabel(group: string | undefined | null): string {
  if (!group) return 'Unlinked'
  const legacy = LEGACY_LINK_GROUPS[group]
  if (legacy) return legacy.label
  const match = group.match(/^group-(\d+)$/)
  return match ? `Group ${match[1]}` : group
}

export const useDashboardLinksStore = defineStore('dashboardLinks', () => {
  const groupSymbols = ref<Record<string, string>>({})

  function scopedKey(scope: string | number | undefined | null, group: string) {
    return `${scope ?? 'dashboard'}:${group}`
  }

  function setGroupSymbol(scope: string | number | undefined | null, group: string, symbol: string) {
    if (!group || !symbol) return
    groupSymbols.value[scopedKey(scope, group)] = symbol
  }

  function getGroupSymbol(scope: string | number | undefined | null, group: string | undefined | null): string {
    if (!group) return ''
    return groupSymbols.value[scopedKey(scope, group)] ?? ''
  }

  return { groupSymbols, setGroupSymbol, getGroupSymbol }
})
