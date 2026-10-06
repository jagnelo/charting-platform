import { describe, expect, it } from 'vitest'
import { resizePanesEvenly } from '@/lib/workstation/modifier-pane-resize'

describe('resizePanesEvenly', () => {
  it('resizes all panes above the divider evenly and uses the nearest lower pane as counterweight', () => {
    expect(resizePanesEvenly([100, 100, 300, 200], [50, 50, 50, 50], 1, 50, 'above'))
      .toEqual([125, 125, 250, 200])
  })

  it('resizes all panes below the divider evenly and uses the nearest upper pane as counterweight', () => {
    expect(resizePanesEvenly([100, 100, 300, 200], [50, 50, 50, 50], 1, 50, 'below'))
      .toEqual([100, 150, 225, 225])
  })

  it('clamps at pane minimums and leaves unrelated panes unchanged', () => {
    expect(resizePanesEvenly([100, 100, 100], [80, 80, 80], 0, 500, 'above'))
      .toEqual([120, 80, 100])
  })

  it('redistributes around unequal minimums while preserving the affected group total', () => {
    expect(resizePanesEvenly([100, 100, 100], [90, 20, 20], 1, 100, 'above'))
      .toEqual([140, 140, 20])
  })

  it('rejects invalid geometry instead of emitting a malformed layout', () => {
    expect(resizePanesEvenly([100], [50], 0, 20, 'above')).toBeNull()
    expect(resizePanesEvenly([100, 100], [50], 0, 20, 'above')).toBeNull()
    expect(resizePanesEvenly([100, 100], [50, 50], 3, 20, 'below')).toBeNull()
    expect(resizePanesEvenly([100, 100], [50, 50], 0, Number.NaN, 'above')).toBeNull()
  })
})
