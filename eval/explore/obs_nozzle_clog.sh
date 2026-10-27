#!/bin/bash
# nozzle_clog dev runs vs a normal dev run: 30-min production view (bead width, pressure, NG) + alarms.
cd "$(dirname "$0")/../.." || exit 1
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
for R in 20261019_0800_0b81a7 20261020_0800_d7855c 20261020_0800_bc0d60; do
  echo "=== $R production 30-min"
  psql "select to_char(date_bin('30 min', start_time, timestamp '2000-01-01'),'HH24:MI') t, count(*) n,
     round(avg(bead_width_mm)::numeric,3) width, round(min(bead_width_mm)::numeric,3) w_min,
     round(avg(disp_pressure_kpa)::numeric,1) press,
     count(*) filter (where judge='NG') ng, string_agg(distinct ng_reason, ',') reasons
   from production where run_id='$R' group by 1 order by 1"
  echo "--- alarms"; psql "select code, set_ts::time(0), clear_ts::time(0) from alarms where run_id='$R' order by set_ts"
done
echo "=== normal dev runs: bead width spread (OK + NG)"
psql "select run_id, recipe, count(*), round(avg(bead_width_mm)::numeric,3) avg,
   round(percentile_cont(0.01) within group (order by bead_width_mm)::numeric,3) p01,
   round(min(bead_width_mm)::numeric,3) min
 from production where run_id in ('20261019_0800_0b81a7','20261019_0800_105dc8') group by 1,2"
