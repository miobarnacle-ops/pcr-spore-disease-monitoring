# Windows 桌面端

桌面端使用 Electron 加载 `dist/index.html`，页面数据全部为本地演示数据。

```bash
npm run desktop:dev
npm run desktop:package
npm run desktop:portable
```

Windows 安装包默认输出到 `release/desktop`。当前已生成 `release/desktop/穗巡-展示应用-0.1.0-portable.exe`，可在 Windows 上直接双击；标准 NSIS 安装包在 Linux 环境需要 Wine/NSIS 或 Windows 构建环境。
