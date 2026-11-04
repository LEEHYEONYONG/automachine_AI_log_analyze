import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { usePrefs } from "../../prefs";
import { beep } from "../alarmSound";

const LEVELS = ["GUEST", "OPERATOR", "ENGINEER", "MAKER"];
const atLeast = (level, need) => LEVELS.indexOf(level) >= LEVELS.indexOf(need);

const GROUPS = [
  ["production", "생산"],
  ["dispenser", "디스펜서 감시"],
  ["vision", "비전"],
  ["inspection", "비드 검사"],
  ["hmi", "화면"],
];
const RUN_HINT = {
  PRODUCTION: "실제 제품을 생산합니다. 자동 작업자는 이 방식에서만 움직입니다.",
  DRY: "제품과 접착제 없이 동작 순서만 돌립니다. 진공·토출·검사를 하지 않고, 생산 수와 기록에 남지 않습니다.",
  DUMMY: "더미 제품을 정한 수만큼 실제 공정으로 돌리고 자동으로 멈춥니다. 결과는 기록되지만 생산 수에는 넣지 않고, 더미 트레이로 배출합니다.",
};

function useSettings() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const reload = useCallback(() => {
    fetch("/api/settings")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(reload, [reload]);
  return { data, setData, error, setError, reload };
}

function RunTab({ state, data, onDone, t }) {
  const run = state.run;
  const [mode, setMode] = useState(run.mode);
  const [count, setCount] = useState(run.dummy_count);
  const [noMotion, setNoMotion] = useState(run.dry_no_motion);
  const [message, setMessage] = useState(null);
  const allowed = state.hmi.permissions.run_mode;
  const canReset = state.hmi.permissions.counter_reset;
  const changed = mode !== run.mode || (mode === "DUMMY" && count !== run.dummy_count) || (mode === "DRY" && noMotion !== run.dry_no_motion);

  const apply = async () => {
    setMessage(null);
    try {
      await api.setRunMode(mode, mode === "DUMMY" ? Number(count) : undefined, mode === "DRY" ? noMotion : undefined);
      setMessage({ ok: true, text: t("운전 방식을 바꿨습니다: {mode}", { mode: t(data.run_modes[mode]) }) });
      onDone();
    } catch (e) {
      setMessage({ ok: false, text: t(e.message) });
    }
  };
  const reset = async () => {
    try {
      await api.resetCounters();
      setMessage({ ok: true, text: t("생산 카운터를 0으로 만들었습니다. 기록 파일은 그대로입니다.") });
      onDone();
    } catch (e) {
      setMessage({ ok: false, text: t(e.message) });
    }
  };

  return (
    <>
      <section className="panel">
        <h2>{t("운전 방식")}</h2>
        <p className="hint">
          {t("지금: {mode}", { mode: t(run.label) })}
          {run.mode === "DUMMY" && ` · ${t("더미 {fed}/{count}개, 트레이 {tray}개", { fed: run.dummy_fed, count: run.dummy_count, tray: run.dummy_tray })}`}
          {run.mode === "DRY" && ` · ${t("드라이 사이클 {n}회", { n: run.dry_cycles })}`}
        </p>
        <div className="run-modes" role="radiogroup" aria-label={t("운전 방식")}>
          {Object.entries(data.run_modes).map(([key, label]) => (
            <label key={key} className={`run-mode ${mode === key ? "active" : ""}`}>
              <input type="radio" name="run-mode" value={key} checked={mode === key} disabled={!allowed} onChange={() => setMode(key)} />
              <span className="run-mode-name">{t(label)}</span>
              <span className="small muted">{t(RUN_HINT[key])}</span>
            </label>
          ))}
        </div>
        {mode === "DUMMY" && (
          <div className="form-row">
            <label htmlFor="dummy-count">{t("더미 수량")}</label>
            <input id="dummy-count" type="number" min={1} max={data.dummy_max} value={count} disabled={!allowed}
              onChange={(e) => setCount(Number(e.target.value))} />
            <span className="muted small">1~{data.dummy_max}</span>
          </div>
        )}
        {mode === "DRY" && (
          <label className="check-row">
            <input type="checkbox" checked={noMotion} disabled={!allowed} onChange={(e) => setNoMotion(e.target.checked)} />
            {t("기구 동작 끄기 (시뮬레이션 모드: 순서만 진행하고 실린더·축 출력을 내보내지 않음)")}
          </label>
        )}
        <div className="form-row">
          <button className="btn" disabled={!allowed || !changed} onClick={apply}>{t("적용")}</button>
          <span className="hint">
            {allowed
              ? t("정지 상태, AUTO 모드, 라인이 비어 있을 때만 바뀝니다. 재시작하면 자동 운전으로 돌아갑니다.")
              : t("ENGINEER 이상 로그인하면 바꿀 수 있습니다.")}
          </span>
        </div>
      </section>

      <section className="panel">
        <h2>{t("생산 카운터")}</h2>
        <p className="hint">{t("OK {ok} · NG {ng}. 화면의 숫자만 0으로 만들고, 생산 기록 파일은 지우지 않습니다.", { ok: state.counts.OK, ng: state.counts.NG })}</p>
        <button className="btn btn-ghost" disabled={!canReset} onClick={reset}>{t("카운터 초기화")}</button>
      </section>
      {message && <p className={`hint ${message.ok ? "" : "analysis-error"}`}>{message.text}</p>}
    </>
  );
}

function MachineTab({ state, data, onSaved, t }) {
  const items = [...data.machine.editable, ...data.session];
  const [draft, setDraft] = useState({});
  const [message, setMessage] = useState(null);
  const level = state.hmi.level;
  const edits = Object.fromEntries(Object.entries(draft).filter(([k, v]) => items.find((s) => s.key === k)?.value !== Number(v)));

  const save = async (fn) => {
    setMessage(null);
    try {
      const res = await fn();
      setDraft({});
      onSaved(res);
      setMessage({ ok: true, text: res.changed.length ? t("{n}개 설정을 바꿨습니다.", { n: res.changed.length }) : t("바뀐 설정이 없습니다.") });
    } catch (e) {
      setMessage({ ok: false, text: t(e.message) });
    }
  };

  return (
    <>
      {GROUPS.map(([group, label]) => {
        const rows = items.filter((s) => s.group === group);
        if (!rows.length) return null;
        return (
          <section className="panel" key={group}>
            <h2>{t(label)}</h2>
            <div className="table-wrap">
              <table className="alarm-table settings-table">
                <thead>
                  <tr><th>{t("항목")}</th><th>{t("값")}</th><th>{t("표준값")}</th><th>{t("범위")}</th><th>{t("권한")}</th></tr>
                </thead>
                <tbody>
                  {rows.map((s) => {
                    const editable = atLeast(level, s.level);
                    const value = draft[s.key] ?? s.value;
                    const off = s.value !== s.standard;
                    return (
                      <tr key={s.key} className={off ? "setting-off" : undefined}>
                        <td>{t(s.label)}</td>
                        <td>
                          <input type="number" aria-label={t(s.label)} value={value} min={s.min} max={s.max} step={s.step} disabled={!editable}
                            onChange={(e) => setDraft((d) => ({ ...d, [s.key]: e.target.value }))} />
                          <span className="muted small"> {t(s.unit)}</span>
                        </td>
                        <td className="mono">{s.standard}{off && <span className="setting-flag"> {t("표준과 다름")}</span>}</td>
                        <td className="mono small">{s.min} ~ {s.max}</td>
                        <td className="small">{s.level}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
      <div className="form-row">
        <button className="btn" disabled={!Object.keys(edits).length} onClick={() => save(() => api.saveSettings(Object.fromEntries(Object.entries(edits).map(([k, v]) => [k, Number(v)]))))}>
          {t("저장")}
        </button>
        <button className="btn btn-ghost" disabled={!state.hmi.permissions.settings} onClick={() => save(() => api.standardSettings())}>
          {t("모두 표준값으로")}
        </button>
        <span className="hint">{t("바꾼 설정은 장비에 저장되어 재시작 뒤에도 남고, 이벤트 로그에 기록됩니다.")}</span>
      </div>
      {message && <p className={`hint ${message.ok ? "" : "analysis-error"}`}>{message.text}</p>}

      <section className="panel">
        <h2>{t("고정값 (하드웨어·기록 장치로 정해짐)")}</h2>
        <div className="stats stats-3">
          {data.machine.read_only.map((s) => (
            <div className="stat" key={s.key}>
              <span className="stat-label">{t(s.label)}</span>
              <span className="stat-value">{s.value} {t(s.unit)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>{t("최근 변경")}</h2>
        {data.history.length === 0 ? <p className="hint">{t("변경 기록이 없습니다.")}</p> : (
          <ul className="settings-history mono small">
            {data.history.slice(0, 15).map((h) => <li key={`${h.ts}-${h.text}`}>{h.ts?.slice(11, 19)} {h.text}</li>)}
          </ul>
        )}
      </section>
    </>
  );
}

function Choice({ value, options, onChange, label, t }) {
  return (
    <div className="segmented" role="group" aria-label={t(label)}>
      {options.map(([v, text]) => (
        <button key={String(v)} className={value === v ? "active" : ""} onClick={() => onChange(v)}>{t(text)}</button>
      ))}
    </div>
  );
}

function DisplayTab({ t }) {
  const { prefs, setPref } = usePrefs();
  const rows = [
    ["언어", <Choice key="lang" label="언어" t={t} value={prefs.lang} onChange={(v) => setPref("lang", v)} options={[["ko", "한국어"], ["en", "English"]]} />],
    ["화면 테마", <Choice key="theme" label="화면 테마" t={t} value={prefs.theme} onChange={(v) => setPref("theme", v)}
      options={[["dark", "어두운 화면"], ["light", "밝은 화면"], ["system", "기기 설정 따르기"]]} />],
    ["글자 크기", <Choice key="size" label="글자 크기" t={t} value={prefs.textSize} onChange={(v) => setPref("textSize", v)}
      options={[["small", "작게"], ["normal", "보통"], ["large", "크게"]]} />],
    ["알람 소리", (
      <span key="sound" className="form-row">
        <Choice label="알람 소리" t={t} value={prefs.alarmSound} onChange={(v) => setPref("alarmSound", v)} options={[[true, "켜기"], [false, "끄기"]]} />
        <button className="btn btn-ghost" onClick={() => beep()}>{t("들어 보기")}</button>
      </span>
    )],
    ["트렌드 기본 구간", <Choice key="trend" label="트렌드 기본 구간" t={t} value={prefs.trendMinutes} onChange={(v) => setPref("trendMinutes", v)}
      options={[[10, "10분"], [60, "1시간"], [480, "8시간"]]} />],
    ["AI 경보 띠", <Choice key="ai" label="AI 경보 띠" t={t} value={prefs.aiBar} onChange={(v) => setPref("aiBar", v)} options={[[true, "보이기"], [false, "숨기기"]]} />],
    ["3D 그래픽 효과", <Choice key="fx" label="3D 그래픽 효과" t={t} value={prefs.viewerEffects} onChange={(v) => setPref("viewerEffects", v)} options={[[true, "켜기"], [false, "끄기"]]} />],
  ];
  return (
    <section className="panel">
      <h2>{t("화면 설정")}</h2>
      <p className="hint">{t("이 기기(브라우저)에만 저장됩니다. 다른 사람의 화면이나 장비에는 영향이 없습니다.")}</p>
      <div className="display-settings">
        {rows.map(([label, control]) => (
          <div className="display-row" key={label}>
            <span>{t(label)}</span>
            {control}
          </div>
        ))}
      </div>
    </section>
  );
}

const TABS = [["run", "운전"], ["machine", "장비"], ["display", "화면"]];

/** Settings: how the line runs, machine limits (saved on the machine), and this screen (saved in the browser). */
export function SettingsPage({ state }) {
  const { t } = usePrefs();
  const [tab, setTab] = useState("run");
  const { data, setData, error, reload } = useSettings();

  return (
    <div className="page">
      <div className="segmented settings-tabs" role="tablist">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {t(label)}
          </button>
        ))}
      </div>
      {tab === "display" && <DisplayTab t={t} />}
      {tab !== "display" && !data && <p className="hint">{error ? t("설정을 불러오지 못했습니다: {e}", { e: error }) : t("불러오는 중…")}</p>}
      {tab === "run" && data && <RunTab key={`${state.run.mode}-${state.run.dummy_count}-${state.run.dry_no_motion}`} state={state} data={data} onDone={reload} t={t} />}
      {tab === "machine" && data && <MachineTab state={state} data={data} onSaved={setData} t={t} />}
    </div>
  );
}
