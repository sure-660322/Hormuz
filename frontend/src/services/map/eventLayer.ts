import * as L from 'leaflet'
import type { ApiEvent } from '../../api'
import { eventKind, eventLocationLabel, eventPriority, eventTimeText, type LocatedEvent } from '../../domain/maritime'
import type { LayerState } from '../../domain/maritime'

// 事件渲染上下文：由 MapView 在每次渲染时从最新 props 构造。
// 新闻代表点与模拟船位回放独立；筛选、图层开关等变化会更新显隐集合。
// Marker 按坐标组复用，未变化的组无需重建。
export interface EventRenderContext {
  events: LocatedEvent[]
  selectedEvent: ApiEvent | null
  layers: LayerState
  isolated: boolean
  picking: boolean
}

interface EventEntry {
  marker: L.Marker
  /** 组内事件构成：筛选改变同坐标事件集合时重建 Marker（弹窗列表闭包依赖组内容） */
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
// 船位回放时间推进不改变新闻集合；筛选和图层状态变化时增量更新，
// 避免对未变化的坐标组执行 clearLayers + 全量重建。
export class EventLayerManager {
  private entries = new Map<string, EventEntry>()
  private lastCtx: EventRenderContext | null = null
  private options: EventLayerManagerOptions
  // 当前地图缩放级别：图标按屏幕固定尺寸渲染，仅在极端缩放级别做少量微调
  private zoom = 8
  // 当前弹出信息卡所在的坐标组 key；null 表示无弹窗
  private openKey: string | null = null
  // 切换弹窗（openOn 会先关闭旧弹窗触发 popupclose）期间屏蔽 close 回调
  private switchingPopup = false

  constructor(options: EventLayerManagerOptions) {
    this.options = options
  }

  /** 地图缩放结束时由 MapView 调用；尺寸变化会触发 icon 重绘 */
  setZoom(zoom: number) {
    this.zoom = zoom
  }

  /** 地图弹窗被关闭（点击空白处 / 手动关闭）时由 MapView 调用 */
  onPopupClosed() {
    if (this.switchingPopup || this.openKey === null) return
    this.openKey = null
    this.refreshVisuals()
  }

  /** 打开新弹窗时置位：openOn 内部关闭旧弹窗触发的 popupclose 不应清掉新 key */
  private beginPopupSwitch() {
    this.switchingPopup = true
  }

  private endPopupSwitch(key: string) {
    this.switchingPopup = false
    this.openKey = key
    // 新弹窗对应的 Marker 需要立即套用选中高亮
    this.refreshVisuals()
    if (this.lastCtx) this.update(this.lastCtx)
  }

  // 事件图标屏幕尺寸：以 zoom 8 为基准 28px，随缩放最多 ±20% 微调，
  // 保证任何缩放级别下事件都易于发现和点击。
  private symbolSize(): number {
    const scale = Math.min(1.2, Math.max(0.8, 1 + (this.zoom - 8) * 0.04))
    return Math.round(28 * scale)
  }

  private refreshVisuals() {
    for (const entry of this.entries.values()) entry.visualSignature = ''
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
      // 组因筛选等条件消失时，若其信息卡仍开着则关闭
      if (this.openKey === key) {
        this.beginPopupSwitch()
        this.options.getMap()?.closePopup()
        this.switchingPopup = false
        this.openKey = null
      }
      this.options.eventLayer.removeLayer(entry.marker)
      this.entries.delete(key)
    }
  }

