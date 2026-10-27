#!/bin/bash
# Why does v3 fire on recipe_error (89781f) and realistic_day 8da1cd afternoon? Look at valve-open samples.
cd "$(dirname "$0")/../.." || exit 1
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
for spec in "20261029_0800_89781f 11:00 12:00" "20261028_0800_aba133 10:20 11:20" "20261019_0800_0b81a7 10:20 11:20" "20261030_0800_8da1cd 16:30 17:40"; do
  set -- $spec
  echo "=== $1 $2-$3 valve-open samples, 10-min"
  psql "select to_char(date_bin('10 min', ts, timestamp '2000-01-01'),'HH24:MI') t, count(*) n,
     round(avg(disp_pressure_kpa)::numeric,1) press, round(avg(fixture_vac_kpa)::numeric,1) vac_avg,
     round(max(fixture_vac_kpa)::numeric,1) vac_weakest, count(*) filter (where fixture_vac_kpa > -75) weak
   from sensor_trend where run_id='$1' and mode='RUNNING' and disp_valve_open=1
     and ts::time between '$2' and '$3' group by 1 order by 1"
done
grep -m3 -E 'recipe|Recipe' logs/20261029_0800_89781f/event.log | sed -n '1,3p'
grep -E '^2026-10-29 11:2[0-3]' logs/20261029_0800_89781f/event.log | grep -v DEBUG | grep -E 'DISPENSER|MACHINE|OPERATOR|ALARM' | head -8
