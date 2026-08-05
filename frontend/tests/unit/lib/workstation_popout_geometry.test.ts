import { describe, expect, it } from 'vitest'
import { popoutWindowFeatures, readPopoutGeometry } from '@/lib/workstation/popoutGeometry'

describe('workstation pop-out geometry', () => {
  it('uses stable defaults when no persisted geometry exists', () => {
    expect(readPopoutGeometry({})).toEqual({ left: 80, top: 80, width: 1100, height: 760 })
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
})
