import type { DrawingStyle, DrawingType } from '@/types'

export interface DrawingPoint {
  time: number   // unix timestamp
  price: number
}

export interface DrawingBase {
  id?: number
  type: DrawingType
  points: DrawingPoint[]
  style: DrawingStyle
  label?: string
  isSelected?: boolean
  isLocked?: boolean
  isVisible?: boolean
  sourceTag?: string | null
  radarLinked?: boolean
  radarHighlightOpacity?: number
  radarRoles?: string[]
}

export interface TrendlineDrawing extends DrawingBase {
  type: 'trendline'
  points: [DrawingPoint, DrawingPoint]
  extendRight?: boolean
  extendLeft?: boolean
}

export interface HorizontalLineDrawing extends DrawingBase {
  type: 'horizontal_line'
  points: [DrawingPoint]
}

export interface FibonacciDrawing extends DrawingBase {
  type: 'fibonacci_retracement' | 'fibonacci_extension'
  points: [DrawingPoint, DrawingPoint]
  levels?: number[]
}

export interface RectangleDrawing extends DrawingBase {
  type: 'rectangle' | 'circle' | 'half_circle'
  points: [DrawingPoint, DrawingPoint]
  filled?: boolean
}

export interface TextBoxDrawing extends DrawingBase {
  type: 'text_box'
  points: [DrawingPoint]
  text: string
}

export interface FreehandDrawing extends DrawingBase {
  type: 'freehand'
  points: DrawingPoint[]
}

export type AnyDrawing =
  | TrendlineDrawing
  | HorizontalLineDrawing
  | FibonacciDrawing
  | RectangleDrawing
  | TextBoxDrawing
  | FreehandDrawing
  | DrawingBase

/** Standard Fibonacci retracement levels (0%–100% of the selected range) */
export const FIBO_RETRACEMENT_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

/** Fibonacci extension levels — projections beyond the 100% mark */
export const FIBO_EXTENSION_LEVELS  = [0, 0.382, 0.618, 1.0, 1.272, 1.414, 1.618, 2.0, 2.618]

/** @deprecated kept for backward-compat with saved drawings that stored a custom levels array */
export const FIBO_DEFAULT_LEVELS = FIBO_RETRACEMENT_LEVELS

export const FIBO_LEVEL_COLORS: Record<string, string> = {
  '0':     '#9e9e9e',
  '0.236': '#64b5f6',
  '0.382': '#81c784',
  '0.5':   '#ffb74d',
  '0.618': '#e57373',
  '0.786': '#ba68c8',
  '1':     '#9e9e9e',
  '1.272': '#4db6ac',
  '1.414': '#80cbc4',
  '1.618': '#f06292',
  '2':     '#ce93d8',
  '2.618': '#ff8a65',
}
