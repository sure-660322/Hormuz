<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  fetchEvents,
  fetchShipPositions,
  fetchMapShips,
} from './api'

let map: L.Map | undefined
let selectedTrackLayer: L.Polyline | undefined
onMounted(() => {
  map = L.map('map').setView([26.5, 56.5], 8)

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map)

  L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution:
      'Seamark data &copy; <a href="https://www.openseamap.org">OpenSeaMap</a>',
  }).addTo(map)

    const shipIcon = L.divIcon({
    className: 'ship-marker',
    html: '▲',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })

  fetchMapShips()
    .then((ships) => {
      if(!map) return

      for(const ship of ships){
        const popupContent = `
        <strong>船名：</strong>${ship.name}<br>
        <strong>MMSI：</strong>${ship.mmsi}<br>
        <strong>类型：</strong>${ship.ship_type}<br>
        <strong>船旗：</strong>${ship.flag}<br>
        <strong>速度：</strong>${ship.speed} 节<br>
        <strong>航向：</strong>${ship.course}°<br>
        <strong>位置：</strong>${ship.latitude.toFixed(4)}, ${ship.longitude.toFixed(4)}<br>
        <strong>更新时间：</strong>${new Date(ship.recorded_at).toLocaleString('zh-CN')}
        `

      const marker = L.marker(
        [ship.latitude, ship.longitude],
        {
          icon: shipIcon,
        },
      )
        .bindPopup(popupContent)
        .addTo(map)

      marker.on('click', async () => {
        try {
          const trackPoints = await fetchShipPositions(ship.id)

          selectedTrackLayer?.remove()
          selectedTrackLayer = undefined

          if (trackPoints.length < 2 || !map) return

          const trackLatLngs = trackPoints.map(
            (point): L.LatLngTuple => [
              point.latitude,
              point.longitude,
            ],
          )

          selectedTrackLayer = L.polyline(trackLatLngs, {
            color: '#f59e0b',
            weight: 4,
            opacity: 0.9,
          }).addTo(map)

          map.fitBounds(selectedTrackLayer.getBounds(), {
            padding: [30, 30],
          })
        } catch (error) {
          console.error('船舶轨迹加载失败：', error)
        }
      })
      }
    })
    .catch((error) => {
      console.error(`地图船舶数据加载失败：`,error)
    })


    const eventIcon = L.divIcon({
    className: 'event-marker',
    html: '!',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })

  fetchEvents()
    .then((events) => {
      if (!map) return

      for (const maritimeEvent of events) {
        const popupContent = `
          <strong>${maritimeEvent.title}</strong><br>
          ${maritimeEvent.description}<br>
          <strong>类型：</strong>${maritimeEvent.event_type}<br>
          <strong>时间：</strong>${new Date(maritimeEvent.occurred_at).toLocaleString('zh-CN')}<br>
          <strong>位置：</strong>${maritimeEvent.latitude.toFixed(4)}, ${maritimeEvent.longitude.toFixed(4)}
        `

        L.marker(
          [maritimeEvent.latitude, maritimeEvent.longitude],
          {
            icon: eventIcon,
          },
        )
          .bindPopup(popupContent)
          .addTo(map)
      }
    })
    .catch((error) => {
      console.error('事件数据加载失败：', error)
    })

  const harbourLayer = L.layerGroup().addTo(map)

  const harbourIcon = L.icon({
    iconUrl: 'https://map.openseamap.org/resources/places/harbour_32.png',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  })

  const loadHarbours = async () => {
    if (!map) return

    const bounds = map.getBounds()
    const zoom = Math.round(map.getZoom())

    let maxSize = 1

    if (zoom >= 7) maxSize = 2
    if (zoom >= 8) maxSize = 3
    if (zoom >= 9) maxSize = 4
    if (zoom >= 10) maxSize = 6

    const params = new URLSearchParams({
      b: bounds.getSouth().toFixed(5),
      t: bounds.getNorth().toFixed(5),
      l: bounds.getWest().toFixed(5),
      r: bounds.getEast().toFixed(5),
      ucid: '0',
      maxSize: maxSize.toString(),
      zoom: zoom.toString(),
    })

    const response = await fetch(
      `https://harbour.openseamap.org/getHarbours.php?${params}`,
    )

    if (!response.ok) {
      throw new Error(`港口接口请求失败：${response.status}`)
    }

    const text = await response.text()
    const rows = text
      .replace(/(\r|\n)/g, '')
      .replace(/putHarbourMarker\(/g, '')
      .replace(/\);/g, ';')
      .split(';')
      .filter(Boolean)

    harbourLayer.clearLayers()

    for (const row of rows) {
      const [, longitudeText, latitudeText, nameText] = row.split(', ')
      const longitude = Number.parseFloat(longitudeText)
      const latitude = Number.parseFloat(latitudeText)
      const name = nameText?.replace(/'/g, '') || '未命名港口'

      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
        continue
      }

      L.marker([latitude, longitude], { icon: harbourIcon })
        .bindPopup(name)
        .addTo(harbourLayer)
    }
  }

  loadHarbours().catch((error) => {
    console.error('港口数据加载失败：', error)
  })
})

onBeforeUnmount(() => {
  map?.remove()
})
</script>




<template>
  <main id="map"></main>
</template>

<style>
html,
body,
#app {
  width: 100%;
  height: 100%;
  margin: 0;
}

#app {
  max-width: none;
  border: 0;
}

#map {
  width: 100%;
  height: 100vh;
  background-color: #dbeafe;
}

.ship-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  background-color: #2563eb;
  border: 2px solid white;
  border-radius: 50%;
  box-sizing: border-box;
  font-size: 14px;
  line-height: 1;
  box-shadow: 0 1px 4px rgb(0 0 0 / 40%);
}

.event-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  background-color: #dc2626;
  border: 2px solid white;
  border-radius: 50%;
  box-sizing: border-box;
  font-size: 17px;
  font-weight: 700;
  line-height: 1;
  box-shadow: 0 1px 4px rgb(0 0 0 / 40%);
}

</style>
