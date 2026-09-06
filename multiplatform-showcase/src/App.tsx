import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  activities,
  activityBars,
  forecast,
  metricCards,
  navItems,
  routePoints,
  sampleRows,
  type IconName,
  type NavKey,
} from "./data";

import { BRAND } from "./brand";

const LOGO_SRC = BRAND.logoSrc;
const LOGO_MARK_SRC = BRAND.logoMarkSrc;
const TEAM_NAME = BRAND.teamName;

type MobileNavKey = "overview" | "patrol" | "analysis" | "about";

const desktopDemoSequence: Array<{ delay: number; page: NavKey; message: string }> = [
  { delay: 6500, page: "patrol", message: "自动导览 · 查看巡检路线" },
  { delay: 14500, page: "pcr", message: "自动导览 · 查看 PCR 检测" },
  { delay: 22500, page: "risk", message: "自动导览 · 查看风险预警" },
  { delay: 30500, page: "robot", message: "自动导览 · 查看机器人状态" },
  { delay: 38500, page: "overview", message: "自动导览完成 · 返回综合态势" },
];

const mobileDemoSequence: Array<{ delay: number; page: MobileNavKey; message: string }> = [
  { delay: 7000, page: "patrol", message: "自动导览 · 巡检路线" },
  { delay: 16000, page: "analysis", message: "自动导览 · 病害分析" },
  { delay: 27000, page: "about", message: "自动导览 · 项目能力" },
  { delay: 37000, page: "overview", message: "自动导览完成" },
];

const mobileItems: Array<{ key: MobileNavKey; label: string; icon: IconName }> = [
  { key: "overview", label: "首页", icon: "grid" },
  { key: "patrol", label: "巡检", icon: "route" },
  { key: "analysis", label: "分析", icon: "flask" },
  { key: "about", label: "项目", icon: "leaf" },
];

export function App() {
  const [booting, setBooting] = useState(true);
  const [mobile, setMobile] = useState(() => window.innerWidth <= 820);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = window.setTimeout(() => setBooting(false), reduceMotion ? 320 : 2850);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const handleResize = () => setMobile(window.innerWidth <= 820);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (booting) return <SplashScreen />;
  return mobile ? <MobileShell /> : <DesktopShell />;
}

function SplashScreen() {
  return (
    <main className="splash-screen">
      <div className="splash-grid" />
      <div className="splash-orbit splash-orbit-one" />
      <div className="splash-orbit splash-orbit-two" />
      <div className="spore-field" aria-hidden="true">
        {Array.from({ length: 18 }, (_, index) => (
          <i key={index} style={{ "--i": index } as CSSProperties} />
        ))}
      </div>
      <section className="splash-content">
        <div className="splash-logo-shell">
          <img src={LOGO_MARK_SRC} alt={BRAND.appName} className="splash-logo" />
          <span className="logo-scan-line" />
        </div>
        <p className="splash-kicker">SMART FIELD PATROL · PCR INSIGHT</p>
        <h1>{BRAND.appName}</h1>
        <p className="splash-subtitle">{BRAND.subtitle}</p>
        <div className="splash-team"><span /> {TEAM_NAME} <span /></div>
      </section>
      <div className="splash-progress"><span /></div>
      <p className="splash-footer">MULTIPLATFORM SHOWCASE / BUILD {BRAND.version}</p>
    </main>
  );
}

