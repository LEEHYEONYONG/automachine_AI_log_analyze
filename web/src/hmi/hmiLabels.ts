// Korean texts for the operator HMI: sequence steps, wait reasons and alarm guidance.

export const STEP_LABEL: Record<string, string> = {
  WAIT_UPSTREAM: "이전 공정 대기",
  TRANSFER_IN: "반입 이송",
  STOPPER: "스토퍼 상승",
  ID_READ: "2D 코드 판독",
  LIFT_UP: "리프트 상승",
  PUSH_ALIGN: "푸셔 정렬",
  SETTLE: "안정화 대기",
  CAPTURE: "촬영",
  PROCESS: "영상 처리",
  RELEASE: "푸셔 후진",
  LIFT_DOWN: "리프트 하강",
  MOVE_TO_SCALE: "저울로 이동",
  TEST_SHOT: "시험 토출",
  WEIGH: "계량",
  MOVE_FROM_SCALE: "저울에서 복귀",
  VACUUM_ON: "진공 ON",
  RESEAT: "재안착",
  APPROACH: "도포 위치 접근",
  HEIGHT_MEASURE: "높이 측정",
  DISPENSE: "비드 도포",
  DWELL: "토출 후 대기",
  RETRACT: "니들 상승",
  VACUUM_OFF: "진공 OFF",
  SCAN: "라인 스캔",
  SCAN_RETURN: "스캐너 복귀",
  WAIT_DOWNSTREAM: "다음 공정 대기",
  STOPPER_DOWN: "스토퍼 하강",
  TRANSFER_OUT: "반출 이송",
  PICK_DOWN: "픽커 하강",
  PICK_UP: "픽커 상승",
  MOVE_TO_NG: "NG 버퍼로 이동",
  PLACE: "내려놓기",
  RETURN: "픽커 복귀",
};

export const CONDITION_LABEL: Record<string, string> = {
  "": "매 사이클",
  upstream_late: "이전 공정 미준비 시",
  weight_check: "weight check 주기",
  retry: "진공 미달 시",
  ok: "OK 제품",
  ng: "NG 제품",
};

export const WAIT_LABEL: Record<string, string> = {
  ALARM: "알람 정지",
  MACHINE_STOPPED: "장비 정지",
  WAIT_NEXT_STATION: "다음 스테이션 대기",
  WAIT_PART: "제품 대기",
  WAIT_UPSTREAM: "이전 공정 대기",
  WAIT_DOWNSTREAM: "다음 공정 대기",
};

/** Manual-mode device names and what OFF (home) / ON (extended) mean for each. */
export const DEVICE_LABEL: Record<string, { name: string; off: string; on: string }> = {
  INFEED_STOPPER: { name: "투입 스토퍼", off: "하강", on: "상승" },
  VISION_STOPPER: { name: "비전 스토퍼", off: "하강", on: "상승" },
  DISPENSER_STOPPER: { name: "디스펜서 스토퍼", off: "하강", on: "상승" },
  INSPECTION_STOPPER: { name: "검사 스토퍼", off: "하강", on: "상승" },
  OUTFEED_STOPPER: { name: "배출 스토퍼", off: "하강", on: "상승" },
  VISION_LIFT: { name: "비전 리프트", off: "하강", on: "상승" },
  VISION_PUSH_X: { name: "푸셔 X (길이 방향)", off: "후진", on: "전진" },
  VISION_PUSH_Y: { name: "푸셔 Y (폭 방향)", off: "후진", on: "전진" },
  DISP_LIFT: { name: "디스펜서 리프트", off: "하강", on: "상승" },
  DISP_FIXTURE_VAC: { name: "지그 진공", off: "OFF", on: "ON" },
  NG_PICK_Z: { name: "NG 픽커 Z", off: "상승", on: "하강" },
  NG_PICK_VAC: { name: "NG 픽커 진공", off: "OFF", on: "ON" },
  INFEED_BELT: { name: "투입 컨베이어", off: "정지", on: "구동" },
  VISION_BELT: { name: "비전 컨베이어", off: "정지", on: "구동" },
  DISPENSER_BELT: { name: "디스펜서 컨베이어", off: "정지", on: "구동" },
  INSPECTION_BELT: { name: "검사 컨베이어", off: "정지", on: "구동" },
  OUTFEED_BELT: { name: "배출 컨베이어", off: "정지", on: "구동" },
};

export const AXIS_LABEL: Record<string, string> = {
  DISP_X: "디스펜서 X축",
  DISP_Y: "디스펜서 Y축",
  DISP_Z: "디스펜서 Z축",
  SCAN_X: "검사 스캔 축",
  NG_PICK_Y: "NG 픽커 Y축",
};

