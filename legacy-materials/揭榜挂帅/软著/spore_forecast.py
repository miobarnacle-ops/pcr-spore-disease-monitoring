# -*- coding: utf-8 -*-
"""
================================================================================
孢子扩散预测与风险预报模块 V1.0
================================================================================
基于简化高斯烟羽模型(Gaussian Plume Model)的田间孢子扩散预测。
输入: PCR阳性点坐标+浓度 + 气象参数(风向/风速/温湿度)
输出: 24h/48h/72h 浓度分布热力图 + 四级风险预警 + 文本预报报告

技术依据:
  - Pasquill-Gifford 大气稳定度分类
  - Briggs 扩散参数公式 (农村开阔地形)
  - 中国气象局农业气象灾害预警等级划分

============================================================
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import csv
import json
import os
from datetime import datetime, timedelta

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


# =====================================================================
# 高斯扩散模型参数
# =====================================================================

# Pasquill 稳定度分类 → Briggs σy, σz 系数 (农村开阔地)
# σy = a_y * x^b_y,  σz = a_z * x^b_z
# x 为下风向距离(m)
STABILITY_PARAMS = {
    "A": {  # 极不稳定 (强日照, 风速<2m/s)
        "a_y": 0.22, "b_y": 0.92,
        "a_z": 0.20, "b_z": 0.94,
        "name": "A-极不稳定"
    },
    "B": {  # 中度不稳定
        "a_y": 0.16, "b_y": 0.92,
        "a_z": 0.12, "b_z": 0.89,
        "name": "B-中度不稳定"
    },
    "C": {  # 轻度不稳定
        "a_y": 0.11, "b_y": 0.92,
        "a_z": 0.08, "b_z": 0.85,
        "name": "C-轻度不稳定"
    },
    "D": {  # 中性 (阴天或风速>5m/s)
        "a_y": 0.08, "b_y": 0.90,
        "a_z": 0.06, "b_z": 0.81,
        "name": "D-中性"
    },
    "E": {  # 轻度稳定 (夜间, 风速<3m/s)
        "a_y": 0.06, "b_y": 0.89,
        "a_z": 0.03, "b_z": 0.78,
        "name": "E-轻度稳定"
    },
    "F": {  # 中度稳定 (夜间, 风速<2m/s)
        "a_y": 0.04, "b_y": 0.89,
        "a_z": 0.016, "b_z": 0.74,
        "name": "F-中度稳定"
    },
}


def classify_stability(wind_speed_ms, is_daytime, cloud_cover_percent):
    """
    根据风速、昼夜和云量判定 Pasquill 稳定度等级。
    简化判据:
      日间: 风速<2→A, 2-3→B, 3-5→C, >5→D
      夜间: 云量<50%→F, 云量>50%且风速<3→E, 风速>3→D
    """
    if is_daytime:
        if wind_speed_ms < 2.0:
            return "A"
        elif wind_speed_ms < 3.0:
            return "B"
        elif wind_speed_ms < 5.0:
            return "C"
        else:
            return "D"
    else:
        if cloud_cover_percent < 50 and wind_speed_ms < 3.0:
            return "F"
        elif wind_speed_ms < 3.0:
            return "E"
        else:
            return "D"


def gaussian_plume_concentration(source_x, source_y, source_strength,
                                 wind_speed_ms, wind_direction_deg,
                                 stability_class, target_x, target_y,
                                 release_height_m=1.5):
    """
    高斯烟羽模型: 计算点源(source_x,source_y)在(target_x,target_y)处的浓度。

    参数:
      source_x, source_y: 源点坐标(m)
      source_strength: 源强 (孢子释放速率, copies/s)
      wind_speed_ms: 风速 (m/s)
      wind_direction_deg: 风向 (度, 0=北,90=东, 气象惯例)
      stability_class: 稳定度等级 (A~F)
      target_x, target_y: 目标点坐标(m)
      release_height_m: 释放高度 (m), 默认1.5m (作物冠层高度)

    返回: 浓度值 (copies/m³), 若在源点则返回来流浓度上限
    """
    if wind_speed_ms <= 0.1:
        wind_speed_ms = 0.1  # 避免除零

    params = STABILITY_PARAMS.get(stability_class, STABILITY_PARAMS["D"])
    a_y, b_y = params["a_y"], params["b_y"]
    a_z, b_z = params["a_z"], params["b_z"]

    # 将目标点转换到风轴坐标系: x' = 下风向距离, y' = 侧风向偏移
    wind_rad = math.radians(wind_direction_deg)
    # 风向向量: (sin, -cos) —— 0°=北(上), 90°=东(右)
    wind_dx = math.sin(wind_rad)
    wind_dy = -math.cos(wind_rad)

    # 目标点相对源点的向量
    dx = target_x - source_x
    dy = target_y - source_y

    # 下风向距离 (投影到风向)
    downwind_dist = dx * wind_dx + dy * wind_dy

    # 侧风向距离 (垂直于风向)
    crosswind_dist = dx * (-wind_dy) + dy * wind_dx

    # 若目标在源的上风向 → 浓度为零
    if downwind_dist <= 0:
        return 0.0

    # Briggs 扩散参数
    sigma_y = a_y * (downwind_dist ** b_y)
    sigma_z = a_z * (downwind_dist ** b_z)

    # 防止扩散参数过小
    sigma_y = max(sigma_y, 0.5)
    sigma_z = max(sigma_z, 0.3)

    # 地面反射项 (镜像源)
    term1 = math.exp(-0.5 * (crosswind_dist / sigma_y) ** 2)
    term2 = math.exp(-0.5 * (release_height_m / sigma_z) ** 2)
    # 地面反射
    term3 = math.exp(-0.5 * (release_height_m / sigma_z) ** 2)  # 镜像

    # 高斯烟羽公式 (包含地面反射)
    concentration = (source_strength / (math.pi * sigma_y * sigma_z * wind_speed_ms)
                     * term1 * (term2 + term3) * 0.5)

    return max(0.0, concentration)


def compute_field_risk_level(concentration, wind_speed_ms, humidity_pct):
    """
    根据孢子浓度、风速和湿度综合判定风险等级。

    中国农业病害流行学常用判据:
      - 孢子浓度 + 高湿(>80%) + 适温 = 最有利于侵染
      - 大风速有利于扩散但稀释浓度

    返回: (risk_level, risk_color, risk_description)
      risk_level: 'green' / 'yellow' / 'orange' / 'red'
    """
    # 湿度修正系数
    if humidity_pct > 85:
        humidity_factor = 1.5  # 高湿显著促进孢子萌发
    elif humidity_pct > 70:
        humidity_factor = 1.2
    elif humidity_pct > 50:
        humidity_factor = 1.0
    else:
        humidity_factor = 0.7  # 干燥抑制

    # 风速修正: 中等风速(2-5m/s)有利于扩散, 过大(>8m/s)或过小(<1m/s)不利
    if 2 <= wind_speed_ms <= 5:
        wind_factor = 1.2
    elif wind_speed_ms > 8:
        wind_factor = 0.8
    elif wind_speed_ms < 1:
        wind_factor = 0.9
    else:
        wind_factor = 1.0

    adjusted_conc = concentration * humidity_factor * wind_factor

    if adjusted_conc > 5000:
        return 'red', '#e74c3c', '红色预警: 孢子浓度极高, 气象条件利于侵染扩散, 建议24h内紧急施药'
    elif adjusted_conc > 1000:
        return 'orange', '#e67e22', '橙色预警: 孢子浓度较高, 存在明显扩散风险, 建议48h内预防性施药'
    elif adjusted_conc > 200:
        return 'yellow', '#f1c40f', '黄色预警: 检测到孢子扩散趋势, 建议加强监测, 72h内评估是否需要干预'
    else:
        return 'green', '#27ae60', '绿色: 孢子浓度在安全范围内, 维持常规巡检频率即可'


# =====================================================================
# 伪彩色映射 —— 预报热力图专用
# =====================================================================

def forecast_concentration_to_rgba(concentration):
    """
    预报浓度(copies/m³) → RGBA:
    透明/淡蓝(极低) → 绿(低) → 黄(中) → 橙(高) → 红(极高)
    使用对数尺度分段插值。
    """
    if concentration <= 0.01:
        return (0, 0, 0, 0)  # 零浓度完全透明

    logc = math.log10(max(0.1, concentration))
    # 色标范围: 10^-1 → 10^1 → 10^2 → 10^3 → 10^4
    stops = [
        (-1.0, (180, 210, 240, 30)),   # 极淡蓝——本底
        (0.0,  (39, 174, 96, 80)),     # 绿——低浓度
        (1.0,  (241, 196, 15, 110)),   # 黄——中等
        (2.0,  (230, 126, 34, 140)),   # 橙——高浓度
        (3.0,  (231, 76, 60, 170)),    # 红——极高
    ]
    for i in range(len(stops) - 1):
        v0, (r0, g0, b0, a0) = stops[i]
        v1, (r1, g1, b1, a1) = stops[i + 1]
        if logc <= v1:
            t = (logc - v0) / (v1 - v0) if v1 != v0 else 0
            t = max(0, min(1, t))
            return (int(r0 + (r1 - r0) * t), int(g0 + (g1 - g0) * t),
                    int(b0 + (b1 - b0) * t), int(a0 + (a1 - a0) * t))
    return (231, 76, 60, 180)


# =====================================================================
# 主界面类
# =====================================================================

class SporeForecastModule:
    """孢子扩散预测与风险预报系统 V1.0"""

    def __init__(self, root_window):
        self.root = root_window
        self.root.title("孢子扩散预测与风险预报系统 V1.0")
        self.root.geometry("1300x800")

        # ---- 配色 ----
        self.cbg = "#161a1d"
        self.cpn = "#212529"
        self.ccd = "#2c313c"
        self.cac = "#00ecc6"
        self.cal = "#e1b12c"
        self.cdg = "#e74c3c"
        self.cif = "#00a8ff"
        self.csf = "#27ae60"
        self.ctx = "#dcdde1"
        self.cdm = "#718093"

        # ---- 数据 ----
        self.source_points = []     # PCR阳性源点 [{x_m,y_m,conc,label}]
        self.field_polygon_m = []   # 农田边界(米制)
        self.forecast_result = None # 预测结果 {time_label: {grid, concs}}

        # ---- 气象参数 (默认值) ----
        self.wind_speed = 3.5       # m/s
        self.wind_direction = 135   # 度 (东南风)
        self.temperature = 25.0     # °C
        self.humidity = 75.0        # %
        self.cloud_cover = 40.0     # %
        self.is_daytime = True
        self.release_height = 1.5   # m (作物冠层)

        # ---- 预测时间点 ----
        self.forecast_hours = [24, 48, 72]
        self.current_forecast_idx = 0

        # ---- 图像缓存 ----
        self._hm_photo = None
        self._legend_photo = None
        self._src_photo = None

        self._build_ui()

    # =================================================================
    # 界面
    # =================================================================

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')

        # ---- 右侧: 预测画布 ----
        right_frame = tk.Frame(self.root, bg=self.cbg)
        right_frame.pack(side="right", fill="both", expand=True)

        # 时间切换条
        time_bar = tk.Frame(right_frame, bg=self.cpn, height=36)
        time_bar.pack(fill="x")
        time_bar.pack_propagate(False)

        tk.Label(time_bar, text="预测时间:", fg=self.cdm, bg=self.cpn,
                 font=("微软雅黑", 10)).pack(side="left", padx=12)

        self._time_btns = []
        for hours in self.forecast_hours:
            btn = tk.Button(time_bar, text=f"{hours}h",
                            bg=self.ccd, fg=self.ctx, bd=0,
                            padx=12, pady=2, font=("Consolas", 10, "bold"),
                            command=lambda h=hours: self._switch_forecast(h))
            btn.pack(side="left", padx=3)
            self._time_btns.append(btn)

        self._time_info = tk.Label(time_bar, text="",
                                   fg=self.cal, bg=self.cpn,
                                   font=("微软雅黑", 9, "bold"))
        self._time_info.pack(side="right", padx=12)

        # 画布
        self.canvas = tk.Canvas(right_frame, bg=self.cbg, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # 状态栏
        self._status_var = tk.StringVar()
        self._status_var.set("SYS READY: 导入PCR阳性数据 → 设置气象参数 → 运行预测")
        tk.Label(right_frame, textvariable=self._status_var,
                 fg=self.cal, bg=self.cbg,
                 font=("微软雅黑", 10, "bold")).pack(side="bottom", pady=6)

        # ---- 左侧: 控制面板 ----
        left_frame = tk.Frame(self.root, bg=self.cpn, width=380)
        left_frame.pack(side="left", fill="y")
        left_frame.pack_propagate(False)

        # 可滚动内容
        cvs = tk.Canvas(left_frame, bg=self.cpn, highlightthickness=0, width=380)
        sbar = ttk.Scrollbar(left_frame, orient="vertical", command=cvs.yview)
        inner = tk.Frame(cvs, bg=self.cpn)
        inner.bind("<Configure>",
                   lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=inner, anchor="nw", width=364)
        cvs.configure(yscrollcommand=sbar.set)
        cvs.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")

        def _mousewheel(event):
            cvs.yview_scroll(int(-1 * (event.delta / 120)), "units")
        cvs.bind("<Enter>", lambda e: cvs.bind_all("<MouseWheel>", _mousewheel))
        cvs.bind("<Leave>", lambda e: cvs.unbind_all("<MouseWheel>"))

        def btn(text, cmd, pady=6, color=None):
            bg_color = color if color else self.ccd
            fg_color = "white" if color else self.ctx
            tk.Button(inner, text=text, bg=bg_color, fg=fg_color, bd=0,
                      padx=14, pady=4, cursor="hand2",
                      font=("微软雅黑", 10), command=cmd
                      ).pack(pady=pady, fill="x", padx=14)

        tk.Label(inner, text="FORECAST CONTROL", fg=self.cdm, bg=self.cpn,
                 font=("Consolas", 9, "bold")).pack(pady=(12, 2))

        # ---- 数据导入 ----
        impf = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        impf.pack(pady=8, fill="x", padx=14)
        tk.Label(impf, text="数据导入", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 2))
        btn("导入PCR阳性数据 (CSV/JSON)", self._import_sources, 5)

        # 源点统计
        self._src_stats = tk.Label(impf, text="已加载: 0 个阳性源点",
                                   fg=self.cdm, bg=self.ccd, font=("微软雅黑", 8))
        self._src_stats.pack(pady=(2, 6))

        # ---- 气象参数 ----
        wf = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        wf.pack(pady=8, fill="x", padx=14)
        tk.Label(wf, text="气象参数设定", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 2))

        wgi = tk.Frame(wf, bg=self.ccd)
        wgi.pack(pady=4)

        def _wrow(label, default, row_idx, unit=""):
            tk.Label(wgi, text=label, fg=self.ctx, bg=self.ccd,
                     font=("微软雅黑", 9)).grid(
                         row=row_idx, column=0, pady=3, padx=(10, 2), sticky="w")
            ent = tk.Entry(wgi, width=7, bg=self.cbg, fg=self.cac, bd=0,
                           insertbackground="white",
                           font=("Consolas", 10, "bold"))
            ent.insert(0, str(default))
            ent.grid(row=row_idx, column=1, pady=3, padx=2, sticky="e")
            if unit:
                tk.Label(wgi, text=unit, fg=self.cdm, bg=self.ccd,
                         font=("微软雅黑", 8)).grid(
                             row=row_idx, column=2, pady=3, padx=(0, 6), sticky="w")
            return ent

        self._ent_wind_speed = _wrow("风速", 3.5, 0, "m/s")
        self._ent_wind_dir = _wrow("风向", 135, 1, "°")
        tk.Label(wgi, text="(0=北 90=东 180=南 270=西)",
                 fg=self.cdm, bg=self.ccd, font=("微软雅黑", 7)).grid(
                     row=1, column=2, pady=0, padx=2, sticky="w")
        self._ent_temp = _wrow("温度", 25.0, 2, "°C")
        self._ent_humidity = _wrow("湿度", 75.0, 3, "%")
        self._ent_cloud = _wrow("云量", 40.0, 4, "%")

        # 昼夜
        df = tk.Frame(wf, bg=self.ccd)
        df.pack(pady=(3, 2))
        tk.Label(df, text="时段:", fg=self.cdm, bg=self.ccd,
                 font=("微软雅黑", 8)).pack(side="left", padx=(10, 4))
        self._daytime_var = tk.BooleanVar(value=True)
        tk.Radiobutton(df, text="日间", variable=self._daytime_var, value=True,
                       fg=self.ctx, bg=self.ccd, selectcolor=self.cbg,
                       activebackground=self.ccd, activeforeground=self.ctx,
                       font=("微软雅黑", 8)).pack(side="left", padx=3)
        tk.Radiobutton(df, text="夜间", variable=self._daytime_var, value=False,
                       fg=self.ctx, bg=self.ccd, selectcolor=self.cbg,
                       activebackground=self.ccd, activeforeground=self.ctx,
                       font=("微软雅黑", 8)).pack(side="left", padx=3)

        # 释放高度
        self._ent_height = _wrow("释放高度", 1.5, 5, "m")
        tk.Label(wgi, text="(作物冠层高度)",
                 fg=self.cdm, bg=self.ccd, font=("微软雅黑", 7)).grid(
                     row=5, column=2, pady=0, padx=2, sticky="w")

        btn("应用气象参数", self._apply_weather, 5)

        # 稳定度显示
        self._stab_label = tk.Label(wf, text="稳定度: --",
                                    fg=self.cdm, bg=self.ccd,
                                    font=("微软雅黑", 9, "bold"))
        self._stab_label.pack(pady=(2, 6))

        # ---- 运行预测 ----
        btn("▶ 运行扩散预测", self._run_forecast, 8, color=self.cif)

        # 预测时间点
        self._forecast_info = tk.Label(inner, text="",
                                        fg=self.cdm, bg=self.cpn,
                                        font=("微软雅黑", 9))
        self._forecast_info.pack(pady=2)

        # ---- 风险摘要 ----
        rf = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        rf.pack(pady=8, fill="x", padx=14)
        tk.Label(rf, text="风险摘要", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 2))
        self._risk_text = tk.Label(rf, text="等待预测...",
                                   fg=self.cdm, bg=self.ccd,
                                   font=("微软雅黑", 9),
                                   wraplength=320, justify="left")
        self._risk_text.pack(pady=(2, 6), padx=12)

        # ---- 导出 ----
        btn("导出预测报告 (TXT)", self._export_report, 4)
        btn("导出风险热力图数据 (CSV)", self._export_csv, 4)
        btn("清空全部数据", self._clear_all, 6, color=self.cdg)

    # =================================================================
    # 数据导入
    # =================================================================

    def _import_sources(self):
        """导入PCR阳性数据作为扩散源点"""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV/JSON files", "*.csv *.json"),
                       ("All files", "*.*")],
            title="导入 PCR 阳性数据")
        if not file_path:
            return

        self.source_points = []
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".json":
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                points = data.get("sampling_points", [])
                for pt in points:
                    if pt.get("pcr_verdict") and "阳性" in pt.get("pcr_verdict", ""):
                        self.source_points.append({
                            "x_m": pt.get("relative_m", [0, 0])[0],
                            "y_m": pt.get("relative_m", [0, 0])[1],
                            "conc": pt.get("pcr_conc", 100),
                            "label": pt.get("id", "?")
                        })
            elif ext == ".csv":
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    rows = list(csv.reader(f))
                for row in rows:
                    if len(row) < 8 or row[0] == "样本编号":
                        continue
                    verdict = row[6] if len(row) > 6 else ""
                    if "阳性" not in verdict:
                        continue
                    try:
                        x_m = float(row[1])
                        y_m = float(row[2])
                        conc_str = row[5] if len(row) > 5 else "100"
                        # 解析科学计数法浓度
                        try:
                            conc = float(conc_str)
                        except ValueError:
                            conc = 100.0
                        self.source_points.append({
                            "x_m": x_m,
                            "y_m": y_m,
                            "conc": max(1.0, conc),
                            "label": row[0]
                        })
                    except (ValueError, IndexError):
                        continue

            self._src_stats.config(
                text=f"已加载: {len(self.source_points)} 个阳性源点")
            self._status_var.set(
                f"IMPORTED: {len(self.source_points)} 个扩散源点。")

            # 估算农田多边形 (源点bbox + margin)
            if self.source_points and not self.field_polygon_m:
                xs = [p["x_m"] for p in self.source_points]
                ys = [p["y_m"] for p in self.source_points]
                margin = 30
                self.field_polygon_m = [
                    (min(xs) - margin, min(ys) - margin),
                    (max(xs) + margin, min(ys) - margin),
                    (max(xs) + margin, max(ys) + margin),
                    (min(xs) - margin, max(ys) + margin),
                ]

            self._draw_forecast_view()

        except Exception as e:
            messagebox.showerror("导入失败", f"数据解析异常: {e}")

    # =================================================================
    # 气象参数
    # =================================================================

    def _apply_weather(self):
        """读取并应用气象参数"""
        try:
            self.wind_speed = float(self._ent_wind_speed.get())
            self.wind_direction = float(self._ent_wind_dir.get())
            self.temperature = float(self._ent_temp.get())
            self.humidity = float(self._ent_humidity.get())
            self.cloud_cover = float(self._ent_cloud.get())
            self.release_height = float(self._ent_height.get())
        except ValueError:
            messagebox.showerror("输入错误", "气象参数必须为数值。")
            return

        self.is_daytime = self._daytime_var.get()

        # 判定稳定度
        stability = classify_stability(
            self.wind_speed, self.is_daytime, self.cloud_cover)
        stab_info = STABILITY_PARAMS.get(stability, {})
        self._stab_label.config(
            text=f"稳定度: {stab_info.get('name', stability)}",
            fg=self.cif)

        self._status_var.set(
            f"WEATHER: 风速{self.wind_speed}m/s "
            f"风向{self.wind_direction}° "
            f"稳定度{stability}")

    # =================================================================
    # 扩散预测
    # =================================================================

    def _run_forecast(self):
        """执行多时间点扩散预测"""
        if not self.source_points:
            messagebox.showwarning("提示", "请先导入 PCR 阳性源点数据。")
            return

        self._apply_weather()
        stability = classify_stability(
            self.wind_speed, self.is_daytime, self.cloud_cover)

        # 确定预测范围 (源点 bbox + 下风向扩展)
        xs = [p["x_m"] for p in self.source_points]
        ys = [p["y_m"] for p in self.source_points]
        wind_rad = math.radians(self.wind_direction)
        wind_dx = math.sin(wind_rad)
        wind_dy = -math.cos(wind_rad)

        # 计算每个时间窗口的浓度场
        self.forecast_result = {}
        grid_step = 5.0  # 5m 分辨率
        margin = 40

        min_x = min(xs) - margin
        max_x = max(xs) + margin
        min_y = min(ys) - margin
        max_y = max(ys) + margin

        # 沿下风向扩展
        extend_x = abs(wind_dx) * 200
        extend_y = abs(wind_dy) * 200
        if wind_dx > 0:
            max_x += extend_x
        else:
            min_x -= extend_x
        if wind_dy > 0:
            max_y += extend_y
        else:
            min_y -= extend_y

        for hours in self.forecast_hours:
            self._status_var.set(
                f"FORECASTING: 正在计算 {hours}h 扩散场...")
            self.root.update()

            # 时间加权: 模拟累积效应 (浓度随时间的平方根增长)
            time_factor = math.sqrt(hours / 24.0)

            grid_cols = int((max_x - min_x) / grid_step) + 1
            grid_rows = int((max_y - min_y) / grid_step) + 1

            # 限制网格大小
            max_cells = 200
            if grid_cols > max_cells:
                grid_step = (max_x - min_x) / max_cells
                grid_cols = max_cells
                grid_rows = int((max_y - min_y) / grid_step) + 1
            if grid_rows > max_cells:
                grid_step = (max_y - min_y) / max_cells
                grid_rows = max_cells
                grid_cols = int((max_x - min_x) / grid_step) + 1

            concentration_grid = []
            grid_points = []

            for col in range(grid_cols):
                gx = min_x + col * grid_step
                for row in range(grid_rows):
                    gy = min_y + row * grid_step
                    total_conc = 0.0

                    for src in self.source_points:
                        # 源强 ∝ PCR浓度 × 时间因子
                        q_source = src["conc"] * time_factor * 1e3
                        conc = gaussian_plume_concentration(
                            src["x_m"], src["y_m"], q_source,
                            self.wind_speed, self.wind_direction,
                            stability, gx, gy, self.release_height)
                        total_conc += conc

                    concentration_grid.append(total_conc)
                    grid_points.append((gx, gy))

            self.forecast_result[hours] = {
                "grid": grid_points,
                "concs": concentration_grid,
                "min_x": min_x, "max_x": max_x,
                "min_y": min_y, "max_y": max_y,
                "grid_step": grid_step,
                "grid_cols": grid_cols,
                "grid_rows": grid_rows,
            }

        self.current_forecast_idx = 0
        self._update_time_buttons()
        self._draw_forecast_view()
        self._status_var.set(
            f"FORECAST DONE: {len(self.forecast_result)} 个时间点预测完成。")

    def _switch_forecast(self, hours):
        """切换显示不同时间点的预测结果"""
        for i, h in enumerate(self.forecast_hours):
            if h == hours:
                self.current_forecast_idx = i
        self._update_time_buttons()
        self._draw_forecast_view()

    def _update_time_buttons(self):
        """高亮当前选中的时间按钮"""
        for i, btn in enumerate(self._time_btns):
            if i == self.current_forecast_idx:
                btn.config(bg=self.cif, fg="white")
            else:
                btn.config(bg=self.ccd, fg=self.ctx)

        hours = self.forecast_hours[self.current_forecast_idx]
        self._time_info.config(
            text=f"当前: {hours}h 预报  "
            f"| 风向{self.wind_direction}° 风速{self.wind_speed}m/s")

    # =================================================================
    # 画布绘制
    # =================================================================

    def _draw_forecast_view(self):
        """绘制预测热力图、源点、风险标注"""
        self.canvas.delete("all")
        self._hm_photo = None
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10:
            cw, ch = 900, 700

        if not self.source_points:
            return

        # 米制坐标 → 画布映射
        all_xs = [p["x_m"] for p in self.source_points]
        all_ys = [p["y_m"] for p in self.source_points]
        if self.forecast_result:
            hours = self.forecast_hours[self.current_forecast_idx]
            result = self.forecast_result.get(hours)
            if result:
                all_xs = [result["min_x"], result["max_x"]]
                all_ys = [result["min_y"], result["max_y"]]

        margin = 50
        min_x, max_x = min(all_xs), max(all_xs)
        min_y, max_y = min(all_ys), max(all_ys)
        rng_x = max_x - min_x or 1
        rng_y = max_y - min_y or 1

        def _to_canvas(mx, my):
            px = margin + (mx - min_x) / rng_x * (cw - 2 * margin)
            py = margin + (my - min_y) / rng_y * (ch - 2 * margin)
            return px, py

        # 多边形边界
        if self.field_polygon_m and len(self.field_polygon_m) >= 3:
            poly_px = [_to_canvas(v[0], v[1]) for v in self.field_polygon_m]
            for i in range(len(poly_px)):
                self.canvas.create_line(
                    poly_px[i][0], poly_px[i][1],
                    poly_px[(i + 1) % len(poly_px)][0],
                    poly_px[(i + 1) % len(poly_px)][1],
                    fill=self.cif, width=2, dash=(6, 3))

        # 预测热力图
        if self.forecast_result and HAS_PILLOW:
            hours = self.forecast_hours[self.current_forecast_idx]
            result = self.forecast_result.get(hours)
            if result:
                self._render_forecast_heatmap(
                    cw, ch, result, _to_canvas)

        # 风向指示箭头 (画布右上角)
        arrow_cx = cw - 80
        arrow_cy = 60
        self._draw_wind_arrow(arrow_cx, arrow_cy, self.wind_direction, self.wind_speed)

        # 源点标记
        for src in self.source_points:
            px, py = _to_canvas(src["x_m"], src["y_m"])
            # 外圈
            self.canvas.create_oval(
                px - 8, py - 8, px + 8, py + 8,
                fill="", outline=self.cdg, width=2.5)
            # 内芯 (浓度色)
            logc = math.log10(max(1, src.get("conc", 100)))
            t = max(0, min(1, (logc - 2) / 4))
            r_ = int(39 + (231 - 39) * t)
            g_ = int(174 - (174 - 76) * t)
            b_ = int(96 - (96 - 60) * t)
            self.canvas.create_oval(
                px - 4, py - 4, px + 4, py + 4,
                fill=f"#{r_:02x}{g_:02x}{b_:02x}", outline="")
            # 标签
            self.canvas.create_text(
                px + 10, py - 10, text=src.get("label", ""),
                fill=self.cdg, font=("Consolas", 7, "bold"), anchor="w")

        # 风险图例
        self._draw_forecast_legend(cw, ch)

    def _render_forecast_heatmap(self, cw, ch, result, to_canvas):
        """渲染扩散预测热力图"""
        grid = result["grid"]
        concs = result["concs"]
        grid_step = result["grid_step"]
        cols = result["grid_cols"]
        rows = result["grid_rows"]

        if not concs:
            return

        # 找到最大值用于归一化
        max_conc = max(concs) if concs else 1.0

        # 渲染到PIL
        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw_handle = ImageDraw.Draw(overlay)

        for idx, (gx, gy) in enumerate(grid):
            if idx >= len(concs):
                break
            conc = concs[idx]
            if conc <= 0.001:
                continue

            # 将格网中心映射到画布
            # 格网四个角的画布坐标
            px_tl = to_canvas(gx - grid_step / 2, gy - grid_step / 2)
            px_br = to_canvas(gx + grid_step / 2, gy + grid_step / 2)

            rgba = forecast_concentration_to_rgba(conc)
            draw_handle.rectangle(
                [px_tl[0], px_tl[1], px_br[0], px_br[1]],
                fill=rgba)

        self._hm_photo = ImageTk.PhotoImage(overlay)
        self.canvas.create_image(0, 0, anchor="nw", image=self._hm_photo)

        # 更新风险摘要
        self._update_risk_summary(concs, max_conc)

    def _update_risk_summary(self, concentrations, max_conc):
        """更新风险摘要文本"""
        if not concentrations:
            return

        # 统计各级风险格点数
        red_count = sum(1 for c in concentrations
                        if compute_field_risk_level(
                            c, self.wind_speed, self.humidity)[0] == 'red')
        orange_count = sum(1 for c in concentrations
                           if compute_field_risk_level(
                               c, self.wind_speed, self.humidity)[0] == 'orange')
        yellow_count = sum(1 for c in concentrations
                           if compute_field_risk_level(
                               c, self.wind_speed, self.humidity)[0] == 'yellow')
        total = len(concentrations)

        _, _, desc = compute_field_risk_level(
            max_conc, self.wind_speed, self.humidity)

        hours = self.forecast_hours[self.current_forecast_idx]
        text = (
            f"◆ {hours}h 预报摘要 ◆\n"
            f" 峰值浓度: {max_conc:.1f} copies/m³\n"
            f" 风向: {self.wind_direction}°  风速: {self.wind_speed} m/s\n"
            f" 温度: {self.temperature}°C  湿度: {self.humidity}%\n\n"
            f" 风险网格分布 (共{total}网格):\n"
            f"  🔴 红色: {red_count} 格  "
            f"🟠 橙色: {orange_count} 格\n"
            f"  🟡 黄色: {yellow_count} 格  "
            f"🟢 绿色: {total - red_count - orange_count - yellow_count} 格\n\n"
            f" 综合建议: {desc}"
        )
        self._risk_text.config(text=text)

    def _draw_wind_arrow(self, cx, cy, direction_deg, speed_ms):
        """绘制风向风速指示箭头"""
        # 气象惯例: 0°=北(上), 90°=东(右)
        rad = math.radians(direction_deg)
        # 箭头指向下风向 (风吹去的方向)
        tip_x = cx + math.sin(rad) * 35
        tip_y = cy - math.cos(rad) * 35

        # 箭杆
        self.canvas.create_line(cx, cy, tip_x, tip_y,
                                fill=self.cac, width=2, arrow="last",
                                arrowshape=(12, 14, 6))

        # 标注
        self.canvas.create_text(cx, cy - 20,
                                text=f"风 {direction_deg}°",
                                fill=self.ctx, font=("微软雅黑", 8))
        self.canvas.create_text(cx, cy - 8,
                                text=f"{speed_ms} m/s",
                                fill=self.cdm, font=("Consolas", 7))

    def _draw_forecast_legend(self, cw, ch):
        """扩散热力图图例"""
        lw, lh = 180, 34
        lx, ly = cw - lw - 15, ch - lh - 15
        self.canvas.create_rectangle(lx, ly, lx + lw, ly + lh,
                                     fill=self.cbg, outline=self.cdm, width=1)
        bx, by, bw, bh = lx + 8, ly + 8, 110, lh - 16
        for i in range(bw):
            logc = -1 + i / bw * 4  # 10^-1 ~ 10^3
            rgba = forecast_concentration_to_rgba(10 ** logc)
            hex_c = f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"
            self.canvas.create_line(bx + i, by, bx + i, by + bh, fill=hex_c)
        for v, lb in [(0, "0"), (bw, "10⁴")]:
            self.canvas.create_text(bx + v, by + bh + 2, text=lb,
                                    fill=self.cdm,
                                    font=("Consolas", 6), anchor="n")
        ctr_x = bx + bw + 22
        ctr_y = by + bh / 2
        self.canvas.create_text(ctr_x, ctr_y - 2,
                                text="copies", fill=self.cdm,
                                font=("微软雅黑", 6), anchor="w")
        self.canvas.create_text(ctr_x, ctr_y + 8,
                                text="/m³", fill=self.cdm,
                                font=("微软雅黑", 6), anchor="w")

    # =================================================================
    # 导出
    # =================================================================

    def _export_report(self):
        """导出文本预报报告"""
        if not self.forecast_result:
            messagebox.showwarning("提示", "请先运行扩散预测。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            title="导出预报报告")
        if not file_path:
            return

        lines = [
            "=" * 55,
            "  孢子扩散预测与风险预报报告",
            f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 55,
            "",
            "[气象条件]",
            f"  风速: {self.wind_speed} m/s  风向: {self.wind_direction}°",
            f"  温度: {self.temperature}°C  湿度: {self.humidity}%",
            f"  云量: {self.cloud_cover}%  时段: {'日间' if self.is_daytime else '夜间'}",
            f"  释放高度: {self.release_height} m",
            "",
            "[扩散源点]",
            f"  阳性源点数: {len(self.source_points)}",
            "",
        ]

        for src in self.source_points:
            lines.append(
                f"  {src['label']:<10} "
                f"坐标({src['x_m']:.1f}, {src['y_m']:.1f})  "
                f"浓度 {src.get('conc', 0):.2e} copies/m³")

        lines.append("")
        lines.append("[各时间点峰值浓度与最高风险]")

        for hours in self.forecast_hours:
            result = self.forecast_result.get(hours)
            if not result:
                continue
            max_c = max(result["concs"]) if result["concs"] else 0
            risk_level, _, risk_desc = compute_field_risk_level(
                max_c, self.wind_speed, self.humidity)
            risk_cn = {"red": "红色", "orange": "橙色",
                       "yellow": "黄色", "green": "绿色"}
            lines.append(
                f"  {hours}h: 峰值浓度 {max_c:.1f} copies/m³  "
                f"风险等级: {risk_cn.get(risk_level, risk_level)}")
            lines.append(f"    建议: {risk_desc}")

        lines.append("")
        lines.append("=" * 55)
        lines.append("  本报告基于简化高斯烟羽模型生成，仅供参考。")
        lines.append("  实际病害发生受多种因素影响，建议结合田间实地观察综合判断。")

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self._status_var.set(
                f"EXPORTED: {os.path.basename(file_path)}")
            messagebox.showinfo("导出成功", f"报告已写入:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"{e}")

    def _export_csv(self):
        """导出风险热力图网格数据"""
        if not self.forecast_result:
            messagebox.showwarning("提示", "请先运行扩散预测。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            title="导出风险热力图数据")
        if not file_path:
            return

        try:
            hours = self.forecast_hours[self.current_forecast_idx]
            result = self.forecast_result.get(hours)
            if not result:
                messagebox.showwarning("提示", "当前时间点无数据。")
                return

            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['X(m)', 'Y(m)',
                                 '浓度(copies/m³)', '风险等级'])
                for idx, (gx, gy) in enumerate(result["grid"]):
                    if idx >= len(result["concs"]):
                        break
                    conc = result["concs"][idx]
                    risk_level, _, _ = compute_field_risk_level(
                        conc, self.wind_speed, self.humidity)
                    if conc > 0.001:
                        writer.writerow([
                            f"{gx:.1f}", f"{gy:.1f}",
                            f"{conc:.2e}",
                            {"red": "红色", "orange": "橙色",
                             "yellow": "黄色", "green": "绿色"}.get(
                                 risk_level, risk_level)
                        ])

            self._status_var.set(
                f"EXPORTED: {os.path.basename(file_path)}")
            messagebox.showinfo("导出成功", f"已导出至:\n{file_path}")

        except Exception as e:
            messagebox.showerror("导出失败", f"{e}")

    def _clear_all(self):
        """重置全部数据"""
        if messagebox.askyesno("确认", "清空全部预测数据？"):
            self.source_points = []
            self.field_polygon_m = []
            self.forecast_result = None
            self._src_stats.config(text="已加载: 0 个阳性源点")
            self._risk_text.config(text="等待预测...")
            self._stab_label.config(text="稳定度: --")
            self.canvas.delete("all")
            self._status_var.set("SYS READY: 数据已清空。")


if __name__ == "__main__":
    root = tk.Tk()
    app = SporeForecastModule(root)
    root.mainloop()
