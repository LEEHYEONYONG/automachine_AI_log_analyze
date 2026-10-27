#!/bin/bash
# Compare a normal dev run with an air_supply_drop dev run: 30-min sensor averages, alarms, injected faults.
cd "$(dirname "$0")/../.." || exit 1
N=20261019_0800_0b81a7; F=20261028_0800_aba133
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
echo "=== faults ($F)"; python3 -c "import json;[print(f) for f in json.load(open('ground_truth/$F/faults.json'))['faults']]"
for r in $N $F; do
  echo "=== $r sensor 30-min (running only)"
  psql "select to_char(date_bin('30 min', ts, timestamp '2000-01-01'),'HH24:MI') t,
     round(avg(disp_pressure_kpa)::numeric,1) press_avg, round(min(disp_pressure_kpa)::numeric,1) press_min,
     round(avg(fixture_vac_kpa)::numeric,1) vac_avg, round(avg(disp_temp_c)::numeric,2) temp,
     count(*) filter (where mode<>'RUNNING') not_running
   from sensor_trend where run_id='$r' group by 1 order by 1"
  echo "=== $r alarms"; psql "select code, set_ts::time(0), clear_ts::time(0) from alarms where run_id='$r' order by set_ts"
done
