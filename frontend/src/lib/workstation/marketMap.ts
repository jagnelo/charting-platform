import { api } from '@/lib/api'
import type { MarketMap, MarketMapCell, MarketMapRequest, MarketMapSnapshot, MarketMapSnapshotSummary } from '@/types'

export type BenchmarkFamilyRole = 'cap_weight' | 'equal_weight' | 'value' | 'growth'

export interface BenchmarkFamilyMemberBarHistoryTimeframe {
  timeframe: string
  member_count: number
  covered_member_count: number
  coverage_percent: number
  analysis_ready_member_count: number
  analysis_ready_percent: number
  bar_count: number
  oldest?: string | null
  newest?: string | null
  required_bar_count?: number
}

export interface BenchmarkFamilyCoverageSnapshot {
  snapshot_id: number
  composition_date: string
  as_of_date?: string | null
  known_at?: string | null
  provenance?: string | null
  source_provider?: string | null
  source_quality?: string | null
  completeness_status?: string | null
  row_count: number
  resolved_count: number
  unresolved_count: number
}

export interface BenchmarkFamilyCoverageRole {
  role: BenchmarkFamilyRole
  symbol?: string | null
  label: string
  verification_state?: string | null
  instrument_id?: number | null
  adapter_key?: string | null
  adapter_status?: string | null
  adapter_confidence?: string | null
  available: boolean
  status: string
  snapshots?: BenchmarkFamilyCoverageSnapshot[]
  continuity_status?: string | null
  continuity_gap_count?: number
  continuity_max_interval_days?: number | null
  continuity_snapshot_limit_reached?: boolean
  holdings_route_adapter_key?: string | null
  holdings_route_provider?: string | null
  holdings_route_status?: string | null
  holdings_refresh_provider?: string | null
  holdings_refresh_status?: string | null
  holdings_refresh_last_checked_at?: string | null
  holdings_refresh_last_success_at?: string | null
  holdings_refresh_last_failure_at?: string | null
  holdings_refresh_failure_reason?: string | null
  holdings_refresh_composition_date?: string | null
  member_bar_history?: {
    status: string
    placeholder_member_count: number
    timeframes: BenchmarkFamilyMemberBarHistoryTimeframe[]
  }
  entitlement_status?: string | null
  entitlement_provider?: string | null
  entitlement_capabilities?: Record<string, string>
  entitlement_revision?: number | null
  entitlement_effective_at?: string | null
  entitlement_review_due_at?: string | null
  entitlement_live_probe_status?: string | null
  point_in_time_supported: boolean
  member_count: number
  placeholder_member_count: number
  weighted_member_count: number
  weights_status: string
  classified_member_count: number
  classification_status: string
  history_ready: boolean
  composite_readiness_status: string
  composite_readiness_reasons: string[]
}

export interface BenchmarkFamilyCoverage {
  family_key: string
  name: string
  official_index_symbol: string
  coverage: number
  roles: BenchmarkFamilyCoverageRole[]
  freshness: string
}

export type WatchlistHistoryStatusKind = 'pending' | 'partial' | 'fetching' | 'failed' | 'ready' | 'unavailable'

export interface WatchlistHistoryTimeframeStatus {
  timeframe: string
  member_count: number
  covered_member_count: number
  coverage_percent: number
  analysis_ready_member_count?: number
  analysis_ready_percent?: number
  required_bar_count?: number | null
  bar_count: number
  oldest?: string | null
  newest?: string | null
  in_progress_count: number
  complete_count: number
  failed_count: number
  pending_count: number
}

export interface WatchlistSourceHistoryStatus {
  source_id: string
  source_kind?: string | null
  name: string
  locked: boolean
  membership_version?: string | null
  as_of?: string | null
  max_instruments: number
  available_instrument_count: number
  selected_instrument_count: number
  limited: boolean
  excluded_count: number
  overall_status: WatchlistHistoryStatusKind
  analysis_ready?: boolean
  analysis_ready_status?: WatchlistHistoryStatusKind
  timeframes: WatchlistHistoryTimeframeStatus[]
  message?: string | null
}

