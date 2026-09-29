import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { LeadCurveResponse } from '../api/types';
import { formatDateTime, formatProbability } from '../utils/format';

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

interface LeadRiskCurveProps {
  curve: LeadCurveResponse;
  selectedLead: number;
  onSelectLead: (leadDay: number) => void;
}

export function LeadRiskCurve({ curve, selectedLead, onSelectLead }: LeadRiskCurveProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelectLead);
  useEffect(() => { onSelectRef.current = onSelectLead; }, [onSelectLead]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' });
    const validTimes = new Map(curve.points.map((point) => [point.lead_day, point.valid_time]));
    chart.setOption({
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      grid: { left: 52, right: 20, top: 24, bottom: 40 },
      tooltip: {
        trigger: 'axis',
        formatter: (parameters: unknown) => {
          const first = (parameters as Array<{ data: [number, number] }>)[0];
          const day = first.data[0];
          const probability = first.data[1];
          const point = curve.points.find((item) => item.lead_day === day);
          return `<strong>Day ${day}</strong><br/>Valid ${formatDateTime(validTimes.get(day) ?? '')}<br/>Bust probability ${formatProbability(probability)}<br/>Forecast Reliability ${formatProbability(point?.forecast_reliability ?? 0)}`;
        },
      },
      xAxis: { type: 'value', min: 1, max: 10, interval: 1, name: 'Lead day', nameLocation: 'middle', nameGap: 28 },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` } },
      series: [{
        type: 'line',
        data: curve.points.map((point) => [point.lead_day, point.bust_probability]),
        symbol: 'circle',
        symbolSize: (value: [number, number]) => value[0] === selectedLead ? 12 : 7,
        lineStyle: { color: '#0f62fe', width: 2 },
        itemStyle: { color: '#0f62fe', borderColor: '#ffffff', borderWidth: 2 },
        markLine: { symbol: 'none', lineStyle: { color: '#da1e28', width: 1.5 }, data: [{ xAxis: selectedLead, label: { formatter: `Day ${selectedLead}` } }] },
      }],
    });
    chart.on('click', (parameters) => {
      if (Array.isArray(parameters.value) && typeof parameters.value[0] === 'number') {
        onSelectRef.current(parameters.value[0]);
      }
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(chartRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [curve, selectedLead]);

  return (
    <section className="curve-panel" aria-labelledby="lead-curve-title">
      <div className="panel-heading"><div><span className="eyebrow">Calibrated trajectory</span><h2 id="lead-curve-title">Day 1–10 lead-risk curve</h2></div></div>
      <div ref={chartRef} className="lead-chart" role="img" aria-label={`Bust probability by lead day for ${curve.region_name}; Day ${selectedLead} selected`} />
      <table className="sr-only">
        <caption>Accessible lead-risk values for {curve.region_name}</caption>
        <thead><tr><th>Lead</th><th>Valid time</th><th>Bust probability</th><th>Forecast Reliability</th></tr></thead>
        <tbody>{curve.points.map((point) => <tr key={point.lead_day}><td>Day {point.lead_day}</td><td>{formatDateTime(point.valid_time)}</td><td>{formatProbability(point.bust_probability)}</td><td>{formatProbability(point.forecast_reliability)}</td></tr>)}</tbody>
      </table>
    </section>
  );
}
