import { describe, expect, it } from 'vitest'

import { parseTagColumnWatchlistIds, tagColumnKey, tagColumnMembership } from '@/lib/workstation/tagColumns'

describe('personal WatchList Tag Column contracts', () => {
  it('persists only unique positive integer target IDs in user order', () => {
    expect(parseTagColumnWatchlistIds([17, 4, 17, 0, -2, 2.5, '9', null])).toEqual([17, 4])
    expect(parseTagColumnWatchlistIds({ target: 17 })).toEqual([])
    expect(tagColumnKey(17)).toBe('tag-watchlist:17')
  })

  it('distinguishes membership, non-membership, and unavailable evidence', () => {
    const target = { id: 17, name: 'Core', instrumentIds: [101, 202] }
    expect(tagColumnMembership(target, 101)).toBe('member')
    expect(tagColumnMembership(target, 303)).toBe('not_member')
    expect(tagColumnMembership({ ...target, instrumentIds: null }, 303)).toBe('unavailable')
    expect(tagColumnMembership(null, 303)).toBe('unavailable')
    expect(tagColumnMembership(target, null)).toBe('unavailable')
  })
})
