#!/usr/bin/env python3
"""Read-only checker: subscribe /map once and report real mapping statistics."""
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node


def main():
    rclpy.init()
    node = Node("map_checker")
    got = {}

    def cb(msg):
        got["frame"] = msg.header.frame_id
        got["w"] = msg.info.width
        got["h"] = msg.info.height
        got["res"] = msg.info.resolution
        got["ox"] = msg.info.origin.position.x
        got["oy"] = msg.info.origin.position.y
        data = msg.data
        total = len(data)
        unk = sum(1 for v in data if v < 0)
        occ = sum(1 for v in data if v >= 65)
        fre = total - unk - occ
        got.update(total=total, unk=unk, occ=occ, fre=fre)

    node.create_subscription(OccupancyGrid, "/map", cb, 10)

    t0 = time.time()
    while "w" not in got and time.time() - t0 < 10.0:
        rclpy.spin_once(node, timeout_sec=0.5)

    if "w" not in got:
        print("NO_MAP_RECEIVED: /map 上 10 秒内没有收到任何栅格地图")
        rclpy.shutdown()
        return

    tw = got["w"] * got["res"]
    th = got["h"] * got["res"]
    total = max(got["total"], 1)
    print(f"frame={got['frame']}  grid={got['w']}x{got['h']}  res={got['res']:.3f} m/cell")
    print(f"覆盖范围={tw:.1f} x {th:.1f} m  origin=({got['ox']:.2f}, {got['oy']:.2f})")
    print(
        f"格子: 占用={got['occ']}({100*got['occ']/total:.1f}%)  "
        f"自由={got['fre']}({100*got['fre']/total:.1f}%)  "
        f"未知={got['unk']}({100*got['unk']/total:.1f}%)"
    )
    if got["occ"] > 200:
        print("判定: 有实质建图数据（占用墙/障碍充足）")
    elif got["fre"] > 500:
        print("判定: 仅小范围探索，障碍很少")
    else:
        print("判定: 近乎空白地图")

    rclpy.shutdown()


main()
