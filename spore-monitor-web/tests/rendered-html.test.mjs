import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the inspection console", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>多模态农田孢子监测与病害扩散预警系统 V4\.0<\/title>/);
  assert.match(html, /多模态农田孢子监测与病害扩散预警系统 V4\.0/);
  assert.match(html, /路径规划/);
  assert.match(html, /机器人监控/);
  assert.match(html, /inspection-app/);
  assert.doesNotMatch(html, /Your site is taking shape|Building your site|codex-preview/);
});

test("keeps the current app shell and robot integration wired", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(layout, /title:\s*"多模态农田孢子监测与病害扩散预警系统 V4\.0"/);
  assert.match(layout, /<html lang="zh-CN">/);
  assert.match(page, /className="inspection-app"/);
  assert.match(page, /<RobotMonitorPanel/);
  assert.match(page, /routeDocument=\{robotRoute\}/);
  assert.match(page, /任务包 schema/);
  assert.match(packageJson, /"roslib":\s*"\^2\.1\.0"/);
});
