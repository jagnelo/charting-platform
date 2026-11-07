import type { APIRequestContext, Page, Response } from '@playwright/test'
import { expect, test } from './helpers'

const SECTOR_SYMBOLS = [
  'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY',
]
const SP500_SYMBOLS = ['SPY', ...SECTOR_SYMBOLS]
const TIMEFRAMES = ['D1', 'W1', 'MN'] as const
type AnalysisTimeframe = typeof TIMEFRAMES[number]

interface Bar {
  ts: string
  close: number
  is_adjusted: boolean
}

interface RatioResponse {
  symbol: string
  benchmark: string
  timeframe: string
  adjustment: string
  points: Array<{ timestamp: string; value: number }>
  coverage: number
  warnings: Array<{ code: string; message: string }>
}

const RATIO_SERIES_COLORS = ['#6bc0ef', '#e7b35b', '#aa86e8', '#5fc8a2']
const ROTATION_STATE_COLORS = {
  leading: '#61c58c',
  weakening: '#e7be68',
  improving: '#6dbbe6',
  lagging: '#df8181',
} as const

interface RotationRow {
  instrument_id: number
  symbol: string
  state: 'leading' | 'weakening' | 'improving' | 'lagging' | null
  trend: number | null
  momentum: number | null
  coverage: number
  tail: Array<{ timestamp: string; trend: number; momentum: number }>
  history: Array<{ timestamp: string; trend: number; momentum: number }>
  warnings: Array<{ code: string; message: string }>
}

interface RotationResponse {
  group_key: string
  benchmark: string
  timeframe: string
  adjustment: string
  lookback: number
  tail_length: number
  rows: RotationRow[]
  coverage_preflight: { status?: string; evaluator?: string }
}

async function bearerToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'))
  expect(token, 'the ordinary authenticated E2E fixture must provide its session token').toBeTruthy()
  return token!
}

async function getJson<T>(request: APIRequestContext, token: string, path: string, params?: Record<string, string | number | boolean>): Promise<T> {
  const response = await request.get(path, {
    headers: { Authorization: `Bearer ${token}` },
    ...(params ? { params } : {}),
  })
  const body = await response.text()
  expect(response.status(), `GET ${path} returned ${body}`).toBe(200)
  return JSON.parse(body) as T
}

function barResponseFor(response: Response, symbol: string, timeframe: string): boolean {
  const parts = new URL(response.url()).pathname.split('/').filter(Boolean)
  const ohlcvIndex = parts.lastIndexOf('ohlcv')
  if (ohlcvIndex < 0) return false
  const symbolIndex = parts[ohlcvIndex + 1] === 'local' ? ohlcvIndex + 2 : ohlcvIndex + 1
  return parts[symbolIndex]?.toUpperCase() === symbol && parts[symbolIndex + 1] === timeframe
}

function rotationResponseFor(response: Response, timeframe: AnalysisTimeframe): boolean {
  const url = new URL(response.url())
  return url.pathname === '/api/v1/analysis/groups/sp500-sectors/relative-rotation'
    && url.searchParams.get('timeframe') === timeframe
}

function relativeStrengthResponseFor(response: Response, numerator: string, denominator: string): boolean {
  const url = new URL(response.url())
  return url.pathname === '/api/v1/analysis/relative-strength'
    && url.searchParams.get('symbol') === numerator
    && url.searchParams.get('benchmark') === denominator
    && url.searchParams.get('timeframe') === 'D1'
    && url.searchParams.get('adjusted') === 'true'
}

function rotationPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function assertActualBars(symbol: string, bars: Bar[], minimumCount = 2): void {
  expect(bars.length, `${symbol} must have persisted bars in the seeded backend`).toBeGreaterThanOrEqual(minimumCount)
  for (const bar of bars) {
    expect(Number.isFinite(Date.parse(bar.ts)), `${symbol} bar timestamp`).toBe(true)
    expect(Number.isFinite(bar.close) && bar.close > 0, `${symbol} raw close`).toBe(true)
  }
}

