import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { parse as parseTemplate } from '@vue/compiler-dom'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { describe, expect, it, vi } from 'vitest'

import {
  createTagColumnMembershipToggler,
  mergeTagColumnConfiguration,
  resolveTagColumnTargets,
  type TagColumnWatchlist,
} from '@/lib/workstation/tagColumns'

const toolContentPath = join(process.cwd(), 'src/components/workstation/WorkstationToolContent.vue')

function virtualWatchlistNodes(node: ReturnType<typeof parseTemplate>['children'][number]): Array<{
  props: Array<{ type: number; name?: string; arg?: { content?: string }; exp?: { content?: string } }>
  children?: Array<ReturnType<typeof parseTemplate>['children'][number]>
  tag?: string
  type: number
}> {
  if (node.type !== 1) return []
  const current = node.tag === 'VirtualWatchlistTool' ? [node] : []
  return [
    ...current,
    ...node.children.flatMap(child => virtualWatchlistNodes(child)),
  ]
}

function watchlistFixture(overrides: Partial<TagColumnWatchlist> = {}): TagColumnWatchlist {
  return {
    id: 7,
    name: 'Core',
    is_managed: false,
    is_locked: false,
    items: [{ id: 11, instrument_id: 101 }],
    ...overrides,
  }
}

