#!/bin/bash
# Rule 2 v3 on all dev runs (RUNNING + valve open samples, rolling 20-sample medians):
#   median(vac) > -80 and median(pressure) >= 238, and NOT a sudden drop
#   (sudden = median(vac) now is 5+ weaker than ~10 min earlier) -> vacuum_leak.
# Variant "60m": also suppress if a sudden drop happened anywhere in the last 60 min (covers the recovery edge).
cd "$(dirname "$0")/../.." || exit 1
bash eval/explore/split_map.sh \
  | awk -F'\t' '$1=="dev"{print $4"\t"$2}' > /tmp/am_dev.tsv
ids=$(cut -f1 /tmp/am_dev.tsv | sed "s/.*/'&'/" | paste -sd,)
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "	" -c "$0"' "
select run_id, extract(epoch from ts::time)::int, fixture_vac_kpa, disp_pressure_kpa from sensor_trend
where run_id in ($ids) and mode='RUNNING' and disp_valve_open=1 order by run_id, ts" > /tmp/am_open.tsv
python3 - <<'EOF'
import json, collections, statistics, bisect
N, VAC, PRESS, DROP, LOOK, MEMORY = 20, -80, 238, 5, 600, 3600
hhmm = lambda s: f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"
rows = collections.defaultdict(list)
for line in open("/tmp/am_open.tsv"):
    r, t, v, p = line.rstrip("\n").split("\t"); rows[r].append((int(t), float(v), float(p)))
det = {"10m": collections.defaultdict(list), "60m": collections.defaultdict(list)}
for r, xs in rows.items():
    ts = [x[0] for x in xs[N - 1:]]
    mv = [statistics.median(x[1] for x in xs[i - N + 1:i + 1]) for i in range(N - 1, len(xs))]
    mp = [statistics.median(x[2] for x in xs[i - N + 1:i + 1]) for i in range(N - 1, len(xs))]
    sudden = []
    for i, t in enumerate(ts):
        j = bisect.bisect_right(ts, t - LOOK) - 1
        sudden.append(j >= 0 and mv[i] - mv[j] >= DROP)
    last_sudden = None
    on = {"10m": False, "60m": False}
    for i, t in enumerate(ts):
        if sudden[i]: last_sudden = t
        base = mv[i] > VAC and mp[i] >= PRESS
        hit = {"10m": base and not sudden[i],
               "60m": base and not (last_sudden is not None and t - last_sudden <= MEMORY)}
        for k in hit:
            if hit[k] and not on[k]: det[k][r].append(hhmm(t))
            on[k] = hit[k]
fmt = lambda d: (" ".join(d[:3]) + (f" 외 {len(d)-3}번" if len(d) > 3 else "")) or "-"
for line in open("/tmp/am_dev.tsv"):
    r, sc = line.rstrip("\n").split("\t")
    fs = json.load(open(f"ground_truth/{r}/faults.json"))["faults"]
    f = ", ".join(f"{x['type']}@{x['injected_at'][11:16]}" for x in fs) or "-"
    print(f"{r[-6:]}  {sc:<21} 10분: {fmt(det['10m'][r]):<26} 60분: {fmt(det['60m'][r]):<20} 정답: {f}")
EOF