function assertRatioMatchesRawIntersection(
  primary: string,
  benchmark: string,
  primaryBars: Bar[],
  benchmarkBars: Bar[],
  response: RatioResponse,
): void {
  expect(response.symbol).toBe(primary)
  expect(response.benchmark).toBe(benchmark)
  expect(response.timeframe).toBe('D1')
  expect(response.adjustment).toBe('raw')
  expect(response.warnings.filter(warning => warning.code === 'stale_data')).toEqual([])

  const primaryByTime = new Map(primaryBars.map(bar => [Date.parse(bar.ts), bar.close]))
  const benchmarkByTime = new Map(benchmarkBars.map(bar => [Date.parse(bar.ts), bar.close]))
  const expected = [...primaryByTime.keys()]
    .filter(timestamp => benchmarkByTime.has(timestamp))
    .sort((left, right) => left - right)
    .map(timestamp => ({ timestamp, value: primaryByTime.get(timestamp)! / benchmarkByTime.get(timestamp)! }))

  expect(response.points.length, `${primary}/${benchmark} must contain every raw timestamp intersection`).toBe(expected.length)
  expect(response.coverage).toBeGreaterThan(0)
  response.points.forEach((point, index) => {
    expect(Date.parse(point.timestamp)).toBe(expected[index].timestamp)
    expect(Number.isFinite(point.value)).toBe(true)
    expect(Math.abs(point.value - expected[index].value), `${primary}/${benchmark} at ${point.timestamp}`).toBeLessThan(1e-10)
  })
}

async function assertChartRendered(page: Page, symbol: string, bars: Bar[]): Promise<void> {
  assertActualBars(symbol, bars)
  const chart = page.locator('.tool-window[data-window-key="primary-chart"]')
  await expect(chart.locator('.tool-window__symbol')).toHaveText(symbol)
  const plot = chart.locator('.chart-root')
  await expect(plot).toBeVisible()
  const renderer = plot.locator('.uplot-wrapper .uplot')
  await expect(renderer).toBeVisible()
  const canvases = renderer.locator('canvas')
  await expect(canvases.first()).toBeVisible()
  const paints = await canvases.evaluateAll((elements: HTMLCanvasElement[]) => elements.map(element => {
    const context = element.getContext('2d', { willReadFrequently: true })
    if (!context) return { width: element.width, height: element.height, painted: 0, colors: 0 }
    const image = context.getImageData(0, 0, element.width, element.height).data
    const colors = new Set<string>()
    let painted = 0
    for (let offset = 0; offset < image.length; offset += 4) {
      const red = image[offset], green = image[offset + 1], blue = image[offset + 2], alpha = image[offset + 3]
      if (alpha > 0 && (red > 24 || green > 24 || blue > 24)) painted += 1
      if (alpha > 0 && colors.size < 64) colors.add(`${red},${green},${blue}`)
    }
    return { width: element.width, height: element.height, painted, colors: colors.size }
  }))
  const rendererPaint = paints.find(paint => paint.width > 120 && paint.height > 90 && paint.painted > 100 && paint.colors > 8)
  expect(rendererPaint, `${symbol} price renderer must paint actual chart data, not only the drawing overlay`).toBeTruthy()

  // The ordinary pointer tooltip is sourced from the rendered OHLCV series.
  // Match its date and close to the actual bars returned by this page request.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const root = plot.locator('.chart-root')
    if (await root.getAttribute('data-date-pointer-mode') === 'on_with_values') break
    await root.focus()
    await root.press('.')
  }
  const root = plot.locator('.chart-root')
  await expect(root).toHaveAttribute('data-date-pointer-mode', 'on_with_values')
  const rendererBox = await renderer.boundingBox()
  expect(rendererBox, `${symbol} price renderer has a pointer target`).toBeTruthy()
  const tooltip = chart.locator('.ohlcv-info')
  const priorTooltip = await tooltip.getAttribute('aria-label')
  await page.mouse.move(rendererBox!.x + rendererBox!.width * 0.58, rendererBox!.y + rendererBox!.height * 0.46)
  await expect(tooltip).toBeVisible()
  await expect.poll(async () => (await tooltip.getAttribute('aria-label')) !== priorTooltip).toBe(true)
  const ariaLabel = (await tooltip.getAttribute('aria-label')) ?? ''
  const date = ariaLabel.split('.')[0]
  const close = ariaLabel.match(/close ([0-9]+(?:\.[0-9]+)?)/i)?.[1]
  expect(close, `${symbol} rendered tooltip exposes an OHLC close`).toBeTruthy()
  const matchingBar = bars.find(bar => {
    const timestamp = new Date(bar.ts)
    const localDate = `${timestamp.getFullYear()}-${String(timestamp.getMonth() + 1).padStart(2, '0')}-${String(timestamp.getDate()).padStart(2, '0')}`
    return localDate === date && bar.close.toFixed(4) === close
  })
  expect(matchingBar, `${symbol} pointer OHLC/date must match one returned chart bar`).toBeTruthy()
}

