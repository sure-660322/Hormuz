import * as L from 'leaflet'
import type { ApiEvent } from '../../api'
import { eventKind, eventLocationLabel, eventPriority, type LocatedEvent } from '../../domain/maritime'
import type { LayerState } from '../../domain/maritime'

// 事件渲染上下文：由 MapView 在每次渲染时从最新 props 构造。
// 事件数据本身不随回放帧变化（回放只做时间门控的显隐），
// 因此 Marker 一次创建、长期复用，普通帧只做 addLayer/removeLayer。
export interface EventRenderContext {
  events: LocatedEvent[]
  selectedEvent: ApiEvent | null
  layers: LayerState
  isolated: boolean
  picking: boolean
}

interface EventEntry {
  marker: L.Marker
  /** 组内事件构成：同坐标事件随回放门控逐步出现时重建 Marker（弹窗列表闭包依赖组内容） */
  idsSignature: string
  /** 选中/弱化/紧急等可视状态：变化时只换 icon，不重建 Marker */
  visualSignature: string
}

interface EventLayerManagerOptions {
  eventLayer: L.LayerGroup
  getMap: () => L.Map | undefined
  onSelectEvent: (event: ApiEvent) => void
}

const safeText = (value: string) => {
  const el = document.createElement('span')
  el.textContent = value
  return el
}

// 事件图层：按“坐标组”维护稳定 Marker（同坐标事件共享一个 Marker）。
// 回放时间推进只会改变事件的显隐集合，已存在 Marker 不再重建，
// 杜绝普通回放帧 clearLayers + 全量重建。
export class EventLayerManager {
  private entries = new Map<string, EventEntry>()
  private lastCtx: EventRenderContext | null = null
  private options: EventLayerManagerOptions

  constructor(options: EventLayerManagerOptions) {
    this.options = options
  }

  update(ctx: EventRenderContext) {
    this.lastCtx = ctx
    const layerVisible = ctx.layers.events && !ctx.isolated
    const currentKeys = new Set<string>()

    // 只有同坐标（完全一致经纬度）的记录共享 Marker；附近坐标不得移动合并
    const groups = new Map<string, LocatedEvent[]>()
    for (const event of ctx.events) {
      const key = `${event.latitude},${event.longitude}`
      const group = groups.get(key) ?? []
      group.push(event)
      groups.set(key, group)
    }

    for (const [key, group] of groups) {
      currentKeys.add(key)
      this.updateGroup(key, group, layerVisible)
    }

    for (const [key, entry] of this.entries) {
      if (currentKeys.has(key)) continue
      this.options.eventLayer.removeLayer(entry.marker)
      this.entries.delete(key)
    }
  }

  private updateGroup(key: string, group: LocatedEvent[], layerVisible: boolean) {
    const { eventLayer } = this.options
    const ctx = this.lastCtx!
    const event = group.find((item) => item.id === ctx.selectedEvent?.id) ?? group[0]!
    const selected = ctx.selectedEvent?.id === event.id
    const idsSignature = `${group.length}:${group.map((item) => item.id).join(',')}`
    const visualSignature = `${event.id}|${selected}|${ctx.selectedEvent !== null && !selected}|${selected && eventPriority(event.event_type) !== 'normal'}`

    let entry = this.entries.get(key)
    if (entry && entry.idsSignature !== idsSignature) {
      // 组构成变化：弹窗列表闭包过期，整枚重建
      eventLayer.removeLayer(entry.marker)
      this.entries.delete(key)
      entry = undefined
    }

    if (!entry) {
      const marker = this.createMarker(key, group, layerVisible)
      entry = { marker, idsSignature, visualSignature: '' }
      this.entries.set(key, entry)
    }

    if (entry.visualSignature !== visualSignature) {
      entry.visualSignature = visualSignature
      this.applyIcon(entry, group, event, selected)
    }

    const zIndexOffset = selected ? 2000 : 300
    entry.marker.setZIndexOffset(zIndexOffset)
    if (layerVisible && !eventLayer.hasLayer(entry.marker)) entry.marker.addTo(eventLayer)
    else if (!layerVisible && eventLayer.hasLayer(entry.marker)) eventLayer.removeLayer(entry.marker)
  }

  private applyIcon(
    entry: EventEntry,
    group: LocatedEvent[],
    event: LocatedEvent,
    selected: boolean,
  ) {
    const ctx = this.lastCtx!
    const kind = eventKind(event.event_type)
    const locationLabel = eventLocationLabel(event)
    const markerTitle =
      group.length > 1
        ? `${group.length} 条同坐标事件（点击展开）`
        : `${kind.label} · ${locationLabel} · ${event.title}`
    entry.marker.setIcon(
      L.divIcon({
        className: `incident-marker${selected ? ' selected' : ''}${ctx.selectedEvent && !selected ? ' muted' : ''}${selected && eventPriority(event.event_type) !== 'normal' ? ' urgent' : ''}`,
        html: `<div class="incident-symbol" style="--risk:${kind.color}">${selected ? '<i class="incident-halo"></i><i class="selection-corners"></i>' : ''}<span class="incident-core"><img class="incident-icon" src="${kind.icon}" alt=""></span>${group.length > 1 ? `<b class="incident-count">${group.length}</b>` : ''}${selected ? `<span class="incident-label"><b>●</b> ${locationLabel} · 报道 ${event.publish_date_min ?? '日期未明'}</span>` : ''}</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      }),
    )
    entry.marker.setTooltipContent(
      safeText(`${markerTitle} · ${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}`),
    )
    entry.marker.options.title = markerTitle
    const element = entry.marker.getElement()
    if (element) {
      element.setAttribute('aria-label', markerTitle)
      element.dataset.eventIds = group.map((item) => item.event_id).join(',')
      element.dataset.latitude = String(event.latitude)
      element.dataset.longitude = String(event.longitude)
    }
  }

  private createMarker(key: string, group: LocatedEvent[], layerVisible: boolean) {
    const { eventLayer, getMap } = this.options
    const event = group[0]!
    const marker = L.marker([event.latitude, event.longitude], {
      bubblingMouseEvents: false,
    }).bindTooltip('')
    marker.on('click', () => {
      const ctx = this.lastCtx
      const map = getMap()
      if (!ctx || !map || ctx.picking) return
      const current = this.entries.get(key)
      if (!current) return
      const currentGroup = this.groupFor(key)
      if (!currentGroup.length) return
      const representative = currentGroup.find((item) => item.id === ctx.selectedEvent?.id) ?? currentGroup[0]!
      if (currentGroup.length === 1) {
        this.options.onSelectEvent(representative)
      } else {
        const list = document.createElement('div')
        list.className = 'cluster-list'
        for (const item of currentGroup) {
          const button = document.createElement('button')
          button.textContent = `${eventKind(item.event_type).label} · ${eventLocationLabel(item)} · ${item.title}`
          button.onclick = () => {
            map.closePopup()
            this.options.onSelectEvent(item)
          }
          list.append(button)
        }
        L.popup().setLatLng([representative.latitude, representative.longitude]).setContent(list).openOn(map)
      }
    })
    if (layerVisible) marker.addTo(eventLayer)
    return marker
  }

  private groupFor(key: string): LocatedEvent[] {
    const ctx = this.lastCtx
    if (!ctx) return []
    return ctx.events.filter(
      (event) => `${event.latitude},${event.longitude}` === key,
    )
  }

  clear() {
    for (const entry of this.entries.values())
      this.options.eventLayer.removeLayer(entry.marker)
    this.entries.clear()
    this.lastCtx = null
  }
}