function DesktopShell() {
  const [active, setActive] = useState<NavKey>("overview");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(68);
  const [toast, setToast] = useState("");
  const [demoPlaying, setDemoPlaying] = useState(false);
  const [demoStage, setDemoStage] = useState(0);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      setProgress((current) => (current >= 100 ? 68 : current + 1));
    }, 1600);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!demoPlaying) return;
    setActive("overview");
    setProgress(68);
    setRunning(true);
    setDemoStage(1);
    setToast("自动导览已开始 · 全程约 40 秒");

    const timers = desktopDemoSequence.map((step, index) => window.setTimeout(() => {
      setActive(step.page);
      setDemoStage(Math.min(index + 2, 5));
      setToast(step.message);
    }, step.delay));
    const finishTimer = window.setTimeout(() => {
      setDemoPlaying(false);
      setRunning(false);
      setProgress(68);
      setDemoStage(0);
      setToast("自动导览已完成，可再次播放");
    }, 42000);

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      window.clearTimeout(finishTimer);
    };
  }, [demoPlaying]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  };

  const startPatrol = () => {
    if (demoPlaying) {
      setDemoPlaying(false);
      setRunning(false);
      setDemoStage(0);
      notify("自动导览已停止");
      return;
    }
    setDemoPlaying(true);
  };

  const resetDemo = () => {
    setDemoPlaying(false);
    setRunning(false);
    setProgress(68);
    setActive("overview");
    notify("演示状态已重置");
  };

  const togglePatrol = () => {
    if (demoPlaying) {
      setDemoPlaying(false);
      setDemoStage(0);
    }
    setRunning((current) => !current);
    notify(running ? "演示巡检已暂停" : "演示巡检任务已启动");
  };

  const navigateTo = (key: NavKey) => {
    if (demoPlaying) {
      setDemoPlaying(false);
      setRunning(false);
      setDemoStage(0);
    }
    setActive(key);
  };

  return (
    <div className="desktop-shell">
      <aside className="desktop-sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark"><img src={LOGO_MARK_SRC} alt="" /></div>
          <div><strong>{BRAND.appName}</strong><span>智能农田巡检平台</span></div>
        </div>
        <div className="sidebar-mode"><span className="live-dot" /> 演示模式</div>
        <nav className="desktop-nav" aria-label="主导航">
          <p className="nav-label">WORKSPACE</p>
          {navItems.map((item) => (
            <button key={item.key} className={active === item.key ? "active" : ""} onClick={() => navigateTo(item.key)} type="button">
              <Icon name={item.icon} />
              <span><b>{item.label}</b><small>{item.caption}</small></span>
              {active === item.key && <i className="nav-active-line" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-team"><span className="avatar">穗</span><span><b>{TEAM_NAME}</b><small>Demo workspace</small></span><Icon name="settings" /></div>
          <p className="sidebar-version">{BRAND.appName} SHOWCASE <span>v{BRAND.version}</span></p>
        </div>
      </aside>
      <main className="desktop-main" data-demo-state={demoPlaying ? "playing" : "idle"}>
        <header className="desktop-topbar">
          <div><span className="topbar-breadcrumb">WORKSPACE / {navItems.find((item) => item.key === active)?.caption.toUpperCase()}</span><h1>{navItems.find((item) => item.key === active)?.label}</h1></div>
          <div className="topbar-actions">
            <button type="button" className="icon-button" onClick={() => notify("暂无新的系统通知")} aria-label="通知"><Icon name="bell" /><i /></button>
            <div className="topbar-date"><span>数据更新时间</span><b>2026.09.06 · 09:42:18</b></div>
            {demoPlaying && <span className="demo-stage"><i style={{ width: `${demoStage * 20}%` }} />自动导览 {demoStage}/5</span>}
            <button type="button" className="ghost-button demo-reset" onClick={resetDemo}>重置</button>
            <button type="button" className="topbar-action" onClick={startPatrol} aria-pressed={demoPlaying}><Icon name="pulse" /> {demoPlaying ? "停止导览" : "自动演示"}</button>
          </div>
        </header>
        <div className="desktop-content">
          {active === "overview" && <OverviewPage running={running} progress={progress} onAction={notify} />}
          {active === "patrol" && <PatrolPage running={running} progress={progress} onAction={notify} onToggle={togglePatrol} />}
          {active === "pcr" && <PcrPage onAction={notify} />}
          {active === "risk" && <RiskPage onAction={notify} />}
          {active === "robot" && <RobotPage running={running} progress={progress} onAction={notify} />}
        </div>
      </main>
      {toast && <div className="toast"><span className="toast-check">✓</span>{toast}</div>}
    </div>
  );
}

function OverviewPage({ running, progress, onAction }: { running: boolean; progress: number; onAction: (message: string) => void }) {
  return (
    <div className="page-stack page-enter">
      <div className="hero-row">
        <div><p className="eyebrow">今日巡检概览 · 09/06</p><h2>早上好，{BRAND.appName}正在守护田间。</h2><p className="hero-copy">从路线规划到孢子风险预警，当前共有 3 个数据链路处于稳定状态。</p></div>
        <div className="hero-status"><span className="pulse-ring"><i /></span><span><b>巡检系统正常</b><small>所有演示模块已就绪</small></span></div>
      </div>
      <div className="metric-grid">
        {metricCards.map((card) => <MetricCard key={card.label} {...card} />)}
      </div>
      <div className="overview-grid">
        <section className="panel map-panel">
          <PanelHeading eyebrow="FIELD MONITOR" title="实时巡检地图" action={<button className="ghost-button" type="button" onClick={() => onAction("已切换至全屏地图视图")}>全屏查看 <Icon name="arrow" /></button>} />
          <div className="map-meta"><span><i className="legend-dot route-dot" />当前路线 <b>东区 03 号地块</b></span><span><i className="legend-dot robot-dot" />机器人 <b>SP-01</b></span><span className="map-coord">局部坐标 ENU · 0.05 m</span></div>
          <RouteMap progress={progress} running={running} />
          <div className="map-footer"><span><i className="legend-line" />已完成路线 <b>{progress}%</b></span><span><i className="legend-outline" />待巡检区域 <b>4.2 亩</b></span><span className="map-footer-right">最后定位 <b>09:42:18</b></span></div>
        </section>
        <section className="panel activity-panel">
          <PanelHeading eyebrow="LIVE FEED" title="动态事件" action={<button className="text-button" type="button" onClick={() => onAction("已刷新事件流")}>刷新</button>} />
          <div className="activity-list">{activities.map((activity) => <ActivityItem key={activity.time} {...activity} />)}</div>
          <div className="activity-summary"><span>今日事件</span><b>18</b><small>+4 较昨日</small><div className="mini-bars">{activityBars.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div></div>
        </section>
      </div>
      <div className="bottom-grid">
        <section className="panel trend-panel"><PanelHeading eyebrow="RISK TREND" title="未来 7 日风险趋势" action={<button className="text-button" type="button" onClick={() => onAction("已打开风险趋势详情")}>查看详情 <Icon name="arrow" /></button>} /><RiskChart compact /></section>
        <section className="panel mission-panel"><PanelHeading eyebrow="MISSION STATUS" title="当前任务" action={<StatusPill label={running ? "执行中" : "待机"} tone={running ? "green" : "blue"} />} /><div className="mission-card"><div className="mission-title"><span className="mission-icon"><Icon name="route" /></span><span><b>东区孢子病害巡检</b><small>任务编号 SX-20260906-01</small></span><i>68%</i></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><div className="mission-details"><span>已采样 <b>6 / 9</b></span><span>预计完成 <b>10:16</b></span><span>剩余路程 <b>148 m</b></span></div></div><button className="panel-link" type="button" onClick={() => onAction("已打开任务详情")}>查看任务详情 <Icon name="arrow" /></button></section>
      </div>
    </div>
  );
}

function PatrolPage({ running, progress, onAction, onToggle }: { running: boolean; progress: number; onAction: (message: string) => void; onToggle: () => void }) {
  return (
    <div className="page-stack page-enter">
      <PageIntro eyebrow="AUTONOMOUS PATROL" title="地块巡检任务" copy="路线、采样点与机器人轨迹统一呈现，当前使用本地演示数据。" action={<button className="primary-button" type="button" onClick={onToggle} aria-pressed={running}><Icon name="pulse" />{running ? "暂停任务" : "开始任务"}</button>} />
      <div className="patrol-layout"><section className="panel patrol-map-panel"><div className="panel-topline"><div><p className="eyebrow">ROUTE_V1 / LOCAL_ENU</p><h3>东区 · 03 号地块</h3></div><StatusPill label={running ? "巡检中" : "已规划"} tone={running ? "green" : "blue"} /></div><RouteMap progress={progress} running={running} large /><div className="route-stats"><Stat label="路线长度" value="426 m" /><Stat label="采样点" value="9 个" /><Stat label="预计用时" value="34 min" /><Stat label="安全状态" value="正常" tone="green" /></div></section><section className="panel route-plan-panel"><PanelHeading eyebrow="MISSION STEPS" title="任务流程" /><div className="step-list"><Step number="01" title="路线校验" detail="边界与坐标系检查通过" done /><Step number="02" title="自主巡检" detail={running ? "SP-01 正在沿规划路线移动" : "等待启动演示任务"} active={running} /><Step number="03" title="定点采样" detail="共 9 个采样点，驻留 2 s" /><Step number="04" title="风险分析" detail="PCR 与环境数据融合" /><Step number="05" title="生成报告" detail="巡检结束后自动归档" /></div><div className="route-callout"><Icon name="leaf" /><span><b>路线策略</b><small>Pure Pursuit · 0.12 m/s · 前方 90° 障碍检测</small></span></div><button className="panel-link" type="button" onClick={() => onAction("route_v1.json 已准备导出")}>导出 route_v1.json <Icon name="arrow" /></button></section></div>
    </div>
  );
}

function PcrPage({ onAction }: { onAction: (message: string) => void }) {
  return (
    <div className="page-stack page-enter">
      <PageIntro eyebrow="MOLECULAR ASSAY" title="PCR 检测分析" copy="将 Ct 值、浓度估计与样本位置绑定，形成可追溯的田间检测记录。" action={<button className="primary-button" type="button" onClick={() => onAction("已生成 PCR 演示报告")}><Icon name="arrow" />导出分析报告</button>} />
      <div className="pcr-kpi-grid"><Kpi label="今日样本" value="24" unit="份" trend="+6" /><Kpi label="阳性样本" value="07" unit="份" trend="29.2%" tone="amber" /><Kpi label="平均 Ct" value="29.8" unit="Ct" trend="稳定" /><Kpi label="数据质量" value="96.4" unit="%" trend="优" tone="green" /></div>
      <div className="pcr-layout"><section className="panel table-panel"><PanelHeading eyebrow="SAMPLE TRACE" title="最新样本记录" action={<button className="text-button" type="button" onClick={() => onAction("样本列表已刷新")}>刷新数据</button>} /><div className="data-table"><div className="table-head"><span>样本编号</span><span>采样位置</span><span>Ct 值</span><span>浓度估计</span><span>判定</span></div>{sampleRows.map((row) => <div className="table-row" key={row.id}><b>{row.id}</b><span>{row.location}</span><span>{row.ct}</span><span>{row.concentration}</span><StatusPill label={row.result} tone={row.tone === "high" ? "red" : row.tone === "medium" ? "amber" : "green"} /></div>)}</div></section><section className="panel pcr-chart-panel"><PanelHeading eyebrow="CONCENTRATION" title="样本浓度分布" /><div className="concentration-chart">{[44, 66, 52, 78, 58, 32, 46, 70, 88, 57, 72, 49].map((height, index) => <div key={index}><i style={{ height: `${height}%` }} /><small>{index + 1}</small></div>)}</div><div className="chart-legend"><span><i className="legend-dot high-dot" />阳性样本</span><span><i className="legend-dot low-dot" />低风险样本</span></div><div className="assay-note"><Icon name="flask" /><span><b>检测流程完整</b><small>标准曲线、LOD、离群值与多点融合均已纳入演示数据。</small></span></div></section></div>
    </div>
  );
}

function RiskPage({ onAction }: { onAction: (message: string) => void }) {
  return (
    <div className="page-stack page-enter">
      <PageIntro eyebrow="EARLY WARNING" title="风险趋势预警" copy="融合 PCR、气象、叶面湿度与孢子传播模型，查看未来 3/5/7 天风险变化。" action={<button className="primary-button" type="button" onClick={() => onAction("风险模型已重新计算")}><Icon name="pulse" />重新计算</button>} />
      <div className="risk-hero"><div className="risk-gauge"><div className="gauge-inner"><span>68</span><small>当前指数</small></div></div><div className="risk-hero-copy"><p className="eyebrow">CURRENT RISK LEVEL</p><h3>中风险 · 建议加强巡检</h3><p>东区 03 号地块在未来 72 小时存在孢子累积窗口，建议优先复核 03、04 号采样点。</p><div className="risk-tags"><span>孢子负荷 1.82×10³</span><span>叶面湿度 72%</span><span>风向 NE · 2.4 m/s</span></div></div><div className="risk-hero-stat"><span>峰值预测</span><b>76</b><small>09/09 · 14:00</small></div></div>
      <div className="risk-layout"><section className="panel risk-chart-panel"><PanelHeading eyebrow="7-DAY FORECAST" title="地块风险趋势" action={<button className="text-button" type="button" onClick={() => onAction("已切换至 7 日预测")}>7 日预测 <Icon name="chevron" /></button>} /><RiskChart /></section><section className="panel warning-panel"><PanelHeading eyebrow="ACTION CENTER" title="处置建议" /><div className="warning-card critical"><span className="warning-symbol">!</span><div><b>优先复核东区 03 号垄</b><p>检测到 PCR 阳性样本，建议 24 小时内进行二次采样。</p></div></div><div className="warning-card"><span className="warning-symbol">i</span><div><b>关注叶面湿度变化</b><p>当前湿度接近感染窗口阈值，保持 2 小时巡检频率。</p></div></div><button className="panel-link" type="button" onClick={() => onAction("已生成风险处置清单")}>生成处置清单 <Icon name="arrow" /></button></section></div>
    </div>
  );
}

function RobotPage({ running, progress, onAction }: { running: boolean; progress: number; onAction: (message: string) => void }) {
  return (
    <div className="page-stack page-enter">
      <PageIntro eyebrow="ROBOT MONITOR" title="机器人状态" copy="当前为只读演示模式，界面模拟车端遥测与任务状态，不发送运动控制指令。" action={<button className="ghost-button large" type="button" onClick={() => onAction("已打开设备详情")}>设备详情 <Icon name="arrow" /></button>} />
      <div className="robot-layout"><section className="panel robot-visual-panel"><div className="robot-visual-header"><div><p className="eyebrow">SP-01 / R550 PLUS</p><h3>自主巡检车</h3></div><StatusPill label={running ? "MISSION ACTIVE" : "STANDBY"} tone={running ? "green" : "blue"} /></div><div className="robot-stage"><div className="radar-grid"><span /><span /><span /><span /><i className={running ? "radar-sweep running" : "radar-sweep"} /></div><div className="robot-card-illustration"><div className="robot-head"><i /><i /></div><div className="robot-body"><span /><b /></div><div className="robot-wheel wheel-left" /><div className="robot-wheel wheel-right" /></div><div className="robot-path-lines"><i /><i /><i /></div></div><div className="telemetry-row"><Telemetry label="电量" value="86%" tone="green" /><Telemetry label="线速度" value={running ? "0.12 m/s" : "0.00 m/s"} /><Telemetry label="定位" value="EKF / SLAM" /><Telemetry label="激光雷达" value="11.3 Hz" tone="green" /></div></section><section className="panel robot-event-panel"><PanelHeading eyebrow="SYSTEM HEALTH" title="系统状态" /><div className="health-list"><Health label="底盘通信" detail="20 Hz · 稳定" tone="green" /><Health label="EKF 里程计" detail="/odometry/filtered" tone="green" /><Health label="SLAM 地图" detail="map → odom" tone="green" /><Health label="采样器" detail="演示状态 · 待机" tone="blue" /><Health label="GNSS / RTK" detail="演示数据 · 普通 GNSS" tone="amber" /></div><div className="robot-mini-task"><div><span>当前任务进度</span><b>{progress}%</b></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><small>采样点 6 / 9 · 剩余路程 148 m</small></div><button className="panel-link" type="button" onClick={() => onAction("实时遥测面板已刷新")}>刷新遥测 <Icon name="arrow" /></button></section></div>
    </div>
  );
}

function MobileShell() {
  const [active, setActive] = useState<MobileNavKey>("overview");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(68);
  const [toast, setToast] = useState("");
  const [demoPlaying, setDemoPlaying] = useState(false);
  const [demoStage, setDemoStage] = useState(0);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setProgress((current) => (current >= 100 ? 68 : current + 1)), 1700);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!demoPlaying) return;
    setActive("overview");
    setProgress(68);
    setRunning(true);
    setDemoStage(1);
    setToast("自动导览已开始 · 约 40 秒");
    window.history.replaceState({ ...window.history.state, suixunPage: "overview" }, "");

    const timers = mobileDemoSequence.map((step, index) => window.setTimeout(() => {
      setActive(step.page);
      setDemoStage(Math.min(index + 2, 4));
      setToast(step.message);
      window.history.replaceState({ ...window.history.state, suixunPage: step.page }, "");
    }, step.delay));
    const finishTimer = window.setTimeout(() => {
      setDemoPlaying(false);
      setRunning(false);
      setProgress(68);
      setDemoStage(0);
      setToast("自动导览已完成，可再次播放");
    }, 40500);

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      window.clearTimeout(finishTimer);
    };
  }, [demoPlaying]);

  useEffect(() => {
    const validKeys = new Set<MobileNavKey>(mobileItems.map((item) => item.key));
    const handlePopState = (event: PopStateEvent) => {
      const next = event.state?.suixunPage;
      setActive(validKeys.has(next) ? next : "overview");
    };

    window.history.replaceState({ ...window.history.state, suixunPage: "overview" }, "");
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2300);
  };

  const navigateTo = (key: MobileNavKey) => {
    if (key === active) return;
    if (demoPlaying) {
      setDemoPlaying(false);
      setRunning(false);
      setDemoStage(0);
    }
    setActive(key);
    window.history.pushState({ ...window.history.state, suixunPage: key }, "");
  };

  const resetDemo = () => {
    setDemoPlaying(false);
    setRunning(false);
    setProgress(68);
    setDemoStage(0);
    setActive("overview");
    window.history.replaceState({ ...window.history.state, suixunPage: "overview" }, "");
    notify("演示状态已重置");
  };

  const toggleMobilePatrol = () => {
    if (demoPlaying) {
      setDemoPlaying(false);
      setDemoStage(0);
    }
    setRunning((current) => !current);
    notify(running ? "演示巡检已暂停" : "演示巡检已启动");
  };

  return (
    <div className="mobile-shell" data-demo-state={demoPlaying ? "playing" : "idle"}>
      <header className="mobile-header"><div className="mobile-brand"><div className="mobile-mark"><img src={LOGO_MARK_SRC} alt="" /></div><span><b>{BRAND.appName}</b><small>智能农田巡检</small></span></div><div className="mobile-header-actions">{demoPlaying && <span className="mobile-demo-stage">{demoStage}/4</span>}<button className={`mobile-auto ${demoPlaying ? "active" : ""}`} type="button" onClick={() => { if (demoPlaying) { setDemoPlaying(false); setRunning(false); setDemoStage(0); notify("自动导览已停止"); } else { setDemoPlaying(true); } }} aria-pressed={demoPlaying}><Icon name="pulse" />{demoPlaying ? "停止" : "导览"}</button><button className="mobile-bell" type="button" onClick={() => notify("暂无新的系统通知")} aria-label="通知"><Icon name="bell" /><i /></button></div></header>
      <main className="mobile-content">
        {active === "overview" && <MobileHome running={running} progress={progress} onAction={notify} onToggle={() => { setRunning((current) => !current); notify(running ? "演示巡检已暂停" : "演示巡检已启动"); }} />}
        {active === "patrol" && <MobilePatrol running={running} progress={progress} onAction={notify} onToggle={toggleMobilePatrol} />}
        {active === "analysis" && <MobileAnalysis onAction={notify} />}
        {active === "about" && <MobileAbout onAction={notify} onReset={resetDemo} />}
      </main>
      <nav className="mobile-nav" aria-label="移动端主导航">{mobileItems.map((item) => <button key={item.key} className={active === item.key ? "active" : ""} type="button" onClick={() => navigateTo(item.key)} aria-current={active === item.key ? "page" : undefined}><Icon name={item.icon} /><span>{item.label}</span></button>)}</nav>
      {toast && <div className="toast mobile-toast"><span className="toast-check">✓</span>{toast}</div>}
    </div>
  );
}

