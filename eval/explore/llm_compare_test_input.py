"""모델 비교의 test 입력: test 런마다 저장된 분류 모델의 답안을 JSON으로 출력한다. 정답지 내용은 넣지 않는다."""
import json
import sys

sys.path.insert(0, "eval")
from score import ask_api, load_runs  # noqa: E402

json.dump({t["run_id"]: ask_api(t["run_id"], "classify") for t in load_runs("test")[0]}, sys.stdout)
