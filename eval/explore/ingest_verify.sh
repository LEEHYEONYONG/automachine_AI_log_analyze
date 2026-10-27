#!/bin/bash
# Compare per-run row counts in the DB with line counts in logs/<run>/ files.
cd "$(dirname "$0")/../.." || exit 1
psql() { docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F "	" -c "$0"' "$1"; }

psql "select r.run_id,
  (select count(*) from events e where e.run_id=r.run_id),
  (select count(*) from alarms a where a.run_id=r.run_id),
  (select count(*) from production p where p.run_id=r.run_id),
  (select count(*) from sensor_trend s where s.run_id=r.run_id),
  r.loaded_at::time(0)
  from runs r order by 1" > /tmp/am_db.tsv

for d in logs/*/; do
  r=$(basename "$d"); [ -f "$d/machine_info.json" ] || continue
  ev=$(wc -l < "$d/event.log"); al=$(grep -c " SET " "$d/alarm.log")
  pr=$(($(wc -l < "$d/production.csv") - 1)); se=$(($(wc -l < "$d/sensor_trend.csv") - 1))
  printf "%s\t%s\t%s\t%s\t%s\n" "$r" "$ev" "$al" "$pr" "$se"
done > /tmp/am_files.tsv

echo "runs in logs: $(wc -l < /tmp/am_files.tsv)   runs in DB: $(wc -l < /tmp/am_db.tsv)"
echo "loaded_at range: $(cut -f6 /tmp/am_db.tsv | sort | sed -n '1p;$p' | paste -sd ' ~ ')"
echo "--- mismatches (run  file:ev/al/pr/se  db:ev/al/pr/se)"
join -t $'\t' -a1 /tmp/am_files.tsv /tmp/am_db.tsv | awk -F'\t' '
  { if ($2!=$6 || $3!=$7 || $4!=$8 || $5!=$9) { bad++; print $1, $2"/"$3"/"$4"/"$5, $6"/"$7"/"$8"/"$9 } }
  END { print (bad ? bad : 0) " mismatched runs" }'
echo "--- totals"
psql "select 'runs',count(*) from runs union all select 'alarm_codes',count(*) from alarm_codes
 union all select 'events',count(*) from events union all select 'alarms',count(*) from alarms
 union all select 'alarms still open',count(*) from alarms where clear_ts is null
 union all select 'production',count(*) from production union all select 'sensor_trend',count(*) from sensor_trend"
echo "--- db size"
psql "select pg_size_pretty(pg_database_size(current_database()))"
