/** In MANUAL mode the HMI moves devices directly; these read their positions (null in AUTO). */
export function manualDevice(m, id) {
  return m.op_mode === "MANUAL" ? m.manual?.devices.find((d) => d.id === id)?.position ?? null : null;
}

export function manualAxis(m, id) {
  return m.op_mode === "MANUAL" ? m.manual?.axes.find((a) => a.id === id)?.position ?? null : null;
}
