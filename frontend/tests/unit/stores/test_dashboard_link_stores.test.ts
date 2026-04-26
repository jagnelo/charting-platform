import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  dashboardLinkGroupColor,
  dashboardLinkGroupLabel,
  useDashboardLinksStore,
} from '@/stores/dashboardLinks'
import { usePanelLinksStore } from '@/stores/panelLinks'

describe('dashboard/panel link stores', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('dashboard link helpers resolve labels and colors', () => {
    expect(dashboardLinkGroupColor('blue')).toBe('#64b5f6')
    expect(dashboardLinkGroupLabel('group-3')).toBe('Group 3')
    expect(dashboardLinkGroupLabel(null)).toBe('Unlinked')
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
    expect(store.colorFor('main')).toBe('#26a69a')
    expect(store.linkedPanelIds('main', ['main', 'secondary'])).toEqual(['main'])
  })
})

