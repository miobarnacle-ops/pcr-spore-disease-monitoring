# ROS 路线 JSON 与网页验证说明

## 导出

在“路径规划”完成边界闭合和路线求解后，使用：

- `校验 ROS 路线`：生成路线并显示错误、警告和统计；
- `导出 ROS 路线 JSON`：仅在没有阻断错误时下载 `route_v1.json`；
- 原有“导出路径规划 JSON”和 Ctrl+S 也会输出同一版本的米制路线。

## 坐标约定

路线使用 `field/local_enu` 米制坐标：

- 原点：第一个边界点；
- `+X`：第一个边界边方向；
- `+Y`：指向田块内部的一侧；
- `field_polygon_m`、`sampling_points` 和 `path` 使用同一坐标系；
- 车辆端还需要根据实车起始位姿将 `field` 转换为 ROS `map` 或 `odom`。

路线文档的顶层固定字段必须包含：

```json
{
  "schema_version": "1.0",
  "frame_id": "field",
  "coordinate_type": "local_enu",
  "unit": "m"
}
```

`meta` 只保存地块、地图和路线的标识信息（`field_id`、`map_id`、`map_version`、`route_id`）以及 `y_axis_positive`，不重复保存坐标协议字段。车辆端解析器直接读取上述顶层字段。

网页内部的画布像素点会在导出时旋转、缩放并转换，不能再直接把 `route_segments[].waypoints` 当作 ROS 航点使用。

## 航点字段

每个航点包括：

```json
{
  "seq": 0,
  "x_m": 1.2,
  "y_m": 0.8,
  "yaw_rad": null,
  "type": "sampling",
  "round": 1,
  "sample_id": "R1-P1",
  "speed_limit_mps": 0.12,
  "tolerance_m": 0.2
}
```

非采样航点的 `sample_id` 必须显式写为 `null`；车辆端将该字段作为必需字段校验。

`type` 可取 `start`、`transit`、`sampling`、`turn`、`return`。急转折只会产生校验警告，不会自动宣称路径已经满足实车转弯半径要求；实车前还需要圆弧/样条平滑。

## 自动化测试

```bash
npm run test:route
```

测试覆盖像素到米制转换、坐标方向、采样点编号、正常路线统计、越界/超速拒绝，并通过跨仓库测试把网页导出的路线交给 `spore-vehicle-nav` 的 Python 解析器验证。

## 当前边界

- 该文件描述的是路线数据和校验，不会向小车发送运动指令；
- ROS 2 路线跟踪节点尚未实现；
- 网页机器人桥接默认锁定运动控制，只有明确确认后才允许发送非零 `/cmd_vel`；
- 真实 `map` 起始位姿、SLAM 定位和雷达避障仍需后续 ROS/实车验证。
