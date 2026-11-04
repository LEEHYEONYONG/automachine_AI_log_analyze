// HMI menu pages. Kept out of HmiShell.jsx so that file only exports components (fast refresh).

export const PAGES = [
  { id: "main", label: "메인" },
  { id: "sequence", label: "시퀀스" },
  { id: "manual", label: "수동" },
  { id: "io", label: "I/O" },
  { id: "alarm", label: "알람" },
  { id: "log", label: "로그" },
  { id: "production", label: "생산" },
  { id: "recipe", label: "레시피" },
  { id: "maintenance", label: "유지보수" },
  { id: "settings", label: "설정" },
];

export const isHmiPage = (p) => PAGES.some((x) => x.id === p);
