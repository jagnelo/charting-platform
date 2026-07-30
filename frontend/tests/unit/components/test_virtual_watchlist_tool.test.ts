import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import VirtualWatchlistTool from '@/components/workstation/VirtualWatchlistTool.vue'

const rows = [
  { instrumentId: 1, symbol: 'XLK', name: 'Technology', values: { relative_1m: 0.12 } },
  { instrumentId: 2, symbol: 'XLE', name: 'Energy', values: { relative_1m: -0.03 } },
  { instrumentId: 3, symbol: 'XLV', name: 'Health Care', values: { relative_1m: 0.02 } },
]

beforeEach(() => apiGet.mockResolvedValue([]))
afterEach(() => apiGet.mockReset())

describe('VirtualWatchlistTool', () => {
  it('filters canonical rows and publishes the selected canonical row', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors',
        rows,
        columns: [
          { key: 'symbol', label: 'Symbol', width: '60px' },
          { key: 'name', label: 'Name', width: '1fr' },
        ],
      },
    })

    expect(wrapper.text()).toContain('XLK')
    await wrapper.find('input').setValue('energy')
    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')
    expect(wrapper.emitted('update:filterText')?.at(-1)).toEqual(['energy'])

    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([rows[1]])
  })

  it('restores a persisted filter and follows a workspace-state update', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows, filterText: 'technology' },
    })

    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('technology')
    expect(wrapper.text()).toContain('XLK')
    expect(wrapper.text()).not.toContain('XLE')

    await wrapper.setProps({ filterText: 'energy' })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('energy')
    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')
  })

  it('applies a saved condition from its latest retained local scan result', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 91, name: 'Close above threshold' }])
      if (path === '/screeners/91/results') return Promise.resolve([{ matched_ids: [2], run_at: '2026-07-30T00:00:00Z' }])
      return Promise.resolve([])
    })
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await vi.waitFor(() => expect(wrapper.findAll('option')).toHaveLength(2))
    await wrapper.find('select').setValue('91')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved condition active'))

    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')
    expect(wrapper.emitted('update:conditionScreenerId')?.at(-1)).toEqual([91])
  })

  it('keeps a saved condition configured while inactive and clears it only when off', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 91, name: 'Close above threshold' }])
      if (path === '/screeners/91/results') return Promise.resolve([{ matched_ids: [2], run_at: '2026-07-30T00:00:00Z' }])
      return Promise.resolve([])
    })
    const wrapper = mount(VirtualWatchlistTool, { props: { label: 'Sectors', rows } })
    await vi.waitFor(() => expect(wrapper.findAll('option')).toHaveLength(2))
    await wrapper.find('select').setValue('91')
    await vi.waitFor(() => expect(wrapper.findAll('select')).toHaveLength(2))
    await wrapper.findAll('select')[1].setValue('inactive')

    expect(wrapper.text()).toContain('inactive')
    expect(wrapper.find('.watchlist__controls b').text()).toBe('3')
    expect(wrapper.emitted('update:conditionFilterMode')?.at(-1)).toEqual(['inactive'])
    expect(wrapper.emitted('update:conditionScreenerId')?.at(-1)).toEqual([91])

    await wrapper.findAll('select')[1].setValue('off')
    expect(wrapper.emitted('update:conditionFilterMode')?.at(-1)).toEqual(['off'])
    expect(wrapper.emitted('update:conditionScreenerId')?.at(-1)).toEqual([null])
  })

  it('shows no rows rather than silently ignoring an unrun saved condition', async () => {
    apiGet.mockImplementation((path: string) => path === '/screeners'
      ? Promise.resolve([{ id: 92, name: 'Unrun condition' }])
      : Promise.resolve([]))
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await vi.waitFor(() => expect(wrapper.findAll('option')).toHaveLength(2))
    await wrapper.find('select').setValue('92')
    await vi.waitFor(() => expect(wrapper.text()).toContain('has not been run yet'))

    expect(wrapper.findAll('.watchlist__row')).toHaveLength(0)
  })

  it('sorts a selected column without losing row identity', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await wrapper.findAll('.watchlist__header button')[0].trigger('click')
    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ instrumentId: 3, symbol: 'XLV' })
  })

  it('publishes a persisted visible-column set without allowing an empty table', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'name', label: 'Name' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    const choices = wrapper.findAll('.watchlist__column-menu input[type="checkbox"]')
    await choices[1].setValue(false)
    expect(wrapper.emitted('update:visibleColumnKeys')?.[0]).toEqual([['symbol']])

    await wrapper.setProps({ visibleColumnKeys: ['symbol'] })
    await choices[0].setValue(false)
    expect(wrapper.emitted('update:visibleColumnKeys')).toHaveLength(1)
  })

  it('renders explicitly numeric technical columns without percentage scaling', () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows: [{ instrumentId: 1, symbol: 'XLK', name: 'Technology', values: { rsi14: 67.2, performance_1m: 0.12 } }],
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'rsi14', label: 'RSI', format: 'number' }, { key: 'performance_1m', label: '1M' }],
      },
    })
    expect(wrapper.text()).toContain('67.20')
    expect(wrapper.text()).toContain('12.00%')
  })

  it('pins true Boolean rows ahead of the secondary sort and persists the pin choice', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'above_ma50', label: '>50', kind: 'boolean' }],
        pinnedBooleanKeys: ['above_ma50'],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await wrapper.find('.watchlist__column-menu button:not(.watchlist__stack-button)').trigger('click')
    expect(wrapper.emitted('update:pinnedBooleanKeys')?.at(-1)).toEqual([[]])
  })

  it('persists column grouping without changing virtualized canonical row identity', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'relative_1m', label: '1M relative' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    const groupInput = wrapper.find('input[aria-label="1M relative group"]')
    await groupInput.setValue('Momentum')

    expect(wrapper.emitted('update:columnGroups')?.at(-1)).toEqual([{ relative_1m: 'Momentum' }])
    await wrapper.setProps({ columnGroups: { relative_1m: 'Momentum' } })
    expect(wrapper.find('.watchlist__header em').text()).toBe('Momentum')
    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.at(-1)?.[0]).toMatchObject({ instrumentId: 2, symbol: 'XLE' })
  })

  it('stacks saved columns in one dense cell without duplicating their canonical row', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'relative_1m', label: '1M relative' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await wrapper.find('.watchlist__stack-button').trigger('click')
    expect(wrapper.emitted('update:stackedColumnKeys')?.at(-1)).toEqual([['symbol']])

    await wrapper.setProps({ stackedColumnKeys: ['symbol', 'relative_1m'] })
    expect(wrapper.findAll('.watchlist__row')).toHaveLength(1)
    expect(wrapper.find('.watchlist__stack-cell').text()).toContain('Symbol')
    expect(wrapper.find('.watchlist__stack-cell').text()).toContain('1M relative')
  })
})
