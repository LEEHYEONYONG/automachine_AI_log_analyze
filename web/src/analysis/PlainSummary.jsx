import { tr } from "../prefs";
import { checks, summary, TERM, TERM_HELP } from "./plain";

/** "처음 보시나요?": how an alert becomes a cause, and what each name on this tab means. */
export function Glossary() {
  return (
    <details className="glossary">
      <summary>{tr("처음 보시나요? 이 화면을 읽는 법")}</summary>
      <ol className="glossary-flow">
        <li>
          <strong>{tr("1. 감지")}</strong>
          <span>{tr("{a}와 {b}가 장비 기록을 계속 살핍니다.", { a: TERM.rule, b: TERM.anomaly })}</span>
        </li>
        <li>
          <strong>{tr("2. 원인 판정")}</strong>
          <span>{tr("감지 결과와 {a} 의견을 정해진 순서로 따져 코드가 원인을 정합니다.", { a: TERM.classify })}</span>
        </li>
        <li>
          <strong>{tr("3. 설명")}</strong>
          <span>{tr("AI(LLM)가 기록을 찾아보고 근거를 글로 씁니다. 원인은 바꾸지 못합니다.")}</span>
        </li>
      </ol>
      <dl className="glossary-terms">
        {Object.keys(TERM_HELP).map((k) => (
          <div key={k}>
            <dt>{TERM[k]}</dt>
            <dd>{TERM_HELP[k]}</dd>
          </div>
        ))}
        <div>
          <dt>{tr("런")}</dt>
          <dd>{tr("장비를 한 번 켜서 끌 때까지 남긴 기록 묶음입니다. 장비를 다시 시작할 때마다 새로 생깁니다.")}</dd>
        </div>
        <div>
          <dt>{tr("이상 건")}</dt>
          <dd>{tr("가까운 시각에 울린 경보들을 하나로 묶은 것입니다. 이상 건마다 원인을 하나 정합니다.")}</dd>
        </div>
      </dl>
    </details>
  );
}

/** The plain paragraph and the three checkmarks at the top of one incident or live alert. */
export function IncidentSummary({ incident }) {
  const s = summary(incident);
  return (
    <div className="plain-summary">
      <p>{s.text}</p>
      {s.todo && (
        <p>
          <strong>{tr("할 일")}:</strong> {s.todo}
        </p>
      )}
      <ul className="plain-checks">
        {checks(incident).map((c) => (
          <li key={c.key} className={c.hit ? "hit" : "miss"} title={TERM_HELP[c.key]}>
            <span aria-hidden="true">{c.hit ? "✔" : "–"}</span> {c.text} <span className="muted">({TERM[c.key]})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
