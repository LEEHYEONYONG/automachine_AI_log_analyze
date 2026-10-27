#!/bin/bash
# realistic_day dev run e84c24: why does the pressure rule fire all afternoon? 15-min view + recipe/refill events.
cd "$(dirname "$0")/../.." || exit 1
R=20261030_0800_e84c24
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
psql "select to_char(date_bin('15 min', ts, timestamp '2000-01-01'),'HH24:MI') t,
  round(avg(disp_pressure_kpa) filter (where mode='RUNNING')::numeric,1) press_run,
  round(min(disp_pressure_kpa) filter (where mode='RUNNING')::numeric,1) press_min,
  round(min(fixture_vac_kpa)::numeric,1) vac_strongest, round(min(syringe_level_pct)::numeric,0) syr
from sensor_trend where run_id='$R' and ts::time between '13:00' and '16:00' group by 1 order by 1"
echo "--- ground truth faults"
python3 -c "import json;[print(f['type'],f['injected_at'][11:19],f.get('resolved_at'),f.get('origin'),f['params']) for f in json.load(open('ground_truth/$R/faults.json'))['faults']]"
echo "--- event.log lines mentioning pressure/recipe/regulator 13:30-14:30"
grep -E '^2026-10-30 1(3:[3-5]|4:[0-2])' logs/$R/event.log | grep -iE 'press|recipe|regul|set' | grep -v -iE 'DISPENSE_(START|END)' | head -15
