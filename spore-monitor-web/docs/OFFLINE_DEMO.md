# 离线演示包

本演示包不访问外网、不连接 rosbridge、不打开串口，也不会发布真实运动指令。

在本地控制台的“机器人监控”中：先在“路径规划”生成路线，再在“任务与遥测总线”中选择 Mock 并依次点击“载入规划任务”“启动模拟”。要展示回放，选择“载入回放”并打开 `tests/fixtures/contracts/replay-normal.json`。

故障演示由 `tests/fixtures/demo/offline-demo-scenarios.json` 定义：RTK 降级、低电量、障碍停车、采样失败及断联/恢复均通过 Mock 故障按钮触发。它们只代表软件模拟结果；“障碍停车”“软件停车”均不等同于物理急停或已完成实车安全验证。

统一执行两端检查：

```bash
cd /path/to/PCR
./verify_remote.sh
```

脚本会生成 `remote_quality_gate_summary.md`，并明确区分代码验证、模拟验证和待实机验证。