export const PRESET_LABEL: Record<string, string> = {
  HOME: "원점",
  SAFE: "안전 높이",
  WORK: "도포 높이",
  WORK_START: "도포 시작점",
  SCALE: "저울",
  SCALE_SHOT: "저울 토출 높이",
  END: "끝",
  NG_BUFFER: "NG 버퍼",
};

/** Recipe-driven standard times for steps whose `std_s` is null. */
export function standardTime(step: string, std: number | null, setpoints: Record<string, number>): number | null {
  if (std !== null) return std;
  if (step === "DISPENSE" || step === "TEST_SHOT") return setpoints.dispense_time_s ?? null;
  if (step === "DWELL") return setpoints.retract_delay_s ?? null;
  return null;
}

/** E4001 guidance by the NG type in its detail ("last=..."). */
export const NG_GUIDE: Record<string, { cause: string; action: string }> = {
  BEAD_VOID: { cause: "시린지 안 기포로 비드가 끊김", action: "퍼지로 기포를 빼고, 반복되면 시린지를 교체합니다." },
  STRINGING: { cause: "니들 끝 접착제 누적, 또는 dwell 설정 이상", action: "노즐(니들 끝)을 청소합니다. 반복되면 레시피 dwell 값을 확인합니다." },
  BEAD_OFFSET: { cause: "니들 위치가 티칭 값에서 틀어짐", action: "니들 캘리브레이션을 합니다." },
  WIDTH_LOW: { cause: "토출량 부족 (노즐 막힘, 압력 저하) 또는 니들이 높음", action: "노즐 청소 후 weight check를 확인하고, 정상이면 니들 캘리브레이션을 합니다." },
  WIDTH_HIGH: { cause: "토출량 과다 또는 니들이 낮음", action: "니들 캘리브레이션을 하고 레시피 압력을 확인합니다." },
  BEAD_BREAK: { cause: "노즐 부분 막힘", action: "노즐을 청소합니다." },
  PARTICLE: { cause: "이물", action: "제품과 작업 영역의 이물을 확인합니다." },
};

export const ALARM_GUIDE: Record<string, { title: string; cause: string; action: string }> = {
  E1001: {
    title: "2D 코드 판독 실패",
    cause: "코드 오염이나 손상, 리더 렌즈 오염",
    action: "제품을 제거하고 리셋합니다. 반복되면 리더 렌즈를 청소합니다.",
  },
  E2001: {
    title: "정렬 마크 인식 실패",
    cause: "마크 오염이나 손상, 링 조명 이상",
    action: "제품을 제거하고 리셋합니다. 반복되면 조명과 카메라 렌즈를 점검합니다.",
  },
  E2002: {
    title: "정렬 오차 초과",
    cause: "푸셔나 기준 핀 이상, 제품 치수 불량",
    action: "제품을 제거하고 푸셔 동작과 기준 핀을 확인합니다.",
  },
  E3001: {
    title: "진공 지그 흡착 미달",
    cause: "진공 패드 마모나 이물, 공장 에어 압력 저하",
    action: "패드를 청소하거나 교체합니다. 반복되면 에어 공급 압력을 확인합니다.",
  },
  E3002: {
    title: "시린지 온도 이상",
    cause: "히터나 온도 센서 이상",
    action: "엔지니어를 호출합니다.",
  },
  E3003: {
    title: "시린지 잔량 부족",
    cause: "접착제 소진",
    action: "시린지를 교체한 뒤 퍼지하고 weight check 결과를 확인합니다.",
  },
  E3005: {
    title: "토출량 이상 (weight check)",
    cause: "노즐 막힘, 점도 변화, 기포, 토출 압력 이상",
    action: "노즐 청소 → 퍼지 → 시린지 교체 순서로 확인합니다. 해결되지 않으면 레시피 압력과 엔지니어 점검을 요청합니다.",
  },
  E3006: {
    title: "재료 가사시간 초과",
    cause: "시린지 장착 후 가사시간 경과",
    action: "시린지를 교체합니다.",
  },
  E4001: {
    title: "비드 연속 불량",
    cause: "불량 유형에 따라 다름",
    action:
      "상세의 불량 유형을 확인합니다. BEAD_VOID: 퍼지, STRINGING: 니들 청소, BEAD_OFFSET: 니들 캘리브레이션, WIDTH_LOW / BEAD_BREAK: 노즐 청소와 토출량 확인.",
  },
  E5001: {
    title: "NG 버퍼 가득 참",
    cause: "NG 제품 누적",
    action: "NG 버퍼를 비우고 리셋합니다. NG가 많다면 불량 원인을 먼저 확인합니다.",
  },
  E9001: {
    title: "메인 에어 압력 저하",
    cause: "공장 에어 공급 저하, 레귤레이터 이상",
    action: "공장 에어 공급과 장비 입구 레귤레이터를 확인합니다.",
  },
};
