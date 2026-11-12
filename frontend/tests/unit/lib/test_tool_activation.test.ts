import { describe, expect, it } from 'vitest'

import { dockTabWindowKey, isActiveVirtualToolRoot } from '@/lib/workstation/toolActivation'

describe('virtual workstation tool activation', () => {
  it('uses the exact active workspace key when a virtual tool has no lm_stack ancestor', () => {
    const virtualHost = document.createElement('section')
    virtualHost.className = 'workspace-layout-host__virtual-tool'
    virtualHost.dataset.toolKey = 'market-map-17'
    const toolRoot = document.createElement('section')
    toolRoot.className = 'tool-window'
    toolRoot.dataset.windowKey = 'market-map-17'
    virtualHost.append(toolRoot)

    expect(toolRoot.closest('.lm_stack')).toBeNull()
    expect(isActiveVirtualToolRoot(toolRoot, 'market-map-17', 'market-map-17')).toBe(true)
    expect(isActiveVirtualToolRoot(toolRoot, 'market-map-17', 'chart-main')).toBe(false)
    expect(isActiveVirtualToolRoot(toolRoot, 'market-map-old', 'market-map-17')).toBe(false)
  })

  it('leaves ordinary Golden Layout roots to their real tab activation path', () => {
    const stack = document.createElement('section')
    stack.className = 'lm_stack'
    const toolRoot = document.createElement('section')
    toolRoot.className = 'tool-window'
    stack.append(toolRoot)

    expect(isActiveVirtualToolRoot(toolRoot, 'market-map-17', 'market-map-17')).toBe(false)
  })

  it('maps a pointer inside a visible dock tab to its exact instance and ignores close controls', () => {
    const studyTab = document.createElement('div')
    studyTab.className = 'lm_tab'
    const title = document.createElement('span')
    studyTab.append(title)
    const otherStudyTab = document.createElement('div')
    otherStudyTab.className = 'lm_tab'
    const close = document.createElement('div')
    close.className = 'lm_close_tab'
    studyTab.append(close)

    const bindings = [
      { windowKey: 'study-lab-copy', element: otherStudyTab },
      { windowKey: 'study-lab-main', element: studyTab },
    ]
    expect(dockTabWindowKey(title, bindings)).toBe('study-lab-main')
    expect(dockTabWindowKey(close, bindings)).toBeNull()
    expect(dockTabWindowKey(document.createElement('button'), bindings)).toBeNull()
  })
})
