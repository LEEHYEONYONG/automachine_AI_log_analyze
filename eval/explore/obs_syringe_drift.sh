#!/bin/bash
# Alarm code meanings, and syringe level vs bead width in the normal dev run (is the daily width drift tied to the syringe?).
cd "$(dirname "$0")/../.." || exit 1
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"' "$1"; }
psql "select * from alarm_codes where code in ('E2001','E3005','E3006','E4001') order by code"
psql "select to_char(date_bin('60 min', s.ts, timestamp '2000-01-01'),'HH24:MI') t,
   round(min(s.syringe_level_pct)::numeric,0) syr_min, round(max(s.syringe_level_pct)::numeric,0) syr_max
 from sensor_trend s where s.run_id='20261019_0800_0b81a7' group by 1 order by 1"
