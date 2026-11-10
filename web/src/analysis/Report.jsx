import { tr } from "../prefs";
import { faultName } from "./evidence";
import { plainText } from "./plain";

/** The cause-analysis report: the LLM's evidence and doubts, the code's checks, and the manual's actions.
 *  The LLM's sentences are shown with code names (air_supply_drop, vacuum_kpa …) swapped for plain words. */
export function Report({ report }) {
  return (
    <div className="report">
      <h4>{tr("근거 (AI 설명)")}</h4>
      <ul>
        {report.reasoning.map((line) => (
          <li key={line}>{plainText(line)}</li>
        ))}
      </ul>
      {report.doubts?.length > 0 && (
        <>
          <h4>{tr("반대 근거 (AI가 판정과 맞지 않는다고 본 기록)")}</h4>
          <ul>
            {report.doubts.map((line) => (
              <li key={line}>{plainText(line)}</li>
            ))}
          </ul>
        </>
      )}
      {report.other_causes?.length > 0 && (
        <p className="hint analysis-error">
          {tr("AI 설명이 판정과 다른 고장을 근거로 들었습니다: {a}. 이 설명은 믿지 마세요.", { a: report.other_causes.map(faultName).join(", ") })}
        </p>
      )}
      {report.unverified_numbers.length > 0 && (
        <p className="hint analysis-error">
          {tr("측정 기록에서 확인되지 않은 수치가 있습니다: {a}", { a: report.unverified_numbers.join(", ") })}
        </p>
      )}
      {report.actions && (
        <>
          <h4>{tr("할 일 (조치 매뉴얼: {a})", { a: plainText(report.actions.section) })}</h4>
          <p>{plainText(report.actions.steps)}</p>
        </>
      )}
      <p className="hint">
        {tr("AI가 쓴 설명은 틀릴 수 있으니 조치 전에 기록을 확인하세요. AI가 찾아본 기록:")}{" "}
        {report.tools_called.map(plainText).join(", ") || tr("없음")}
      </p>
    </div>
  );
}
