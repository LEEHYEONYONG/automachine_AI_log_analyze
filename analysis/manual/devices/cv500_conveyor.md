# AM-CV500 컨베이어 (가상 제품 설명서, 검색용 요약)

사람용 원본: docs/manual/devices/cv500-conveyor.html. 가상 장비용 가상 제품이며 실제 제조사 설명서와 관계없다.

## AM-CV500 구간 구성과 앞뒤 설비 연동

스테이션마다 따로 도는 전동 벨트 5구간(INFEED → VISION → DISPENSER → INSPECTION → OUTFEED), 구간 이송 TRANSFER_IN 1.0 s, 다음 구간이 비어야 넘긴다. 공기 영향 없음. 로트 500개("Lot start", "Lot end ok=… ng=…"). 앞 설비가 늦으면 투입부가 기다리고(WAIT_UPSTREAM, 화면 STARVED): 제품 약 1.5 %에서 5–60 s, 약 0.2 %에서 2–10분 정지. 뒤 설비가 바쁘면 배출부가 기다린다(WAIT_DOWNSTREAM, 화면 BLOCKED): 합격품 약 1.5 %에서 3–30 s, 약 0.15 %에서 2–8분. 로그 "Waiting for upstream/downstream", "… ready waited=…". 이것은 장비 고장이 아니라 라인 사정이며, 알람 없이 생산량(UPH)이 줄면 STARVED·BLOCKED 시간을 본다.

## NG 배출과 E5001

불량품은 OUTFEED의 진공 픽커가 NG 버퍼로 옮긴다: PICK_DOWN 0.3 s → VACUUM_ON 0.2 s → PICK_UP 0.3 s → MOVE_TO_NG 0.8 s → PLACE 0.3 s → RETURN 0.8 s. 로그 "NG part to buffer reason=… buffer=n/24". 버퍼 24개가 차면 E5001 NG buffer full, 버퍼를 비우고 리셋한다. E5001이 평소보다 빨리 오면 불량률이 늘어난 것이므로 NG 이유를 보고 비드 검사 설명서의 원인 표를 참고한다.