describe('WorkstationToolContent Tag Column contracts', () => {
  it('resolves configured personal targets and preserves unavailable or read-only evidence', () => {
    expect(resolveTagColumnTargets(
      [7, 8, 7, 0, '9'],
      [watchlistFixture(), watchlistFixture({ id: 8, name: 'Managed', is_managed: true, items: [] })],
    )).toEqual([
      { id: 7, name: 'Core', locked: false, instrumentIds: [101] },
      { id: 8, name: 'Managed', locked: true, instrumentIds: [] },
    ])

    expect(resolveTagColumnTargets([9], [])).toEqual([
      { id: 9, name: 'WatchList 9 (unavailable)', locked: false, instrumentIds: null },
    ])
  })

  it('normalizes updates while preserving sibling configuration and the current columns on malformed input', () => {
    expect(mergeTagColumnConfiguration(
      { title: 'Core', tag_watchlist_ids: [3], column_keys: ['symbol'], untouched: true },
      { targetWatchlistIds: [7, 7, -1, '8'], visibleColumnKeys: ['symbol', 'tag-watchlist:7', 'symbol'] },
      ['last'],
    )).toEqual({
      title: 'Core',
      tag_watchlist_ids: [7],
      column_keys: ['symbol', 'tag-watchlist:7'],
      untouched: true,
    })

    expect(mergeTagColumnConfiguration(
      { column_keys: ['symbol'] },
      { targetWatchlistIds: null, visibleColumnKeys: null },
      ['symbol', 'change'],
    )).toEqual({ tag_watchlist_ids: [], column_keys: ['symbol', 'change'] })
  })

  it('toggles membership only in the selected unlocked personal target', async () => {
    const watchlists = [watchlistFixture(), watchlistFixture({ id: 8, name: 'Other', items: [] })]
    const error = { value: 'previous error' }
    const addItem = vi.fn(async (watchlistId: number, instrumentId: number) => {
      const target = watchlists.find(item => item.id === watchlistId)!
      const added = { id: 22, instrument_id: instrumentId }
      target.items = [...target.items, added]
      return added
    })
    const removeItem = vi.fn(async (watchlistId: number, itemId: number) => {
      const target = watchlists.find(item => item.id === watchlistId)!
      target.items = target.items.filter(item => item.id !== itemId)
    })
    const toggle = createTagColumnMembershipToggler({
      getPersonalWatchlists: () => watchlists,
      isDisposed: () => false,
      addItem,
      removeItem,
      setError: message => { error.value = message },
    })

    await toggle({ symbol: 'SPY', instrumentId: 101 }, 8)
    expect(addItem).toHaveBeenCalledOnce()
    expect(addItem).toHaveBeenCalledWith(8, 101)
    expect(watchlists[0].items).toEqual([{ id: 11, instrument_id: 101 }])
    expect(watchlists[1].items).toEqual([{ id: 22, instrument_id: 101 }])
    expect(error.value).toBe('')

    await toggle({ symbol: 'SPY', instrumentId: 101 }, 8)
    expect(removeItem).toHaveBeenCalledOnce()
    expect(removeItem).toHaveBeenCalledWith(8, 22)
    expect(watchlists[1].items).toEqual([])
    expect(error.value).toBe('')
  })

  it('rejects locked, managed, invalid and unavailable targets before transport', async () => {
    const watchlists = [
      watchlistFixture({ id: 7, is_locked: true }),
      watchlistFixture({ id: 8, is_managed: true }),
    ]
    const setError = vi.fn()
    const addItem = vi.fn()
    const removeItem = vi.fn()
    const toggle = createTagColumnMembershipToggler({
      getPersonalWatchlists: () => watchlists,
      isDisposed: () => false,
      addItem,
      removeItem,
      setError,
    })

    for (const targetId of [7, 8, 9, 0, Number.NaN]) {
      await toggle({ symbol: 'SPY', instrumentId: 101 }, targetId)
    }
    await toggle({ symbol: 'SPY', instrumentId: null }, 7)

    expect(addItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
    expect(setError).toHaveBeenCalledTimes(4)
    expect(setError).toHaveBeenLastCalledWith('Tag Columns can change membership only in an unlocked personal WatchList.')
  })

  it('reports failed add and remove confirmations without inventing membership', async () => {
    const watchlists = [watchlistFixture()]
    const setError = vi.fn()
    const toggle = createTagColumnMembershipToggler({
      getPersonalWatchlists: () => watchlists,
      isDisposed: () => false,
      addItem: vi.fn().mockResolvedValue(null),
      removeItem: vi.fn().mockResolvedValue(undefined),
      setError,
    })

    await toggle({ symbol: 'QQQ', instrumentId: 202 }, 7)
    expect(setError).toHaveBeenLastCalledWith('Unable to add QQQ to Core.')

    await toggle({ symbol: 'SPY', instrumentId: 101 }, 7)
    expect(setError).toHaveBeenLastCalledWith('Unable to remove SPY from Core.')
    expect(watchlists[0].items).toEqual([{ id: 11, instrument_id: 101 }])
  })

  it('coalesces a duplicate in-flight mutation for the same target and instrument', async () => {
    const watchlists = [watchlistFixture({ items: [] })]
    let resolveAdd: ((item: { id: number; instrument_id: number }) => void) | undefined
    const addItem = vi.fn(() => new Promise<{ id: number; instrument_id: number }>(resolve => { resolveAdd = resolve }))
    const toggle = createTagColumnMembershipToggler({
      getPersonalWatchlists: () => watchlists,
      isDisposed: () => false,
      addItem,
      removeItem: vi.fn(),
      setError: vi.fn(),
    })

    const first = toggle({ symbol: 'SPY', instrumentId: 101 }, 7)
    await toggle({ symbol: 'SPY', instrumentId: 101 }, 7)
    expect(addItem).toHaveBeenCalledOnce()
    watchlists[0].items = [{ id: 22, instrument_id: 101 }]
    resolveAdd?.({ id: 22, instrument_id: 101 })
    await first
  })

  it('does not start mutations after the owning tool has been disposed', async () => {
    const addItem = vi.fn()
    const removeItem = vi.fn()
    const toggle = createTagColumnMembershipToggler({
      getPersonalWatchlists: () => [watchlistFixture()],
      isDisposed: () => true,
      addItem,
      removeItem,
      setError: vi.fn(),
    })

    await toggle({ symbol: 'SPY', instrumentId: 101 }, 7)
    expect(addItem).not.toHaveBeenCalled()
    expect(removeItem).not.toHaveBeenCalled()
  })

  it('binds the normalized Tag Column contract on every WatchList host template', () => {
    const source = readFileSync(toolContentPath, 'utf8')
    const { descriptor, errors } = parseSfc(source, { filename: toolContentPath })
    expect(errors).toEqual([])
    expect(descriptor.template).not.toBeNull()
    const template = parseTemplate(descriptor.template!.content)
    const hosts = template.children.flatMap(node => virtualWatchlistNodes(node))

    expect(hosts).toHaveLength(6)
    for (const host of hosts) {
      expect(host.props).toContainEqual(expect.objectContaining({
        type: 7,
        name: 'bind',
        arg: expect.objectContaining({ content: 'tag-columns' }),
        exp: expect.objectContaining({ content: 'configuredTagColumns' }),
      }))
      expect(host.props).toContainEqual(expect.objectContaining({
        type: 7,
        name: 'on',
        arg: expect.objectContaining({ content: 'update:tag-columns' }),
        exp: expect.objectContaining({ content: 'updateTagColumns' }),
      }))
    }
  })
})