function MobileHome({ running, progress, onAction, onToggle }: { running: boolean; progress: number; onAction: (message: string) => void; onToggle: () => void }) {
  return <div className="mobile-page page-enter"><div className="mobile-greeting"><div><p className="eyebrow">09/06 · TODAY</p><h1>早上好，{BRAND.appName}。</h1><p>田间数据正在持续汇聚</p></div><span className="mobile-status"><i />正常</span></div><div className="mobile-risk-card"><div><p>当前孢子风险</p><strong>68</strong><span>/100 · 中风险</span></div><div className="mobile-risk-ring"><i /></div><small>峰值预测 76 · 09/09</small></div><div className="mobile-section-heading"><span>核心数据</span><button type="button" onClick={() => onAction("已刷新首页数据")}>刷新</button></div><div className="mobile-stat-grid"><MiniMetric label="机器人电量" value="86" unit="%" /><MiniMetric label="环境温度" value="26.8" unit="°C" /><MiniMetric label="叶面湿度" value="72" unit="%" /><MiniMetric label="待处理预警" value="2" unit="项" /></div><section className="mobile-card mobile-pcr-peek"><span className="mobile-pcr-icon"><Icon name="flask" /></span><span><small>PCR 最新结果 · S-024</small><b>东区 03 号垄 · Ct 28.4</b></span><StatusPill label="阳性" tone="red" /></section><section className="mobile-card mobile-mission-card"><div className="mobile-card-heading"><span className="small-icon teal"><Icon name="route" /></span><span><b>东区孢子病害巡检</b><small>SX-20260906-01 · SP-01</small></span><StatusPill label={running ? "执行中" : "待机"} tone={running ? "green" : "blue"} /></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><div className="mobile-mission-bottom"><span>{progress}% 已完成</span><button type="button" onClick={onToggle}>{running ? "暂停" : "启动演示"}<Icon name="arrow" /></button></div></section><section className="mobile-card mobile-map-card"><div className="mobile-card-heading"><span><b>实时巡检地图</b><small>SP-01 · 东区 03 号地块</small></span><button className="card-more" type="button" onClick={() => onAction("地图已放大")}>···</button></div><RouteMap progress={progress} running={running} mobile /></section><div className="mobile-section-heading"><span>最新动态</span><button type="button" onClick={() => onAction("已打开全部动态")}>全部</button></div><div className="mobile-activity-list">{activities.slice(0, 2).map((activity) => <ActivityItem key={activity.time} {...activity} compact />)}</div></div>;
}

