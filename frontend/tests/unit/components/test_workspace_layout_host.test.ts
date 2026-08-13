import { h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { goldenLayouts, MockGoldenLayout } = vi.hoisted(() => {
  const layouts: any[] = []
  class Layout {
  callbacks = new Map<string, (arg?: unknown) => void>()
  loaded: unknown = null
  root: any = { contentItems: [] }
  destroyed = false
  sizes: Array<[number, number]> = []
  saved = { root: { type: 'row', content: [] as unknown[] } }
  factory: ((container: any, state: unknown) => unknown) | null = null

  constructor(public host: HTMLElement) {
      layouts.push(this)
  }

  registerComponentFactoryFunction(_name: string, factory: (container: any, state: unknown) => unknown) {
    this.factory = factory
  }

  on(name: string, callback: (arg?: unknown) => void) {
    this.callbacks.set(name, callback)
  }

  loadLayout(layout: unknown) {
    this.loaded = layout
    const parentItem: any = {
      setActiveComponentItem: vi.fn(),
      contentItems: [] as any[],
      header: { tabs: [] as any[] },
    }
    const component: any = {
      type: 'component',
      config: { componentState: { instance_key: 'chart-1' } },
      parentItem,
    }
    parentItem.contentItems = [component]
    parentItem.header.tabs = [{ contentItem: component }]
    this.root = {
      contentItems: [component],
    }
  }

  saveLayout() {
    return this.saved
  }

  setSize(width: number, height: number) {
    this.sizes.push([width, height])
  }

  destroy() {
    this.destroyed = true
  }
  }
  return { goldenLayouts: layouts, MockGoldenLayout: Layout }
})

vi.mock('golden-layout', () => ({ GoldenLayout: MockGoldenLayout }))
vi.mock('@/lib/workstation/layout', () => ({
  normaliseGoldenLayoutConfig: (layout: unknown) => layout,
}))

import WorkspaceLayoutHost from '@/components/workstation/WorkspaceLayoutHost.vue'

describe('WorkspaceLayoutHost', () => {
  beforeEach(() => {
    goldenLayouts.length = 0
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    })
  })

  it('installs virtual tools, forwards app actions, emits serialised state, resizes, and cleans up', async () => {
    const renderTool = vi.fn((tool: any, actions: any) => h('button', {
      'data-tool': tool.instance_key,
      onClick: actions.close,
    }, 'tool'))
    const layout = { root: { type: 'row', content: [{ type: 'component', componentName: 'workstation-tool', componentState: { instance_key: 'chart-1', title: 'Chart', tool_type: 'chart' } }] } } as any
    const wrapper = mount(WorkspaceLayoutHost, { props: { layout, renderTool } })
    const host = wrapper.find('.workspace-layout-host').element as HTMLElement
    Object.defineProperty(host, 'clientWidth', { value: 800 })
    Object.defineProperty(host, 'clientHeight', { value: 600 })
    const gl = goldenLayouts[0]
    expect(gl.loaded).toEqual(layout)
    expect(gl.sizes).toEqual([])

    const root = document.createElement('div')
    const rendered = gl.factory!({ close: vi.fn(), parent: { parentItem: { toggleMaximise: vi.fn() } } }, { instance_key: 'chart-1', title: 'Chart', tool_type: 'chart' }) as any
    root.appendChild(rendered.rootHtmlElement)
    expect(renderTool).toHaveBeenCalledWith(expect.objectContaining({ instance_key: 'chart-1' }), expect.any(Object))
    expect(rendered.rootHtmlElement.dataset.toolKey).toBe('chart-1')

    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    host.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    gl.saved = { root: { componentState: { instance_key: 'chart-1' } } }
    gl.callbacks.get('stateChanged')!()
    expect(wrapper.emitted('changed')?.[0]).toEqual([gl.saved, ['chart-1']])

    await wrapper.setProps({ layout: { root: { type: 'column', content: [] } } as any })
    await nextTick()
    expect(gl.destroyed).toBe(true)
    expect(goldenLayouts).toHaveLength(2)
    wrapper.unmount()
    expect(goldenLayouts[1].destroyed).toBe(true)
  })

  it('does not reinstall when the normalised layout fingerprint is unchanged', async () => {
    const layout = { root: { type: 'row', content: [] } } as any
    const wrapper = mount(WorkspaceLayoutHost, { props: { layout, renderTool: () => h('div') } })
    await wrapper.setProps({ layout: { root: { type: 'row', content: [] } } as any })
    await nextTick()
    expect(goldenLayouts).toHaveLength(1)
    wrapper.unmount()
  })

  it('reinstalls virtual roots when a complete workspace snapshot is replaced', async () => {
    const layout = { root: { type: 'row', content: [] } } as any
    const wrapper = mount(WorkspaceLayoutHost, {
      props: { layout, reloadKey: 0, renderTool: () => h('div') },
    })

    await wrapper.setProps({ reloadKey: 1 })
    await nextTick()

    expect(goldenLayouts).toHaveLength(2)
    expect(goldenLayouts[0].destroyed).toBe(true)
    wrapper.unmount()
  })

  it('fully tears down virtual roots and resize observation through the exposed destroy action', () => {
    const wrapper = mount(WorkspaceLayoutHost, { props: { layout: { root: { type: 'row', content: [] } } as any, renderTool: () => h('div') } })
    const layout = goldenLayouts[0]

    ;(wrapper.vm as any).destroy()

    expect(layout.destroyed).toBe(true)
    wrapper.unmount()
  })

  it('activates a newly opened or restored tool after the layout is loaded', () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        activeWindowKey: 'chart-1',
        renderTool: () => h('div'),
      },
    })
    const component = goldenLayouts[0].root.contentItems[0]
    expect(component.parentItem.setActiveComponentItem).toHaveBeenCalledWith(component, false, true)
    wrapper.unmount()
  })

  it('does not reassert a component through a header that no longer owns it during a drag', async () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        activeWindowKey: 'chart-1',
        renderTool: () => h('div'),
      },
    })
    const component = goldenLayouts[0].root.contentItems[0]
    const processActiveComponentChanged = vi.fn()
    component.parentItem.header = {
      tabs: [],
      processActiveComponentChanged,
    }
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    expect(processActiveComponentChanged).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('publishes the active component key when a Golden Layout tab changes', async () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: { layout: { root: { type: 'row', content: [] } } as any, renderTool: () => h('div') },
    })
    const gl = goldenLayouts[0]
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    wrapper.find('.workspace-layout-host').element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    gl.callbacks.get('activeContentItemChanged')!({ config: { componentState: { instance_key: 'chart-2' } } })
    expect(wrapper.emitted('active-window-changed')).toEqual([['chart-2']])
    wrapper.unmount()
  })
})
