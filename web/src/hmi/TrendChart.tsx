import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { TrendLimits, TrendPoint } from "../types";

const HEIGHT = 160;
const M = { top: 12, right: 64, bottom: 24, left: 48 };
const MARKER_MAX_POINTS = 60; // sparse series (e.g. weight checks) also get a dot per point

interface Props {
  title: string;
  unit: string;
  digits: number;
  minSpan: number; // smallest y range shown, in the series' unit
  points: TrendPoint[];
  limits: TrendLimits;
  since: number;
  now: number;
}

function niceStep(span: number, count: number): number {
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  return (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
}

function yDomain(points: TrendPoint[], limits: TrendLimits, minSpan: number): [number, number] {
  const values = points.map((p) => p[1]);
  if (limits.lo !== undefined) values.push(limits.lo);
  if (limits.hi !== undefined) values.push(limits.hi);
  if (values.length === 0) return [0, 1];
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  // Without spec limits, autoscaling would blow normal sensor noise up to full height.
  const span = Math.max(hi - lo, minSpan, 1e-6);
  const mid = (lo + hi) / 2;
  lo = mid - span / 2;
  hi = mid + span / 2;
  const pad = (hi - lo) * 0.12;
  return [lo - pad, hi + pad];
}

function nearestIndex(points: TrendPoint[], t: number): number {
  let lo = 0;
  let hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid][0] < t) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && t - points[lo - 1][0] < points[lo][0] - t) lo -= 1;
  return lo;
}

const pad2 = (n: number) => String(n).padStart(2, "0");
function fmtTime(ms: number, seconds: boolean): string {
  const d = new Date(ms);
  const hm = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  return seconds ? `${hm}:${pad2(d.getSeconds())}` : hm;
}

export function TrendChart({ title, unit, digits, minSpan, points, limits, since, now }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(360);
  const [hoverT, setHoverT] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const innerW = Math.max(10, width - M.left - M.right);
  const innerH = HEIGHT - M.top - M.bottom;
  const [y0, y1] = yDomain(points, limits, minSpan);
  const x = (t: number) => M.left + ((t - since) / (now - since || 1)) * innerW;
  const y = (v: number) => M.top + (1 - (v - y0) / (y1 - y0)) * innerH;

  const step = niceStep(y1 - y0, 3);
  const yTicks: number[] = [];
  for (let v = Math.ceil(y0 / step) * step; v <= y1; v += step) yTicks.push(v);
  const tickDigits = step >= 1 ? 0 : Math.ceil(-Math.log10(step));
  const withSeconds = now - since <= 15 * 60_000;
  const xTicks = [0, 1 / 3, 2 / 3, 1].map((f) => since + f * (now - since));

  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const last = points.length ? points[points.length - 1] : undefined;
  const hoverIdx = hoverT !== null && points.length ? nearestIndex(points, hoverT) : null;
  const hp = hoverIdx !== null ? points[hoverIdx] : null;

  const onPointerMove = (e: PointerEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHoverT(since + ((e.clientX - rect.left) / rect.width) * (now - since));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!points.length || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault();
    const from = hoverIdx ?? points.length - 1;
    const next = Math.max(0, Math.min(points.length - 1, from + (e.key === "ArrowLeft" ? -1 : 1)));
    setHoverT(points[next][0]);
  };

  const limitLines = [
    limits.lo !== undefined && { v: limits.lo, label: "하한" },
    limits.hi !== undefined && { v: limits.hi, label: "상한" },
  ].filter(Boolean) as { v: number; label: string }[];

  const fmt = (v: number) => v.toFixed(digits);
  const summary = last ? `${title} 추세, 최근값 ${fmt(last[1])}${unit}` : `${title} 추세, 데이터 없음`;

  return (
    <div className="trend-card">
      <div className="trend-title">
        {title} <span className="muted">({unit})</span>
      </div>
      <div
        ref={wrapRef}
        className="trend-plot"
        tabIndex={0}
        onKeyDown={onKeyDown}
        onBlur={() => setHoverT(null)}
        aria-label={`${summary}. 좌우 화살표로 값을 확인할 수 있습니다.`}
      >
        <svg width={width} height={HEIGHT} role="img" aria-label={summary}>
          {yTicks.map((v) => (
            <g key={v}>
              <line className="grid" x1={M.left} x2={M.left + innerW} y1={y(v)} y2={y(v)} />
              <text className="axis" x={M.left - 6} y={y(v) + 4} textAnchor="end">
                {v.toFixed(tickDigits)}
              </text>
            </g>
          ))}
          {xTicks.map((t, i) => (
            <text
              key={i}
              className="axis"
              x={x(t)}
              y={HEIGHT - 6}
              textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
            >
              {fmtTime(t, withSeconds)}
            </text>
          ))}

          {limitLines.map((l) => (
            <g key={l.label}>
              <line className="limit" x1={M.left} x2={M.left + innerW} y1={y(l.v)} y2={y(l.v)} />
              <text className="limit-label" x={M.left + 4} y={y(l.v) - 4}>
                {l.label} {fmt(l.v)}
              </text>
            </g>
          ))}

          {points.length > 0 && <path className="series" d={path} />}
          {points.length <= MARKER_MAX_POINTS &&
            points.map((p) => <circle key={p[0]} className="marker" cx={x(p[0])} cy={y(p[1])} r={4} />)}
          {last && (
            <>
              <circle className="marker" cx={x(last[0])} cy={y(last[1])} r={4} />
              <text className="end-label" x={M.left + innerW + 8} y={y(last[1]) + 4}>
                {fmt(last[1])}
              </text>
            </>
          )}

          {hp && (
            <>
              <line className="crosshair" x1={x(hp[0])} x2={x(hp[0])} y1={M.top} y2={M.top + innerH} />
              <circle className="marker" cx={x(hp[0])} cy={y(hp[1])} r={5} />
            </>
          )}

          {points.length === 0 && (
            <text className="axis" x={M.left + innerW / 2} y={M.top + innerH / 2} textAnchor="middle">
              아직 데이터가 없습니다
            </text>
          )}

          <rect
            className="hit"
            x={M.left}
            y={M.top}
            width={innerW}
            height={innerH}
            onPointerMove={onPointerMove}
            onPointerLeave={() => setHoverT(null)}
          />
        </svg>

        {hp && (
          <div
            className="trend-tooltip"
            style={{ left: Math.min(Math.max(x(hp[0]), 70), width - 70), top: M.top }}
          >
            <strong>
              {fmt(hp[1])}
              {unit}
            </strong>
            <span className="muted">{fmtTime(hp[0], true)}</span>
          </div>
        )}
      </div>

      <details className="trend-table">
        <summary>표 보기 (최근 10개)</summary>
        <table>
          <thead>
            <tr>
              <th>시각</th>
              <th>값 ({unit})</th>
            </tr>
          </thead>
          <tbody>
            {points
              .slice(-10)
              .reverse()
              .map((p) => (
                <tr key={p[0]}>
                  <td className="mono">{fmtTime(p[0], true)}</td>
                  <td className="mono">{fmt(p[1])}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
