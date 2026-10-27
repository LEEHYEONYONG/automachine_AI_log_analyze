#!/bin/bash
# Rule v3 on all dev runs: look only at RUNNING seconds with disp_valve_open=1 (part held, dispensing).
# If consecutive such samples all have pressure < 230 and vac > -75, 20+ samples in a row (~1 min of dispensing) -> air_supply_drop.
cd "$(dirname "$0")/../.." || exit 1
bash eval/explore/split_map.sh \
  | awk -F'\t' '$1=="dev"{print $4"\t"$2}' > /tmp/am_dev.tsv
ids=$(cut -f1 /tmp/am_dev.tsv | sed "s/.*/'&'/" | paste -sd,)
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "	" -c "$0"' "
with s as (
  select run_id, ts, (disp_pressure_kpa < 230 and fixture_vac_kpa > -75) bad,
         row_number() over (partition by run_id order by ts) rn
  from sensor_trend
  where run_id in ($ids) and mode='RUNNING' and disp_valve_open=1),
b as (
  select run_id, ts, rn - row_number() over (partition by run_id order by ts) grp from s where bad)
select run_id, min(ts)::time(0), count(*)
from b group by run_id, grp
having count(*) >= 20 order by 1, 2" > /tmp/am_det.tsv
python3 - <<'EOF'
import json, collections
det = collections.defaultdict(list)
for line in open("/tmp/am_det.tsv"):
    r, t, n = line.rstrip("\n").split("\t"); det[r].append(f"{t}({n}개)")
for line in open("/tmp/am_dev.tsv"):
    r, sc = line.rstrip("\n").split("\t")
    fs = json.load(open(f"ground_truth/{r}/faults.json"))["faults"]
    f = ", ".join(f"{x['type']}@{x['injected_at'][11:16]}" + ("*" if x.get("origin") != "injected" else "") for x in fs) or "-"
    print(f"{r[-6:]}  {sc:<21} 탐지: {' '.join(det[r]) or '-':<28} 정답: {f}")
EOF
