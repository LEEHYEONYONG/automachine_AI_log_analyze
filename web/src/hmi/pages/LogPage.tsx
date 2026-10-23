import { useEffect, useState } from "react";
import { STATION_LABEL } from "../../labels";
import type { LogEntry } from "../../types";

type Kind = "event" | "alarm" | "production";

const KINDS: { id: Kind; label: string }[] = [
  { id: "event", label: "이벤트" },
  { id: "alarm", label: "알람" },
  { id: "production", label: "생산" },
];
const UNITS = ["", "MACHINE", "INFEED", "VISION", "DISPENSER", "INSPECTION", "OUTFEED", "OPERATOR", "MAINT", "HMI"];
const LEVELS = ["DEBUG", "INFO", "WARN", "ALARM"];

interface AlarmRow {
  ts: string;
  action: string;
  code: string;
  unit: string;
  text: string;
  detail: string;
}

type ProductionRow = Record<string, string | number>;

/** Searchable view of the recent logs kept in memory; the complete history is in the log files. */
export function LogPage() {
  const [kind, setKind] = useState<Kind>("event");
  const [level, setLevel] = useState("INFO");
  const [unit, setUnit] = useState("");
  const [q, setQ] = useState("");
  const [live, setLive] = useState(true);
  const [items, setItems] = useState<unknown[]>([]);
  const [logDir, setLogDir] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      const params = new URLSearchParams({ kind, level, unit, q, limit: "300" });
      fetch(`/api/logs?${params}`)
        .then((r) => r.json())
        .then((d) => {
          if (cancelled) return;
          setItems(d.items);
          setLogDir(d.log_dir);
        })
        .catch(() => {});
    };
    load();
    const timer = live ? window.setInterval(load, 1000) : undefined;
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [kind, level, unit, q, live]);

  return (
    <div className="page">
      <section className="panel">
        <div className="log-filters">
          <div className="segmented" role="tablist">
            {KINDS.map((k) => (
              <button key={k.id} className={kind === k.id ? "active" : ""} onClick={() => setKind(k.id)}>
                {k.label}
              </button>
            ))}
          </div>
          {kind === "event" && (
            <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="최소 레벨">
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l} 이상
                </option>
              ))}
            </select>
          )}
          {kind !== "production" && (
            <select value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="유닛">
              {UNITS.map((u) => (
                <option key={u} value={u}>
                  {u ? STATION_LABEL[u] ?? u : "전체 유닛"}
                </option>
              ))}
            </select>
          )}
          <input type="search" placeholder="검색 (예: wp 번호, vac, E3005)" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="toggle">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            자동 갱신
          </label>
        </div>
        <p className="hint">최근 기록 {items.length}건 (최신순). 전체 기록은 로그 파일에 있습니다: <span className="mono">{logDir}</span></p>

        <div className="table-wrap log-table-wrap">
          {kind === "event" && <EventTable rows={items as LogEntry[]} />}
          {kind === "alarm" && <AlarmTable rows={items as AlarmRow[]} />}
          {kind === "production" && <ProductionTable rows={items as ProductionRow[]} />}
        </div>
      </section>
    </div>
  );
}

function EventTable({ rows }: { rows: LogEntry[] }) {
  return (
    <table className="log-table">
      <thead>
        <tr>
          <th>시각</th>
          <th>레벨</th>
          <th>유닛</th>
          <th>내용</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((e, i) => (
          <tr key={`${e.ts}-${i}`} className={`lv-${e.level}`}>
            <td className="mono">{e.ts.slice(11)}</td>
            <td className="log-level">{e.level}</td>
            <td>{e.unit}</td>
            <td className="mono wrap">{e.text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AlarmTable({ rows }: { rows: AlarmRow[] }) {
  return (
    <table className="log-table">
      <thead>
        <tr>
          <th>시각</th>
          <th>구분</th>
          <th>코드</th>
          <th>유닛</th>
          <th>내용</th>
          <th>상세</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((a, i) => (
          <tr key={`${a.ts}-${i}`} className={a.action === "SET" ? "lv-ALARM" : ""}>
            <td className="mono">{a.ts.slice(11)}</td>
            <td>{a.action}</td>
            <td className="mono">{a.code}</td>
            <td>{a.unit}</td>
            <td>{a.text}</td>
            <td className="mono wrap">{a.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const PRODUCTION_COLUMNS = [
  ["end_time", "완료"],
  ["wp_id", "제품"],
  ["recipe", "레시피"],
  ["cycle_s", "체류(s)"],
  ["fixture_vac_kpa", "진공"],
  ["disp_pressure_kpa", "압력"],
  ["bead_width_mm", "비드 폭"],
  ["bead_offset_mm", "위치 오차"],
  ["judge", "판정"],
  ["ng_reason", "NG 사유"],
] as const;

function ProductionTable({ rows }: { rows: ProductionRow[] }) {
  return (
    <table className="log-table">
      <thead>
        <tr>
          {PRODUCTION_COLUMNS.map(([, label]) => (
            <th key={label}>{label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.wp_id}-${i}`} className={r.judge === "NG" ? "lv-WARN" : ""}>
            {PRODUCTION_COLUMNS.map(([key]) => (
              <td key={key} className="mono">
                {key === "end_time" ? String(r[key] ?? "").slice(11) : String(r[key] ?? "")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
