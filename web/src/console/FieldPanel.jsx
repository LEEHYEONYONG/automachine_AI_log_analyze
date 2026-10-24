import { api } from "../api";

const DOORS = [
  { id: "FRONT_LEFT", label: "전면 좌측 도어" },
  { id: "FRONT_RIGHT", label: "전면 우측 도어" },
];

/** Things a person does at the machine itself rather than on the HMI: opening guards, hitting the E-stop. */
export function FieldPanel({ state, run }) {
  return (
    <section className="panel">
      <h2>현장 조작 (사람의 물리적 행동)</h2>
      <p className="hint">운전 중에 도어를 열면 E9101로 즉시 정지합니다. 비상정지는 HMI 하단 버튼으로도 누를 수 있습니다.</p>
      {DOORS.map((d) => {
        const open = state.safety.doors_open[d.id];
        return (
          <div key={d.id} className="device-row">
            <span className="device-name">{d.label}</span>
            <div className="segmented">
              <button className={!open ? "active" : ""} onClick={() => run(() => api.door(d.id, false))}>
                닫힘
              </button>
              <button className={open ? "active" : ""} onClick={() => run(() => api.door(d.id, true))}>
                열림
              </button>
            </div>
            <span className={`tag ${open ? "danger" : ""}`}>{open ? "열림" : "닫힘"}</span>
          </div>
        );
      })}
      <div className="device-row">
        <span className="device-name">비상정지 버튼</span>
        <div className="segmented">
          <button className={!state.safety.estop ? "active" : ""} onClick={() => run(() => api.estop(false))}>
            해제
          </button>
          <button className={state.safety.estop ? "active" : ""} onClick={() => run(() => api.estop(true))}>
            누름
          </button>
        </div>
        <span className={`tag ${state.safety.estop ? "danger" : ""}`}>{state.safety.estop ? "눌림" : "정상"}</span>
      </div>
    </section>
  );
}
