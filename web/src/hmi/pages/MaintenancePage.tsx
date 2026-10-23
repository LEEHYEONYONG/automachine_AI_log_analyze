import { api } from "../../api";
import { ACTION_LABEL } from "../../labels";
import type { MachineState } from "../../types";

const GROUPS: { title: string; actions: { id: string; note: string }[] }[] = [
  {
    title: "디스펜서",
    actions: [
      { id: "nozzle_clean", note: "노즐 막힘과 니들 끝 접착제를 제거합니다. 니들을 다시 장착하므로 캘리브레이션을 함께 하세요." },
      { id: "purge", note: "시린지 안 기포를 토출해 버립니다. 접착제가 조금 소모됩니다." },
      { id: "needle_calibration", note: "니들 끝 높이와 위치를 다시 티칭합니다." },
      { id: "replace_syringe", note: "새 시린지로 교체합니다. 교체 후 첫 도포 전에 weight check를 합니다." },
    ],
  },
  {
    title: "진공 지그",
    actions: [
      { id: "vacuum_check", note: "진공 라인과 패드 상태를 점검합니다." },
      { id: "replace_vacuum_pad", note: "마모된 진공 패드를 교체합니다." },
    ],
  },
  {
    title: "비전 / 투입 / 배출",
    actions: [
      { id: "vision_check", note: "카메라 렌즈와 링 조명을 점검합니다." },
      { id: "remove_part", note: "문제 제품을 손으로 꺼냅니다." },
      { id: "empty_ng_buffer", note: "NG 버퍼의 제품을 꺼내 비웁니다." },
    ],
  },
  {
    title: "공용",
    actions: [
      { id: "air_check", note: "장비 입구 에어 압력과 레귤레이터를 확인합니다." },
      { id: "call_engineer", note: "엔지니어가 센서 교정, 레시피 확인, 니들 캘리브레이션을 포함해 전체 점검합니다." },
    ],
  },
];

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

export function MaintenancePage({ state, run }: Props) {
  const running = state.mode === "RUNNING";
  return (
    <div className="page">
      <p className={`notice ${running ? "notice-warn" : ""}`}>
        {running
          ? "운전 중에는 유지보수를 할 수 없습니다. CYCLE STOP 또는 STOP으로 정지한 뒤 진행하세요."
          : "조치가 끝나면 알람이 있을 경우 RESET, 그다음 START로 재가동합니다."}
      </p>
      <div className="maint-groups">
        {GROUPS.map((g) => (
          <section key={g.title} className="panel">
            <h2>{g.title}</h2>
            {g.actions.map((a) => (
              <div key={a.id} className="maint-row">
                <button className="maint" disabled={running} onClick={() => run(() => api.maintenance(a.id))}>
                  {ACTION_LABEL[a.id] ?? a.id}
                </button>
                <span className="hint">{a.note}</span>
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