function assertRotationPayload(payload: RotationResponse, timeframe: AnalysisTimeframe): void {
  expect(payload.group_key).toBe('sp500-sectors')
  expect(payload.benchmark).toBe('SPY')
  expect(payload.timeframe).toBe(timeframe)
  expect(payload.adjustment).toBe('split_adjusted')
  expect(payload.coverage_preflight.status).toBe('full')
  expect(payload.rows.map(row => row.symbol).sort()).toEqual([...SECTOR_SYMBOLS].sort())
  for (const row of payload.rows) {
    expect(row.state, `${timeframe} ${row.symbol} has a computed quadrant`).toMatch(/^(leading|weakening|improving|lagging)$/)
    expect(Number.isFinite(row.trend), `${timeframe} ${row.symbol} trend is finite`).toBe(true)
    expect(Number.isFinite(row.momentum), `${timeframe} ${row.symbol} momentum is finite`).toBe(true)
    expect(row.coverage, `${timeframe} ${row.symbol} has coverage`).toBeGreaterThan(0)
    expect(row.tail.length, `${timeframe} ${row.symbol} has its configured RRG tail`).toBeGreaterThanOrEqual(10)
    for (const point of row.tail) {
      expect(Number.isFinite(Date.parse(point.timestamp))).toBe(true)
      expect(Number.isFinite(point.trend) && Number.isFinite(point.momentum)).toBe(true)
    }
    for (let index = 1; index < row.tail.length; index += 1) {
      expect(Date.parse(row.tail[index - 1].timestamp)).toBeLessThan(Date.parse(row.tail[index].timestamp))
    }
  }
}

async function assertRotationPainted(page: Page, payload: RotationResponse): Promise<{ width: number; height: number }> {
  const plot = page.getByRole('group', { name: 'Relative rotation trend and momentum plane' })
  await expect(plot).toBeVisible()
  const canvas = plot.locator('canvas').first()
  await expect(canvas).toBeVisible()
  const paint = await canvas.evaluate((element: HTMLCanvasElement, expectedRows: RotationRow[]) => {
    const context = element.getContext('2d', { willReadFrequently: true })
    if (!context) return { width: element.width, height: element.height, painted: 0, markers: [], tails: [] }
    const image = context.getImageData(0, 0, element.width, element.height).data
    const stateColors: Record<string, [number, number, number]> = {
      leading: [97, 197, 140], weakening: [231, 190, 104], improving: [109, 187, 230], lagging: [223, 129, 129],
    }
    let painted = 0
    for (let offset = 0; offset < image.length; offset += 4) {
      const red = image[offset], green = image[offset + 1], blue = image[offset + 2], alpha = image[offset + 3]
      if (alpha > 0 && (red < 65 || green < 65 || blue < 65)) painted += 1
    }
    const audit = (window as any).__rrgCanvasAudit as {
      markers: Array<{ x: number; y: number; radius: number; color: string }>
      tails: Array<{ color: string; alpha: number; points: Array<{ x: number; y: number }> }>
    }
    const bounds = element.getBoundingClientRect()
    const pixelRatio = element.width / bounds.width
    const latestMarkers = audit.markers
      .filter(marker => marker.radius >= 3.4 * pixelRatio)
      .slice(-expectedRows.length)
    const tailPaths = audit.tails.slice(-expectedRows.length)
    const exactMarkerPixel = (x: number, y: number, color: [number, number, number]) => {
      for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
        const px = Math.round(x) + dx, py = Math.round(y) + dy
        if (px < 0 || py < 0 || px >= element.width || py >= element.height) continue
        const offset = (py * element.width + px) * 4
        if (image[offset] === color[0] && image[offset + 1] === color[1] && image[offset + 2] === color[2] && image[offset + 3] > 245) return true
      }
      return false
    }
    const tailRasterHits = (path: Array<{ x: number; y: number }>, color: [number, number, number]) => {
      let hits = 0
      for (let index = 1; index < path.length; index += 1) {
        const x = Math.round((path[index - 1].x + path[index].x) / 2)
        const y = Math.round((path[index - 1].y + path[index].y) / 2)
        let found = false
        for (let dy = -1; dy <= 1 && !found; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
          const px = x + dx, py = y + dy
          if (px < 0 || py < 0 || px >= element.width || py >= element.height) continue
          const offset = (py * element.width + px) * 4
          const distance = Math.hypot(image[offset] - color[0], image[offset + 1] - color[1], image[offset + 2] - color[2])
          if (image[offset + 3] > 100 && distance < 88) { found = true; break }
        }
        if (found) hits += 1
      }
      return hits
    }
    return {
      width: element.width,
      height: element.height,
      painted,
      markers: latestMarkers.map((marker, index) => ({
        ...marker,
        rasterHit: exactMarkerPixel(marker.x, marker.y, stateColors[expectedRows[index]?.state ?? '']),
      })),
      tails: tailPaths.map((path, index) => ({
        ...path,
        expectedColor: Object.entries(stateColors).find(([, color]) => `#${color.map(value => value.toString(16).padStart(2, '0')).join('')}` === path.color)?.[0],
        requiredState: expectedRows[index]?.state,
        rasterHits: tailRasterHits(path.points, stateColors[expectedRows[index]?.state ?? '']),
      })),
    }
  }, payload.rows)
  expect(paint.width).toBeGreaterThan(250)
  expect(paint.height).toBeGreaterThan(140)
  expect(paint.painted, 'RRG canvas must contain painted axes, quadrants and actual plotted data').toBeGreaterThan(150)
  expect(paint.markers, 'each returned sector has an audited latest point marker').toHaveLength(payload.rows.length)
  expect(paint.tails, 'each returned sector has an audited tail stroke').toHaveLength(payload.rows.length)
  for (let index = 0; index < payload.rows.length; index += 1) {
    const row = payload.rows[index]
    expect(row.history, `${row.symbol} uses the returned tail, not a history substitute`).toHaveLength(0)
    const marker = paint.markers[index]
    const tail = paint.tails[index]
    const expectedColor = ROTATION_STATE_COLORS[row.state!]
    expect(marker.color.toLowerCase(), `${row.symbol} marker matches its computed quadrant`).toBe(expectedColor)
    expect(marker.rasterHit, `${row.symbol} marker has opaque state-colored pixels at its audited center`).toBe(true)
    expect(tail.color.toLowerCase(), `${row.symbol} tail uses its computed quadrant color`).toBe(expectedColor)
    expect(tail.alpha).toBeCloseTo(0.72, 2)
    expect(tail.points.length, `${row.symbol} tail path contains every configured point`).toBeGreaterThanOrEqual(10)
    expect(tail.rasterHits, `${row.symbol} state-colored tail has raster pixels along its audited path`).toBeGreaterThanOrEqual(5)
  }

  const rowsRegion = page.getByRole('region', { name: 'Relative rotation rows' })
  for (const row of payload.rows) {
    const rowButton = rowsRegion.getByRole('button', { name: new RegExp(`^${row.symbol},`) })
    await expect(rowButton).toBeVisible()
    await expect(rowButton).toContainText(row.state!)
    await expect(rowButton).toHaveAttribute('aria-label', expect.stringContaining('trend'))
    await expect(rowButton).toHaveAttribute('aria-label', expect.stringContaining('momentum'))
    await expect(rowButton).toHaveAttribute('aria-label', expect.stringContaining('coverage'))
  }
  return { width: paint.width, height: paint.height }
}

