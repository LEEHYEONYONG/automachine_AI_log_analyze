#!/bin/bash
# e84c24 14:16~14:23: rule v2 still fires. What is the machine doing? (sensor sample + events)
cd "$(dirname "$0")/../.." || exit 1
R=20261030_0800_e84c24
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "
select ts::time(0), mode, fixture_vac_kpa vac, disp_pressure_kpa press, disp_valve_open valve
from sensor_trend where run_id='$R' and ts between '2026-10-30 14:16:20' and '2026-10-30 14:16:50' order by ts"
echo "--- events 14:16:00-14:18:00 (no DEBUG)"
grep -E '^2026-10-30 14:1[67]' logs/$R/event.log | grep -v DEBUG | head -20