function MobilePatrol({ running, progress, onAction, onToggle }: { running: boolean; progress: number; onAction: (message: string) => void; onToggle: () => void }) {
  return <div className="mobile-page page-enter"><MobilePageTitle eyebrow="PATROL ROUTE" title="地块巡检" action={<StatusPill label={running ? "巡检中" : "已规划"} tone={running ? "green" : "blue"} />} /><section className="mobile-card mobile-map-card tall"><div className="mobile-card-heading"><span><b>东区 · 03 号地块</b><small>route_v1 · local_enu</small></span><button className="card-more" type="button" onClick={() => onAction("路线详情已打开")}>···</button></div><RouteMap progress={progress} running={running} mobile large /></section><div className="mobile-stat-grid three"><MiniMetric label="路线长度" value="426" unit="m" /><MiniMetric label="采样点" value="9" unit="个" /><MiniMetric label="剩余路程" value="148" unit="m" /></div><button className="mobile-primary-action" type="button" onClick={onToggle} aria-pressed={running}><Icon name="pulse" />{running ? "暂停巡检演示" : "启动巡检演示"}</button><section className="mobile-card"><div className="mobile-section-heading inner"><span>任务流程</span><button type="button" onClick={() => onAction("已导出路线文件")}>导出</button></div><div className="mobile-step-list"><Step number="01" title="路线校验" detail="边界检查通过" done /><Step number="02" title="自主巡检" detail={running ? "机器人执行中" : "等待启动"} active={running} /><Step number="03" title="定点采样" detail="9 个采样点" /></div></section></div>;
}

