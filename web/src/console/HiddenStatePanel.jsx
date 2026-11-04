import { tr } from "../prefs";
function Row({ label, value, note, abnormal }) {
  return (
    <div className={`hidden-row ${abnormal ? "abnormal" : ""}`}>
      <span>{label}</span>
      <span className="mono hidden-value">{value}</span>
      {note && <span className="hidden-note">{note}</span>}
    </div>
  );
}

const signed = (v, digits) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;

export function HiddenStatePanel({ hidden: h, sensors, setpointErrors }) {
  const shown = sensors.disp_temp_c;
  const errors = Object.entries(setpointErrors);
  return (
    <section className="panel">
      <h2>{tr("실제 물리 상태 (센서로 보이지 않는 값)")}</h2>

      <h3>{tr("공장 에어")}</h3>
      <Row label={tr("공급압")} value={`${h.plant_air_kpa.toFixed(0)} kPa`} note={tr("정상 약 550 · 300 미만이면 E9001")}
        abnormal={h.plant_air_kpa < 450} />
      <Row label={tr("토출 레귤레이터 출력")} value={`${h.regulator_out_kpa.toFixed(1)} kPa`}
        note={tr("공급압이 낮으면 설정값까지 못 올라감")} abnormal={h.plant_air_kpa - 120 < h.regulator_out_kpa + 1 && h.plant_air_kpa < 450} />

      <h3>{tr("디스펜서")}</h3>
      <Row label={tr("노즐 개방률")} value={h.nozzle_open_ratio.toFixed(3)} note={tr("정상 1.000 · 낮을수록 토출량 감소")}
        abnormal={h.nozzle_open_ratio < 0.97} />
      <Row label={tr("니들 높이 오차")} value={`${signed(h.needle_z_offset_mm, 3)} mm`}
        note={tr("높이 레이저는 제품 표면만 재므로 보이지 않음")} abnormal={Math.abs(h.needle_z_offset_mm) > 0.02} />
      <Row label={tr("니들 위치 오차")} value={`${h.needle_xy_offset_mm.toFixed(3)} mm`} note={tr("검사 기준 0.10 mm")}
        abnormal={h.needle_xy_offset_mm > 0.03} />
      <Row label={tr("니들 끝 접착제 누적")} value={h.tip_buildup.toFixed(2)} note={tr("높을수록 실 끊김 증가")}
        abnormal={h.tip_buildup > 0.1} />
      <Row label={tr("시린지 안 기포")} value={tr("{a}개", { a: h.bubbles })} note={tr("도포 중 하나씩 빠지며 비드 끊김을 만듦")}
        abnormal={h.bubbles > 0} />
      <Row label={tr("시린지 실제 온도")} value={`${h.temp_true_c.toFixed(2)} °C`}
        note={tr("HMI 표시 {a} °C", { a: shown === undefined ? "-" : shown.toFixed(2) })}
        abnormal={shown !== undefined && Math.abs(shown - h.temp_true_c) > 0.5} />
      <Row label={tr("온도 센서 오차")} value={`${signed(h.temp_sensor_offset_c, 2)} °C`} note={tr("정상 0.00")}
        abnormal={Math.abs(h.temp_sensor_offset_c) > 0.5} />
      <Row label={tr("재료 점도 계수 / 장착 시간")} value={`${h.material_viscosity.toFixed(3)} / ${h.syringe_age_h.toFixed(1)} h`}
        note={tr("재료 로트마다 다르고, 장착 후 시간이 지날수록 점도가 오름")}
        abnormal={Math.abs(h.material_viscosity - 1) > 0.04 || h.syringe_age_h > 5} />

      <h3>{tr("디스펜서 진공 지그")}</h3>
      <Row label={tr("진공 패드 누설률")} value={h.fixture_leak_ratio.toFixed(3)} note={tr("정상 0.000")}
        abnormal={h.fixture_leak_ratio > 0.03} />
      <Row label={tr("도달 가능한 지그 진공")} value={`${h.achievable_vac_kpa.toFixed(1)} kPa`}
        note={tr("고정 판정 기준 -60.0 kPa · 에어가 약해져도 낮아짐")} abnormal={h.achievable_vac_kpa > -70} />

      <h3>{tr("레시피")}</h3>
      {errors.length === 0 ? (
        <p className="hint">{tr("검증된 레시피와 실제 설정값이 같습니다.")}</p>
      ) : (
        errors.map(([k, v]) => (
          <Row key={k} label={k} value={String(v)} note={tr("검증된 레시피와 다른 값이 들어가 있음")} abnormal />
        ))
      )}
    </section>
  );
}
