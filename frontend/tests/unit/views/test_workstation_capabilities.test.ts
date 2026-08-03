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
})