async function installRotationCanvasAudit(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const selector = '[role="group"][aria-label="Relative rotation trend and momentum plane"]'
    const colors = new Set(['#61c58c', '#e7be68', '#6dbbe6', '#df8181'])
    const audit = { markers: [] as Array<{ x: number; y: number; radius: number; color: string }>, tails: [] as Array<{ color: string; alpha: number; points: Array<{ x: number; y: number }> }> }
    ;(window as any).__rrgCanvasAudit = audit
    const paths = new WeakMap<CanvasRenderingContext2D, Array<{ x: number; y: number }>>()
    const isRotationCanvas = (context: CanvasRenderingContext2D) => Boolean(context.canvas.closest(selector))
    const prototype = CanvasRenderingContext2D.prototype
    const originalArc = prototype.arc
    prototype.arc = function (x, y, radius, startAngle, endAngle, counterclockwise) {
      const color = String(this.fillStyle).toLowerCase()
      if (isRotationCanvas(this) && colors.has(color)) audit.markers.push({ x, y, radius, color })
      return originalArc.call(this, x, y, radius, startAngle, endAngle, counterclockwise)
    }
    const originalBeginPath = prototype.beginPath
    prototype.beginPath = function () {
      if (isRotationCanvas(this)) paths.set(this, [])
      return originalBeginPath.call(this)
    }
    const originalMoveTo = prototype.moveTo
    prototype.moveTo = function (x, y) {
      if (isRotationCanvas(this)) paths.get(this)?.push({ x, y })
      return originalMoveTo.call(this, x, y)
    }
    const originalLineTo = prototype.lineTo
    prototype.lineTo = function (x, y) {
      if (isRotationCanvas(this)) paths.get(this)?.push({ x, y })
      return originalLineTo.call(this, x, y)
    }
    const originalStroke = prototype.stroke
    prototype.stroke = function (path?: Path2D) {
      const color = String(this.strokeStyle).toLowerCase()
      const points = paths.get(this) ?? []
      if (isRotationCanvas(this) && colors.has(color) && this.globalAlpha < 1 && points.length >= 10) {
        audit.tails.push({ color, alpha: this.globalAlpha, points: [...points] })
      }
      return originalStroke.call(this, path)
    }
  })
}

