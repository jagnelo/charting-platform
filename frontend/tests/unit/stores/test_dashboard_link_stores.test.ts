import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  dashboardLinkGroupColor,
  dashboardLinkGroupLabel,
  useDashboardLinksStore,
  WORKSTATION_LINK_GROUPS,
} from '@/stores/dashboardLinks'
import { usePanelLinksStore } from '@/stores/panelLinks'

describe('dashboard/panel link stores', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('dashboard link helpers resolve labels and colors', () => {
    expect(dashboardLinkGroupColor('blue')).toBe('#64b5f6')
    expect(dashboardLinkGroupColor('yellow')).toBe('#ffca28')
    expect(dashboardLinkGroupLabel('grey')).toBe('Grey')
    expect(dashboardLinkGroupLabel('group-3')).toBe('Group 3')
    expect(dashboardLinkGroupLabel(null)).toBe('Unlinked')
    expect(WORKSTATION_LINK_GROUPS.map(group => group.id)).toEqual([
      'blue', 'red', 'green', 'purple', 'orange', 'cyan', 'pink', 'brown', 'yellow', 'grey',
    ])
  })

  it('dashboard links store tracks scoped symbols', () => {
    const store = useDashboardLinksStore()
    store.setGroupSymbol('tab-1', 'group-1', 'NVDA')
    expect(store.getGroupSymbol('tab-1', 'group-1')).toBe('NVDA')
    expect(store.getGroupSymbol('tab-2', 'group-1')).toBe('')
  })

  it('panel links store defaults to blue and persists panel groups', () => {
    const store = usePanelLinksStore()
    expect(store.groupFor('main')).toBe('blue')
    store.setPanelGroup('main', 'green')
    expect(store.colorFor('main')).toBe('#81c784')
    expect(store.linkedPanelIds('main', ['main', 'secondary'])).toEqual(['main'])
  })

  it('panel symbol links provide eight groups, yellow wildcard receiving, and grey isolation', () => {
    const store = usePanelLinksStore()
    const panels = ['blue-source', 'blue-peer', 'red', 'yellow', 'grey']
    store.setPanelGroup('red', 'red')
    store.setPanelGroup('yellow', 'yellow')
    store.setPanelGroup('grey', 'grey')

    expect(store.linkedPanelIds('blue-source', panels)).toEqual(['blue-source', 'blue-peer', 'yellow'])
    expect(store.linkedPanelIds('red', panels)).toEqual(['red', 'yellow'])
    expect(store.linkedPanelIds('yellow', panels)).toEqual(['yellow'])
    expect(store.linkedPanelIds('grey', panels)).toEqual(['grey'])
  })

  it('migrates legacy unlinked panels to the explicit grey group and ignores invalid values', () => {
    localStorage.setItem('chart.panelLinks.v1', JSON.stringify({ legacy: null, invalid: 'magenta' }))
    const store = usePanelLinksStore()

    expect(store.groupFor('legacy')).toBe('grey')
    expect(store.groupFor('invalid')).toBe('blue')
  })
})
