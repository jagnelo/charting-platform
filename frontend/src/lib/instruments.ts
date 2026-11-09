import { api, setQueuedApiRequestPriority, type ApiRequestOptions } from '@/lib/api'
import type { Instrument } from '@/types'

const EXPR_RE = /^\s*=/
const EXPR_OPERATOR_RE = /[+\-*/]/
const EXPR_TRAILING_RE = /[+\-*/(]\s*$/

function transportOptions(options: Pick<ApiRequestOptions, 'priority' | 'signal' | 'foreground'>): Pick<ApiRequestOptions, 'priority' | 'signal' | 'foreground'> | undefined {
  return options.priority || options.signal || options.foreground
    ? { priority: options.priority, signal: options.signal, foreground: options.foreground }
    : undefined
}

export function instrumentLookupQueueKey(symbol: string, canonicalOnly = false): string {
  return `instrument-lookup:${symbol.trim().toUpperCase()}:${canonicalOnly ? 'canonical' : 'standard'}`
}

export type InstrumentInputKind = 'empty' | 'symbol' | 'expression' | 'pending_expression'

export interface InstrumentInputState {
  kind: InstrumentInputKind
  value: string
}

export interface ResolvedInstrument {
  symbol: string
  id: number | null
  instrumentType?: string
}

export interface CanonicalSymbolBatchResolution {
  resolved: Array<{ symbol: string; instrument_id: number }>
  missing: string[]
}

function parseApiStatus(message: string): number | null {
  const match = message.match(/→\s*(\d{3})\s*:/)
  return match ? Number(match[1]) : null
}

function parseApiDetail(message: string): string {
  const match = message.match(/→\s*\d{3}\s*:\s*(.+)$/s)
  const raw = (match?.[1] ?? message).trim()
  if (!raw) return ''
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim()
  } catch {
    // Fall back to the raw API error text when the body is not JSON.
  }
  return raw
}

function buildLookupError(raw: string, error: unknown, feature = 'Instrument'): Error {
  const input = classifyInstrumentInput(raw)
  if (input.kind === 'pending_expression') return new Error('Finish the expression to continue.')

  const message = error instanceof Error ? error.message : String(error ?? '')
  const status = parseApiStatus(message)
  const detail = parseApiDetail(message)

  if (input.kind === 'expression' && (status === 400 || status === 404)) {
    return new Error(`Could not resolve ${input.value}`)
  }
  if (status === 404) {
    return new Error(`${feature} "${input.value}" is not available.`)
  }
  return new Error(detail || message || `${feature} unavailable`)
}

export function classifyInstrumentInput(raw: string): InstrumentInputState {
  const trimmed = raw.trim()
  if (!trimmed) return { kind: 'empty', value: '' }
  if (!EXPR_RE.test(trimmed)) return { kind: 'symbol', value: trimmed.toUpperCase() }

  const body = trimmed.slice(1).trim()
  if (!body || !EXPR_OPERATOR_RE.test(body) || EXPR_TRAILING_RE.test(body)) {
    return { kind: 'pending_expression', value: trimmed }
  }
  return { kind: 'expression', value: trimmed }
}

export function isExpressionInput(raw: string): boolean {
  const kind = classifyInstrumentInput(raw).kind
  return kind === 'expression' || kind === 'pending_expression'
}

export function isResolvableExpressionInput(raw: string): boolean {
  return classifyInstrumentInput(raw).kind === 'expression'
}

export function getInstrumentInputHint(raw: string): string {
  return classifyInstrumentInput(raw).kind === 'pending_expression'
    ? 'Finish the expression to continue.'
    : ''
}

