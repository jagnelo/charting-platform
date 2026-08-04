/**
 * Real-browser uPlot performance guard.
 *
 * This intentionally runs against the packaged uPlot distribution rather than
 * the Vitest mock. It is a renderer-level acceptance check for the workstation's
 * 100,000-point interaction contract; authenticated-stack flows remain covered
 * by flows.spec.ts.
 */
import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const uPlotSource = readFileSync(
  new URL('../../node_modules/uplot/dist/uPlot.iife.min.js', import.meta.url),
  'utf8',
)

test.describe('uPlot large-history interaction', () => {
  test('renders and repeatedly zooms/pans 100,000 points without replacing the chart', async ({ page }) => {
    await page.setContent(`
      <style>
        html, body { margin: 0; background: #10141c; }
        #host { width: 1200px; height: 520px; }
      </style>
      <div id="host"></div>
      <script>${uPlotSource}</script>
      <script>
        const count = 100000
        const timestamps = new Array(count)
        const values = new Array(count)
        const volume = new Array(count)
        const start = Date.UTC(2010, 0, 1) / 1000
        for (let i = 0; i < count; i += 1) {
          timestamps[i] = start + i * 86400
          values[i] = 100 + Math.sin(i / 90) * 8 + Math.log1p(i) * 0.08
          volume[i] = 1000000 + (i % 5000) * 37
        }
        window.__chart = new uPlot({
          width: 1200,
          height: 520,
          scales: { x: { time: true }, y: { auto: true } },
          series: [{}, { label: 'Value', stroke: '#55b7ff', width: 1 }, { label: 'Volume', stroke: '#6fd08c', width: 1 }],
          axes: [{}, { side: 1 }, { side: 1, show: false }],
        }, [timestamps, values, volume], document.getElementById('host'))
        window.__initialChartElement = document.querySelector('.uplot')
        const startTime = performance.now()
        const visibleSpan = 2000
        for (let cycle = 0; cycle < 40; cycle += 1) {
          const right = count - 1 - cycle * 250
          const left = Math.max(0, right - visibleSpan)
          window.__chart.setScale('x', {
            min: timestamps[left],
            max: timestamps[right],
          })
        }
        window.__interactionMs = performance.now() - startTime
      </script>
    `)

    await expect(page.locator('.uplot')).toHaveCount(1)
    const result = await page.evaluate(() => ({
      pointCount: (window.__chart?.data?.[0] ?? []).length,
      interactionMs: window.__interactionMs ?? Number.POSITIVE_INFINITY,
      chartPreserved: window.__initialChartElement === document.querySelector('.uplot'),
    }))

    expect(result.pointCount).toBe(100000)
    expect(result.chartPreserved).toBe(true)
    // Keep this deliberately generous for shared CI workers while still
    // catching accidental O(n)-per-gesture regressions in the renderer path.
    expect(result.interactionMs).toBeLessThan(2_500)
  })
})