function MobileAnalysis({ onAction }: { onAction: (message: string) => void }) {
  const [days, setDays] = useState<3 | 5 | 7>(7);
  return <div className="mobile-page page-enter"><MobilePageTitle eyebrow="PCR & RISK" title="病害分析" action={<button className="mobile-text-action" type="button" onClick={() => onAction("分析数据已更新")}>更新</button>} /><section className="mobile-card mobile-assay-card"><div className="mobile-section-heading inner"><span>PCR 最新判定</span><StatusPill label="阳性" tone="red" /></div><div className="mobile-assay-result"><div><small>样本编号</small><b>S-024</b></div><div><small>Ct 值</small><b>28.4</b></div><div><small>浓度估计</small><b>1.82×10³</b></div></div><p>东区 03 号垄 · 建议 24 小时内二次采样</p></section><div className="mobile-risk-card expanded"><div><p>东区 03 号地块</p><strong>68</strong><span>中风险 · 建议加强巡检</span></div><div className="mobile-risk-ring"><i /></div><small>未来 72 小时存在孢子累积窗口</small></div><section className="mobile-card"><div className="mobile-section-heading inner"><span>{days} 日风险趋势</span><div className="forecast-switch" aria-label="预测周期">{([3, 5, 7] as const).map((value) => <button key={value} className={days === value ? "active" : ""} type="button" onClick={() => setDays(value)}>{value}D</button>)}</div></div><RiskChart compact mobile days={days} /></section><section className="mobile-card mobile-warning-card"><span className="warning-symbol">!</span><div><b>优先复核东区 03 号垄</b><p>PCR 阳性样本 S-024，建议安排二次采样并持续观察叶面湿度。</p></div></section></div>;
}