export async function resolveKnownInstrument(
  raw: string,
  feature = 'Instrument',
  options: { canonicalOnly?: boolean } & Pick<ApiRequestOptions, 'priority' | 'signal' | 'foreground'> = {},
): Promise<ResolvedInstrument> {
  const input = classifyInstrumentInput(raw)
  if (input.kind === 'empty') return { symbol: '', id: null }
  if (input.kind === 'pending_expression') throw new Error('Finish the expression to continue.')
  const requestOptions = transportOptions(options)

  try {
    let symbol: string
    if (input.kind === 'expression') {
      const path = '/instruments/resolve-expression' + (options.canonicalOnly ? '?canonical_only=true' : '')
      const payload = { expression: input.value }
      const result = await (requestOptions
        ? api.post<{ symbol: string }>(path, payload, requestOptions)
        : api.post<{ symbol: string }>(path, payload))
      // Expression resolution intentionally preserves the established single
      // POST contract. Synthetic IDs are surfaced by the instrument report
      // when constituent chips are selected; ordinary symbol search uses the
      // canonical GET below to carry identity without adding a second request
      // to every expression editor.
      return { symbol: result.symbol, id: null }
    } else {
      symbol = input.value
    }

    const path = `/instruments/${encodeURIComponent(symbol)}`
    const params = options.canonicalOnly ? { canonical_only: true } : undefined
    const queueKey = instrumentLookupQueueKey(symbol, options.canonicalOnly)
    if (options.foreground && options.priority === 'high') setQueuedApiRequestPriority(queueKey, 'high', true)
    const transport = transportOptions(options)
    const queuedOptions = transport ? { ...transport, queueKey } : undefined
    const instrument = await (queuedOptions
      ? api.get<Instrument>(path, params, queuedOptions)
      : api.get<Instrument>(path, params))
    return {
      symbol: instrument.symbol,
      id: typeof instrument.id === 'number' ? instrument.id : null,
      ...(typeof instrument.instrument_type === 'string' && instrument.instrument_type.trim()
        ? { instrumentType: instrument.instrument_type.trim() }
        : {}),
    }
  } catch (error) {
    throw buildLookupError(raw, error, feature)
  }
}

/** Resolve a bounded symbol set in one canonical-only request. */
export async function resolveCanonicalSymbols(
  rawSymbols: string[],
  feature = 'Instrument',
  options: Pick<ApiRequestOptions, 'priority' | 'signal'> = {},
): Promise<ResolvedInstrument[]> {
  const symbols = [...new Set(rawSymbols.map(value => value.trim().toUpperCase()).filter(Boolean))]
  if (!symbols.length) return []
  if (symbols.length > 500) throw new Error('A maximum of 500 canonical symbols can be selected at once.')
  if (symbols.some(value => classifyInstrumentInput(value).kind !== 'symbol')) {
    throw new Error(`${feature} selections must be plain ticker symbols.`)
  }
  try {
    const requestOptions = transportOptions(options)
    const result = await (requestOptions
      ? api.post<CanonicalSymbolBatchResolution>('/instruments/resolve-canonical', { symbols }, requestOptions)
      : api.post<CanonicalSymbolBatchResolution>('/instruments/resolve-canonical', { symbols }))
    if (result.missing.length) throw new Error(`Could not resolve ${result.missing.join(', ')}`)
    const bySymbol = new Map(result.resolved.map(item => [item.symbol.toUpperCase(), item.instrument_id]))
    return symbols.map(symbol => ({ symbol, id: bySymbol.get(symbol) ?? null }))
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('Could not resolve ')) throw error
    throw buildLookupError(symbols.join(', '), error, feature)
  }
}

export async function ensureKnownInstrumentSymbol(
  raw: string,
  feature = 'Instrument',
  options: { canonicalOnly?: boolean } & Pick<ApiRequestOptions, 'priority' | 'signal' | 'foreground'> = {},
): Promise<string> {
  const input = classifyInstrumentInput(raw)
  if (input.kind === 'empty') return ''
  if (input.kind === 'pending_expression') throw new Error('Finish the expression to continue.')
  const requestOptions = transportOptions(options)

  try {
    if (input.kind === 'expression') {
      const path = '/instruments/resolve-expression' + (options.canonicalOnly ? '?canonical_only=true' : '')
      const payload = { expression: input.value }
      const instrument = await (requestOptions
        ? api.post<{ symbol: string }>(path, payload, requestOptions)
        : api.post<{ symbol: string }>(path, payload))
      return instrument.symbol
    }
    const path = `/instruments/${encodeURIComponent(input.value)}`
    const params = options.canonicalOnly ? { canonical_only: true } : undefined
    const queueKey = instrumentLookupQueueKey(input.value, options.canonicalOnly)
    if (options.foreground && options.priority === 'high') setQueuedApiRequestPriority(queueKey, 'high', true)
    const transport = transportOptions(options)
    const queuedOptions = transport ? { ...transport, queueKey } : undefined
    const instrument = await (queuedOptions
      ? api.get<Instrument>(path, params, queuedOptions)
      : api.get<Instrument>(path, params))
    return instrument.symbol
  } catch (error) {
    throw buildLookupError(raw, error, feature)
  }
}

export function formatInstrumentLookupError(symbol: string, error: unknown, feature = 'Instrument'): string {
  return buildLookupError(symbol, error, feature).message
}