async function clearRotationCanvasAudit(page: Page): Promise<void> {
  await page.evaluate(() => {
    const audit = (window as any).__rrgCanvasAudit
    if (audit) { audit.markers.length = 0; audit.tails.length = 0 }
  })
}

async function latestRotationMarker(page: Page, payload: RotationResponse, symbol: string): Promise<{ x: number; y: number; left: number; top: number }> {
  const rowIndex = payload.rows.findIndex(row => row.symbol === symbol)
  expect(rowIndex, `${symbol} exists in the active RRG payload`).toBeGreaterThanOrEqual(0)
  return page.evaluate((index: number) => {
    const selector = '[role="group"][aria-label="Relative rotation trend and momentum plane"]'
    const canvas = document.querySelector(`${selector} canvas`) as HTMLCanvasElement | null
    const audit = (window as any).__rrgCanvasAudit as { markers: Array<{ x: number; y: number; radius: number }> }
    if (!canvas) throw new Error('RRG plot canvas is missing')
    const bounds = canvas.getBoundingClientRect()
    const pixelRatio = canvas.width / bounds.width
    const latest = audit.markers.filter(marker => marker.radius >= 3.4 * pixelRatio)
    const marker = latest[index]
    if (!marker) throw new Error(`RRG latest marker ${index} is missing`)
    return {
      x: marker.x * bounds.width / canvas.width,
      y: marker.y * bounds.height / canvas.height,
      left: bounds.left,
      top: bounds.top,
    }
  }, rowIndex)
}

async function assertRatioUiLine(page: Page, numerator: string, denominator: string, response: RatioResponse): Promise<void> {
  expect(response.symbol).toBe(numerator)
  expect(response.benchmark).toBe(denominator)
  expect(response.timeframe).toBe('D1')
  expect(response.adjustment).toBe('split_adjusted')
  expect(response.points.length, `${numerator}/${denominator} UI request has actual aligned points`).toBeGreaterThanOrEqual(20)
  expect(response.points.every(point => Number.isFinite(Date.parse(point.timestamp)) && Number.isFinite(point.value))).toBe(true)
  const ratio = page.locator('.tool-window[data-window-key="ratio-chart"] .ratio-chart')
  await expect(ratio).toBeVisible()
  await expect(ratio.locator('.ratio-chart__legend strong')).toContainText(`${numerator}/${denominator}`)
  await expect(ratio.locator('.ratio-chart__legend [role="status"]')).toContainText('local adjusted')
  const benchmarkNames = await ratio.locator('.ratio-chart__chip').evaluateAll(elements => elements.map(element => element.getAttribute('aria-label')?.replace('Remove ratio comparison ', '') ?? ''))
  const colorIndex = benchmarkNames.indexOf(denominator)
  expect(colorIndex, `${numerator}/${denominator} is an actual visible comparison leg`).toBeGreaterThanOrEqual(0)
  const expectedColor = RATIO_SERIES_COLORS[colorIndex % RATIO_SERIES_COLORS.length]
  const expectedRgb = expectedColor.slice(1).match(/.{2}/g)!.map(channel => Number.parseInt(channel, 16))
  const canvases = ratio.locator('.ratio-chart__host .uplot canvas')
  await expect(canvases.first()).toBeVisible()
  await expect.poll(async () => canvases.evaluateAll((elements: HTMLCanvasElement[], color: number[]) => elements.reduce((total, element) => {
    const context = element.getContext('2d', { willReadFrequently: true })
    if (!context) return total
    const pixels = context.getImageData(0, 0, element.width, element.height).data
    let matches = 0
    for (let offset = 0; offset < pixels.length; offset += 4) {
      if (pixels[offset + 3] > 0 && Math.hypot(pixels[offset] - color[0], pixels[offset + 1] - color[1], pixels[offset + 2] - color[2]) < 32) matches += 1
    }
    return total + matches
  }, 0), expectedRgb)).toBeGreaterThan(8)
}

