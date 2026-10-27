#!/bin/bash
# Per dev run: biggest drop of the 50-part median bead width vs ~30 min earlier (same recipe only), and when.
cd "$(dirname "$0")/../.." || exit 1
bash eval/explore/rule3_nozzle_clog.sh > /dev/null
awk '{print $1"\t"$2"\t"$3"\t"$5}' /tmp/am_prod2.tsv > /tmp/am_prod.tsv
python3 - <<'EOF'
import collections, statistics, bisect
N, LOOK = 50, 1800
rows = collections.defaultdict(list)
for line in open("/tmp/am_prod.tsv"):
    r, t, w, rc = line.rstrip("\n").split("\t"); rows[(r, rc)].append((int(t), float(w)))
sc = dict(l.rstrip("\n").split("\t") for l in open("/tmp/am_dev.tsv"))
for (r, rc), xs in sorted(rows.items()):
    ts = [x[0] for x in xs[N - 1:]]
    med = [statistics.median(x[1] for x in xs[i - N + 1:i + 1]) for i in range(N - 1, len(xs))]
    best = (0, 0)
    for i, t in enumerate(ts):
        j = bisect.bisect_right(ts, t - LOOK) - 1
        if j >= 0 and med[j] - med[i] > best[0]: best = (med[j] - med[i], t)
    print(f"{r[-6:]} {sc[r]:<21} {rc[-1]}  max drop {best[0]:.3f} at {best[1]//3600:02d}:{best[1]%3600//60:02d}")
EOF
