import { tr } from "../prefs";
import { useEffect, useState } from "react";
import { time } from "./evidence";

const API = "/api/analysis";

function shiftName(iso) {
  const d = new Date(iso);
  const day = `${d.getMonth() + 1}/${d.getDate()}`;
  return tr("{a} {b}", { a: day, b: d.getHours() < 12 ? tr("주간 조") : tr("야간 조") });
}

/** What the code checked in the AI summary. Shown so nobody acts on a made-up number. */
function Checks({ result }) {
  const madeUp = [...result.made_up_numbers, ...result.made_up_codes, ...result.made_up_times];
  return (
    <>
      {madeUp.length > 0 && (
        <p className="hint analysis-error">{tr("기록에서 확인되지 않은 수치·코드·시각이 있습니다: {a}", { a: madeUp.join(", ") })}</p>
      )}
      {result.missing.length > 0 && (
        <p className="hint analysis-error">{tr("요약에 빠진 중요 항목: {a} (아래 전체 기록에는 있습니다)", { a: result.missing.join(" / ") })}</p>
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
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(tr("인수인계 기록을 불러오지 못했습니다 ({a})", { a: res.status })))))
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
        throw new Error(body.detail ?? tr("요약을 쓰지 못했습니다 ({a})", { a: res.status }));
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
      <h2>{tr("교대 인수인계")}</h2>
      <p className="hint">
        {tr("전체 기록은 코드가 빠짐없이 모읍니다. AI는 그 기록만 보고 다음 조가 먼저 읽을 요약과 할 일을 씁니다. 지어낸 수치가 있거나 중요 항목이")}
        {tr("빠지면 코드가 표시합니다.")}
      </p>
      {error && <p className="hint analysis-error">{error}</p>}
      {shifts === null && !error && <p className="hint">{tr("기록을 모으는 중…")}</p>}
      {shifts?.length === 0 && <p className="hint">{tr("이 런에는 1시간 넘게 돈 교대가 없습니다.")}</p>}
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
                  {tr("기록 {a}개", { a: s.facts.length })}{open.length > 0 && <span className="analysis-error"> {tr("· 이어 볼 일 {a}개", { a: open.length })}</span>}
                </div>
              </div>
              <button className="btn" disabled={writing !== null} onClick={() => write(s.shift)}>
                {writing === s.shift ? tr("쓰는 중…") : result ? tr("다시 쓰기") : tr("요약 쓰기")}
              </button>
            </div>
            {result && (
              <div className="report">
                <h4>{tr("요약 (AI)")}</h4>
                <ul>
                  {result.summary.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                {result.todo.length > 0 && (
                  <>
                    <h4>{tr("다음 조 할 일 (AI)")}</h4>
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
              <summary>{tr("전체 기록 (코드)")}</summary>
              <ul className="handover-facts">
                {s.facts.map((f) => (
                  <li key={f.text} className={f.open ? "analysis-error" : undefined}>
                    {f.open && tr("[이어 볼 일] ")}
                    {tr(f.text)}
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
