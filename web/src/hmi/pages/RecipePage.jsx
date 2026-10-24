import { useCallback, useEffect, useState } from "react";

import { LEVEL_LABEL } from "../hmiLabels";

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const show = (v) => (v === undefined ? "-" : Array.isArray(v) ? v.join(" ~ ") : String(v));
const toDraft = (recipe) =>
  Object.fromEntries(Object.entries(recipe).map(([k, v]) => [k, (Array.isArray(v) ? v : [v]).map(String)]));

async function call(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? res.statusText);
  return data;
}

/** View recipes, compare them with the setpoints actually running, edit (maker) and load (engineer). */
export function RecipePage({ state, run }) {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState({});
  const [draftOf, setDraftOf] = useState(null);

  const load = useCallback(() => {
    fetch("/api/recipes")
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  // Refresh when the loaded recipe changes (e.g. a changeover by the simulated operator).
  useEffect(load, [load, state.recipe]);

  const name = selected ?? data?.current ?? "";
  const recipe = data?.recipes[name];
  const canEdit = state.hmi.permissions.recipe_edit;
  const canLoad = state.hmi.permissions.recipe_load && state.mode === "STOPPED" && state.op_mode === "AUTO";

  // Start a fresh draft whenever another recipe is shown or the recipes are reloaded.
  if (recipe && draftOf !== recipe) {
    setDraftOf(recipe);
    setDraft(toDraft(recipe));
  }
  const resetDraft = () => setDraft(toDraft(recipe));

  if (!data || !recipe) return <p className="hint">불러오는 중…</p>;

  const parsed = Object.fromEntries(
    Object.entries(draft).map(([k, parts]) => {
      const nums = parts.map(Number);
      return [k, Array.isArray(recipe[k]) ? nums : nums[0]];
    }),
  );
  const edits = Object.fromEntries(Object.entries(parsed).filter(([k, v]) => !same(v, recipe[k])));
  const dirty = Object.keys(edits).length > 0;
  const isCurrent = name === data.current;

  const save = () =>
    run(async () => {
      setData(await call(`/api/recipes/${name}`, { values: edits }));
    });

  return (
    <div className="page">
      <div className="station-tabs recipe-tabs" role="tablist">
        {Object.keys(data.recipes).map((r) => (
          <button
            key={r}
            role="tab"
            aria-selected={r === name}
            className={`station-tab ${r === name ? "active" : ""} ${r === data.current ? "st-BUSY" : ""}`}
            onClick={() => setSelected(r)}
          >
            <strong>{r}</strong>
            <span>{r === data.current ? "현재 로드됨" : "대기"}</span>
          </button>
        ))}
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>{name} 파라미터</h2>
          <div className="recipe-actions">
            {!isCurrent && (
              <button
                className="btn"
                disabled={!canLoad}
                title={canLoad ? "" : "엔지니어 이상 권한, 정지한 AUTO 상태에서 로드할 수 있습니다"}
                onClick={() => run(async () => setData(await call(`/api/recipes/${name}/load`)))}
              >
                이 레시피 로드 (모델 체인지)
              </button>
            )}
            {canEdit && (
              <>
                <button className="btn-text" disabled={!dirty} onClick={resetDraft}>
                  되돌리기
                </button>
                <button className="btn" disabled={!dirty} onClick={save}>
                  저장 ({Object.keys(edits).length})
                </button>
              </>
            )}
          </div>
        </div>
        <p className="hint">
          {canEdit
            ? "값을 바꾸고 저장하면 범위를 확인한 뒤 적용됩니다. 로드된 레시피라면 운전 설정값도 바로 바뀌고 다음 도포 전에 weight check를 합니다."
            : `레시피 편집은 ${LEVEL_LABEL.MAKER} 권한이 필요합니다. 지금은 보기만 할 수 있습니다.`}
        </p>
        <div className="table-wrap">
          <table className="seq-table recipe-table">
            <thead>
              <tr>
                <th>항목</th>
                <th>범위</th>
                <th>레시피 값</th>
                {isCurrent && <th>운전 설정값</th>}
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.spec).map(([key, spec]) => {
                const mismatch = isCurrent && !same(recipe[key], data.setpoints[key]);
                return (
                  <tr key={key} className={key in edits ? "edited" : mismatch ? "slow" : ""}>
                    <td>
                      {spec.label}
                      <div className="io-id mono">{key}</div>
                    </td>
                    <td className="mono">
                      {spec.min} ~ {spec.max} {spec.unit}
                    </td>
                    <td>
                      {canEdit ? (
                        <div className="recipe-inputs">
                          {(draft[key] ?? []).map((v, i) => (
                            <input
                              key={i}
                              type="number"
                              step={spec.step}
                              min={spec.min}
                              max={spec.max}
                              value={v}
                              aria-label={`${spec.label} ${i ? "상한" : ""}`}
                              onChange={(e) => {
                                const next = [...draft[key]];
                                next[i] = e.target.value;
                                setDraft({ ...draft, [key]: next });
                              }}
                            />
                          ))}
                          <span className="unit">{spec.unit}</span>
                        </div>
                      ) : (
                        <span className="mono">
                          {show(recipe[key])} {spec.unit}
                        </span>
                      )}
                    </td>
                    {isCurrent && (
                      <td className="mono">
                        {show(data.setpoints[key])} {spec.unit}
                        {mismatch && <span className="tag warn">레시피와 다름</span>}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2>변경 이력</h2>
        {data.history.length === 0 ? (
          <p className="hint">변경 이력이 없습니다.</p>
        ) : (
          <div className="log-box">
            {data.history.map((e, i) => (
              <div key={`${e.ts}-${i}`} className="log-line">
                <span className="mono log-ts">{e.ts.slice(11, 19)}</span>
                <span className="log-level">{e.level}</span>
                <span className="log-unit">{e.unit}</span>
                <span className="mono log-text">{e.text}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
