import { describe, expect, it } from 'vitest'
import { OPENABLE_WORKSTATION_TOOLS } from '@/stores/workspace'

describe('primary workstation capability boundary', () => {
  it('does not register excluded TC2000 domains in the authenticated tool menu', () => {
    const registered = new Set(OPENABLE_WORKSTATION_TOOLS.map(tool => tool.tool_type))
    for (const excluded of [
      'brokerage', 'trading', 'options', 'news', 'analyst-ratings',
      'earnings', 'financial-statements', 'consolidated-realtime',
    ]) expect(registered.has(excluded)).toBe(false)
  })

  it('keeps supported workstation research and analysis tools discoverable', () => {
    const registered = new Set(OPENABLE_WORKSTATION_TOOLS.map(tool => tool.tool_type))
    for (const supported of ['chart', 'watchlist', 'scan', 'gauge', 'study_lab', 'relative_rotation', 'breadth']) {
      expect(registered.has(supported)).toBe(true)
    }
  })

  it('exposes My Favorites as a distinct fixed Quick List, not a personal watchlist alias', () => {
    const favorites = OPENABLE_WORKSTATION_TOOLS.find(tool => tool.title === 'My Favorites')
    expect(favorites).toMatchObject({
      tool_type: 'watchlist',
      instance_prefix: 'favorites',
      configuration: { personal: true, favorites: true },
    })
  })
})
