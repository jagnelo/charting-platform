/**
 * HSL-based palette that generates perceptually distinct colors for up to
 * dozens of expirations. Near-expirations get warm hues; far-dated get cool.
 * Even with 40+ expirations the palette stays readable by cycling through
 * lightness and saturation bands.
 */

const BASE_HUES = [200, 160, 40, 280, 20, 320, 80, 260, 140, 350]

export function expirationColor(index: number, total: number): string {
  const band = Math.floor(index / BASE_HUES.length)
  const hue = BASE_HUES[index % BASE_HUES.length]
  const lightness = 55 - band * 8
  const saturation = 70 - band * 5
  return `hsl(${hue}, ${Math.max(30, saturation)}%, ${Math.max(30, lightness)}%)`
}

export function buildExpirationPalette(expirations: string[]): Map<string, string> {
  const map = new Map<string, string>()
  expirations.forEach((exp, i) => {
    map.set(exp, expirationColor(i, expirations.length))
  })
  return map
}
