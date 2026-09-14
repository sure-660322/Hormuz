import * as L from 'leaflet'
import { countryLabelPosition, type CountryData } from '../domain/countryLabels'

const attribution = '<a href="https://www.naturalearthdata.com/">Natural Earth</a> · 概化国界'

const countryOrder = ['IRN', 'ISR', 'PSX', 'SYR', 'LBN', 'JOR', 'SAU', 'IRQ', 'OMN', 'ARE', 'KWT', 'QAT', 'BHR']
const isHighlighted = (code: string) => code === 'IRN' || code === 'ISR'
// Muted hues distinguish adjacent countries; orange remains the primary emphasis.
const countryColors: Record<string, string> = {
  IRN: '#E87848', ISR: '#E87848', LBN: '#B1AD78', JOR: '#72A69A', PSX: '#8F9DC5',
  SAU: '#B9A36D', IRQ: '#789CB9', SYR: '#A18FB5', OMN: '#6EA89B',
  ARE: '#BB8995', KWT: '#94AC79', QAT: '#AD91AE', BHR: '#7BAEBB',
}

export function createCountryLayer(map: L.Map, status: (value: string) => void) {
  for (const [name, z] of [['countryBoundaries', '250'], ['countryLabels', '350']] as const) {
    const pane = map.createPane(name)
    pane.style.zIndex = z
    pane.style.pointerEvents = 'none'
  }
  const renderer = L.svg({ pane: 'countryBoundaries' })
  const borders = L.geoJSON(undefined, {
    pane: 'countryBoundaries', interactive: false, bubblingMouseEvents: false,
    style: feature => ({
      renderer,
      color: countryColors[feature?.properties.code] ?? '#8C9BA7',
      weight: isHighlighted(feature?.properties.code) ? 2.2 : 1.5,
      opacity: isHighlighted(feature?.properties.code) ? .95 : .9,
      fillColor: countryColors[feature?.properties.code] ?? '#8C9BA7',
      fillOpacity: isHighlighted(feature?.properties.code) ? .3 : .26,
      className: isHighlighted(feature?.properties.code) ? 'country-border country-border-highlight' : 'country-border',
    }),
  })
  const labels = L.layerGroup()
  let data: CountryData | null = null, pending: Promise<void> | null = null
  let enabled = false, disposed = false
  const abort = new AbortController()

  function renderLabels() {
    labels.clearLayers()
    if (!enabled || !data || disposed) return
    const size = map.getSize(), zoom = map.getZoom()
    // Reserve a small inset so labels stay legible at the viewport edges.
    const sw = map.containerPointToLatLng([55, Math.max(55, size.y - 45)])
    const ne = map.containerPointToLatLng([Math.max(55, size.x - 55), 45])
    const occupied: { x: number; y: number; w: number }[] = []
    for (const code of countryOrder) {
      const feature = data.features.find(f => f.properties.code === code)!
      if (zoom < (['BHR', 'QAT', 'KWT'].includes(code) ? 5 : ['ARE', 'ISR', 'LBN', 'PSX'].includes(code) ? 4 : 3)) continue
      const position = countryLabelPosition(feature, { south: sw.lat, north: ne.lat, west: sw.lng, east: ne.lng })
      if (!position) continue
      const point = map.latLngToContainerPoint(position)
      const fontSize = zoom < 6 ? 14 : zoom > 12 ? 13 : 16
      const width = feature.properties.name_zh.length * (fontSize + (isHighlighted(code) ? 2 : 0)) + 16
      if (occupied.some(r => Math.abs(r.x - point.x) < (r.w + width) / 2 + 6 && Math.abs(r.y - point.y) < 28)) continue
      occupied.push({ x: point.x, y: point.y, w: width })
      const span = document.createElement('span')
      span.textContent = feature.properties.name_zh
      span.style.fontSize = `${fontSize + (isHighlighted(code) ? 2 : 0)}px`
      span.dataset.country = code
      L.marker(position, {
        pane: 'countryLabels', interactive: false, keyboard: false,
        icon: L.divIcon({ html: span, className: `country-name${isHighlighted(code) ? ' country-name-highlight' : ''}`,
          iconSize: [width, 26], iconAnchor: [width / 2, 13] }),
      }).addTo(labels)
    }
  }

  function show() {
    if (!enabled || !data || disposed) return
    borders.addTo(map); labels.addTo(map)
    map.attributionControl?.addAttribution(attribution)
    renderLabels()
  }

  async function setVisible(value: boolean) {
    if (enabled === value && (pending || data)) return
    enabled = value
    if (!value) {
      borders.remove(); labels.remove(); labels.clearLayers()
      map.attributionControl?.removeAttribution(attribution)
      return
    }
    if (data) { show(); return }
    if (pending) return pending
    status('正在加载中文国界…')
    pending = (async () => {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/gulf-countries.geojson`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15_000)]) })
        if (!response.ok) throw new Error('Country data unavailable')
        const loaded: CountryData = await response.json()
        if (loaded.type !== 'FeatureCollection' || loaded.features.length !== countryOrder.length || !countryOrder.every(code => loaded.features.some(f => f.properties.code === code)))
          throw new Error('Invalid country data')
        if (disposed) return
        data = loaded
        borders.addData(data)
        status(`${countryOrder.length}国 · 中文标注 · 概化边界`)
        show()
      } catch {
        if (!disposed) status('国界加载失败，关闭后重新开启可重试')
      } finally { pending = null }
    })()
    return pending
  }

  map.on('moveend zoomend resize', renderLabels)
  const refreshPrintLayout = () => { map.invalidateSize({ pan: false }); renderLabels() }
  window.addEventListener('beforeprint', refreshPrintLayout)
  window.addEventListener('afterprint', refreshPrintLayout)
  return {
    setVisible,
    destroy() {
      disposed = true; abort.abort()
      map.off('moveend zoomend resize', renderLabels)
      window.removeEventListener('beforeprint', refreshPrintLayout)
      window.removeEventListener('afterprint', refreshPrintLayout)
      borders.remove(); labels.remove()
      map.attributionControl?.removeAttribution(attribution)
    },
  }
}