function MobileAbout({ onAction, onReset }: { onAction: (message: string) => void; onReset: () => void }) {
  return <div className="mobile-page page-enter"><MobilePageTitle eyebrow="PROJECT PROFILE" title="关于项目" action={<StatusPill label="演示模式" tone="green" />} /><section className="mobile-card mobile-about-hero"><img src={LOGO_SRC} alt={`${BRAND.appName} Logo`} /><div><h2>{BRAND.appName}</h2><p>{BRAND.subtitle}</p><span>{TEAM_NAME}</span></div></section><section className="mobile-card mobile-about-list"><div><span>应用版本</span><b>v{BRAND.version}</b></div><div><span>运行模式</span><b>本地展示</b></div><div><span>产品形态</span><b>Windows · Android</b></div><div><span>数据来源</span><b>本地模拟数据</b></div></section><section className="mobile-card"><div className="mobile-section-heading inner"><span>展示能力</span><button type="button" onClick={() => onAction("项目能力清单已展开")}>详情</button></div><div className="capability-tags"><span>智能巡检</span><span>PCR 分析</span><span>风险预警</span><span>机器人状态</span></div></section><button className="mobile-secondary-action" type="button" onClick={onReset}>重置演示状态</button><section className="mobile-about-note"><Icon name="leaf" /><p>本应用仅用于项目展示，不连接真实设备或发送控制指令。</p></section></div>;
}

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    route: <><path d="M4 18c2.1-5.4 4.4-8.1 7.1-8.1 2.8 0 3.4 3.7 6.8 3.7 1.2 0 2-.5 2.6-1.6" /><circle cx="4" cy="18" r="1.5" /><circle cx="20.5" cy="8" r="1.5" /></>,
    flask: <><path d="M9 3h6" /><path d="M10 3v6.2l-5.4 8.6A2.1 2.1 0 0 0 6.4 21h11.2a2.1 2.1 0 0 0 1.8-3.2L14 9.2V3" /><path d="M7.7 15h8.6" /></>,
    warning: <><path d="m12 3 9 17H3L12 3Z" /><path d="M12 9v4.2" /><circle cx="12" cy="16.5" r=".8" fill="currentColor" stroke="none" /></>,
    robot: <><rect x="5" y="7" width="14" height="12" rx="3" /><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8" /><path d="M3 11v4M21 11v4" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-2.6V20a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H4v-2.6h.2a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V4h2.6v.2a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v2.6h-.2a1.7 1.7 0 0 0-1.6 1Z" /></>,
    arrow: <><path d="M4 12h15" /><path d="m13 6 6 6-6 6" /></>,
    leaf: <><path d="M20 4c-7.7.2-13.2 2.2-15.4 6.3C2.9 13.4 4.8 17 8 17c4.4 0 7.2-4.8 8.7-9.5" /><path d="M4 20c2.8-4.3 6.2-6.9 10.4-8.1" /></>,
    map: <><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" /><path d="M9 3v15M15 6v15" /></>,
    pulse: <><path d="M3 12h4l2.3-6 4.3 12 2.2-6H21" /></>,
    chevron: <path d="m9 6 6 6-6 6" />,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function MetricCard({ label, value, unit, change, tone, icon }: { label: string; value: string; unit: string; change: string; tone: string; icon: IconName }) {
  return <article className={`metric-card ${tone}`}><div className="metric-card-top"><span>{label}</span><i><Icon name={icon} /></i></div><div className="metric-card-value"><b>{value}</b><span>{unit}</span></div><div className="metric-card-change"><Icon name="arrow" />{change}</div></article>;
}

function PanelHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) {
  return <div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div>{action}</div>;
}

function PageIntro({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy: string; action: ReactNode }) {
  return <div className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{copy}</p></div>{action}</div>;
}

function MobilePageTitle({ eyebrow, title, action }: { eyebrow: string; title: string; action: ReactNode }) {
  return <div className="mobile-page-title"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>{action}</div>;
}

function RouteMap({ progress, running, large = false, mobile = false }: { progress: number; running: boolean; large?: boolean; mobile?: boolean }) {
  const path = routePoints.map(([x, y]) => `${x},${y}`).join(" ");
  const activePoint = routePoints[Math.min(routePoints.length - 1, Math.floor((progress / 100) * routePoints.length))];
  return <div className={`route-map ${large ? "large" : ""} ${mobile ? "mobile-map" : ""}`}><svg viewBox="0 0 760 440" role="img" aria-label="东区地块巡检路线示意图"><defs><pattern id="map-grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#284149" strokeWidth=".8" opacity=".45" /></pattern><linearGradient id="field-a" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#163b37" /><stop offset="1" stopColor="#102925" /></linearGradient><linearGradient id="field-b" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#1f493b" /><stop offset="1" stopColor="#142f2d" /></linearGradient><filter id="route-glow"><feGaussianBlur stdDeviation="4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs><rect width="760" height="440" fill="#0c1b21" /><rect width="760" height="440" fill="url(#map-grid)" /><path d="M25 55 165 32l89 44-20 298-183 30-46-132Z" fill="url(#field-a)" stroke="#34655a" strokeWidth="2" /><path d="m286 57 182-18 80 43-5 316-263-24Z" fill="url(#field-b)" stroke="#3b6d5c" strokeWidth="2" /><path d="m575 74 147 20 20 283-157 17Z" fill="#173a35" stroke="#376357" strokeWidth="2" /><path d="M78 109h118M69 155h141M60 201h149M53 248h156M45 295h165M348 94h120M330 145h145M329 199h146M327 253h148M322 308h154M321 360h149M610 132h100M612 184h100M612 236h103M612 288h104" stroke="#5b9b65" strokeWidth="3" opacity=".5" strokeLinecap="round" /><path d="M25 362h693" stroke="#89b8ad" strokeWidth="1" strokeDasharray="5 7" opacity=".35" /><polyline points={path} fill="none" stroke="#00e0bb" strokeWidth="11" opacity=".12" filter="url(#route-glow)" /><polyline points={path} fill="none" stroke="#00d3b1" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${Math.max(0, progress)} 1000`} /><polyline points={path} fill="none" stroke="#617c85" strokeWidth="2" strokeDasharray="5 8" strokeLinecap="round" strokeLinejoin="round" opacity=".9" /><g className="route-points">{routePoints.slice(1, -1).map(([x, y], index) => <g key={`${x}-${y}`}><circle cx={x} cy={y} r="7" fill="#132c31" stroke={index < Math.floor(progress / 12) ? "#00d3b1" : "#78969a"} strokeWidth="2" /><circle cx={x} cy={y} r="2" fill={index < Math.floor(progress / 12) ? "#00d3b1" : "#78969a"} /></g>)}</g><g className={`map-robot ${running ? "moving" : ""}`} transform={`translate(${activePoint[0]} ${activePoint[1]})`}><circle r="22" fill="#00d3b1" opacity=".13" /><circle r="12" fill="#0e2327" stroke="#6effd9" strokeWidth="2" /><path d="M-4 0h8M0-4v8" stroke="#baffef" strokeWidth="1.5" /></g><g className="map-pin" transform="translate(672 112)"><path d="M0-20c-9 0-16 7-16 16 0 12 16 27 16 27S16 8 16-4C16-13 9-20 0-20Z" fill="#f3a832" stroke="#ffe5a1" strokeWidth="2" /><circle cy="-4" r="5" fill="#502f13" /></g><text x="45" y="42" fill="#91b7ae" fontSize="12" letterSpacing="2">FIELD 03</text><text x="624" y="407" fill="#80a5a4" fontSize="11">N</text><path d="m630 424 0-15m0 0-4 6m4-6 4 6" stroke="#80a5a4" strokeWidth="1.5" /></svg><div className="map-scale"><span>0</span><i /><span>100 m</span></div></div>;
}

