import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiPut } = vi.hoisted(() => ({ apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { put: apiPut } }))

import { useWorkspaceStore } from '@/stores/workspace'

describe('workspace store layout tabs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiPut.mockReset()
  })

  it('clones the active serializable layout with remapped tool identities and saves it', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'primary-chart',
        layout_config: { root: { componentState: { instance_key: 'primary-chart' } } },
        windows: [{ id: 30, instance_key: 'primary-chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    apiPut.mockResolvedValue(store.workspace)

    store.cloneActiveTab()

    expect(store.workspace.tabs).toHaveLength(2)
    const clone = store.workspace.tabs[1]
    expect(clone.stable_key).not.toBe('us-top-down')
    expect(clone.windows[0].instance_key).not.toBe('primary-chart')
    expect((clone.layout_config.root as { componentState: { instance_key: string } }).componentState.instance_key).toBe(clone.windows[0].instance_key)
    expect(store.activeTabKey).toBe(clone.stable_key)

    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.objectContaining({ base_revision: 4, tabs: expect.any(Array) }))
  })

  it('persists a closed layout tool by removing only that serialized window', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [
          { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'notes', tool_type: 'notes', title: 'Notes', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    }
    apiPut.mockResolvedValue(store.workspace)

    store.applyActiveLayout({ root: { componentState: { instance_key: 'chart' } } }, ['chart'])

    expect(store.activeTab?.windows.map(window => window.instance_key)).toEqual(['chart'])
    expect(store.activeTab?.active_window_key).toBe('chart')
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalled()
  })
})
