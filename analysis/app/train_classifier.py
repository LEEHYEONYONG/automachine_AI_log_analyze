"""원인 분류를 배워 classifier.json에 저장한다. 또는 런 하나씩 빼고 배워 공정한 답안을 낸다.
analysis는 정답지를 못 보므로, 호스트에서 dev 런의 고장 구간과 종류만 뽑아 표준 입력으로 넘긴다.

    python3 eval/normal_periods.py | <analysis에서> python -m app.train_classifier          # 저장
    python3 eval/normal_periods.py | <analysis에서> python -m app.train_classifier --fair   # 답안 JSON 출력, 저장 안 함
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from sklearn.tree import DecisionTreeClassifier, export_text

from .anomaly import COUNTS, FEATURES, Z_MAX, features, learn, load_profile
from .classify import (FEATURE_NAMES, MODEL_FILE, NO_FAULT, alert_snapshots, classify_run, load_context, snapshot,
                       to_json)
from .database import SessionLocal
from .train_anomaly import normal_rows

MAX_DEPTH = 8           # 5로는 10가지를 못 가른다 (오프셋 가지조차 안 생겼음, dev 11/31). 더 깊으면 런 하나의 우연까지 외운다
MIN_LEAF = 3
EVERY = 5               # 제품이 연달아 나오면 거의 같은 모습이라 5개마다 하나만 예시로 쓴다
SETTLE = timedelta(minutes=10)   # 고장이 끝난 직후는 값이 덜 돌아왔을 수 있어 예시로 쓰지 않음


def label(ts, faults):
    """그 순간의 정답. 진행 중인 고장이 여럿이면 가장 최근에 시작한 것. 끝난 직후는 None(예시에서 뺌)."""
    active = None
    for f in sorted(faults, key=lambda x: x["start"]):
        start = datetime.fromisoformat(f["start"])
        end = datetime.fromisoformat(f["end"]) if f["end"] else datetime.max
        if start <= ts <= end:
            active = f["type"]
        elif end < ts <= end + SETTLE and active is None:
            return None
    return active or NO_FAULT


def abnormal(values, normal):
    """경비원의 연속 조건 없이, 이 제품 시점의 값이 평소를 벗어났는가."""
    for k in FEATURES:
        if k in COUNTS:
            if values[k] > normal[k]["max"]:
                return True
        elif normal[k]["std"] and abs(values[k] - normal[k]["mean"]) / normal[k]["std"] > Z_MAX:
            return True
    return False


def examples(ctx, faults, profile):
    """울린 순간만 쓰면 런 하나에 예시가 몇 개 없다. 고장 중 값이 벗어난 제품도 띄엄띄엄(EVERY개마다) 예시로 쓴다.
    고장이 없는 순간은 실제로 울린 경우만 no_fault 예시가 된다. 분류는 울렸을 때만 하기 때문이다."""
    rows = []
    for alert, row in alert_snapshots(ctx, profile):
        name = label(alert["detected_at"], faults)
        if name:
            rows.append(([row[k] for k in FEATURE_NAMES], name))

    seen = defaultdict(int)
    for ts, recipe, values in features(ctx["parts"], ctx["sensors"]):
        normal = profile.get(recipe)
        name = label(ts, faults)
        if not normal or not name or name == NO_FAULT or not abnormal(values, normal):
            continue
        seen[name] += 1
        if seen[name] % EVERY == 1:
            row = snapshot(ctx, ts, recipe, values, normal)
            rows.append(([row[k] for k in FEATURE_NAMES], name))
    return rows


def fit(rows):
    tree = DecisionTreeClassifier(max_depth=MAX_DEPTH, min_samples_leaf=MIN_LEAF, class_weight="balanced",
                                  random_state=0)
    tree.fit([x for x, _ in rows], [y for _, y in rows])
    return tree


def trained(rows):
    """sklearn 트리와 API가 읽는 숫자 표를 함께 돌려준다."""
    tree = fit(rows)
    return tree, to_json(tree, tree.classes_)


def main():
    runs = json.load(sys.stdin)
    db = SessionLocal()
    contexts = {r["run_id"]: load_context(db, r["run_id"]) for r in runs}

    if "--fair" not in sys.argv:
        profile = load_profile()
        rows = [x for r in runs for x in examples(contexts[r["run_id"]], r["faults"], profile)]
        tree, model = trained(rows)
        MODEL_FILE.write_text(json.dumps(model) + "\n", encoding="utf-8")
        print(f"예시 {len(rows)}개에서 배움 → {MODEL_FILE.name}")
        print(export_text(tree, feature_names=FEATURE_NAMES))
        return

    # 시험 볼 런은 평소 모습에서도, 트리 예시에서도 뺀다.
    normal = {r["run_id"]: normal_rows(contexts[r["run_id"]]["parts"], contexts[r["run_id"]]["sensors"], r["faults"])
              for r in runs}
    answers = {}
    for held in runs:
        others = [r for r in runs if r["run_id"] != held["run_id"]]
        profile = learn([x for r in others for x in normal[r["run_id"]]])
        rows = [x for r in others for x in examples(contexts[r["run_id"]], r["faults"], profile)]
        answers[held["run_id"]] = classify_run(contexts[held["run_id"]], profile, trained(rows)[1])
    json.dump(answers, sys.stdout, default=lambda d: d.isoformat())


if __name__ == "__main__":
    main()
