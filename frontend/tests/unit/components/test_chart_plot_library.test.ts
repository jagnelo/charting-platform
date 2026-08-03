import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChartPlotLibrary from '@/components/workstation/ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'

describe('ChartPlotLibrary', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('manages indicator plots without losing their serializable configuration', async () => {
    const chart = usePanelStore('plot-library-test')
    chart.setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Add indicator plot"]').setValue('ema')
    expect(chart.indicators).toHaveLength(2)

    await wrapper.get('[aria-label="Hide SMA(20)"]').trigger('click')
    expect(chart.indicators[0].hidden).toBe(true)
    await wrapper.get('[aria-label="Duplicate EMA(50)"]').trigger('click')
    expect(chart.indicators).toHaveLength(3)
    await wrapper.get('[aria-label="Move EMA(50) up"]').trigger('click')
    expect(chart.indicators[0].type).toBe('ema')
    await wrapper.findAll('[aria-label="Delete EMA(50)"]')[0].trigger('click')
    expect(chart.indicators).toHaveLength(2)
  })

  it('copies a plot only to chart windows in its linked symbol group', async () => {
    const workspace = useWorkspaceStore()
    workspace.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: {},
      tabs: [{ id: 1, stable_key: 'test', name: 'Test', position: 0, active_window_key: 'source', layout_config: {}, windows: [
        { id: 1, instance_key: 'source', tool_type: 'chart', title: 'Source', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 2, instance_key: 'linked', tool_type: 'chart', title: 'Linked', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
        { id: 3, instance_key: 'isolated', tool_type: 'chart', title: 'Isolated', link_group: 'grey', configuration: {}, style: {}, state_schema_version: 1, position: 2 },
      ] }],
    }
    workspace.activeTabKey = 'test'
    const scheduleSnapshot = vi.spyOn(workspace, 'scheduleSnapshot').mockImplementation(() => {})
    usePanelStore('linked-copy-test').setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'linked-copy-test' } } })

    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Copy SMA(20) to linked charts"]').trigger('click')

    expect(workspace.activeTab?.windows[1].configuration.indicators).toEqual([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    expect(workspace.activeTab?.windows[2].configuration.indicators).toBeUndefined()
    expect(scheduleSnapshot).toHaveBeenCalledOnce()
  })

  it('copies a plot to an explicitly selected isolated chart target', async () => {
    const workspace = useWorkspaceStore()
    workspace.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: {},
      tabs: [{ id: 1, stable_key: 'test', name: 'Test', position: 0, active_window_key: 'source', layout_config: {}, windows: [
        { id: 1, instance_key: 'source', tool_type: 'chart', title: 'Source', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 2, instance_key: 'isolated', tool_type: 'chart', title: 'Isolated', link_group: 'grey', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    workspace.activeTabKey = 'test'
    vi.spyOn(workspace, 'scheduleSnapshot').mockImplementation(() => {})
    usePanelStore('explicit-copy-test').setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'explicit-copy-test' } } })

    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Copy plot target"]').setValue('isolated')
    await wrapper.get('[aria-label="Copy SMA(20) to selected chart target"]').trigger('click')

    expect(workspace.activeTab?.windows[1].configuration.indicators).toEqual([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
  })
})
