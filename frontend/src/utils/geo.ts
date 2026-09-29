import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type { RegionGeometryCollection, RegionRisk } from '../api/types';

export type RiskFeatureProperties = {
  canonical_region_id: string;
  region_name: string;
  bust_probability: number | null;
  forecast_confidence: number | null;
  lead_day: number | null;
  valid_time: string | null;
};

export type RiskFeatureCollection = FeatureCollection<Geometry, RiskFeatureProperties>;

function canonicalRegionId(value: string | number): string {
  if (typeof value === 'string' && value.startsWith('imd-')) return value;
  return `imd-${String(Number(value)).padStart(2, '0')}`;
}

export function joinRiskGeoJson(geometry: RegionGeometryCollection, risks: RegionRisk[]): RiskFeatureCollection {
  const byRegion = new Map(risks.map((risk) => [risk.region_id, risk]));
  const features = geometry.features.map((feature): Feature<Geometry, RiskFeatureProperties> => {
    const regionId = canonicalRegionId(feature.properties.region_id);
    const risk = byRegion.get(regionId);
    return {
      type: 'Feature',
      id: regionId,
      geometry: feature.geometry,
      properties: {
        canonical_region_id: regionId,
        region_name: risk?.region_name ?? feature.properties.region_name,
        bust_probability: risk?.bust_probability ?? null,
        forecast_confidence: risk?.forecast_confidence ?? null,
        lead_day: risk?.lead_day ?? null,
        valid_time: risk?.valid_time ?? null,
      },
    };
  });
  return { type: 'FeatureCollection', features };
}
