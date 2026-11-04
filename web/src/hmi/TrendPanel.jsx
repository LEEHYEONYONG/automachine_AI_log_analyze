import { useState } from "react";
import { useTrends } from "../api";
import { usePrefs } from "../prefs";
import { TrendChart } from "./TrendChart";

const WINDOWS = [
  { minutes: 10, label: "10분" },
  { minutes: 60, label: "1시간" },
  { minutes: 480, label: "8시간" },
];

const METRICS = [
  { key: "weight_check_mg", title: "Weight check 토출량", unit: "mg", digits: 2, minSpan: 2 },
  { key: "bead_width_mm", title: "비드 폭", unit: "mm", digits: 3, minSpan: 0.2 },
  { key: "bead_offset_mm", title: "비드 위치 오차", unit: "mm", digits: 3, minSpan: 0.12 },
  { key: "fixture_vac_kpa", title: "지그 흡착 진공", unit: "kPa", digits: 1, minSpan: 20 },
  { key: "disp_temp_c", title: "시린지 온도", unit: "°C", digits: 2, minSpan: 6 },
  { key: "disp_pressure_kpa", title: "토출 압력 (도포 중)", unit: "kPa", digits: 1, minSpan: 20 },
];

export function TrendPanel() {
  const { prefs, t } = usePrefs();
  const [minutes, setMinutes] = useState(prefs.trendMinutes);
  const trends = useTrends(minutes);

  return (
    <section className="panel">
      <div className="trend-header">
        <h2>{t("공정 트렌드")}</h2>
        <div className="segmented" role="group" aria-label={t("표시 기간")}>
          {WINDOWS.map((w) => (
            <button key={w.minutes} className={minutes === w.minutes ? "active" : ""} onClick={() => setMinutes(w.minutes)}>
              {t("최근 {period}", { period: t(w.label) })}
            </button>
          ))}
        </div>
        <span className="hint">{t("시뮬레이션 시간 기준 · 제품별 측정값 (구간이 길면 평균)")}</span>
      </div>
      {trends && (
        <div className="trend-grid">
          {METRICS.map((m) => (
            <TrendChart
              key={m.key}
              title={t(m.title)}
              unit={m.unit}
              digits={m.digits}
              minSpan={m.minSpan}
              points={trends.series[m.key]?.points ?? []}
              limits={trends.series[m.key]?.limits ?? {}}
              since={trends.since}
              now={trends.now}
            />
          ))}
        </div>
      )}
    </section>
  );
}
