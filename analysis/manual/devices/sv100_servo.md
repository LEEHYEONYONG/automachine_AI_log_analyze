# AM-SV100 서보 축 (가상 제품 설명서, 검색용 요약)

사람용 원본: docs/manual/devices/sv100-servo.html. 가상 장비용 가상 제품이며 실제 제조사 설명서와 관계없다.

## AM-SV100 개요와 축 목록

전기로 위치를 정해 움직이는 서보 축 5개로 공장 공기의 영향을 받지 않는다. DISP_X −80–180 mm, 200 mm/s, 원점 0(작업 시작 −58, 저울 150). DISP_Y −220–40 mm, 200 mm/s, 원점 0(작업 시작 −24, 저울 −200). DISP_Z −12–100 mm, 60 mm/s, 원점 88 안전 높이(도포 0, 저울 시험 토출 −10). SCAN_X(비드 검사) −84–84 mm, 150 mm/s, 원점 −84. NG_PICK_Y 0–260 mm, 300 mm/s, 원점 0(NG 버퍼 260). 서보는 장비 기록에 자체 오류를 남기지 않으며 토출 품질 문제의 원인 목록에 넣지 않는다. 니들 위치 어긋남은 서보가 아니라 니들 설치 문제다.

## 원점 복귀와 인터록

장비를 켠 뒤, 비상 정지(E9100, 서보 전원 차단) 뒤, 수동 조작 뒤에는 자동 운전 전에 원점 복귀가 필요하다. 운전 중 도어가 열리면 E9101, 원점 복귀 중 열리면 다시 해야 한다. 순서: SAFETY_CHECK(비상 정지·도어·메인 공기 300 kPa 이상) → VACUUM_OFF → CYLINDERS_RETRACT → LIFTS_DOWN → STOPPERS_UP → Z_HOME → XY_HOME → AUX_AXES_HOME → WIP_CHECK(도포를 시작한 제품은 INIT_INCOMPLETE 불량). 축 하나는 약 1 s + 원점까지 거리 ÷ 40 mm/s. 로그 "Initialize step … done", "Initialize done t=…s". 인터록: Z가 80 mm 아래이거나 움직이면 X·Y 이동 금지, Z를 30 mm 아래로는 제품 위(디스펜서 리프트 올라감)나 저울 위에서만, 제품 위에서 Z 0 mm 아래 금지, NG 픽커가 내려가 있으면 NG_PICK_Y 이동 금지.
