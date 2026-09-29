import { useEffect, useMemo, useRef } from 'react';
import { Map, NavigationControl, Popup, setWorkerUrl, type GeoJSONSource, type Map as MapLibreMap, type MapLayerMouseEvent } from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import { Map as MapIcon, ChevronDown } from 'lucide-react';
import type { RegionGeometryCollection, RegionRisk } from '../api/types';
import { formatDateTime, formatProbability } from '../utils/format';
import { joinRiskGeoJson, type RiskFeatureProperties } from '../utils/geo';
import { RiskLegend } from './RiskLegend';

setWorkerUrl(maplibreWorkerUrl);

interface RiskMapProps {
  geometry: RegionGeometryCollection;
  risks: RegionRisk[];
  selectedRegionId?: string;
  onSelectRegion: (regionId: string) => void;
}

export function RiskMap({ geometry, risks, selectedRegionId, onSelectRegion }: RiskMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelectRegion);
  const joined = useMemo(() => joinRiskGeoJson(geometry, risks), [geometry, risks]);
  const initialJoined = useRef(joined);

  useEffect(() => { onSelectRef.current = onSelectRegion; }, [onSelectRegion]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: { subdivisions: { type: 'geojson', data: initialJoined.current } },
        layers: [
          { id: 'background', type: 'background', paint: { 'background-color': '#f6f9f5' } },
          {
            id: 'subdivision-fill',
            type: 'fill',
            source: 'subdivisions',
            paint: {
              'fill-color': [
                'case',
                ['==', ['get', 'bust_probability'], null], '#dbe5dc',
                [
                  'interpolate',
                  ['linear'],
                  ['get', 'bust_probability'],
                  0, '#edf5eb',
                  0.25, '#a3c9a8',
                  0.5, '#e2b46c',
                  0.75, '#d97043',
                  1, '#78281f',
                ],
              ],
              'fill-opacity': 0.9,
            },
          },
          {
            id: 'subdivision-outline',
            type: 'line',
            source: 'subdivisions',
            paint: { 'line-color': '#1f2a1d', 'line-width': 0.8, 'line-opacity': 0.6 },
          },
        ],
      },
      bounds: [67, 5, 99, 39],
      fitBoundsOptions: { padding: 20 },
      attributionControl: false,
    });
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 });
    const handleClick = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const id = feature?.properties?.canonical_region_id as string | undefined;
      if (id) onSelectRef.current(id);
    };
    map.on('click', 'subdivision-fill', handleClick);
    map.on('mousemove', 'subdivision-fill', (event: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = 'pointer';
      const properties = event.features?.[0]?.properties as RiskFeatureProperties | undefined;
      if (!properties || properties.bust_probability === null) return;
      popup
        .setLngLat(event.lngLat)
        .setHTML(
          `<div style="font-family: 'Neue Haas Grotesk Text Pro', sans-serif;">` +
          `<strong style="font-size: 13px; color: #85AB8B;">${properties.region_name}</strong><br/>` +
          `<span style="font-size: 11px; opacity: 0.85;">Day ${properties.lead_day} · Bust Probability: <strong>${formatProbability(Number(properties.bust_probability))}</strong></span><br/>` +
          `<span style="font-size: 11px; opacity: 0.85;">Forecast Reliability: <strong>${formatProbability(Number(properties.forecast_confidence))}</strong></span><br/>` +
          `<small style="font-size: 10px; color: #85AB8B;">Valid: ${formatDateTime(String(properties.valid_time))}</small>` +
          `</div>`
        )
        .addTo(map);
    });
    map.on('mouseleave', 'subdivision-fill', () => {
      map.getCanvas().style.cursor = '';
      popup.remove();
    });
    mapRef.current = map;
    return () => {
      popup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    (map.getSource('subdivisions') as GeoJSONSource | undefined)?.setData(joined);
  }, [joined]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    map.setPaintProperty('subdivision-outline', 'line-width', [
      'case', ['==', ['get', 'canonical_region_id'], selectedRegionId ?? ''], 3.2, 0.8,
    ]);
    map.setPaintProperty('subdivision-outline', 'line-color', [
      'case', ['==', ['get', 'canonical_region_id'], selectedRegionId ?? ''], '#78281f', '#1f2a1d',
    ]);
  }, [selectedRegionId]);

  return (
    <section className="bg-white rounded-xl border border-[#1f2a1d]/10 overflow-hidden shadow-sm flex flex-col" aria-labelledby="risk-map-title">
      <div className="p-4 border-b border-[#1f2a1d]/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#fdfdfd]">
        <div className="flex flex-col">
          <span className="text-[11px] font-mono uppercase tracking-wider text-[#85AB8B] flex items-center gap-1">
            <MapIcon className="w-3 h-3 text-[#336443]" />
            36 IMD Subdivisions
          </span>
          <h2 id="risk-map-title" className="text-base font-semibold text-[#1f2a1d]">
            Probabilistic Bust Risk Map
          </h2>
        </div>

        <div className="relative">
          <select
            id="keyboard-region-select"
            aria-label="Keyboard region selection"
            value={selectedRegionId ?? ''}
            onChange={(event) => onSelectRegion(event.target.value)}
            className="w-full sm:w-64 bg-[#f8faf7] hover:bg-[#eef4ed] focus:bg-white text-[#1f2a1d] text-xs font-medium px-3 py-1.5 rounded-lg border border-[#1f2a1d]/15 focus:border-[#336443] outline-none cursor-pointer appearance-none pr-8"
          >
            <option value="">Select subdivision...</option>
            {risks.map((risk) => (
              <option key={risk.region_id} value={risk.region_id}>
                {risk.region_name} · {formatProbability(risk.bust_probability)}
              </option>
            ))}
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-[#4b5b47] absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>
      </div>

      <div
        ref={containerRef}
        className="w-full h-[400px] lg:h-[480px] bg-[#f6f9f5]"
        role="img"
        aria-label="Map of calibrated forecast-bust probabilities across 36 IMD meteorological subdivisions"
      />
      <RiskLegend />
    </section>
  );
}
