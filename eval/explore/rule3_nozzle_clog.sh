#!/bin/bash
# Rule 3 final on all dev runs (production.csv, one row per part, each recipe its own series):
#   median bead width of the last 50 parts is 0.015+ smaller than the same median ~30 min earlier,
#   and median pressure of the newest 10 parts >= 238 -> nozzle_clog.
#   Ignored if that pressure median fell below 238 at any time in the last 60 min (after-effect of a pressure problem). Detection time = the part where it first holds.
cd "$(dirname "$0")/../.." || exit 1
bash eval/explore/split_map.sh \
  | awk -F'\t' '$1=="dev"{print $4"\t"$2}' > /tmp/am_dev.tsv
ids=$(cut -f1 /tmp/am_dev.tsv | sed "s/.*/'&'/" | paste -sd,)
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "	" -c "$0"' "
select run_id, extract(epoch from start_time::time)::int, bead_width_mm, disp_pressure_kpa, recipe from production
where run_id in ($ids) and bead_width_mm is not null order by run_id, start_time" > /tmp/am_prod2.tsv
python3 - <<'EOF'
import json, collections, statistics, bisect
N, NP, DROP, LOOK, PRESS, MEMORY = 50, 10, 0.015, 1800, 238, 3600
hhmm = lambda s: f"{s//3600:02d}:{s%3600//60:02d}"
rows = collections.defaultdict(list)
for line in open("/tmp/am_prod2.tsv"):
    r, t, w, p, rc = line.rstrip("\n").split("\t"); rows[(r, rc)].append((int(t), float(w), float(p)))
det = collections.defaultdict(list)
for (r, rc), xs in rows.items():
    ts = [x[0] for x in xs[N - 1:]]
    mw = [statistics.median(x[1] for x in xs[i - N + 1:i + 1]) for i in range(N - 1, len(xs))]
    mp = [statistics.median(x[2] for x in xs[i - NP + 1:i + 1]) for i in range(N - 1, len(xs))]
    on, last_low = False, None
    for i, t in enumerate(ts):
        if mp[i] < PRESS: last_low = t
        j = bisect.bisect_right(ts, t - LOOK) - 1
        hit = j >= 0 and mw[j] - mw[i] >= DROP and (last_low is None or t - last_low > MEMORY)
        if hit and not on: det[r].append(f"{hhmm(t)}({mw[j]:.3f}→{mw[i]:.3f})")
        on = hit
fmt = lambda d: (" ".join(d[:2]) + (f" 외 {len(d)-2}번" if len(d) > 2 else "")) or "-"
for line in open("/tmp/am_dev.tsv"):
    r, sc = line.rstrip("\n").split("\t")
    fs = json.load(open(f"ground_truth/{r}/faults.json"))["faults"]
    f = ", ".join(f"{x['type']}@{x['injected_at'][11:16]}" for x in fs) or "-"
    print(f"{r[-6:]}  {sc:<21} 탐지: {fmt(det[r]):<44} 정답: {f}")
EOF