  private updateGroup(key: string, group: LocatedEvent[], layerVisible: boolean) {
    const { eventLayer } = this.options
    const ctx = this.lastCtx!
    const event = group.find((item) => item.id === ctx.selectedEvent?.id) ?? group[0]!
    const popupOpen = this.openKey === key
    const selected = ctx.selectedEvent?.id === event.id || popupOpen
    const idsSignature = `${group.length}:${group.map((item) => item.id).join(',')}`
    const visualSignature = `${event.id}|${selected}|${ctx.selectedEvent !== null && !selected}|${selected && eventPriority(event.event_type) !== 'normal'}|${this.symbolSize()}`

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
    const size = this.symbolSize()
    const core = size - 2
    const icon = Math.round(size * 0.72)
    entry.marker.setIcon(
      L.divIcon({
        className: `incident-marker${selected ? ' selected' : ''}${ctx.selectedEvent && !selected ? ' muted' : ''}${selected && eventPriority(event.event_type) !== 'normal' ? ' urgent' : ''}`,
        html: `<div class="incident-symbol" style="--risk:${kind.color};--symbol:${size}px;--core:${core}px;--icon:${icon}px">${selected ? '<i class="incident-halo"></i><i class="selection-corners"></i>' : ''}<span class="incident-core"><img class="incident-icon" src="${kind.icon}" alt=""></span>${group.length > 1 ? `<b class="incident-count">${group.length}</b>` : ''}${selected ? `<span class="incident-label"><b>●</b> ${locationLabel} · 报道 ${event.publish_date_min ?? '日期未明'}</span>` : ''}</div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
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
      const currentGroup = this.groupFor(key)
      if (!currentGroup.length) return
      const representative = currentGroup.find((item) => item.id === ctx.selectedEvent?.id) ?? currentGroup[0]!
      if (currentGroup.length === 1) {
        // 单击事件：在图标附近弹出轻量信息卡，不直接跳右侧侧边栏
        this.openCard(map, key, representative)
      } else {
        // 同坐标多事件：先给事件清单，点选某条后再打开该事件的信息卡
        const list = document.createElement('div')
        list.className = 'cluster-list'
        for (const item of currentGroup) {
          const button = document.createElement('button')
          button.textContent = `${eventKind(item.event_type).label} · ${eventLocationLabel(item)} · ${item.title}`
          button.onclick = () => {
            map.closePopup()
            this.openCard(map, key, item)
          }
          list.append(button)
        }
        this.beginPopupSwitch()
        L.popup({ maxWidth: 300 }).setLatLng([representative.latitude, representative.longitude]).setContent(list).openOn(map)
        this.endPopupSwitch(key)
      }
    })
    if (layerVisible) marker.addTo(eventLayer)
    return marker
  }

  // 在事件图标附近打开轻量信息卡：标题、时间、类型、摘要 + 「查看详情」入口。
  // 卡片内容来自新闻加工字段，一律 textContent 注入，不解析 HTML。
  private openCard(map: L.Map, key: string, event: LocatedEvent) {
    const kind = eventKind(event.event_type)
    const card = document.createElement('article')
    card.className = 'event-pop'

    const head = document.createElement('p')
    head.className = 'event-pop-kind'
    head.style.setProperty('--risk', kind.color)
    const icon = document.createElement('img')
    icon.src = kind.icon
    icon.alt = ''
    const kindText = document.createElement('span')
    kindText.textContent = kind.label
    head.append(icon, kindText)
    card.append(head)

    const title = document.createElement('h3')
    title.className = 'event-pop-title'
    title.textContent = event.title
    card.append(title)

    const meta = document.createElement('p')
    meta.className = 'event-pop-meta'
    meta.textContent = `${eventTimeText(event)} · ${eventLocationLabel(event)}`
    card.append(meta)

    const summaryText = (event.description ?? '').trim()
    if (summaryText) {
      const summary = document.createElement('p')
      summary.className = 'event-pop-summary'
      summary.textContent = summaryText.length > 150 ? `${summaryText.slice(0, 150)}…` : summaryText
      card.append(summary)
    }

    const actions = document.createElement('div')
    actions.className = 'event-pop-actions'
    const detail = document.createElement('button')
    detail.type = 'button'
    detail.className = 'primary'
    detail.textContent = '查看详情'
    detail.onclick = () => {
      // 关闭信息卡，再打开右侧侧边栏展示完整事件信息
      map.closePopup()
      this.options.onSelectEvent(event)
    }
    actions.append(detail)
    card.append(actions)

    this.beginPopupSwitch()
    L.popup({ maxWidth: 280, minWidth: 220, autoPan: true })
      .setLatLng([event.latitude, event.longitude])
      .setContent(card)
      .openOn(map)
    this.endPopupSwitch(key)
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
    this.openKey = null
    this.switchingPopup = false
  }
}