export interface WatchlistSourceHistoryRefreshResult {
  run_id?: number | null
  source_ids: string[]
  timeframes: string[]
  as_of?: string | null
  max_instruments: number
  available_instrument_count: number
  selected_instrument_count: number
  limited: boolean
  queued: number
  already_queued: number
  queue_unavailable: boolean
  message?: string | null
}

export interface WatchlistHistoryRefreshRun {
  id: number
  source_ids: string[]
  timeframes: string[]
  membership_versions?: Record<string, string | null>
  as_of?: string | null
  max_instruments: number
  available_instrument_count: number
  selected_instrument_count: number
  queued_count: number
  already_queued_count: number
  status: string
  cancel_requested: boolean
  progress: Record<string, number | string | boolean>
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export function fetchMarketMap(request: MarketMapRequest): Promise<MarketMap> {
  return api.post<MarketMap>('/analysis/market-map', request)
}

export function fetchBenchmarkFamilyCoverage(
  familyKey: string,
  asOf?: string | null,
  limit = 256,
): Promise<BenchmarkFamilyCoverage> {
  return api.get<BenchmarkFamilyCoverage>(
    `/analysis/benchmark-families/${encodeURIComponent(familyKey)}/coverage`,
    { limit, ...(asOf ? { as_of: asOf } : {}) },
  )
}

export function fetchWatchlistSourceHistoryStatus(
  sourceId: string,
  timeframes: string[] = ['D1'],
  maxInstruments = 5000,
  asOf?: string | null,
): Promise<WatchlistSourceHistoryStatus> {
  return api.get<WatchlistSourceHistoryStatus>(
    `/watchlists/sources/history-status/${encodeURIComponent(sourceId)}`,
    { timeframes, max_instruments: maxInstruments, ...(asOf ? { as_of: asOf } : {}) },
  )
}

export function refreshWatchlistSourceHistory(
  sourceId: string,
  timeframes: string[] = ['D1'],
  maxInstruments = 5000,
  asOf?: string | null,
): Promise<WatchlistSourceHistoryRefreshResult> {
  return api.post<WatchlistSourceHistoryRefreshResult>('/watchlists/sources/history-refresh', {
    source_ids: [sourceId],
    timeframes,
    max_instruments: maxInstruments,
    ...(asOf ? { as_of: asOf } : {}),
  })
}

export function fetchWatchlistHistoryRefreshRun(runId: number): Promise<WatchlistHistoryRefreshRun> {
  return api.get<WatchlistHistoryRefreshRun>(`/watchlists/history-refresh-runs/${runId}`)
}

export function cancelWatchlistHistoryRefreshRun(runId: number): Promise<WatchlistHistoryRefreshRun> {
  return api.post<WatchlistHistoryRefreshRun>(`/watchlists/history-refresh-runs/${runId}/cancel`, {})
}

export function fetchMarketMapCache(cacheKey: string): Promise<MarketMap> {
  return api.get<MarketMap>(`/analysis/market-map/cache/${encodeURIComponent(cacheKey)}`)
}

export function fetchMarketMapSnapshots(): Promise<MarketMapSnapshotSummary[]> {
  return api.get<MarketMapSnapshotSummary[]>('/analysis/market-map/snapshots')
}

export function saveMarketMapSnapshot(name: string, cacheKey: string): Promise<MarketMapSnapshot> {
  return api.post<MarketMapSnapshot>('/analysis/market-map/snapshots', { name, cache_key: cacheKey })
}

export function fetchMarketMapSnapshot(snapshotId: number): Promise<MarketMapSnapshot> {
  return api.get<MarketMapSnapshot>(`/analysis/market-map/snapshots/${snapshotId}`)
}

export function deleteMarketMapSnapshot(snapshotId: number): Promise<void> {
  return api.delete<void>(`/analysis/market-map/snapshots/${snapshotId}`)
}

export interface MarketMapLayoutCell extends MarketMapCell {
  x: number
  y: number
  width: number
  height: number
}

export interface MarketMapLayoutGroup {
  key: string
  label: string
  level: number
  parent_key: string | null
  x: number
  y: number
  width: number
  height: number
  member_count: number
}

interface LayoutItem {
  key: string
  area: number
}

interface LayoutRect extends LayoutItem {
  x: number
  y: number
  width: number
  height: number
}

/** Deterministic slice-and-dice rectangles with no DOM/provider-dependent inputs. */
function layoutRectangles(items: LayoutItem[], x: number, y: number, width: number, height: number): LayoutRect[] {
  const ordered = [...items].sort((left, right) => right.area - left.area || left.key.localeCompare(right.key))
  const total = ordered.reduce((sum, item) => sum + item.area, 0) || 1
  let cursorX = x
  let cursorY = y
  let remainingWidth = width
  let remainingHeight = height
  let remainingArea = total
  return ordered.map((item, index) => {
    const fraction = item.area / Math.max(remainingArea, 0.0001)
    const horizontal = remainingWidth >= remainingHeight
    const tileWidth = horizontal ? remainingWidth * fraction : remainingWidth
    const tileHeight = horizontal ? remainingHeight : remainingHeight * fraction
    const result: LayoutRect = { ...item, x: cursorX, y: cursorY, width: tileWidth, height: tileHeight }
    if (horizontal) {
      cursorX += tileWidth
      remainingWidth -= tileWidth
    } else {
      cursorY += tileHeight
      remainingHeight -= tileHeight
    }
    remainingArea -= item.area
    if (index === ordered.length - 1) {
      result.width = Math.max(result.width, width - result.x)
      result.height = Math.max(result.height, height - result.y)
    }
    return result
  })
}

/**
 * Deterministic hierarchical map geometry.
 *
 * Grouped universes (index/ETF constituents, sectors, industries, and ordinary
 * watchlists with classifications) are first partitioned by their top-level
 * group, then each group is partitioned into its members. Explicit/ungrouped
 * selections retain the original single-level slice-and-dice behavior.
 */
export function layoutMarketMapCells(cells: MarketMapCell[], width = 100, height = 100): MarketMapLayoutCell[] {
  // A cell without a finite positive area has no drawable treemap geometry. Keep it
  // in the source response for warning/coverage detail, but do not invent a unit tile.
  const weighted = cells
    .filter(cell => cell.area_value != null && Number.isFinite(cell.area_value) && cell.area_value > 0)
    .map(cell => ({ cell, area: cell.area_value as number }))
  if (!weighted.length) return []
  const cellsById = new Map(weighted.map(({ cell }) => [String(cell.instrument_id), cell]))

  const hasGroups = weighted.some(({ cell }) => cell.group_path.length > 0)
  if (!hasGroups) {
    return layoutRectangles(
      weighted.map(({ cell, area }) => ({ key: String(cell.instrument_id), area })),
      0,
      0,
      width,
      height,
    ).map((rect) => {
      const cell = cellsById.get(rect.key)
      if (!cell) return null
      return { ...cell, x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    }).filter((cell): cell is MarketMapLayoutCell => Boolean(cell))
  }

  type GroupTree = {
    path: string[]
    members: typeof weighted
    children: Map<string, GroupTree>
  }
  const root: GroupTree = { path: [], members: [], children: new Map() }
  for (const item of weighted) {
    let node = root
    for (const label of item.cell.group_path) {
      const childPath = [...node.path, label]
      const child = node.children.get(label) ?? { path: childPath, members: [], children: new Map() }
      node.children.set(label, child)
      node = child
    }
    node.members.push(item)
  }

  /**
   * Recursively partition the full group path before laying out its leaf cells.
   * The previous implementation split only on group_path[0] and then painted
   * industry frames around interleaved cells. That looked plausible for a small
   * fixture but could not guarantee a real sector → industry treemap. Direct
   * members at a mixed level are represented by a deterministic synthetic leaf
   * and retain their source cells without inventing a visible group frame.
   */
  const result: MarketMapLayoutCell[] = []
  const layoutNode = (node: GroupTree, x: number, y: number, nodeWidth: number, nodeHeight: number) => {
    const childItems = [...node.children.entries()].map(([key, child]) => ({
      key: `group:${key}`,
      area: child.members.reduce((sum, item) => sum + item.area, 0)
        + [...child.children.values()].reduce((sum, descendant) => sum + treeArea(descendant), 0),
    }))
    if (node.members.length) {
      childItems.push({
        key: '__direct_members__',
        area: node.members.reduce((sum, item) => sum + item.area, 0),
      })
    }
    if (!childItems.length) return
    const rectangles = layoutRectangles(childItems, x, y, nodeWidth, nodeHeight)
    for (const rectangle of rectangles) {
      if (rectangle.key === '__direct_members__') {
        layoutMembers(node.members, rectangle)
        continue
      }
      const childKey = rectangle.key.slice('group:'.length)
      const child = node.children.get(childKey)
      if (child) layoutNode(child, rectangle.x, rectangle.y, rectangle.width, rectangle.height)
    }
  }
  const treeArea = (node: GroupTree): number => node.members.reduce((sum, item) => sum + item.area, 0)
    + [...node.children.values()].reduce((sum, child) => sum + treeArea(child), 0)
  const layoutMembers = (members: typeof weighted, rectangle: LayoutRect) => {
    const memberRects = layoutRectangles(
      members.map(({ cell, area }) => ({ key: String(cell.instrument_id), area })),
      rectangle.x,
      rectangle.y,
      rectangle.width,
      rectangle.height,
    )
    for (const memberRect of memberRects) {
      const cell = cellsById.get(memberRect.key)
      if (cell) result.push({ ...cell, x: memberRect.x, y: memberRect.y, width: memberRect.width, height: memberRect.height })
    }
  }
  layoutNode(root, 0, 0, width, height)
  return result
}

/**
 * Returns nested rectangles used to frame grouped map members. This is
 * deliberately separate from member geometry so the large-universe canvas can
 * draw sector/industry boundaries without creating one DOM node per tile.
 */
export function layoutMarketMapGroups(cells: MarketMapCell[], width = 100, height = 100): MarketMapLayoutGroup[] {
  return layoutMarketMapGroupsFromLayout(layoutMarketMapCells(cells, width, height))
}

/** Build nested group frames from an existing member layout to avoid a second geometry pass. */
export function layoutMarketMapGroupsFromLayout(layout: MarketMapLayoutCell[]): MarketMapLayoutGroup[] {
  const groups = new Map<string, {
    path: string[]
    x: number
    y: number
    right: number
    bottom: number
    member_count: number
  }>()
  for (const cell of layout) {
    for (let level = 0; level < cell.group_path.length; level += 1) {
      const path = cell.group_path.slice(0, level + 1)
      const key = JSON.stringify(path)
      const right = cell.x + cell.width
      const bottom = cell.y + cell.height
      const group = groups.get(key)
      if (group) {
        group.x = Math.min(group.x, cell.x)
        group.y = Math.min(group.y, cell.y)
        group.right = Math.max(group.right, right)
        group.bottom = Math.max(group.bottom, bottom)
        group.member_count += 1
      } else {
        groups.set(key, { path, x: cell.x, y: cell.y, right, bottom, member_count: 1 })
      }
    }
  }
  return [...groups.entries()]
    .sort(([, left], [, right]) => left.path.length - right.path.length || left.y - right.y || left.x - right.x || left.path.join('\u0000').localeCompare(right.path.join('\u0000')))
    .map(([key, group]) => ({
      key,
      label: group.path[group.path.length - 1],
      level: group.path.length - 1,
      parent_key: group.path.length > 1 ? JSON.stringify(group.path.slice(0, -1)) : null,
      x: group.x,
      y: group.y,
      width: Math.max(0, group.right - group.x),
      height: Math.max(0, group.bottom - group.y),
      member_count: group.member_count,
    }))
}