function ActivityItem({ time, title, detail, tone, compact = false }: { time: string; title: string; detail: string; tone: string; compact?: boolean }) {
  return <div className={`activity-item ${compact ? "compact" : ""}`}><span className={`activity-dot ${tone}`} /><div><b>{title}</b><small>{detail}</small></div><time>{time}</time></div>;
}

function RiskChart({ compact = false, mobile = false, days = 7 }: { compact?: boolean; mobile?: boolean; days?: 3 | 5 | 7 }) {
  const visibleForecast = forecast.slice(0, days);
  const step = visibleForecast.length > 1 ? 468 / (visibleForecast.length - 1) : 0;
  const points = visibleForecast.map((item, index) => `${index * step + 22},${170 - item.value * 1.55}`).join(" ");
  return <div className={`risk-chart ${compact ? "compact" : ""} ${mobile ? "mobile-chart" : ""}`}><svg viewBox="0 0 500 190" preserveAspectRatio="none"><defs><linearGradient id="risk-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#f3a832" stopOpacity=".32" /><stop offset="1" stopColor="#f3a832" stopOpacity="0" /></linearGradient></defs><path d="M20 150H490M20 105H490M20 60H490" stroke="#29434a" strokeWidth="1" strokeDasharray="4 6" /><polygon points={`22,170 ${points} 490,170`} fill="url(#risk-area)" /><polyline points={points} fill="none" stroke="#f3b34c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />{visibleForecast.map((item, index) => <g key={item.day}><circle cx={index * step + 22} cy={170 - item.value * 1.55} r="4.5" fill="#102229" stroke="#f6c86e" strokeWidth="2" /><text x={index * step + 22} y="187" textAnchor="middle" fill="#779198" fontSize="9">{item.day.slice(3)}</text></g>)}</svg><div className="chart-scale"><span>80</span><span>40</span><span>0</span></div></div>;
}

function StatusPill({ label, tone }: { label: string; tone: string }) {
  return <span className={`status-pill ${tone}`}><i />{label}</span>;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className="route-stat"><span>{label}</span><b className={tone}>{value}</b></div>;
}

function Step({ number, title, detail, done = false, active = false }: { number: string; title: string; detail: string; done?: boolean; active?: boolean }) {
  return <div className={`step ${done ? "done" : ""} ${active ? "active" : ""}`}><span className="step-number">{done ? "✓" : number}</span><span><b>{title}</b><small>{detail}</small></span></div>;
}

function Kpi({ label, value, unit, trend, tone = "blue" }: { label: string; value: string; unit: string; trend: string; tone?: string }) {
  return <div className={`pcr-kpi ${tone}`}><span>{label}</span><b>{value}<small>{unit}</small></b><em>{trend}</em></div>;
}

function Telemetry({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className="telemetry"><span>{label}</span><b className={tone}>{value}</b></div>;
}

function Health({ label, detail, tone }: { label: string; detail: string; tone: string }) {
  return <div className="health-item"><i className={tone} /><span><b>{label}</b><small>{detail}</small></span><Icon name="chevron" /></div>;
}

function MiniMetric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return <div className="mini-metric"><span>{label}</span><b>{value}<small>{unit}</small></b></div>;
}
