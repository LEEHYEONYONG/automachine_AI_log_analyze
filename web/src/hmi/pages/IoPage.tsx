import { useEffect, useState } from "react";
import { STATION_LABEL } from "../../labels";
import type { MachineState } from "../../types";

interface IoSignal {
  address: string;
  id: string;
  label: string;
  unit: string;
  value: boolean;
  changed_at: string | null;
  device: string | null;
  invert: boolean;
}

interface IoState {
  op_mode: "AUTO" | "MANUAL";
  inputs: IoSignal[];
  outputs: IoSignal[];
}

const UNITS = ["", "MACHINE", "INFEED", "VISION", "DISPENSER", "INSPECTION", "OUTFEED"];
const POLL_MS = 200;

interface Props {
  state: MachineState;
  run: (action: () => Promise<void>) => void;
}

/** Live PLC input/output bits. Outputs backed by a device can be forced in MANUAL mode. */
export function IoPage({ state, run }: Props) {
  const [io, setIo] = useState<IoState | null>(null);
  const [unit, setUnit] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch("/api/io")
        .then((r) => r.json())
        .then((d: IoState) => !cancelled && setIo(d))
        .catch(() => {});
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const force = (s: IoSignal) =>
    run(async () => {
      const res = await fetch("/api/io/force", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: s.address, value: !s.value }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? res.statusText);
      setIo(body);
    });

  const needle = q.toLowerCase();
  const visible = (s: IoSignal) =>
    (!unit || s.unit === unit) &&
    (!needle || `${s.address} ${s.id} ${s.label}`.toLowerCase().includes(needle));
  const manual = state.op_mode === "MANUAL";

  return (
    <div className="page">
      <section className="panel">
        <div className="log-filters">
          <select value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="유닛">
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u ? STATION_LABEL[u] ?? u : "전체 유닛"}
              </option>
            ))}
          </select>
          <input type="search" placeholder="주소나 신호 이름 검색 (예: X02, 리프트, VAC)" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <p className="hint">
          {manual
            ? "MANUAL 모드: 이름 옆에 ⇄ 표시가 있는 출력은 눌러서 강제로 켜고 끌 수 있습니다. 인터록은 그대로 적용됩니다."
            : "출력 강제는 MANUAL 모드에서만 할 수 있습니다. 신호 변화는 io_trace.csv에 기록됩니다."}
        </p>
      </section>

      {!io ? (
        <p className="hint">불러오는 중…</p>
      ) : (
        <div className="io-grid">
          <IoTable title="입력 (X)" signals={io.inputs.filter(visible)} />
          <IoTable title="출력 (Y)" signals={io.outputs.filter(visible)} onForce={manual ? force : undefined} />
        </div>
      )}
    </div>
  );
}

function IoTable({ title, signals, onForce }: { title: string; signals: IoSignal[]; onForce?: (s: IoSignal) => void }) {
  return (
    <section className="panel">
      <h2>
        {title} · {signals.filter((s) => s.value).length}/{signals.length} ON
      </h2>
      <div className="table-wrap">
        <table className="io-table">
          <thead>
            <tr>
              <th>주소</th>
              <th>상태</th>
              <th>신호</th>
              <th>유닛</th>
              <th>마지막 변화</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => {
              const forcible = !!onForce && !!s.device;
              return (
                <tr key={s.address} className={s.value ? "on" : ""}>
                  <td className="mono">{s.address}</td>
                  <td>
                    {forcible ? (
                      <button className={`io-bit ${s.value ? "on" : ""}`} onClick={() => onForce!(s)} title="강제 출력 전환">
                        {s.value ? "ON" : "OFF"}
                      </button>
                    ) : (
                      <span className={`io-bit ${s.value ? "on" : ""}`}>{s.value ? "ON" : "OFF"}</span>
                    )}
                  </td>
                  <td>
                    {s.label}
                    {forcible && <span className="force-mark" title="강제 출력 가능"> ⇄</span>}
                    <div className="io-id mono">{s.id}</div>
                  </td>
                  <td>{STATION_LABEL[s.unit] ?? s.unit}</td>
                  <td className="mono">{s.changed_at ? s.changed_at.slice(11, 21) : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
