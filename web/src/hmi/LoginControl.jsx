import { tr } from "../prefs";
import { useState } from "react";
import { api } from "../api";

import { LEVEL_LABEL } from "./hmiLabels";

/** Current HMI user with login/logout. The PIN is checked by the server. */
export function LoginControl({ state, run }) {
  const { hmi } = state;
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState(hmi.users[0]?.id ?? "");
  const [pin, setPin] = useState("");

  const submit = (e) => {
    e.preventDefault();
    run(async () => {
      await api.login(user, pin);
      setPin("");
      setOpen(false);
    });
  };

  return (
    <div className="login-control">
      <span className={`level-badge level-${hmi.level}`}>{LEVEL_LABEL[hmi.level]}</span>
      {hmi.user ? (
        <>
          <span className="muted">{hmi.user.name} ({hmi.user.id})</span>
          <button className="btn-text" onClick={() => run(() => api.logout())}>
            {tr("로그아웃")}
          </button>
        </>
      ) : (
        <button className="btn" onClick={() => setOpen(true)}>
          {tr("로그인")}
        </button>
      )}

      {open && (
        <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="login-title">
          <form className="dialog" onSubmit={submit}>
            <h2 id="login-title">{tr("HMI 로그인")}</h2>
            <label className="field">
              <span>{tr("사용자")}</span>
              <select value={user} onChange={(e) => setUser(e.target.value)}>
                {hmi.users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} ({u.id}) · {LEVEL_LABEL[u.level]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>PIN</span>
              <input type="password" inputMode="numeric" autoFocus value={pin} onChange={(e) => setPin(e.target.value)} />
            </label>
            <p className="hint">{tr("시뮬레이터 기본 PIN은 config/hmi_users.json에 있습니다. {min}분 동안 조작이 없으면 자동으로 로그아웃됩니다.", { min: hmi.auto_logout_min })}</p>
            <div className="dialog-actions">
              <button type="button" className="btn-text" onClick={() => setOpen(false)}>
                {tr("취소")}
              </button>
              <button type="submit" className="btn" disabled={!pin}>
                {tr("로그인")}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
