export type NavKey = "overview" | "patrol" | "pcr" | "risk" | "robot";

export type IconName =
  | "grid"
  | "route"
  | "flask"
  | "warning"
  | "robot"
  | "bell"
  | "settings"
  | "arrow"
  | "leaf"
  | "map"
  | "pulse"
  | "chevron";

export interface NavItem {
  key: NavKey;
  label: string;
  caption: string;
  icon: IconName;
}

export const navItems: NavItem[] = [
  { key: "overview", label: "综合态势", caption: "Overview", icon: "grid" },
  { key: "patrol", label: "地块巡检", caption: "Patrol route", icon: "route" },
  { key: "pcr", label: "PCR 检测", caption: "Molecular assay", icon: "flask" },
  { key: "risk", label: "风险预警", caption: "Risk forecast", icon: "warning" },
  { key: "robot", label: "机器人状态", caption: "Robot monitor", icon: "robot" },
];

export const metricCards = [
  { label: "今日巡检面积", value: "12.6", unit: "亩", change: "+18.4%", tone: "teal", icon: "route" as IconName },
  { label: "有效采样点", value: "24", unit: "个", change: "+6 今日", tone: "blue", icon: "map" as IconName },
  { label: "孢子风险指数", value: "68", unit: "/100", change: "中风险", tone: "amber", icon: "pulse" as IconName },
  { label: "机器人电量", value: "86", unit: "%", change: "约 3.8 h", tone: "green", icon: "robot" as IconName },
];

export const forecast = [
  { day: "09/06", value: 42, label: "低" },
  { day: "09/07", value: 58, label: "中" },
  { day: "09/08", value: 68, label: "中" },
  { day: "09/09", value: 76, label: "较高" },
  { day: "09/10", value: 63, label: "中" },
  { day: "09/11", value: 51, label: "中" },
  { day: "09/12", value: 37, label: "低" },
];

export const sampleRows = [
  { id: "S-024", location: "东区 · 03 号垄", ct: "28.4", concentration: "1.82 × 10³", result: "阳性", tone: "high" },
  { id: "S-023", location: "东区 · 02 号垄", ct: "31.7", concentration: "4.26 × 10²", result: "关注", tone: "medium" },
  { id: "S-022", location: "西区 · 05 号垄", ct: "—", concentration: "未检出", result: "阴性", tone: "low" },
  { id: "S-021", location: "西区 · 03 号垄", ct: "29.8", concentration: "1.06 × 10³", result: "阳性", tone: "high" },
];

export const activities = [
  { time: "09:42:18", title: "采样点 S-024 已完成", detail: "东区 · 03 号垄 · Ct 28.4", tone: "teal" },
  { time: "09:38:06", title: "风险模型完成更新", detail: "未来 3 日 P90 风险上升至 76", tone: "amber" },
  { time: "09:31:44", title: "巡检路线进入返航段", detail: "当前任务进度 68%", tone: "blue" },
  { time: "09:18:22", title: "环境传感器数据同步", detail: "温度 26.8°C · 叶面湿度 72%", tone: "green" },
];

export const routePoints = [
  [94, 325],
  [170, 325],
  [170, 254],
  [284, 254],
  [284, 350],
  [412, 350],
  [412, 190],
  [554, 190],
  [554, 294],
  [672, 294],
  [672, 112],
] as const;

export const activityBars = [38, 52, 45, 68, 61, 76, 72, 86, 82, 91, 88, 96];
