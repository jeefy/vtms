import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GpsData } from "../types/telemetry";

// Fix default Leaflet marker icon issue with bundlers
const markerIcon = new L.Icon({
  iconUrl: "/images/marker-icon.png",
  iconRetinaUrl: "/images/marker-icon-2x.png",
  shadowUrl: "/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

interface MapViewProps {
  gps: GpsData;
  trail: [number, number][];
}

/** Auto-pans the map to follow the current position */
function MapFollower({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  const isFirstRef = useRef(true);

  useEffect(() => {
    if (isFirstRef.current) {
      map.setView([lat, lng], 15);
      isFirstRef.current = false;
    } else {
      map.panTo([lat, lng], { animate: true, duration: 1 });
    }
  }, [map, lat, lng]);

  return null;
}

export function MapView({ gps, trail }: MapViewProps) {
  const hasPosition = gps.latitude !== null && gps.longitude !== null;

  // Default center: roughly center of US if no GPS data yet
  const center: [number, number] = hasPosition
    ? [gps.latitude!, gps.longitude!]
    : [39.8283, -98.5795];

  return (
    <div className="map-container">
      <MapContainer
        center={center}
        zoom={hasPosition ? 15 : 4}
        className="map"
        zoomControl={true}
        attributionControl={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {hasPosition && (
          <>
            <MapFollower lat={gps.latitude!} lng={gps.longitude!} />
            <Marker
              position={[gps.latitude!, gps.longitude!]}
              icon={markerIcon}
            />
          </>
        )}

        {trail.length > 1 && (
          <Polyline
            positions={trail}
            pathOptions={{
              color: "#3b82f6",
              weight: 3,
              opacity: 0.7,
            }}
          />
        )}
      </MapContainer>

      {/* GPS info overlay */}
      {hasPosition && (
        <div className="map-overlay">
          <span>
            {gps.latitude!.toFixed(6)}, {gps.longitude!.toFixed(6)}
          </span>
          {gps.speed !== null && (
            <span>{(gps.speed * 3.6).toFixed(1)} km/h</span>
          )}
          {gps.altitude !== null && <span>{gps.altitude.toFixed(0)}m</span>}
        </div>
      )}
    </div>
  );
}
