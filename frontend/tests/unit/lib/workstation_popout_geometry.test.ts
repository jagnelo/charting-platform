import { describe, expect, it } from 'vitest'
import { capturePopoutGeometry, geometryVisibleOnAnyScreen, popoutWindowFeatures, readPopoutGeometry, recoverPopoutGeometry } from '@/lib/workstation/popoutGeometry'

describe('workstation pop-out geometry', () => {
  it('uses stable defaults when no persisted geometry exists', () => {
    expect(readPopoutGeometry({})).toEqual({ left: 80, top: 80, width: 1100, height: 760 })
    expect(readPopoutGeometry({}, { availLeft: 1920, availTop: 0 })).toEqual({ left: 2000, top: 80, width: 1100, height: 760 })
  })

  it('clamps malformed and undersized persisted dimensions', () => {
    expect(readPopoutGeometry({ popout: { left: 12.4, top: -8.8, width: 10, height: Number.NaN } })).toEqual({
      left: 12,
      top: -9,
      width: 320,
      height: 760,
    })
  })

  it('serializes geometry into browser window features', () => {
    expect(popoutWindowFeatures({ left: 12, top: 24, width: 900, height: 600 })).toBe(
      'popup=yes,width=900,height=600,left=12,top=24,resizable=yes,scrollbars=no',
    )
  })

  it('captures negative-coordinate geometry from a secondary monitor', () => {
    const popup = {
      screenX: -1440,
      screenY: 120,
      outerWidth: 1280,
      outerHeight: 900,
    } as Window

    expect(capturePopoutGeometry(popup)).toEqual({
      left: -1440,
      top: 120,
      width: 1280,
      height: 900,
    })
  })

  it('keeps a saved window on any currently available monitor', () => {
    const screens = [
      { availLeft: 0, availTop: 0, availWidth: 1920, availHeight: 1080 },
      { availLeft: -1440, availTop: 0, availWidth: 1440, availHeight: 900 },
    ]
    const saved = { popout: { left: -1300, top: 40, width: 900, height: 700 } }
    expect(geometryVisibleOnAnyScreen(readPopoutGeometry(saved), screens)).toBe(true)
    expect(recoverPopoutGeometry(saved, screens, screens[0])).toEqual({ left: -1300, top: 40, width: 900, height: 700 })
  })

  it('recovers an off-screen saved window only with a complete screen inventory', () => {
    const screens = [{ availLeft: 0, availTop: 0, availWidth: 1920, availHeight: 1080 }]
    const saved = { popout: { left: 3200, top: 40, width: 900, height: 700 } }
    expect(recoverPopoutGeometry(saved, screens, screens[0])).toEqual({ left: 80, top: 80, width: 1100, height: 760 })
    // Without Window Management permission/details, do not destroy a possibly
    // valid secondary-monitor placement based on an incomplete guess.
    expect(recoverPopoutGeometry(saved, null, screens[0])).toEqual({ left: 3200, top: 40, width: 900, height: 700 })
  })

  it('preserves an off-screen window when any reported display lacks authoritative bounds', () => {
    const partialScreens = [
      { availLeft: 0, availTop: 0, availWidth: 1920, availHeight: 1080 },
      { availLeft: -1440, availTop: 0 },
    ]
    const saved = { popout: { left: 3200, top: 40, width: 900, height: 700 } }
    expect(recoverPopoutGeometry(saved, partialScreens, partialScreens[0])).toEqual({
      left: 3200,
      top: 40,
      width: 900,
      height: 700,
    })
  })
})
