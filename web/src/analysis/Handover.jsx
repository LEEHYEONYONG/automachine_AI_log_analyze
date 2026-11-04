import { useEffect, useState } from "react";
import { time } from "./evidence";

const API = "/api/analysis";

function shiftName(iso) {
  const d = new Date(iso);
  const day = `${d.getMonth() + 1}/${d.getDate()}`;
  return `${day} ${d.getHours() < 12 ? "주간 조" : "야간 조"}`;
}

/** What the code checked in the AI summary. Shown so nobody acts on a made-up number. */
function Checks({ result }) {
  const madeUp = [...result.made_up_numbers, ...result.made_up_codes, ...result.made_up_times];
  return (
    <>
      {madeUp.length > 0 && (
        <p className="hint analysis-error">기록에서 확인되지 않은 수치·코드·시각이 있습니다: {madeUp.join(", ")}</p>
      )}
      {result.missing.length > 0 && (
        <p className="hint analysis-error">요약에 빠진 중요 항목: {result.missing.join(" / ")} (아래 전체 기록에는 있습니다)</p>
      )}
    </>
  );
}

/** Shift handover: the code lists every fact of the shift, the AI writes the few lines the next crew reads first. */
export function HandoverPanel({ runId }) {
  const [shifts, setShifts] = useState(null);
  const [summaries, setSummaries] = useState({});
  const [writing, setWriting] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let current = true;
    fetch(`${API}/runs/${runId}/handover`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`인수인계 기록을 불러오지 못했습니다 (${res.status})`))))
      .then((data) => current && setShifts(data.shifts))
      .catch((e) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [runId]);

  const write = async (shift) => {
    setWriting(shift);
    setError(null);
    try {
      const res = await fetch(`${API}/runs/${runId}/handover/summary?shift=${encodeURIComponent(shift)}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `요약을 쓰지 못했습니다 (${res.status})`);
      }
      const result = await res.json();
      setSummaries((s) => ({ ...s, [shift]: result }));
    } catch (e) {
      setError(e.message);
    } finally {
      setWriting(null);
    }
  };

  return (
    <section className="panel">
      <h2>교대 인수인계</h2>
      <p className="hint">
        전체 기록은 코드가 빠짐없이 모읍니다. AI는 그 기록만 보고 다음 조가 먼저 읽을 요약과 할 일을 씁니다. 지어낸 수치가 있거나 중요 항목이
        빠지면 코드가 표시합니다.
      </p>
      {error && <p className="hint analysis-error">{error}</p>}
      {shifts === null && !error && <p className="hint">기록을 모으는 중…</p>}
      {shifts?.length === 0 && <p className="hint">이 런에는 1시간 넘게 돈 교대가 없습니다.</p>}
      {shifts?.map((s) => {
        const result = summaries[s.shift];
        const open = s.facts.filter((f) => f.open);
        return (
          <div className="incident" key={s.shift}>
            <div className="incident-head">
              <div>
                <strong>{shiftName(s.shift)}</strong>{" "}
                <span className="mono">
                  {time(s.from)} ~ {time(s.to)}
                </span>
                <div className="small muted">
                  기록 {s.facts.length}개{open.length > 0 && <span className="analysis-error"> · 이어 볼 일 {open.length}개</span>}
                </div>
              </div>
              <button className="btn" disabled={writing !== null} onClick={() => write(s.shift)}>
                {writing === s.shift ? "쓰는 중…" : result ? "다시 쓰기" : "요약 쓰기"}
              </button>
            </div>
            {result && (
              <div className="report">
                <h4>요약 (AI)</h4>
                <ul>
                  {result.summary.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                {result.todo.length > 0 && (
                  <>
                    <h4>다음 조 할 일 (AI)</h4>
                    <ul>
                      {result.todo.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </>
                )}
                <Checks result={result} />
              </div>
            )}
            <details open={!result}>
              <summary>전체 기록 (코드)</summary>
              <ul className="handover-facts">
                {s.facts.map((f) => (
                  <li key={f.text} className={f.open ? "analysis-error" : undefined}>
                    {f.open && "[이어 볼 일] "}
                    {f.text}
                  </li>
                ))}
              </ul>
            </details>
          </div>
        );
      })}
    </section>
  );
}
