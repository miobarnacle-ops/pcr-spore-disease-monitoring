# Android 移动端

移动端使用 Capacitor 将 `dist` 中的竖屏展示界面封装为 Android 应用。

```bash
npm run mobile:sync
npm run mobile:apk
npm run mobile:open
```

执行前需要 Android SDK、平台工具和 Gradle。移动端页面在浏览器窄屏模式下也可以直接预览。
当前已生成 `release/mobile/穗巡-展示应用-0.1.0-debug.apk`，用于本轮安装与视频演示。顶部“导览”可自动切换四个核心页面，“项目”页可重置演示状态。