test('SPY and all eleven sector charts use real bars, and both sector/SPY ratios match raw aligned closes', async ({ page, request, loggedIn }) => {
  void loggedIn
  test.setTimeout(180_000)
  const token = await bearerToken(page)
  const group = await getJson<{ stable_key: string; members: Array<{ instrument: { symbol: string } }> }>(
    request, token, '/api/v1/market-groups/sp500-sectors',
  )
  expect(group.stable_key).toBe('sp500-sectors')
  const groupSymbols = group.members.map(member => member.instrument.symbol).sort()
  expect(groupSymbols).toEqual([...SECTOR_SYMBOLS].sort())

  const ratioResponses = new Map<string, RatioResponse>()
  for (const symbol of SECTOR_SYMBOLS) {
    for (const [primary, benchmark] of [[symbol, 'SPY'], ['SPY', symbol]] as const) {
      const response = await getJson<RatioResponse>(request, token, '/api/v1/analysis/relative-strength', {
        symbol: primary,
        benchmark,
        timeframe: 'D1',
        adjusted: false,
      })
      ratioResponses.set(`${primary}/${benchmark}`, response)
    }
  }

  const ratioTimestamps = [...ratioResponses.values()].flatMap(response => response.points.map(point => Date.parse(point.timestamp)))
  expect(ratioTimestamps.length, 'the actual ratio APIs must return aligned raw points').toBeGreaterThan(0)
  const start = new Date(Math.min(...ratioTimestamps)).toISOString()
  const end = new Date(Math.max(...ratioTimestamps)).toISOString()
  const rawBarsBySymbol = new Map<string, Bar[]>()
  await Promise.all(SP500_SYMBOLS.map(async symbol => {
    // The default chart endpoint is capped at its latest 500 bars. A bounded
    // explicit range keeps this independent arithmetic aligned with the full
    // timestamp span returned by the analysis API.
    const bars = await getJson<Bar[]>(request, token, `/api/v1/ohlcv/${symbol}/D1`, {
      start,
      end,
      adjusted: false,
      local_only: true,
    })
    assertActualBars(symbol, bars, 20)
    expect(bars.every(bar => bar.is_adjusted === false), `${symbol} response is raw`).toBe(true)
    rawBarsBySymbol.set(symbol, bars)
  }))

  for (const symbol of SECTOR_SYMBOLS) {
    for (const [primary, benchmark] of [[symbol, 'SPY'], ['SPY', symbol]] as const) {
      assertRatioMatchesRawIntersection(
        primary,
        benchmark,
        rawBarsBySymbol.get(primary)!,
        rawBarsBySymbol.get(benchmark)!,
        ratioResponses.get(`${primary}/${benchmark}`)!,
      )
    }
  }

  const spyChartResponse = page.waitForResponse(response => response.ok() && barResponseFor(response, 'SPY', 'D1'))
  await page.reload()
  await assertChartRendered(page, 'SPY', await spyChartResponse.then(response => response.json() as Promise<Bar[]>))

  const ratioTool = page.locator('.tool-window[data-window-key="ratio-chart"] .ratio-chart')
  const sectorList = page.locator('.tool-window[data-window-key="sector-list"]')
    .getByRole('listbox', { name: 'Relative to SPY symbols' })
  for (let index = 0; index < SECTOR_SYMBOLS.length; index += 1) {
    const symbol = SECTOR_SYMBOLS[index]
    await sectorList.evaluate((element: HTMLElement, rowIndex) => {
      element.scrollTop = Math.max(0, rowIndex * 28 - element.clientHeight / 2)
      element.dispatchEvent(new Event('scroll'))
    }, index)
    const option = sectorList.getByRole('option', { name: new RegExp(`^${symbol}\\b`) })
    await expect(option).toBeVisible()
    const chartResponse = page.waitForResponse(response => response.ok() && barResponseFor(response, symbol, 'D1'))
    const uiRatioResponse = page.waitForResponse(response => response.ok() && relativeStrengthResponseFor(response, symbol, 'SPY'))
    await option.click()
    await assertChartRendered(page, symbol, await chartResponse.then(response => response.json() as Promise<Bar[]>))
    await assertRatioUiLine(page, symbol, 'SPY', await uiRatioResponse.then(response => response.json() as Promise<RatioResponse>))
    await expect(ratioTool.locator('.ratio-chart__legend strong')).toContainText(`${symbol}/SPY`)
  }

  // The active-symbol control chooses the numerator; RatioUPlot's public
  // Compare control adds each inverse SPY/sector leg to the visible chart.
  const activeSymbol = page.getByRole('combobox', { name: 'Active symbol' })
  await activeSymbol.fill('SPY')
  const activeSpyBars = page.waitForResponse(response => response.ok() && barResponseFor(response, 'SPY', 'D1'))
  await page.getByRole('button', { name: 'Go' }).click()
  await assertChartRendered(page, 'SPY', await activeSpyBars.then(response => response.json() as Promise<Bar[]>))
  for (const symbol of SECTOR_SYMBOLS) {
    const compare = ratioTool.getByRole('textbox', { name: 'Ratio comparison symbol' })
    await compare.fill(symbol)
    const uiRatioResponse = page.waitForResponse(response => response.ok() && relativeStrengthResponseFor(response, 'SPY', symbol))
    await ratioTool.getByRole('button', { name: 'Add ratio comparison' }).click()
    await assertRatioUiLine(page, 'SPY', symbol, await uiRatioResponse.then(response => response.json() as Promise<RatioResponse>))
  }
})

