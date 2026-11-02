# analysis/

AI 로그 분석 영역입니다. 입력은 `logs/<run_id>/`를 적재한 DB뿐이고, `ground_truth/`는 볼 수 없습니다.

| 단계 | 파일 | 하는 일 | 고장 이름 |
|---|---|---|---|
| 규칙 | `app/rules.py` | 사람이 쓴 조건 7개로 아는 고장을 찾는다 | 말함 |
| 경비원 | `app/anomaly.py` | 정상 구간에서 배운 평소 모습과 다른 값을 찾는다 | 모름 |
| 분류 | `app/classify.py` | 경비원이 울린 순간의 값을 결정 트리로 분류한다 | 말함 (참고용) |
| 반장 | `app/foreman.py` | 위 의견을 사건으로 묶어 코드가 원인을 정하고, LLM이 기록을 조회해 근거를 설명한다 | 말함 |

`app/manual.py`는 `manual/*.md`를 `##` 제목 단위로 임베딩해 `manual_chunks`에 넣고 검색합니다.

## 반장이 할 수 있는 것과 없는 것

- 사건의 시각과 원인은 코드가 정합니다. LLM에게 원인을 고르게 했을 때 dev에서 규칙보다 나빠서 바꿨습니다 (`eval/README.md` 7절).
- LLM은 읽기 전용 함수만 부르고, 원인·장비·DB를 바꾸지 못합니다. 원인과 맞지 않는 기록은 의문점으로 적을 수 있습니다.
- 조치 문장은 LLM이 쓰지 않습니다. 코드가 안내서에서 그 원인 절의 조치를 가져옵니다.
- 근거 문장의 수치가 경보·함수 결과에 없으면 코드가 표시합니다. 수치가 없는 문장의 사실 여부는 검사하지 못합니다.
- 런 전체를 볼 수 있는 사후 보고입니다. 그래서 탐지 점수와 섞지 않습니다 (`eval/README.md` 7절).

## 다시 배우기

고장 런이 바뀌거나 평소 모습을 다시 배웠다면 분류도 다시 배웁니다. 결과 파일은 저장소에 함께 커밋하고 이미지에 들어갑니다.

```bash
python3 eval/normal_periods.py | docker compose exec -T analysis python -m app.train_anomaly
python3 eval/normal_periods.py | docker compose exec -T analysis python -m app.train_classifier
```

## 테스트

LLM과 DB 없이 도는 판단 코드의 테스트입니다.

```bash
docker compose exec -T analysis python -m unittest discover -s tests -t .
```
