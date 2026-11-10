import { tr } from "../prefs";
import { useEffect, useRef, useState } from "react";
import { ACTION_LABEL } from "../labels";
import { time } from "./evidence";

const API = "/api/analysis";
const HEIGHT = 150;
const M = { top: 36, right: 16, bottom: 22, left: 52 };

// Both are the dispensing-time values the rules and the guard look at (analysis/app/trend.py).
const PLOTS = [
  { key: "pressure", title: "토출 압력 (도포 중)", unit: "kPa", minSpan: 8 },
  { key: "vacuum", title: "지그 흡착 진공 (도포 중)", unit: "kPa", minSpan: 8 },
];

// Naive timestamps from the DB are all read the same way, so positions and labels agree.
const ms = (iso) => new Date(iso).getTime();
const pad2 = (n) => String(n).padStart(2, "0");
const hm = (t) => `${pad2(new Date(t).getHours())}:${pad2(new Date(t).getMinutes())}`;
const LABEL_GAP = 64; // px between two labels on the same row

function yDomain(points, key, minSpan) {
  const values = [];
  for (const p of points) {
    if (p[key] !== null) values.push(p[key]);
    if (p[`${key}_band`]) values.push(...p[`${key}_band`]);
  }
  if (!values.length) return [0, 1];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = Math.max(hi - lo, minSpan);
  const mid = (lo + hi) / 2;
  const pad = span * 0.1;
  return [mid - span / 2 - pad, mid + span / 2 + pad];
}

function ticks(y0, y1) {
  const raw = (y1 - y0) / 3;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const n = raw / mag;
  const step = (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.ceil(y0 / step) * step; v <= y1; v += step) out.push(v);
  return out;
}

/** The incident's moments as vertical lines: the AI alert, equipment alarms and maintenance. */
function moments(data, at) {
  return [
    { at, kind: "ai", label: tr("AI 경보") },
    ...data.alarms.map((a) => ({ at: a.at, kind: "alarm", label: a.code, title: a.message })),
    ...data.maintenance.map((m) => ({ at: m.at, kind: "maint", label: ACTION_LABEL[m.action] ?? m.action })),
  ].sort((a, b) => ms(a.at) - ms(b.at));
}

