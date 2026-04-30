import { api } from '@/lib/api'
import type { Instrument } from '@/types'

const EXPR_RE = /^\s*=/
const EXPR_OPERATOR_RE = /[+\-*/]/
const EXPR_TRAILING_RE = /[+\-*/(]\s*$/

export type InstrumentInputKind = 'empty' | 'symbol' | 'expression' | 'pending_expression'

export interface InstrumentInputState {
  kind: InstrumentInputKind
  value: string
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

export async function ensureKnownInstrumentSymbol(raw: string): Promise<string> {
  const input = classifyInstrumentInput(raw)
  if (input.kind === 'empty') return ''
  if (input.kind === 'pending_expression') throw new Error('Finish the expression to continue.')

  try {
    if (input.kind === 'expression') {
      const instrument = await api.post<{ symbol: string }>('/instruments/resolve-expression', {
        expression: input.value,
      })
      return instrument.symbol
    }

    const instrument = await api.get<Instrument>(`/instruments/${encodeURIComponent(input.value)}`)
    return instrument.symbol
  } catch (error) {
    throw buildLookupError(raw, error)
  }
}

export function formatInstrumentLookupError(symbol: string, error: unknown, feature = 'Instrument'): string {
  return buildLookupError(symbol, error, feature).message
}
