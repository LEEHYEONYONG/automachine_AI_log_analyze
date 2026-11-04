import { tr } from "./prefs";
import { api } from "./api";

const SPEEDS = [1, 10, 60, 300];

/** Simulator controls. These are not part of the machine, so they live outside the HMI frame. */
export function SimBar({ state, connected, run }) {
  const { sim } = state;
  return (
    <div className="simbar" aria-label={tr("시뮬레이터 제어")}>
      <span className="simbar-label">SIM</span>
      <span className={`conn ${connected ? "on" : "off"}`} title={connected ? tr("서버 연결됨") : tr("서버 연결 끊김")} />
      <div className="segmented" role="group" aria-label={tr("시뮬레이션 배속")}>
        {SPEEDS.map((s) => (
          <button key={s} className={sim.speed === s ? "active" : ""} onClick={() => run(() => api.setSim({ speed: s }))}>
            ×{s}
          </button>
        ))}
        <button className={sim.paused ? "active" : ""} onClick={() => run(() => api.setSim({ paused: !sim.paused }))}>
          {sim.paused ? tr("재개") : tr("일시정지")}
        </button>
      </div>
      <label className="toggle" title={tr("켜면 가상 작업자가 알람 대응, 휴식, 모델 체인지를 합니다")}>
        <input
          type="checkbox"
          checked={sim.auto_operator}
          onChange={(e) => run(() => api.setAutoOperator(e.target.checked))}
        />
        {tr("자동 작업자")}
      </label>
    </div>
  );
}
