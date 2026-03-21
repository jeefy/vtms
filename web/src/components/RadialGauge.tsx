import { useMemo } from "react";
import type { GaugeConfig, GaugeZone } from "../types/telemetry";

interface RadialGaugeProps {
  config: GaugeConfig;
  value: number;
}

const SIZE = 200;
const CENTER = SIZE / 2;
const RADIUS = 80;
const NEEDLE_LENGTH = 65;
const TICK_OUTER = RADIUS + 2;
const TICK_INNER_MAJOR = RADIUS - 10;
const TICK_INNER_MINOR = RADIUS - 5;

// Gauge arc: from 225deg (bottom-left) to -45deg (bottom-right) = 270deg sweep
const ARC_START = 225;
const ARC_END = -45;
const ARC_SWEEP = ARC_START - ARC_END; // 270

function polarToCartesian(angle: number, r: number): [number, number] {
  const rad = (angle * Math.PI) / 180;
  return [CENTER + r * Math.cos(rad), CENTER - r * Math.sin(rad)];
}

function valueToAngle(value: number, min: number, max: number): number {
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return ARC_START - ratio * ARC_SWEEP;
}

function describeArc(
  startAngle: number,
  endAngle: number,
  r: number
): string {
  const [sx, sy] = polarToCartesian(startAngle, r);
  const [ex, ey] = polarToCartesian(endAngle, r);
  const sweep = startAngle - endAngle;
  const largeArc = sweep > 180 ? 1 : 0;
  return `M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`;
}

function ZoneArc({ zone, min, max }: { zone: GaugeZone; min: number; max: number }) {
  const startAngle = valueToAngle(Math.max(zone.from, min), min, max);
  const endAngle = valueToAngle(Math.min(zone.to, max), min, max);
  if (startAngle === endAngle) return null;

  return (
    <path
      d={describeArc(startAngle, endAngle, RADIUS)}
      fill="none"
      stroke={zone.color}
      strokeWidth={6}
      strokeLinecap="round"
      opacity={0.6}
    />
  );
}

export function RadialGauge({ config, value }: RadialGaugeProps) {
  const { min, max, label, unit, zones, decimals = 0 } = config;
  const clampedValue = Math.max(min, Math.min(max, isNaN(value) ? min : value));
  const needleAngle = valueToAngle(clampedValue, min, max);
  const [nx, ny] = polarToCartesian(needleAngle, NEEDLE_LENGTH);

  // Generate tick marks
  const ticks = useMemo(() => {
    const count = 10;
    const result = [];
    for (let i = 0; i <= count; i++) {
      const v = min + (i / count) * (max - min);
      const angle = valueToAngle(v, min, max);
      const isMajor = i % 2 === 0;
      const inner = isMajor ? TICK_INNER_MAJOR : TICK_INNER_MINOR;
      const [ox, oy] = polarToCartesian(angle, TICK_OUTER);
      const [ix, iy] = polarToCartesian(angle, inner);
      result.push({ ox, oy, ix, iy, v, isMajor, angle });
    }
    return result;
  }, [min, max]);

  // Determine current zone color for the value display
  const valueColor = useMemo(() => {
    if (!zones || zones.length === 0) return "#e2e8f0";
    const zone = zones.find((z) => clampedValue >= z.from && clampedValue <= z.to);
    return zone?.color ?? "#e2e8f0";
  }, [zones, clampedValue]);

  const displayValue = isNaN(value) ? "--" : clampedValue.toFixed(decimals);

  return (
    <div className="radial-gauge">
      <svg viewBox={`0 15 ${SIZE} ${SIZE - 20}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
        {/* Background arc */}
        <path
          d={describeArc(ARC_START, ARC_END, RADIUS)}
          fill="none"
          stroke="#334155"
          strokeWidth={8}
          strokeLinecap="round"
        />

        {/* Zone arcs */}
        {zones?.map((zone, i) => (
          <ZoneArc key={i} zone={zone} min={min} max={max} />
        ))}

        {/* Tick marks */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line
              x1={t.ox}
              y1={t.oy}
              x2={t.ix}
              y2={t.iy}
              stroke="#94a3b8"
              strokeWidth={t.isMajor ? 2 : 1}
            />
            {t.isMajor && (
              <text
                x={polarToCartesian(t.angle, RADIUS - 18)[0]}
                y={polarToCartesian(t.angle, RADIUS - 18)[1]}
                textAnchor="middle"
                dominantBaseline="central"
                fill="#94a3b8"
                fontSize="10"
                fontFamily="monospace"
              >
                {Math.round(t.v)}
              </text>
            )}
          </g>
        ))}

        {/* Needle */}
        <line
          x1={CENTER}
          y1={CENTER}
          x2={nx}
          y2={ny}
          stroke="#ef4444"
          strokeWidth={2.5}
          strokeLinecap="round"
          style={{ transition: "all 0.3s ease-out" }}
        />
        {/* Needle center cap */}
        <circle cx={CENTER} cy={CENTER} r={5} fill="#ef4444" />

        {/* Value display */}
        <text
          x={CENTER}
          y={CENTER + 30}
          textAnchor="middle"
          fill={valueColor}
          fontSize="22"
          fontWeight="bold"
          fontFamily="monospace"
        >
          {displayValue}
        </text>
        <text
          x={CENTER}
          y={CENTER + 45}
          textAnchor="middle"
          fill="#64748b"
          fontSize="11"
          fontFamily="monospace"
        >
          {unit}
        </text>

        {/* Label */}
        <text
          x={CENTER}
          y={SIZE - 10}
          textAnchor="middle"
          fill="#e2e8f0"
          fontSize="13"
          fontWeight="600"
        >
          {label}
        </text>
      </svg>
    </div>
  );
}
