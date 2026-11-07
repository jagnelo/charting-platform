import { defineAsyncComponent, defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
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
    let activeComponentItem: any = undefined
    const parentItem: any = {
      setActiveComponentItem: vi.fn((item: any) => { activeComponentItem = item }),
      getActiveComponentItem: () => activeComponentItem,
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
import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { api } from '@/lib/api'

describe('WorkspaceLayoutHost', () => {
  beforeEach(() => {
    goldenLayouts.length = 0
    setActivePinia(createPinia())
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
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(gl.destroyed).toBe(true)
    expect(goldenLayouts).toHaveLength(2)
    wrapper.unmount()
    expect(goldenLayouts[1].destroyed).toBe(true)
  })

  it('forwards maximised and minimised Stack events through a reactive virtual-tool action', () => {
    const renderTool = vi.fn((_tool: any, _actions: any) => h('div'))
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        renderTool,
      },
    })
    const listeners = new Map<string, () => void>()
    const stack = {
      isMaximised: false,
      on: (event: string, listener: () => void) => listeners.set(event, listener),
      off: (event: string) => listeners.delete(event),
      toggleMaximise() {
        this.isMaximised = !this.isMaximised
        listeners.get(this.isMaximised ? 'maximised' : 'minimised')?.()
      },
    }
    goldenLayouts[0].factory!({ parent: { parentItem: stack } }, { instance_key: 'industry-1', title: 'Industries', tool_type: 'watchlist' })
    const actions = renderTool.mock.calls[0][1] as { maximized: { value: boolean }; toggleMaximize: () => void }

    expect(actions.maximized.value).toBe(false)
    actions.toggleMaximize()
    expect(actions.maximized.value).toBe(true)
    actions.toggleMaximize()
    expect(actions.maximized.value).toBe(false)
    wrapper.unmount()
    expect(listeners.size).toBe(0)
  })

  it('publishes maximize state only after the workspace snapshot is saved', async () => {
    let resolveSave!: (saved: boolean) => void
    const pendingSave = new Promise<boolean>(resolve => { resolveSave = resolve })
    const renderTool = vi.fn((_tool: any, _actions: any) => h('div'))
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        persistLayout: () => pendingSave,
        renderTool,
      },
    })
    const listeners = new Map<string, () => void>()
    const stack = {
      isMaximised: false,
      on: (event: string, listener: () => void) => listeners.set(event, listener),
      off: (event: string) => listeners.delete(event),
      toggleMaximise() {
        this.isMaximised = !this.isMaximised
        listeners.get(this.isMaximised ? 'maximised' : 'minimised')?.()
      },
    }
    goldenLayouts[0].factory!({ parent: { parentItem: stack } }, { instance_key: 'relative-rotation', title: 'Relative Rotation', tool_type: 'relative_rotation' })
    const actions = renderTool.mock.calls[0][1] as {
      maximized: { value: boolean }
      maximizing: { value: boolean }
      toggleMaximize: () => Promise<void>
    }

    const toggling = actions.toggleMaximize()
    expect(stack.isMaximised).toBe(true)
    expect(actions.maximizing.value).toBe(true)
    expect(actions.maximized.value).toBe(false)

    resolveSave(true)
    await toggling
    expect(actions.maximizing.value).toBe(false)
    expect(actions.maximized.value).toBe(true)
    wrapper.unmount()
  })

  it('does not reinstall when the normalised layout fingerprint is unchanged', async () => {
    const layout = { root: { type: 'row', content: [] } } as any
    const wrapper = mount(WorkspaceLayoutHost, { props: { layout, renderTool: () => h('div') } })
    await wrapper.setProps({ layout: { root: { type: 'row', content: [] } } as any })
    await nextTick()
    expect(goldenLayouts).toHaveLength(1)
    wrapper.unmount()
  })

  it('adds one appended dock tool without rebuilding or dropping its mounted sibling', async () => {
    const layout = {
      root: { type: 'stack', content: [
        { type: 'component', componentName: 'workstation-tool', title: 'Chart', componentState: { instance_key: 'chart-1', title: 'Chart', tool_type: 'chart' } },
      ] },
    } as any
    const addedLayout = {
      root: { type: 'stack', content: [
        layout.root.content[0],
        { type: 'component', componentName: 'workstation-tool', title: 'Benchmarks', componentState: { instance_key: 'benchmark-1', title: 'Benchmarks', tool_type: 'watchlist' } },
      ] },
    } as any
    const renderTool = vi.fn((tool: any) => h('div', { 'data-tool': tool.instance_key }))
    const wrapper = mount(WorkspaceLayoutHost, { props: { layout, activeWindowKey: 'chart-1', renderTool } })
    const gl = goldenLayouts[0]
    const stack: any = {
      type: 'stack',
      contentItems: [],
      header: { tabs: [] as any[] },
      isMaximised: false,
      active: null as any,
      setActiveComponentItem(item: any) { this.active = item },
      getActiveComponentItem() { return this.active },
      removeChild: vi.fn((item: any) => {
        stack.contentItems = stack.contentItems.filter((candidate: any) => candidate !== item)
        stack.header.tabs = stack.header.tabs.filter((tab: any) => tab.contentItem !== item)
        item.destroy?.()
        gl.saved = { root: { type: 'stack', content: stack.contentItems.map((candidate: any) => ({
          type: 'component',
          componentName: 'workstation-tool',
          title: candidate.config.componentState.title,
          componentState: candidate.config.componentState,
        })) } }
      }),
      addComponent: vi.fn((_type: string, state: any, _title: string) => {
        const item: any = {
          type: 'component',
          config: { componentState: state },
          parentItem: stack,
          show: vi.fn(),
          hide: vi.fn(),
        }
        stack.contentItems.push(item)
        stack.header.tabs.push({ contentItem: item, element: document.createElement('div') })
        const cleanupHandlers = new Map<string, () => void>()
        item.destroy = () => cleanupHandlers.get('destroy')?.()
        gl.factory!({ parent: item, on: vi.fn((event: string, callback: () => void) => cleanupHandlers.set(event, callback)) }, state)
      }),
    }
    const chartItem: any = {
      type: 'component',
      config: { componentState: { instance_key: 'chart-1' } },
      parentItem: stack,
      show: vi.fn(),
      hide: vi.fn(),
    }
    stack.contentItems.push(chartItem)
    stack.header.tabs.push({ contentItem: chartItem, element: document.createElement('div') })
    gl.root = { contentItems: [stack] }
    const chartCleanupHandlers = new Map<string, () => void>()
    chartItem.destroy = () => chartCleanupHandlers.get('destroy')?.()
    gl.factory!({ parent: chartItem, on: vi.fn((event: string, callback: () => void) => chartCleanupHandlers.set(event, callback)) }, { instance_key: 'chart-1', title: 'Chart', tool_type: 'chart' })

    await wrapper.setProps({ layout: addedLayout, activeWindowKey: 'benchmark-1' })
    await nextTick()

    expect(goldenLayouts).toHaveLength(1)
    expect(gl.destroyed).toBe(false)
    expect(stack.addComponent).toHaveBeenCalledWith('workstation-tool', addedLayout.root.content[1].componentState, 'Benchmarks')
    expect(renderTool.mock.calls.map(([tool]) => tool.instance_key)).toEqual(['chart-1', 'benchmark-1'])
    expect(stack.contentItems.map((item: any) => item.config.componentState.instance_key)).toEqual(['chart-1', 'benchmark-1'])
    gl.saved = addedLayout
    renderTool.mock.calls[1][1].close()
    await nextTick()
    expect(stack.removeChild).toHaveBeenCalledWith(expect.objectContaining({ config: { componentState: expect.objectContaining({ instance_key: 'benchmark-1' }) } }), false)
    expect(stack.contentItems.map((item: any) => item.config.componentState.instance_key)).toEqual(['chart-1'])
    expect(goldenLayouts).toHaveLength(1)
    expect(gl.destroyed).toBe(false)
    wrapper.unmount()
  })

  it('closes a tool by rebuilding the serializable tree before Golden Layout teardown', async () => {
    const layout = {
      root: {
        type: 'stack',
        content: [
          { type: 'component', componentState: { instance_key: 'chart-1', title: 'Chart', tool_type: 'chart' } },
          { type: 'component', componentState: { instance_key: 'notes-1', title: 'Notes', tool_type: 'notes' } },
        ],
      },
    } as any
    const renderTool = vi.fn((tool: any, actions: any) => h('button', {
      'data-tool': tool.instance_key,
      onClick: actions.close,
    }, 'close'))
    const wrapper = mount(WorkspaceLayoutHost, { props: { layout, renderTool } })
    const gl = goldenLayouts[0]
    gl.saved = JSON.parse(JSON.stringify(layout))
    const rendered = gl.factory!({ parent: { parentItem: { toggleMaximise: vi.fn() } } }, { instance_key: 'chart-1', title: 'Chart', tool_type: 'chart' }) as any
    void rendered
    expect(renderTool.mock.calls.at(-1)?.[0]).toMatchObject({ instance_key: 'chart-1' })
    renderTool.mock.calls.at(-1)?.[1].close()
    await nextTick()

    expect(gl.destroyed).toBe(true)
    expect(wrapper.emitted('changed')?.at(-1)?.[0]).toEqual({
      root: {
        type: 'stack',
        activeItemIndex: 0,
        content: [{ type: 'component', componentState: { instance_key: 'notes-1', title: 'Notes', tool_type: 'notes' } }],
      },
    })
    expect(goldenLayouts).toHaveLength(2)
    wrapper.unmount()
  })

  it('reinstalls virtual roots when a complete workspace snapshot is replaced', async () => {
    const layout = { root: { type: 'row', content: [] } } as any
    const wrapper = mount(WorkspaceLayoutHost, {
      props: { layout, reloadKey: 0, renderTool: () => h('div') },
    })

    await wrapper.setProps({ reloadKey: 1 })
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(goldenLayouts).toHaveLength(2)
    expect(goldenLayouts[0].destroyed).toBe(true)
    wrapper.unmount()
  })

  it('ignores late state and activation events from a superseded layout generation', async () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        reloadKey: 0,
        tabKey: 'tab-a',
        renderTool: () => h('div'),
      },
    })
    const previous = goldenLayouts[0]

    await wrapper.setProps({ reloadKey: 1 })
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(goldenLayouts).toHaveLength(2)

    wrapper.find('.workspace-layout-host').element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    previous.saved = { root: { componentState: { instance_key: 'stale' } } }
    previous.callbacks.get('stateChanged')!()
    previous.callbacks.get('activeContentItemChanged')!({ config: { componentState: { instance_key: 'stale' } } })

    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.emitted('active-window-changed')).toBeUndefined()
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

  it('does not synthesize tab clicks when the supported stack getter reports the component active', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const pendingFrames = new Map<number, FrameRequestCallback>()
    let nextFrameId = 0
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      const id = ++nextFrameId
      pendingFrames.set(id, callback)
      return id
    })
    const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => {
      pendingFrames.delete(id)
    })
    let wrapper: ReturnType<typeof mount> | undefined

    try {
      wrapper = mount(WorkspaceLayoutHost, {
        props: {
          layout: { root: { type: 'row', content: [] } } as any,
          activeWindowKey: 'chart-1',
          renderTool: () => h('div'),
        },
      })
      const component = goldenLayouts[0].root.contentItems[0]
      const tabClick = vi.fn()
      component.parentItem.header.tabs = [{ contentItem: component, element: { click: tabClick } }]

      await nextTick()
      // Drain the bounded bootstrap RAF callbacks, including nested reasserts.
      // The cap also fails if a future change creates an unexpected RAF loop.
      for (let frame = 0; pendingFrames.size > 0 && frame < 6; frame += 1) {
        const callbacks = [...pendingFrames.values()]
        pendingFrames.clear()
        callbacks.forEach(callback => callback(frame * 16))
        await nextTick()
        await vi.advanceTimersByTimeAsync(0)
      }
      expect(pendingFrames.size).toBe(0)
      // Let the component's single 25ms active-component poll observe the
      // supported getter and stop before taking the stable baseline.
      await vi.advanceTimersByTimeAsync(25)
      const settledActivationCount = component.parentItem.setActiveComponentItem.mock.calls.length

      await vi.advanceTimersByTimeAsync(75)

      expect('activeComponentItem' in component.parentItem).toBe(false)
      expect(component.parentItem.getActiveComponentItem()).toBe(component)
      expect(component.parentItem.setActiveComponentItem).toHaveBeenCalledTimes(settledActivationCount)
      expect(tabClick).not.toHaveBeenCalled()
    } finally {
      wrapper?.unmount()
      vi.clearAllTimers()
      requestFrame.mockRestore()
      cancelFrame.mockRestore()
      vi.useRealTimers()
    }
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

  it('lets direct tab interaction supersede the persisted activation guard', async () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        activeWindowKey: 'chart-1',
        renderTool: () => h('div'),
      },
    })
    const host = wrapper.find('.workspace-layout-host').element
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    const tab = document.createElement('div')
    tab.className = 'lm_tab'
    host.appendChild(tab)
    tab.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))

    goldenLayouts[0].callbacks.get('activeContentItemChanged')!({ config: { componentState: { instance_key: 'chart-2' } } })

    expect(wrapper.emitted('active-window-changed')).toEqual([['chart-2']])
    wrapper.unmount()
  })

  it('publishes the exact virtual tool key from an ordinary tab pointer before a late GL activation callback', () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        activeWindowKey: 'chart-1',
        tabKey: 'layout-a',
        renderTool: () => h('div'),
      },
    })
    const host = wrapper.find('.workspace-layout-host').element
    const stack = goldenLayouts[0].root.contentItems[0].parentItem
    const chart = goldenLayouts[0].root.contentItems[0]
    const study = {
      type: 'component',
      config: { componentState: { instance_key: 'study-lab-copy' } },
      parentItem: stack,
    }
    stack.contentItems.push(study)
    const chartTab = document.createElement('div')
    chartTab.className = 'lm_tab'
    const studyTab = document.createElement('div')
    studyTab.className = 'lm_tab'
    const title = document.createElement('span')
    studyTab.append(title)
    const close = document.createElement('div')
    close.className = 'lm_close_tab'
    studyTab.append(close)
    stack.header.tabs = [
      { contentItem: chart, element: chartTab },
      { contentItem: study, element: studyTab },
    ]
    host.append(chartTab, studyTab)
    goldenLayouts[0].factory!({ close: vi.fn(), parent: study }, {
      instance_key: 'study-lab-copy',
      title: 'Study Lab',
      tool_type: 'study_lab',
    })

    title.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))

    expect(wrapper.emitted('active-window-changed')).toEqual([['study-lab-copy', 'layout-a']])
    close.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    expect(wrapper.emitted('active-window-changed')).toHaveLength(1)
    wrapper.unmount()
  })

  it('resolves an asynchronously loaded tool body in its detached Golden Layout root', async () => {
    const AsyncTool = defineAsyncComponent(() => Promise.resolve(
      defineComponent({ render: () => h('article', { 'data-loaded-tool-body': '' }, 'Loaded tool body') }),
    ))
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout: { root: { type: 'row', content: [] } } as any,
        renderTool: () => h(AsyncTool),
      },
    })
    const rendered = goldenLayouts[0].factory!({ parent: { parentItem: { toggleMaximise: vi.fn() } } }, {
      instance_key: 'study-lab-main',
      title: 'Study Lab',
      tool_type: 'study_lab',
    }) as { rootHtmlElement: HTMLElement }
    wrapper.find('.workspace-layout-host').element.append(rendered.rootHtmlElement)

    await flushPromises()

    expect(rendered.rootHtmlElement.querySelector('[data-loaded-tool-body]')?.textContent).toBe('Loaded tool body')
    wrapper.unmount()
  })

  it('mounts the real lazy WorkstationToolContent body in a Golden Layout virtual root', async () => {
    vi.spyOn(api, 'get').mockResolvedValue([] as never)
    const pinia = createPinia()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const layout = { root: { type: 'row', content: [] } } as any
    const wrapper = mount(WorkspaceLayoutHost, {
      props: {
        layout,
        activeWindowKey: 'code-library-main',
        renderTool: tool => h(WorkstationToolContent, {
          tool: {
            ...tool,
            instance_key: tool.instance_key,
            title: tool.title,
            tool_type: tool.tool_type,
            link_group: 'blue',
            configuration: {},
            style: {},
          } as any,
          activeWindowKey: 'code-library-main',
        }),
      },
      global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] },
    })
    const stack = { isMaximised: false, on() {}, off() {}, toggleMaximise() {} }
    const rendered = goldenLayouts[0].factory!({ parent: { parentItem: stack } }, {
      instance_key: 'code-library-main',
      title: 'Python Library',
      tool_type: 'code_library',
    }) as { rootHtmlElement: HTMLElement }
    wrapper.find('.workspace-layout-host').element.append(rendered.rootHtmlElement)

    await vi.waitFor(() => expect(rendered.rootHtmlElement.querySelector('.code-library-tool')).not.toBeNull(), { timeout: 2_000 })
    await flushPromises()

    expect(rendered.rootHtmlElement.textContent).not.toContain('Loading tool…')
    expect(rendered.rootHtmlElement.querySelector('.code-library-tool')).not.toBeNull()
    wrapper.unmount()
    queryClient.clear()
    vi.restoreAllMocks()
  })

  it('evenly resizes panes above a Shift-dragged horizontal splitter and persists the layout', async () => {
    const layout = { root: { type: 'column', content: [] } } as any
    const wrapper = mount(WorkspaceLayoutHost, {
      props: { layout, renderTool: () => h('div') },
    })
    const host = wrapper.find('.workspace-layout-host').element as HTMLElement
    Object.defineProperty(host, 'clientWidth', { value: 800 })
    Object.defineProperty(host, 'clientHeight', { value: 400 })
    const panes = [100, 100, 200].map((height, index) => {
      const element = document.createElement('section')
      element.dataset.pane = String(index)
      Object.defineProperty(element, 'getBoundingClientRect', { value: () => ({ height }) })
      return { element, size: height / 4 }
    })
    const splitterBefore = document.createElement('div')
    splitterBefore.className = 'lm_splitter lm_vertical'
    const splitter = document.createElement('div')
    splitter.className = 'lm_splitter lm_vertical'
    const rowElement = document.createElement('div')
    rowElement.append(panes[0].element, splitterBefore, panes[1].element, splitter, panes[2].element)
    host.append(rowElement)
    const row: any = {
      element: rowElement,
      contentItems: panes,
      _splitter: [{ element: splitterBefore }, { element: splitter }],
      calculateContentItemMinSize: () => 50,
    }
    const gl = goldenLayouts[0]
    gl.root = { contentItems: [row] }
    gl.saveLayout = () => ({
      root: { type: 'column', content: panes.map((pane, index) => ({
        type: 'component',
        size: pane.size,
        componentState: { instance_key: `pane-${index}` },
      })) },
    })

    const down = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0, clientY: 100, shiftKey: true })
    splitter.dispatchEvent(down)
    expect(down.defaultPrevented).toBe(true)
    document.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, cancelable: true, clientY: 180 }))
    document.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientY: 180 }))

    expect(panes.map(pane => pane.size)).toEqual([35, 35, 30])
    expect(gl.sizes.at(-1)).toEqual([800, 400])
    expect(wrapper.emitted('changed')?.at(-1)?.[0]).toEqual({
      root: {
        type: 'column',
        content: [
          { type: 'component', size: 35, componentState: { instance_key: 'pane-0' } },
          { type: 'component', size: 35, componentState: { instance_key: 'pane-1' } },
          { type: 'component', size: 30, componentState: { instance_key: 'pane-2' } },
        ],
      },
    })
    wrapper.unmount()
  })

  it('leaves ordinary splitter drags and modified vertical splitters to Golden Layout', () => {
    const wrapper = mount(WorkspaceLayoutHost, {
      props: { layout: { root: { type: 'row', content: [] } } as any, renderTool: () => h('div') },
    })
    const host = wrapper.find('.workspace-layout-host').element
    const horizontalDivider = document.createElement('div')
    horizontalDivider.className = 'lm_splitter lm_vertical'
    const verticalDivider = document.createElement('div')
    verticalDivider.className = 'lm_splitter lm_horizontal'
    host.append(horizontalDivider, verticalDivider)

    const ordinary = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0 })
    horizontalDivider.dispatchEvent(ordinary)
    const modifiedVertical = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0, shiftKey: true })
    verticalDivider.dispatchEvent(modifiedVertical)

    expect(ordinary.defaultPrevented).toBe(false)
    expect(modifiedVertical.defaultPrevented).toBe(false)
    wrapper.unmount()
  })
})
