# 穗巡多端展示应用

这是一个独立的离线展示工程，用于演示《穗巡》在 Windows PC 与 Android 手机上的多端产品形态。

当前版本不连接真实机器人、ROS、rosbridge、PCR 设备、数据库或外部网络；所有数据、路线、遥测和风险变化均来自本地演示数据。

## 快速开始

```bash
npm install
npm run dev
```

浏览器打开 Vite 地址后，宽屏显示桌面控制台，窄屏自动显示手机竖屏界面。启动时会先播放 Logo、DNA 轨迹与团队署名动画。

## 构建

```bash
npm run build
npm run check
npm run audit:security
npm run check:release
```

## 桌面端

```bash
npm run desktop:dev
npm run desktop:package
npm run desktop:portable
```

`desktop:package` 生成标准 NSIS 安装器，`desktop:portable` 生成可直接双击启动的单文件便携包；标准安装器需要 Windows 构建环境，或 Linux 环境中的 Wine/NSIS 工具链。

当前已生成标准安装器 `release/desktop/穗巡-展示应用-0.1.0.exe` 与便携包 `release/desktop/穗巡-展示应用-0.1.0-portable.exe`。

## Android 端

```bash
npm run mobile:sync
npm run mobile:apk
npm run mobile:open
```

需要本机具备 Android SDK、平台工具和 Gradle。`mobile/README.md` 中保留了移动端构建说明。

执行 `npx cap add android` 后生成的 `android/` 原生工程也属于本项目交付内容，已配置穗巡应用名、图标和启动页资源。
Android 主 Activity 已锁定为竖屏，适合手机端演示拍摄。
当前已生成 Android Debug APK：`release/mobile/穗巡-展示应用-0.1.0-debug.apk`，可直接用于本轮安装与视频展示。

移动端采用“首页 / 巡检 / 分析 / 项目”四页结构：首页展示核心遥测与 PCR 摘要，分析页提供 3/5/7 日风险趋势，项目页说明版本、团队和离线展示边界。

## 离线与安全边界

- 页面 CSP 禁止任何网络连接；Electron 外壳再次拦截 HTTP、HTTPS、WebSocket 和下载。
- Android 清单不申请网络权限。
- Electron 渲染进程开启上下文隔离与沙箱，不暴露 Node 能力。
- `npm run check` 自动核对版本、竖屏、品牌资源、移动端信息架构和离线边界。
- 本应用仅使用本地模拟数据，不连接或控制真实设备。

## 品牌素材

- 应用名称：穗巡
- 正式团队署名：穗巡项目团队
- 选定 Logo：`assets/brand/suixun-logo-selected-concept-v1.png`
- 工程透明版本：`assets/brand/suixun-logo-selected-v1-transparent.png`
- 图形标版本：`assets/brand/suixun-symbol-v1-transparent.png`

团队名称集中在 `src/brand.ts` 的 `BRAND.teamName` 中。
