import { tr } from "../prefs";
function Row({ label, value, unit, digits = 1 }) {
  return (
    <div className="sensor-row">
      <span>{label}</span>
      <span className="mono sensor-value">
        {value === undefined ? "-" : value.toFixed(digits)}
        <span className="unit">{unit}</span>
      </span>
    </div>
  );
}

export function SensorPanel({ sensors }) {
  return (
    <section className="panel">
      <h2>{tr("센서")}</h2>
      <Row label={tr("지그 흡착 진공")} value={sensors.fixture_vac_kpa} unit="kPa" />
      <Row label={tr("토출 압력")} value={sensors.disp_pressure_kpa} unit="kPa" />
      <Row label={tr("시린지 온도")} value={sensors.disp_temp_c} unit="°C" digits={2} />
      <div className="sensor-row">
        <span>{tr("토출 밸브")}</span>
        <span className={`valve ${sensors.disp_valve_open ? "open" : ""}`}>{sensors.disp_valve_open ? "OPEN" : "CLOSE"}</span>
      </div>
    </section>
  );
}
