#!/bin/bash
# Normal dev runs: how far does vacuum during dispensing wander? (valve-open, RUNNING, excluding purge shots vac > -50)
# Plus: when does each vacuum_leak dev run first cross candidate thresholds (5-min median)?
cd "$(dirname "$0")/../.." || exit 1
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
psql "select run_id, count(*) n, round(min(fixture_vac_kpa)::numeric,1) strongest,
   round(percentile_cont(0.5) within group (order by fixture_vac_kpa)::numeric,1) med,
   round(percentile_cont(0.99) within group (order by fixture_vac_kpa)::numeric,1) p99,
   round(max(fixture_vac_kpa)::numeric,1) weakest
 from sensor_trend where run_id in ('20261019_0800_0b81a7','20261019_0800_105dc8')
   and mode='RUNNING' and disp_valve_open=1 and fixture_vac_kpa < -50 group by 1"
psql "with m as (
   select run_id, date_bin('5 min', ts, timestamp '2000-01-01') t,
          percentile_cont(0.5) within group (order by fixture_vac_kpa) med
   from sensor_trend where run_id in ('20261021_0800_78b8fd','20261021_0800_10002f')
     and mode='RUNNING' and disp_valve_open=1 group by 1,2)
 select run_id, th, min(t)::time(0) first_cross
 from m, (values (-82),(-80),(-78),(-75)) v(th) where med > th and t::time < '12:00' group by 1,2 order by 1,2"