test('S&P 500 RRG renders deep D1/W1/MN data and survives selection, resize, maximize, layout copy, and tab restore', async ({ page, request, loggedIn }) => {
  void loggedIn
  test.setTimeout(240_000)
  await installRotationCanvasAudit(page)
  const token = await bearerToken(page)
  const monthlyBars = await Promise.all(SP500_SYMBOLS.map(symbol => getJson<Bar[]>(
    request, token, `/api/v1/ohlcv/${symbol}/MN`, { adjusted: true, local_only: true, limit: 120 },
  )))
  monthlyBars.forEach((bars, index) => assertActualBars(SP500_SYMBOLS[index], bars, 60))

  const rrgWindow = page.locator('.tool-window[data-window-key="relative-rotation"]')
  const rotation = page.getByRole('region', { name: 'Relative rotation vs SPY' })
  await expect(rotation).toBeVisible()
  await expect(rrgWindow.getByRole('button', { name: 'Maximize tool' })).toBeVisible()
  await rrgWindow.getByRole('button', { name: 'Maximize tool' }).click()
  await expect(rrgWindow.getByRole('button', { name: 'Restore tool' })).toBeVisible()

  const timeframeControl = rotation.getByLabel('Rotation timeframe')
  const pageResponses = new Map<AnalysisTimeframe, RotationResponse>()
  const directResponses = new Map<AnalysisTimeframe, RotationResponse>()

  const initialD1Response = page.waitForResponse(response => response.ok() && rotationResponseFor(response, 'D1'))
  await page.reload()
  const reloadedD1 = await initialD1Response
  const d1Payload = await reloadedD1.json() as RotationResponse
  pageResponses.set('D1', d1Payload)
  await expect(page.getByRole('region', { name: 'Relative rotation vs SPY' })).toBeVisible()

  for (const timeframe of TIMEFRAMES) {
    directResponses.set(timeframe, await getJson<RotationResponse>(
      request,
      token,
      '/api/v1/analysis/groups/sp500-sectors/relative-rotation',
      { timeframe, adjusted: true, sampling: 1, lookback: 20, tail_length: 10, history_length: 0 },
    ))
    assertRotationPayload(directResponses.get(timeframe)!, timeframe)
  }

  // Validate D1 while it is still the active UI selection, before changing the
  // visible control to W1 and MN.
  assertRotationPayload(d1Payload, 'D1')
  await expect(timeframeControl).toHaveValue('D1')
  expect(d1Payload.rows.map(row => row.symbol).sort())
    .toEqual(directResponses.get('D1')!.rows.map(row => row.symbol).sort())
  for (const row of directResponses.get('D1')!.rows) {
    const uiRow = d1Payload.rows.find(candidate => candidate.symbol === row.symbol)!
    expect(uiRow.trend).toBeCloseTo(row.trend!, 10)
    expect(uiRow.momentum).toBeCloseTo(row.momentum!, 10)
    expect(uiRow.tail.length).toBe(row.tail.length)
  }
  await assertRotationPainted(page, d1Payload)

  for (const timeframe of ['W1', 'MN'] as const) {
    await clearRotationCanvasAudit(page)
    const pageResponse = page.waitForResponse(response => response.ok() && rotationResponseFor(response, timeframe))
    await page.getByRole('region', { name: 'Relative rotation vs SPY' })
      .getByLabel('Rotation timeframe').selectOption(timeframe)
    const actualPagePayload = await pageResponse.then(response => response.json() as Promise<RotationResponse>)
    pageResponses.set(timeframe, actualPagePayload)
    assertRotationPayload(actualPagePayload, timeframe)
    await expect(timeframeControl).toHaveValue(timeframe)
    expect(actualPagePayload.rows.map(row => row.symbol).sort())
      .toEqual(directResponses.get(timeframe)!.rows.map(row => row.symbol).sort())
    for (const row of directResponses.get(timeframe)!.rows) {
      const uiRow = actualPagePayload.rows.find(candidate => candidate.symbol === row.symbol)!
      expect(uiRow.trend).toBeCloseTo(row.trend!, 10)
      expect(uiRow.momentum).toBeCloseTo(row.momentum!, 10)
      expect(uiRow.tail.length).toBe(row.tail.length)
    }
    await assertRotationPainted(page, actualPagePayload)
  }

  const finalPayload = pageResponses.get('MN')!
  const firstSector = finalPayload.rows[0].symbol
  const lastSector = finalPayload.rows[finalPayload.rows.length - 1].symbol
  expect(firstSector).not.toBe(lastSector)

  // A pointer hit on the actual plotted latest marker exposes that server
  // point's timestamp/values and selects it in the linked chart.
  const chartSymbol = page.locator('.tool-window[data-window-key="primary-chart"] .tool-window__symbol')
  const pointerRow = finalPayload.rows[0]
  const pointerPoint = pointerRow.tail[pointerRow.tail.length - 1]
  const marker = await latestRotationMarker(page, finalPayload, pointerRow.symbol)
  await page.mouse.move(marker.left + marker.x, marker.top + marker.y)
  const plotTooltip = page.locator('.rotation-tool__tooltip')
  await expect(plotTooltip).toContainText(pointerRow.symbol)
  await expect(plotTooltip).toContainText(pointerPoint.timestamp)
  await expect(plotTooltip).toContainText(`Trend ${rotationPercent(pointerPoint.trend)}`)
  await expect(plotTooltip).toContainText(`Momentum ${rotationPercent(pointerPoint.momentum)}`)
  const pointerChartResponse = page.waitForResponse(response => response.ok() && barResponseFor(response, pointerRow.symbol, 'D1'))
  await page.mouse.click(marker.left + marker.x, marker.top + marker.y)
  await assertChartRendered(page, pointerRow.symbol, await pointerChartResponse.then(response => response.json() as Promise<Bar[]>))
  await expect(chartSymbol).toHaveText(pointerRow.symbol)

  // Table selection remains a separate ordinary path and also links the chart.
  const tableSector = finalPayload.rows[1].symbol
  const tableChartResponse = page.waitForResponse(response => response.ok() && barResponseFor(response, tableSector, 'D1'))
  await page.getByRole('region', { name: 'Relative rotation rows' })
    .getByRole('button', { name: new RegExp(`^${tableSector},`) }).click()
  await assertChartRendered(page, tableSector, await tableChartResponse.then(response => response.json() as Promise<Bar[]>))
  await expect(chartSymbol).toHaveText(tableSector)

  // Keyboard selection uses the plot's public arrow/Home/End/Enter controls and also links the chart.
  const plot = page.getByRole('group', { name: 'Relative rotation trend and momentum plane' })
  await plot.focus()
  await plot.press('End')
  await expect(page.locator('.rotation-tool__tooltip')).toContainText(lastSector)
  const lastChartResponse = page.waitForResponse(response => response.ok() && barResponseFor(response, lastSector, 'D1'))
  await plot.press('Enter')
  await assertChartRendered(page, lastSector, await lastChartResponse.then(response => response.json() as Promise<Bar[]>))
  await expect(chartSymbol).toHaveText(lastSector)

  // Resize the browser viewport; the plotted canvas must be redrawn at positive geometry.
  const beforeResize = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }))
  const canvasBeforeResize = await plot.locator('canvas').first().evaluate((canvas: HTMLCanvasElement) => canvas.width)
  await page.setViewportSize({ width: beforeResize.width + 180, height: beforeResize.height + 100 })
  await expect.poll(async () => plot.locator('canvas').first().evaluate((canvas: HTMLCanvasElement) => canvas.width))
    .not.toBe(canvasBeforeResize)
  await assertRotationPainted(page, finalPayload)

  // Restore from maximized state without replacing the live analysis context.
  const activeRrgWindow = page.locator('.tool-window[data-window-key="relative-rotation"]')
  if (await activeRrgWindow.getByRole('button', { name: 'Maximize tool' }).count()) {
    await activeRrgWindow.getByRole('button', { name: 'Maximize tool' }).click()
  }
  await expect(activeRrgWindow.getByRole('button', { name: 'Restore tool' })).toBeVisible()
  await activeRrgWindow.getByRole('button', { name: 'Restore tool' }).click()
  await expect(activeRrgWindow.getByRole('button', { name: 'Maximize tool' })).toBeVisible()
  await assertRotationPainted(page, finalPayload)

  // Copy the active layout, switch tabs in both directions, and retain the actual RRG.
  const tabs = page.getByRole('tablist', { name: 'Workspace layouts' }).getByRole('tab')
  await page.getByRole('button', { name: 'Clone active layout' }).click()
  await expect(tabs).toHaveCount(2)
  await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true')
  let copiedRotation = page.getByRole('region', { name: 'Relative rotation vs SPY' })
  await expect(copiedRotation).toBeVisible()
  await expect(copiedRotation.getByLabel('Rotation timeframe')).toHaveValue('MN')
  await assertRotationPainted(page, finalPayload)

  await tabs.nth(0).click()
  await expect(tabs.nth(0)).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('region', { name: 'Relative rotation vs SPY' })).toBeVisible()
  await assertRotationPainted(page, finalPayload)

  await tabs.nth(1).click()
  copiedRotation = page.getByRole('region', { name: 'Relative rotation vs SPY' })
  await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true')
  await expect(copiedRotation.getByLabel('Rotation timeframe')).toHaveValue('MN')
  await assertRotationPainted(page, finalPayload)
})