function Plot({ plot, data, marks, width, hoverIdx, onHover, showLabels }) {
  const t0 = ms(data.start);
  const t1 = ms(data.end);
  const innerW = Math.max(10, width - M.left - M.right);
  const innerH = HEIGHT - M.top - M.bottom;
  const [y0, y1] = yDomain(data.points, plot.key, plot.minSpan);
  const x = (t) => M.left + ((t - t0) / (t1 - t0 || 1)) * innerW;
  const y = (v) => M.top + (1 - (v - y0) / (y1 - y0)) * innerH;
  const half = (data.step_s * 1000) / 2;

  // Break the line where the machine was not dispensing (stopped, alarm, break).
  let path = "";
  let prev = null;
  for (const p of data.points) {
    const v = p[plot.key];
    if (v === null) continue;
    const t = ms(p.t);
    path += `${prev !== null && t - prev <= 4 * half ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`;
    prev = t;
  }
  const hp = hoverIdx !== null ? data.points[hoverIdx] : null;
  // Two label rows, so an alarm right after the AI alert does not hide its name.
  const lastX = [-Infinity, -Infinity];
  const rows = marks.map((m) => {
    const mx = x(ms(m.at));
    const row = mx - lastX[0] < LABEL_GAP && mx - lastX[1] >= LABEL_GAP ? 1 : 0;
    lastX[row] = mx;
    return row;
  });

  const onPointerMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((e.clientX - rect.left) / rect.width) * (t1 - t0);
    let best = null;
    data.points.forEach((p, i) => {
      if (best === null || Math.abs(ms(p.t) - t) < Math.abs(ms(data.points[best].t) - t)) best = i;
    });
    onHover(best);
  };

  return (
    <div className="trend-card">
      <div className="trend-title">
        {tr(plot.title)} <span className="muted">({plot.unit})</span>
      </div>
      <div className="trend-plot">
        <svg width={width} height={HEIGHT} role="img" aria-label={tr(plot.title)}>
          {ticks(y0, y1).map((v) => (
            <g key={v}>
              <line className="grid" x1={M.left} x2={M.left + innerW} y1={y(v)} y2={y(v)} />
              <text className="axis" x={M.left - 6} y={y(v) + 4} textAnchor="end">
                {v.toFixed(0)}
              </text>
            </g>
          ))}
          {[0, 1 / 3, 2 / 3, 1].map((f, i) => (
            <text key={f} className="axis" x={M.left + f * innerW} y={HEIGHT - 6} textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}>
              {hm(t0 + f * (t1 - t0))}
            </text>
          ))}

          {data.points.map((p) => {
            const band = p[`${plot.key}_band`];
            if (!band) return null;
            const t = ms(p.t);
            return (
              <rect
                key={p.t}
                className="band"
                x={x(t - half)}
                width={Math.max(1, x(t + half) - x(t - half))}
                y={y(band[1])}
                height={Math.max(1, y(band[0]) - y(band[1]))}
              />
            );
          })}

          {marks.map((m, i) => (
            <g key={`${m.kind}-${m.at}-${i}`} className={`mark mark-${m.kind}`}>
              <line x1={x(ms(m.at))} x2={x(ms(m.at))} y1={M.top} y2={M.top + innerH} />
              {showLabels && (
                <text x={x(ms(m.at)) + 3} y={M.top - 6 - rows[i] * 14} textAnchor="start">
                  {m.label}
                  {m.title && <title>{m.title}</title>}
                </text>
              )}
            </g>
          ))}

          {path && <path className="series" d={path} />}

          {hp && hp[plot.key] !== null && (
            <>
              <line className="crosshair" x1={x(ms(hp.t))} x2={x(ms(hp.t))} y1={M.top} y2={M.top + innerH} />
              <circle className="marker" cx={x(ms(hp.t))} cy={y(hp[plot.key])} r={4} />
            </>
          )}
          <rect className="hit" x={M.left} y={M.top} width={innerW} height={innerH} onPointerMove={onPointerMove} onPointerLeave={() => onHover(null)} />
        </svg>
        {hp && hp[plot.key] !== null && (
          <div className="trend-tooltip" style={{ left: Math.min(Math.max(x(ms(hp.t)), 70), width - 70), top: M.top }}>
            <strong>
              {hp[plot.key].toFixed(1)} {plot.unit}
            </strong>
            <span className="muted">
              {time(hp.t)}
              {hp[`${plot.key}_band`] && ` · ${tr("평소")} ${hp[`${plot.key}_band`][0].toFixed(1)}~${hp[`${plot.key}_band`][1].toFixed(1)}`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Pressure and vacuum around one incident, with the AI alert next to the equipment alarms. */
export function IncidentChart({ runId, at, until }) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(600);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [hoverIdx, setHoverIdx] = useState(null);

  useEffect(() => {
    let current = true;
    fetch(`${API}/runs/${runId}/trend?at=${encodeURIComponent(at)}&until=${encodeURIComponent(until)}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(tr("그래프를 불러오지 못했습니다 ({a})", { a: res.status })))))
      .then((d) => current && setData(d))
      .catch((e) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [runId, at, until]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width - 24));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const marks = data ? moments(data, at) : [];
  return (
    <div className="incident-chart" ref={wrapRef}>
      {error && <p className="hint analysis-error">{error}</p>}
      {!data && !error && <p className="hint">{tr("그래프를 불러오는 중…")}</p>}
      {data && (
        <>
          <div className="chart-legend small">
            <span className="legend-line">{tr("토출 중 값 ({a}초 중앙값)", { a: data.step_s })}</span>
            <span className="legend-band">{tr("평소 범위 (경비원 기준 ±3σ)")}</span>
            <span className="legend-ai">{tr("AI 경보")}</span>
            <span className="legend-alarm">{tr("설비 알람")}</span>
            <span className="legend-maint">{tr("정비")}</span>
          </div>
          {PLOTS.map((p, i) => (
            <Plot key={p.key} plot={p} data={data} marks={marks} width={width} hoverIdx={hoverIdx} onHover={setHoverIdx} showLabels={i === 0} />
          ))}
          <ol className="chart-moments small">
            {marks.map((m, i) => (
              <li key={`${m.kind}-${m.at}-${i}`} className={`moment-${m.kind}`}>
                <span className="mono">{time(m.at)}</span> {m.label}
                {m.title && <span className="muted"> · {m.title}</span>}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
