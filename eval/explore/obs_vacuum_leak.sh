#!/bin/bash
# vacuum_leak dev runs: 30-min view of valve-open samples (pressure, vacuum), alarms, injected fault.
cd "$(dirname "$0")/../.." || exit 1
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
for R in 20261021_0800_78b8fd 20261021_0800_10002f; do
  echo "=== $R faults"
  python3 -c "import json;[print(f['type'],f['injected_at'][11:19],f.get('resolved_at'),f['params'],f['expected_symptoms']) for f in json.load(open('ground_truth/$R/faults.json'))['faults']]"
  psql "select to_char(date_bin('30 min', ts, timestamp '2000-01-01'),'HH24:MI') t, count(*) n,
     round(avg(disp_pressure_kpa)::numeric,1) press, round(avg(fixture_vac_kpa)::numeric,1) vac_avg,
     round(percentile_cont(0.5) within group (order by fixture_vac_kpa)::numeric,1) vac_med,
     count(*) filter (where fixture_vac_kpa > -75) weak
   from sensor_trend where run_id='$R' and mode='RUNNING' and disp_valve_open=1 group by 1 order by 1"
  echo "--- alarms"; psql "select code, set_ts::time(0), clear_ts::time(0) from alarms where run_id='$R' order by set_ts"
done
