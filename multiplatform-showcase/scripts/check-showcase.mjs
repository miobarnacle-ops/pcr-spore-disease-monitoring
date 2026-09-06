import fs from "node:fs";
import path from "node:path";

const root = path.resolve(new URL("..", import.meta.url).pathname);
const read = (entry) => fs.readFileSync(path.join(root, entry), "utf8");
const required = [
  "dist/index.html",
  "dist/assets",
  "dist/brand/suixun-logo-selected-v1-transparent.png",
  "dist/brand/suixun-symbol-v1-transparent.png",
  "dist/brand/suixun.ico",
  "index.html",
  "src/App.tsx",
  "src/brand.ts",
  "desktop/main.cjs",
  "capacitor.config.ts",
  "android/app/build.gradle",
  "android/app/src/main/AndroidManifest.xml",
  "android/app/src/main/res/values/strings.xml",
  "docs/多端展示应用封装推进计划书-V1.0.md",
  "mobile/README.md",
];

const failures = required
  .filter((entry) => !fs.existsSync(path.join(root, entry)))
  .map((entry) => `缺少必要文件：${entry}`);

const distFiles = [];
function collectFiles(directory, matcher, output) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) collectFiles(fullPath, matcher, output);
    else if (matcher.test(entry.name)) output.push(fullPath);
  }
}
collectFiles(path.join(root, "dist"), /\.(html|js|css|json|map)$/i, distFiles);
const distText = distFiles.map((file) => fs.readFileSync(file, "utf8")).join("\n");

const sourceFiles = [];
collectFiles(path.join(root, "src"), /\.(ts|tsx|css|html)$/i, sourceFiles);
const sourceText = sourceFiles.map((file) => fs.readFileSync(file, "utf8")).join("\n");
for (const pattern of [/cmd_vel/i, /rosbridge/i, /ssh\s*:/i, /password/i, /passwd/i]) {
  if (pattern.test(sourceText)) failures.push(`源码包含真实控制或敏感词：${pattern}`);
}
for (const pattern of [/https?:\/\/(?!localhost|react\.dev\/errors|www\.w3\.org\/)/i]) {
  if (pattern.test(distText)) failures.push(`构建产物包含外部网络地址：${pattern}`);
}

const packageJson = JSON.parse(read("package.json"));
const brand = read("src/brand.ts");
const capacitor = read("capacitor.config.ts");
const gradle = read("android/app/build.gradle");
const manifest = read("android/app/src/main/AndroidManifest.xml");
const html = read("index.html");
const desktop = read("desktop/main.cjs");
const appSource = read("src/App.tsx");

const expectedVersion = packageJson.version;
if (!brand.includes(`version: "${expectedVersion}"`)) failures.push("品牌配置版本与 package.json 不一致");
if (!gradle.includes(`versionName "${expectedVersion}"`)) failures.push("Android versionName 与 package.json 不一致");
if (!capacitor.includes('appName: "穗巡"')) failures.push("Capacitor 应用名不是“穗巡”");
if (!manifest.includes('android:screenOrientation="portrait"')) failures.push("Android 主界面未锁定竖屏");
if (/uses-permission[^>]+INTERNET/.test(manifest)) failures.push("Android 展示包不应申请网络权限");
if (!html.includes("connect-src 'none'")) failures.push("页面 CSP 未禁用网络连接");
if (!desktop.includes('urls: ["http://*/*", "https://*/*", "ws://*/*", "wss://*/*"]')) failures.push("Electron 未拦截网络请求");
if (!desktop.includes('on("will-download"')) failures.push("Electron 未拦截下载");
if (!desktop.includes("contextIsolation: true") || !desktop.includes("nodeIntegration: false") || !desktop.includes("sandbox: true")) failures.push("Electron 渲染进程安全隔离配置不完整");
for (const expected of ['label: "首页"', 'label: "巡检"', 'label: "分析"', 'label: "项目"', "MobileAnalysis", "MobileAbout"]) {
  if (!appSource.includes(expected)) failures.push(`移动端信息架构不完整：${expected}`);
}
for (const expected of ["desktopDemoSequence", "mobileDemoSequence", "自动演示", "演示状态已重置"]) {
  if (!appSource.includes(expected)) failures.push(`可重复演示能力不完整：${expected}`);
}
if (!brand.includes('teamName: "穗巡项目团队"')) failures.push("正式团队名称未统一为“穗巡项目团队”");
if (appSource.includes('label="OFFLINE"') || appSource.includes("OFFLINE SHOWCASE")) failures.push("主展示界面仍突出显示 OFFLINE 标识");

if (failures.length > 0) {
  console.error("展示工程检查失败：\n- " + failures.join("\n- "));
  process.exit(1);
}

console.log(`展示工程检查通过：${distFiles.length} 个构建文件已检查，版本、竖屏、离线边界与移动端信息架构一致。`);
