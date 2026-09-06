import fs from "node:fs";
import path from "node:path";

const root = path.resolve(new URL("..", import.meta.url).pathname);
const artifacts = [
  { path: "release/desktop/穗巡-展示应用-0.1.0.exe", magic: "MZ", minimum: 1_000_000 },
  { path: "release/desktop/穗巡-展示应用-0.1.0-portable.exe", magic: "MZ", minimum: 1_000_000 },
  { path: "release/desktop/win-unpacked/穗巡.exe", magic: "MZ", minimum: 1_000_000 },
  { path: "release/desktop/win-unpacked/resources/app.asar", minimum: 10_000 },
  { path: "release/mobile/穗巡-展示应用-0.1.0-debug.apk", magic: "PK", minimum: 1_000_000 },
];

const failures = [];
for (const artifact of artifacts) {
  const fullPath = path.join(root, artifact.path);
  if (!fs.existsSync(fullPath)) {
    failures.push(`${artifact.path}：文件不存在`);
    continue;
  }
  const stat = fs.statSync(fullPath);
  if (!stat.isFile() || stat.size < artifact.minimum) {
    failures.push(`${artifact.path}：文件异常（${stat.size} bytes）`);
    continue;
  }
  if (artifact.magic) {
    const fd = fs.openSync(fullPath, "r");
    const buffer = Buffer.alloc(2);
    fs.readSync(fd, buffer, 0, 2, 0);
    fs.closeSync(fd);
    if (buffer.toString("ascii") !== artifact.magic) failures.push(`${artifact.path}：文件头无效`);
  }
  console.log(`✓ ${artifact.path} (${(stat.size / 1024 / 1024).toFixed(1)} MiB)`);
}

if (failures.length > 0) {
  console.error("交付物检查失败：\n- " + failures.join("\n- "));
  process.exit(1);
}

console.log("交付物检查通过：Windows 安装包、便携包、解包运行目录和 Android APK 均完整。 ");
