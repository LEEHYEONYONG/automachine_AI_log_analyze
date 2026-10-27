#!/bin/bash
# Minute-level pressure/vacuum around the air_supply_drop fault (10:20~11:20) in the dev run.
cd "$(dirname "$0")/../.." || exit 1
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "
select to_char(date_bin('5 min', ts, timestamp '2000-01-01'),'HH24:MI') t,
  round(min(disp_pressure_kpa)::numeric,1) press_min,
  round(min(fixture_vac_kpa)::numeric,1) vac_strongest,
  count(*) filter (where mode<>'RUNNING') not_running
from sensor_trend where run_id='20261028_0800_aba133'
  and ts::time between '10:20' and '11:25' group by 1 order by 1"
