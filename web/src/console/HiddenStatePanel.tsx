import type { HiddenState, Sensors } from "../types";

interface RowProps {
  label: string;
  value: string;
  note?: string;
  abnormal: boolean;
}

function Row({ label, value, note, abnormal }: RowProps) {
  return (
    <div className={`hidden-row ${abnormal ? "abnormal" : ""}`}>
      <span>{label}</span>
      <span className="mono hidden-value">{value}</span>
      {note && <span className="hidden-note">{note}</span>}
    </div>
  );
}

export function HiddenStatePanel({ hidden, sensors }: { hidden: HiddenState; sensors: Sensors }) {
  const shown = sensors.disp_temp_c;
  return (
    <section className="panel">
      <h2>실제 물리 상태 (센서로 보이지 않는 값)</h2>
      <Row
        label="노즐 개방률"
        value={hidden.nozzle_open_ratio.toFixed(3)}
        note="정상 1.000 · 낮을수록 토출량 감소"
        abnormal={hidden.nozzle_open_ratio < 0.97}
      />
      <Row
        label="흡착 패드 누설률"
        value={hidden.pick_leak_ratio.toFixed(3)}
        note="정상 0.000"
        abnormal={hidden.pick_leak_ratio > 0.03}
      />
      <Row
        label="도달 가능한 흡착 진공"
        value={`${hidden.achievable_vac_kpa.toFixed(1)} kPa`}
        note="픽업 판정 기준 -60.0 kPa"
        abnormal={hidden.achievable_vac_kpa > -70}
      />
      <Row
        label="시린지 실제 온도"
        value={`${hidden.temp_true_c.toFixed(2)} °C`}
        note={`HMI 표시 ${shown === undefined ? "-" : shown.toFixed(2)} °C`}
        abnormal={shown !== undefined && Math.abs(shown - hidden.temp_true_c) > 0.5}
      />
      <Row
        label="온도 센서 오차"
        value={`${hidden.temp_sensor_offset_c >= 0 ? "+" : ""}${hidden.temp_sensor_offset_c.toFixed(2)} °C`}
        note="정상 0.00"
        abnormal={Math.abs(hidden.temp_sensor_offset_c) > 0.5}
      />
      <Row
        label="재료 점도 계수"
        value={hidden.material_viscosity.toFixed(3)}
        note="재료 로트마다 조금씩 다름 (기준 1.000)"
        abnormal={Math.abs(hidden.material_viscosity - 1) > 0.05}
      />
    </section>
  );
}
