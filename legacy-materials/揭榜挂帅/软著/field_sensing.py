import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import json
import random
import math
from datetime import datetime

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def _point_in_poly(x, y, poly):
    """射线法判点在多边形内，poly为[(x,y),...]"""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# =========================================================
# 田间孢子粗定检测与即时预警模块
# [UPDATED 2026-07-13] 新增卫星地图叠加浊度热力图，
# 右栏上为地图+热力图，下为采样点详情表。
# 传感器接口预留，当前使用模拟读数演示流程。
# =========================================================

class FieldSensingModule:
    """田间孢子粗定检测与即时预警系统 V1.0"""

    def __init__(self, root):
        self.root = root
        self.root.title("田间孢子粗定检测与即时预警系统 V1.0")
        self.root.geometry("1300x850")

        # 配色 (与路径规划模块统一)
        self.COLOR_BG = "#161a1d"
        self.COLOR_PANEL = "#212529"
        self.COLOR_CARD = "#2c313c"
        self.COLOR_ACCENT = "#00ecc6"
        self.COLOR_ALERT = "#e1b12c"
        self.COLOR_DANGER = "#e74c3c"
        self.COLOR_INFO = "#00a8ff"
        self.COLOR_SAFE = "#27ae60"

        self.RISK_COLORS = {
            'low': self.COLOR_SAFE,
            'medium': self.COLOR_ALERT,
            'high': self.COLOR_DANGER,
            'pending': '#718093'
        }

        # 热力图伪彩色 (绿->黄->橙->红)
        self.HEAT_COLORS = [
            (0, (39, 174, 96)),       # 0 NTU 绿色
            (150, (241, 196, 15)),     # 150 黄色
            (400, (230, 126, 34)),     # 400 橙色
            (600, (231, 76, 60)),      # 600 红色
        ]

        # 采样点数据: list[dict]
        self.sampling_points = []

        # 浊度三级阈值 (NTU)
        self.threshold_medium = 150.0
        self.threshold_high = 400.0
        self.coverage_radius_m = 20.0  # 传感器有效测量半径(米)
        self.field_polygon_m = []     # 农田边界多边形(米制)，用于裁剪热力图

        # 当前选中与巡检状态
        self.selected_index = -1
        self.is_scanning = False
        self.scan_job = None

        # 地图图像缓存
        self.pil_image = None
        self.photo_image = None
        self._disp_photo = None
        self.heatmap_photo = None
        self._overlay_circles = None
        self._map_point_ids = []  # canvas item IDs for point markers

        self.setup_ui()

    # =========================================================
    # UI 布局
    # =========================================================

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", foreground="#dcdde1", background=self.COLOR_PANEL)
        style.configure("Treeview",
                        background=self.COLOR_BG,
                        foreground="#dcdde1",
                        fieldbackground=self.COLOR_BG,
                        borderwidth=0,
                        font=("Consolas", 10))
        style.configure("Treeview.Heading",
                        background="#2c313c",
                        foreground="#718093",
                        font=("微软雅黑", 9, "bold"))
        style.map("Treeview",
                  background=[('selected', self.COLOR_INFO)])

        # ---- 左侧控制栏 ----
        ctrl = tk.Frame(self.root, bg=self.COLOR_PANEL, width=340)
        ctrl.pack(side="left", fill="y")
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="SPORE DETECTION CONTROL",
                 fg="#718093", bg=self.COLOR_PANEL,
                 font=("Consolas", 9, "bold")).pack(pady=(20, 2))

        # 导入区
        tk.Button(ctrl, text="1. 导入规划采样点 (CSV)", bg=self.COLOR_CARD,
                  fg="#dcdde1", bd=0, padx=15, pady=5, cursor="hand2",
                  font=("微软雅黑", 10), command=self.import_from_csv).pack(
            pady=10, fill="x", padx=20)

        tk.Button(ctrl, text="导入规划结果 (JSON)", bg=self.COLOR_CARD,
                  fg="#dcdde1", bd=0, padx=15, pady=5, cursor="hand2",
                  font=("微软雅黑", 10), command=self.import_from_json).pack(
            pady=2, fill="x", padx=20)

        # 卫星底图
        map_ctrl = tk.Frame(ctrl, bg=self.COLOR_CARD, bd=1, relief="solid")
        map_ctrl.pack(pady=10, fill="x", padx=20)
        tk.Label(map_ctrl, text="卫星底图",
                 fg=self.COLOR_INFO, bg=self.COLOR_CARD,
                 font=("微软雅黑", 10, "bold")).pack(pady=(8, 4))
        tk.Button(map_ctrl, text="加载农田卫星图", bg="#5f6368",
                  fg="#dcdde1", bd=0, padx=12, pady=4, cursor="hand2",
                  font=("微软雅黑", 9), command=self.load_image).pack(pady=4)
        tk.Button(map_ctrl, text="清除底图", bg="#3a3f44",
                  fg="#dcdde1", bd=0, padx=12, pady=4, cursor="hand2",
                  font=("微软雅黑", 9), command=self.clear_image).pack(pady=(2, 8))

        # 阈值设定
        thresh_frame = tk.Frame(ctrl, bg=self.COLOR_CARD, bd=1, relief="solid")
        thresh_frame.pack(pady=10, fill="x", padx=20)

        tk.Label(thresh_frame, text="浊度预警阈值设定",
                 fg=self.COLOR_INFO, bg=self.COLOR_CARD,
                 font=("微软雅黑", 10, "bold")).pack(pady=(10, 8))

        grid_inner = tk.Frame(thresh_frame, bg=self.COLOR_CARD)
        grid_inner.pack()

        def _thresh_row(label, default, r):
            tk.Label(grid_inner, text=label, fg="#dcdde1", bg=self.COLOR_CARD,
                     font=("微软雅黑", 9)).grid(row=r, column=0, pady=5, padx=12, sticky="w")
            ent = tk.Entry(grid_inner, width=8, bg=self.COLOR_BG,
                           fg=self.COLOR_ACCENT, bd=0,
                           insertbackground="white", font=("Consolas", 11, "bold"))
            ent.insert(0, default)
            ent.grid(row=r, column=1, pady=5, padx=12, sticky="e")
            return ent

        self.entry_thresh_mid = _thresh_row("中风险阈值 (NTU)", "150.0", 0)
        self.entry_thresh_high = _thresh_row("高风险阈值 (NTU)", "400.0", 1)
        self.entry_scan_delay = _thresh_row("全检间隔 (秒)", "0.8", 2)
        self.entry_coverage_r = _thresh_row("覆盖半径 (米)", "20.0", 3)

        tk.Button(thresh_frame, text="应用阈值", bg="#5f6368",
                  fg="#dcdde1", bd=0, padx=12, pady=3, cursor="hand2",
                  font=("微软雅黑", 9), command=self.apply_thresholds).pack(pady=(8, 10))

        # 传感器操作面板
        sensor_frame = tk.Frame(ctrl, bg=self.COLOR_CARD, bd=1, relief="solid")
        sensor_frame.pack(pady=10, fill="x", padx=20)

        tk.Label(sensor_frame, text="光敏传感器读数",
                 fg=self.COLOR_INFO, bg=self.COLOR_CARD,
                 font=("微软雅黑", 10, "bold")).pack(pady=(10, 6))

        self.lbl_current_point = tk.Label(sensor_frame, text="当前采样点: 未选中",
                                          fg="#718093", bg=self.COLOR_CARD,
                                          font=("微软雅黑", 11))
        self.lbl_current_point.pack(pady=4)

        self.lbl_reading = tk.Label(sensor_frame, text="-- NTU",
                                    fg=self.COLOR_ACCENT, bg=self.COLOR_CARD,
                                    font=("Consolas", 28, "bold"))
        self.lbl_reading.pack(pady=8)

        self.lbl_risk_result = tk.Label(sensor_frame, text="风险: 等待检测",
                                        fg="#718093", bg=self.COLOR_CARD,
                                        font=("微软雅黑", 12, "bold"))
        self.lbl_risk_result.pack(pady=4)

        btn_row = tk.Frame(sensor_frame, bg=self.COLOR_CARD)
        btn_row.pack(pady=(6, 4))
        tk.Button(btn_row, text="读取传感器 (单点)",
                  bg=self.COLOR_INFO, fg="white", bd=0, padx=10, pady=4,
                  cursor="hand2", font=("微软雅黑", 9, "bold"),
                  command=self.read_sensor_single).pack(fill="x", padx=8)
        tk.Button(btn_row, text="一键全检 (顺序巡检)",
                  bg=self.COLOR_ACCENT, fg=self.COLOR_BG, bd=0, padx=10, pady=4,
                  cursor="hand2", font=("微软雅黑", 9, "bold"),
                  command=self.start_full_scan).pack(fill="x", padx=8, pady=4)
        tk.Button(btn_row, text="停止全检",
                  bg=self.COLOR_DANGER, fg="white", bd=0, padx=10, pady=4,
                  cursor="hand2", font=("微软雅黑", 9, "bold"),
                  command=self.stop_full_scan).pack(fill="x", padx=8)

        self.lbl_scan_progress = tk.Label(sensor_frame, text="",
                                          fg=self.COLOR_ALERT, bg=self.COLOR_CARD,
                                          font=("微软雅黑", 9))
        self.lbl_scan_progress.pack(pady=(2, 10))

        # 底部操作
        tk.Button(ctrl, text="导出粗定检测数据 (CSV)", bg=self.COLOR_CARD,
                  fg="#dcdde1", bd=0, padx=15, pady=5, cursor="hand2",
                  font=("微软雅黑", 10), command=self.export_data).pack(
            pady=8, fill="x", padx=20)

        tk.Button(ctrl, text="清空全部数据", bg="#5f6368",
                  fg="#dcdde1", bd=0, padx=15, pady=5, cursor="hand2",
                  font=("微软雅黑", 10), command=self.clear_all).pack(
            pady=2, fill="x", padx=20)

        self.status_var = tk.StringVar()
        self.status_var.set("SYS READY: 等待导入规划采样点坐标...")
        tk.Label(ctrl, textvariable=self.status_var, wraplength=300,
                 fg=self.COLOR_ALERT, bg=self.COLOR_PANEL,
                 font=("微软雅黑", 10, "bold")).pack(side="bottom", pady=30)

        # ---- 右侧主区域：上地图 + 下表格 ----
        main_frame = tk.Frame(self.root, bg=self.COLOR_BG)
        main_frame.pack(side="right", fill="both", expand=True)

        # 上下分割线 (PanedWindow 可拖动)
        self.pane = tk.PanedWindow(main_frame, orient="vertical",
                                   bg="#3a3f44", sashwidth=3)
        self.pane.pack(fill="both", expand=True)

        # ---- 上半：地图画布 ----
        map_frame = tk.Frame(self.pane, bg=self.COLOR_BG)
        self.pane.add(map_frame, minsize=200)

        self.canvas = tk.Canvas(map_frame, bg=self.COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        # ---- 下半：表格 ----
        detail_frame = tk.Frame(self.pane, bg=self.COLOR_BG)
        self.pane.add(detail_frame, minsize=150)

        # 统计栏
        stats_bar = tk.Frame(detail_frame, bg=self.COLOR_PANEL, height=40)
        stats_bar.pack(fill="x")
        stats_bar.pack_propagate(False)

        self.stats_total = tk.Label(stats_bar, text="总计: 0 点",
                                    fg="#dcdde1", bg=self.COLOR_PANEL,
                                    font=("微软雅黑", 10))
        self.stats_total.pack(side="left", padx=15)
        self.stats_done = tk.Label(stats_bar, text="已检测: 0",
                                   fg=self.COLOR_INFO, bg=self.COLOR_PANEL,
                                   font=("微软雅黑", 10))
        self.stats_done.pack(side="left", padx=15)
        self.stats_high = tk.Label(stats_bar, text="高风险: 0",
                                   fg=self.COLOR_DANGER, bg=self.COLOR_PANEL,
                                   font=("微软雅黑", 10, "bold"))
        self.stats_high.pack(side="left", padx=15)
        self.stats_avg = tk.Label(stats_bar, text="均浊: -- NTU",
                                  fg="#dcdde1", bg=self.COLOR_PANEL,
                                  font=("微软雅黑", 10))
        self.stats_avg.pack(side="left", padx=15)

        # 表格
        table_frame = tk.Frame(detail_frame, bg=self.COLOR_BG)
        table_frame.pack(fill="both", expand=True, padx=6, pady=4)

        columns = ('seq', 'point_id', 'x_m', 'y_m', 'ridge',
                   'turbidity', 'risk', 'read_time')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=10)

        col_defs = [
            ('seq', '#', 38),
            ('point_id', '采样点编号', 105),
            ('x_m', 'X(m)', 72),
            ('y_m', 'Y(m)', 72),
            ('ridge', '垄', 42),
            ('turbidity', '浊度(NTU)', 90),
            ('risk', '风险等级', 78),
            ('read_time', '检测时间', 145),
        ]
        for col_id, col_name, col_w in col_defs:
            self.tree.heading(col_id, text=col_name)
            self.tree.column(col_id, width=col_w, anchor='center', minwidth=col_w)

        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.bind('<<TreeviewSelect>>', self.on_row_select)

        # 初始分割比例 (上 55%, 下 45%)
        self.root.update_idletasks()
        total_h = main_frame.winfo_height()
        if total_h > 200:
            self.pane.sash_place(0, 0, int(total_h * 0.55))

    # =========================================================
    # 地图与底图
    # =========================================================

    def load_image(self):
        if not HAS_PILLOW:
            messagebox.showerror("Error", "需要安装 Pillow 库以支持图像加载。")
            return
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif")])
        if not file_path:
            return
        try:
            self.pil_image = Image.open(file_path)
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if cw < 10:
                cw, ch = 900, 500
            # 统一缩放：长边适配画布 90%，保持比例
            iw, ih = self.pil_image.size
            ratio = min(cw * 0.9 / iw, ch * 0.9 / ih, 1.0)
            new_w, new_h = int(iw * ratio), int(ih * ratio)
            self.pil_image = self.pil_image.resize((new_w, new_h), Image.LANCZOS)
            self.photo_image = ImageTk.PhotoImage(self.pil_image)
            self._render_field_map()
            self.status_var.set("MAP LOADED: 卫星底图已加载。")
        except Exception as e:
            messagebox.showerror("Error", f"图像加载异常: {e}")

    def clear_image(self):
        self.pil_image = None
        self.photo_image = None
        self.heatmap_photo = None
        self._render_field_map()

    # =========================================================
    # 田间地图渲染 (底图 + IDW热力图 + 采样点标记)
    # =========================================================

    def _render_field_map(self):
        """绘制卫星底图、IDW热力图、覆盖圆、采样点标记。
        热力图与覆盖圆被裁剪到农田边界多边形内。
        """
        self.canvas.delete("all")
        self.heatmap_photo = None
        self._map_point_ids = []

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10:
            cw, ch = 900, 500

        if not self.sampling_points:
            return

        # 米制→画布映射，基于采样点+多边形整体bbox
        all_mx = [p['x_m'] for p in self.sampling_points]
        all_my = [p['y_m'] for p in self.sampling_points]
        for vx, vy in self.field_polygon_m:
            all_mx.append(vx)
            all_my.append(vy)
        min_x, max_x = min(all_mx), max(all_mx)
        min_y, max_y = min(all_my), max(all_my)
        rng_x = max_x - min_x or 1
        rng_y = max_y - min_y or 1
        margin = 45

        def _to_canvas(mx, my):
            px = margin + (mx - min_x) / rng_x * (cw - 2 * margin)
            py = margin + (my - min_y) / rng_y * (ch - 2 * margin)
            return px, py

        # 多边形画布坐标 (用于裁剪 + 底图对齐)
        poly_px = [_to_canvas(vx, vy) for vx, vy in self.field_polygon_m] if self.field_polygon_m else []

        # 图层0: 卫星底图 (缩放到与多边形bbox对齐)
        if self.photo_image and poly_px:
            pxs = [p[0] for p in poly_px]
            pys = [p[1] for p in poly_px]
            pmin_x, pmax_x = min(pxs), max(pxs)
            pmin_y, pmax_y = min(pys), max(pys)
            pw, ph = pmax_x - pmin_x, pmax_y - pmin_y
            if pw > 10 and ph > 10:
                # 缩放底图至多边形区域
                iw, ih = self.pil_image.size
                ratio = min(pw / iw, ph / ih)
                disp_w, disp_h = int(iw * ratio), int(ih * ratio)
                disp_img = self.pil_image.resize((disp_w, disp_h), Image.LANCZOS)
                self._disp_photo = ImageTk.PhotoImage(disp_img)
                ox = int(pmin_x + (pw - disp_w) / 2)
                oy = int(pmin_y + (ph - disp_h) / 2)
                self.canvas.create_image(ox, oy, anchor="nw", image=self._disp_photo)
        elif self.photo_image:
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo_image)

        # 图层1: IDW 热力图 (裁剪到多边形内)
        if HAS_PILLOW and poly_px:
            measured = [p for p in self.sampling_points if p['turbidity'] is not None]
            if len(measured) >= 3:
                self._render_idw_heatmap(cw, ch, measured, _to_canvas, poly_px)

        # 图层2: 覆盖半径圆
        if HAS_PILLOW:
            self._render_coverage_circles(cw, ch, _to_canvas, poly_px)

        # 图层3: 多边形边界线
        if poly_px:
            for i in range(len(poly_px)):
                x1, y1 = poly_px[i]
                x2, y2 = poly_px[(i + 1) % len(poly_px)]
                self.canvas.create_line(x1, y1, x2, y2,
                                        fill=self.COLOR_INFO, width=2, dash=(8, 3),
                                        tags="polygon")

        # 图层4: 采样点标记
        for i, pt in enumerate(self.sampling_points):
            px, py = _to_canvas(pt['x_m'], pt['y_m'])
            is_sel = (i == self.selected_index)
            risk = pt['risk']
            color = self.RISK_COLORS.get(risk, '#718093')

            r = 9 if is_sel else 6
            w = 3 if is_sel else 1.5
            oid = self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                          fill=self.COLOR_BG, outline=color,
                                          width=w, tags=("point", str(i)))
            self._map_point_ids.append(oid)

            inner_r = 4 if is_sel else 2.5
            inner_fill = color if pt['turbidity'] is not None else ""
            self.canvas.create_oval(px - inner_r, py - inner_r,
                                    px + inner_r, py + inner_r,
                                    fill=inner_fill, outline="",
                                    tags=("point", str(i)))

            label = pt['point_id'].replace('R', '').replace('-P', '.')
            self.canvas.create_text(px + 12, py - 10, text=label,
                                    fill=color, font=("Consolas", 7, "bold"),
                                    anchor="w", tags=("point", str(i)))

    def _render_coverage_circles(self, cw, ch, to_canvas, poly_px):
        """为每个采样点绘制半透明覆盖半径圆，表示传感器有效测量范围。
        poly_px: 多边形顶点(预留，覆盖圆延伸出边界属正常行为)
        """
        radius_m = self.coverage_radius_m
        # 将米制半径转为画布像素
        # 利用 to_canvas 的 scale: 取两点的画布距离 / 米制距离
        p0 = to_canvas(0, 0)
        p1 = to_canvas(1, 0)
        scale_px_per_m = abs(p1[0] - p0[0])
        radius_px = radius_m * scale_px_per_m

        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for pt in self.sampling_points:
            px, py = to_canvas(pt['x_m'], pt['y_m'])
            r = radius_px
            risk = pt['risk']
            if risk == 'high':
                fill_rgba = (231, 76, 60, 18)
                outline_rgba = (231, 76, 60, 70)
            elif risk == 'medium':
                fill_rgba = (241, 196, 15, 18)
                outline_rgba = (241, 196, 15, 70)
            elif risk == 'low':
                fill_rgba = (39, 174, 96, 18)
                outline_rgba = (39, 174, 96, 70)
            else:
                fill_rgba = (100, 100, 100, 12)
                outline_rgba = (100, 100, 100, 45)

            draw.ellipse([px - r, py - r, px + r, py + r],
                         fill=fill_rgba, outline=outline_rgba, width=1)

        self._overlay_circles = ImageTk.PhotoImage(overlay)
        self.canvas.create_image(0, 0, anchor="nw",
                                 image=self._overlay_circles, tags="circles")

    def _render_idw_heatmap(self, cw, ch, measured, to_canvas, poly_px):
        """IDW 空间插值生成浊度热力图，裁剪到农田多边形内。
        poly_px: 多边形顶点画布坐标列表 [(x,y), ...]
        """
        grid_step = max(12, min(cw, ch) // 60)
        r2_limit = (max(cw, ch) * 0.4) ** 2

        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        half = grid_step / 2.0

        m_pts = []
        for p in measured:
            if p['turbidity'] is not None:
                px, py = to_canvas(p['x_m'], p['y_m'])
                m_pts.append((px, py, p['turbidity']))

        if not poly_px or not m_pts:
            return

        pxs = [p[0] for p in poly_px]
        pys = [p[1] for p in poly_px]
        pad = grid_step * 2
        gx_min = max(0, int(min(pxs)) - pad)
        gx_max = min(cw, int(max(pxs)) + pad)
        gy_min = max(0, int(min(pys)) - pad)
        gy_max = min(ch, int(max(pys)) + pad)

        gx = gx_min
        while gx <= gx_max:
            gy = gy_min
            while gy <= gy_max:
                # 仅渲染多边形内部格点
                if not _point_in_poly(gx, gy, poly_px):
                    gy += grid_step
                    continue

                w_sum = 0.0
                v_sum = 0.0
                for mx, my, mt in m_pts:
                    dx = gx - mx
                    dy = gy - my
                    d2 = dx * dx + dy * dy
                    if d2 < 1.0:
                        d2 = 1.0
                    if d2 > r2_limit:
                        continue
                    w = 1.0 / d2
                    w_sum += w
                    v_sum += w * mt

                if w_sum > 0:
                    turb = v_sum / w_sum
                    color = self._turbidity_to_rgba(turb)
                    draw.rectangle(
                        [gx - half, gy - half, gx + half, gy + half], fill=color)

                gy += grid_step
            gx += grid_step

        self.heatmap_photo = ImageTk.PhotoImage(overlay)
        self.canvas.create_image(0, 0, anchor="nw",
                                 image=self.heatmap_photo, tags="heatmap")

    def _turbidity_to_rgba(self, turb):
        """浊度值映射到 RGBA (绿低->黄中->橙->红高)，alpha 跟随强度"""
        turb = max(0, min(600, turb))
        # 在两段色标之间线性插值
        segs = self.HEAT_COLORS
        for i in range(len(segs) - 1):
            v0, (r0, g0, b0) = segs[i]
            v1, (r1, g1, b1) = segs[i + 1]
            if turb <= v1:
                t = (turb - v0) / (v1 - v0) if v1 != v0 else 0
                r = int(r0 + (r1 - r0) * t)
                g = int(g0 + (g1 - g0) * t)
                b = int(b0 + (b1 - b0) * t)
                break
        else:
            r, g, b = segs[-1][1]

        alpha = int(60 + 100 * (turb / 600))
        return (r, g, b, alpha)

    # =========================================================
    # 地图点击 → 选中采样点
    # =========================================================

    def on_canvas_click(self, event):
        items = self.canvas.find_withtag("point")
        # 查找点击位置附近的点标记
        overlapping = self.canvas.find_overlapping(
            event.x - 10, event.y - 10, event.x + 10, event.y + 10)
        for oid in overlapping:
            tags = self.canvas.gettags(oid)
            for t in tags:
                if t.isdigit():
                    idx = int(t)
                    self.tree.selection_set(str(idx))
                    self.tree.see(str(idx))
                    return

    # =========================================================
    # 数据导入 (兼容路径规划模块的 CSV / JSON 导出格式)
    # [UPDATED 2026-07-13] CSV 导入同时读取像素坐标，用于地图定位
    # =========================================================

    def import_from_csv(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            title="导入路径规划导出的采样点 CSV")
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)

            imported = 0
            in_points = False
            for row in rows:
                if not row:
                    continue
                if '采样点坐标清单' in row[0] or '采集轮次' in row[0]:
                    in_points = True
                    continue
                if '路径段时间预估' in row[0]:
                    in_points = False
                    continue
                if not in_points or len(row) < 8:
                    continue
                try:
                    pid = str(row[1])
                    px_x = float(row[3]) if len(row) > 3 else None  # 像素X
                    px_y = float(row[4]) if len(row) > 4 else None  # 像素Y
                    rel_x = float(row[5]) if len(row) > 5 else 0.0  # 相对X(m)
                    rel_y = float(row[6]) if len(row) > 6 else 0.0  # 相对Y(m)
                    ridge = int(row[7]) if len(row) > 7 else 0
                except (ValueError, IndexError):
                    continue

                if any(p['point_id'] == pid for p in self.sampling_points):
                    continue

                self.sampling_points.append({
                    'point_id': pid,
                    'px_x': px_x,
                    'px_y': px_y,
                    'x_m': rel_x,
                    'y_m': rel_y,
                    'ridge': ridge,
                    'turbidity': None,
                    'risk': 'pending',
                    'read_time': ''
                })
                imported += 1

            self._refresh_all()
            self.status_var.set(f"IMPORTED: 从 CSV 导入 {imported} 个采样点。")

        except Exception as e:
            messagebox.showerror("导入失败", f"CSV 解析异常: {e}")

    def import_from_json(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            title="导入路径规划导出的 JSON")
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            imported = 0
            for rnd_data in data.get('rounds', []):
                for wp in rnd_data.get('waypoints', []):
                    pid = wp.get('id', '')
                    if any(p['point_id'] == pid for p in self.sampling_points):
                        continue
                    rel = wp.get('relative_m', [0, 0])
                    pix = wp.get('pixel', [None, None])
                    self.sampling_points.append({
                        'point_id': pid,
                        'px_x': pix[0] if pix[0] is not None else None,
                        'px_y': pix[1] if pix[1] is not None else None,
                        'x_m': rel[0],
                        'y_m': rel[1],
                        'ridge': wp.get('ridge_index', 0),
                        'turbidity': None,
                        'risk': 'pending',
                        'read_time': ''
                    })
                    imported += 1

            # [UPDATED 2026-07-13] 导入农田边界多边形，用于裁剪热力图
            poly_data = data.get('field_polygon', {})
            verts = poly_data.get('vertices_m', [])
            if verts:
                self.field_polygon_m = [(v[0], v[1]) for v in verts]

            self._refresh_all()
            self.status_var.set(f"IMPORTED: 从 JSON 导入 {imported} 个采样点。"
                                + (f" 含农田边界({len(verts)}顶点)。" if verts else ""))

        except Exception as e:
            messagebox.showerror("导入失败", f"JSON 解析异常: {e}")

    # =========================================================
    # 传感器读数 (核心检测逻辑)
    # =========================================================

    def _read_physical_sensor(self):
        """
        光敏传感器读数接口。
        实际部署时替换为串口/USB/I2C 读取传感器模组的浊度值。
        返回值: float, 单位 NTU
        """
        # TODO: 替换为实际传感器驱动代码
        return round(random.uniform(30, 600), 1)

    def _classify_risk(self, turbidity):
        if turbidity < self.threshold_medium:
            return 'low'
        elif turbidity < self.threshold_high:
            return 'medium'
        else:
            return 'high'

    def apply_thresholds(self):
        try:
            tm = float(self.entry_thresh_mid.get())
            th = float(self.entry_thresh_high.get())
            cr = float(self.entry_coverage_r.get())
        except ValueError:
            messagebox.showerror("输入错误", "阈值必须为数值。")
            return
        if tm <= 0 or th <= tm:
            messagebox.showerror("输入错误", "中风险阈值需>0，高风险阈值需>中风险阈值。")
            return
        if cr <= 0:
            messagebox.showerror("输入错误", "覆盖半径需>0。")
            return
        self.threshold_medium = tm
        self.threshold_high = th
        self.coverage_radius_m = cr

        for pt in self.sampling_points:
            if pt['turbidity'] is not None:
                pt['risk'] = self._classify_risk(pt['turbidity'])

        self._refresh_all()
        self.status_var.set(
            f"THRESHOLD UPDATED: 中>{tm}NTU, 高>{th}NTU, 覆盖半径{cr}m。")

    def read_sensor_single(self):
        if self.selected_index < 0:
            messagebox.showwarning("提示", "请先选中一个采样点（点击地图或表格）。")
            return

        pt = self.sampling_points[self.selected_index]
        turb = self._read_physical_sensor()
        risk = self._classify_risk(turb)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        pt['turbidity'] = turb
        pt['risk'] = risk
        pt['read_time'] = now_str

        self.lbl_reading.config(text=f"{turb:.1f} NTU", fg=self.COLOR_ACCENT)
        self.lbl_risk_result.config(
            text=f"风险: {self._risk_label(risk)}", fg=self.RISK_COLORS[risk])

        self._refresh_all()

        if risk == 'high':
            self.status_var.set(
                f"ALERT! {pt['point_id']} 浊度 {turb:.1f} NTU 超出高风险阈值！建议立即干预。")
            self.root.bell()
        elif risk == 'medium':
            self.status_var.set(
                f"WARNING: {pt['point_id']} 浊度 {turb:.1f} NTU，中等风险，关注变化趋势。")
        else:
            self.status_var.set(
                f"OK: {pt['point_id']} 浊度 {turb:.1f} NTU，当前风险可控。")

    # =========================================================
    # 一键全检
    # =========================================================

    def start_full_scan(self):
        unchecked = [i for i, pt in enumerate(self.sampling_points)
                     if pt['turbidity'] is None]
        if not unchecked:
            messagebox.showinfo("提示", "所有采样点均已完成检测。")
            return

        try:
            delay = float(self.entry_scan_delay.get())
        except ValueError:
            delay = 0.8

        self.is_scanning = True
        self.status_var.set(f"SCANNING: 开始顺序巡检，共 {len(unchecked)} 个待测点...")
        self._scan_next(unchecked, 0, delay)

    def _scan_next(self, indices, pos, delay):
        if not self.is_scanning or pos >= len(indices):
            if pos >= len(indices):
                self.is_scanning = False
                self.lbl_scan_progress.config(text="全检完成")
                self.status_var.set("SCAN COMPLETE: 全部待测点巡检完毕。")
            return

        idx = indices[pos]
        pt = self.sampling_points[idx]
        turb = self._read_physical_sensor()
        risk = self._classify_risk(turb)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        pt['turbidity'] = turb
        pt['risk'] = risk
        pt['read_time'] = now_str

        self.tree.selection_set(str(idx))
        self.tree.see(str(idx))
        self.selected_index = idx

        self.lbl_current_point.config(text=f"当前采样点: {pt['point_id']}")
        self.lbl_reading.config(text=f"{turb:.1f} NTU", fg=self.COLOR_ACCENT)
        self.lbl_risk_result.config(
            text=f"风险: {self._risk_label(risk)}", fg=self.RISK_COLORS[risk])
        self.lbl_scan_progress.config(text=f"进度: {pos + 1}/{len(indices)}")

        if risk == 'high':
            self.status_var.set(
                f"ALERT! [{pos + 1}/{len(indices)}] {pt['point_id']} "
                f"浊度 {turb:.1f} NTU — 高风险！")
            self.root.bell()

        self._refresh_all()

        ms_delay = int(delay * 1000)
        self.scan_job = self.root.after(ms_delay,
                                        lambda: self._scan_next(indices, pos + 1, delay))

    def stop_full_scan(self):
        self.is_scanning = False
        if self.scan_job:
            self.root.after_cancel(self.scan_job)
            self.scan_job = None
        self.lbl_scan_progress.config(text="已手动停止")
        self.status_var.set("SCAN STOPPED: 巡检已手动终止。")

    # =========================================================
    # 统一刷新 (表格 + 地图)
    # =========================================================

    def _refresh_all(self):
        self._refresh_table()
        self._render_field_map()

    def _refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        for i, pt in enumerate(self.sampling_points):
            turb_str = f"{pt['turbidity']:.1f}" if pt['turbidity'] is not None else '--'
            risk_str = self._risk_label(pt['risk'])
            time_str = pt['read_time'] if pt['read_time'] else '--'

            iid = str(i)
            self.tree.insert('', 'end', iid=iid, values=(
                i + 1,
                pt['point_id'],
                f"{pt['x_m']:.2f}",
                f"{pt['y_m']:.2f}",
                pt['ridge'],
                turb_str,
                risk_str,
                time_str
            ))

        self.tree.tag_configure('high_risk', foreground=self.COLOR_DANGER)
        self.tree.tag_configure('medium_risk', foreground=self.COLOR_ALERT)
        self.tree.tag_configure('low_risk', foreground=self.COLOR_SAFE)

        for i, pt in enumerate(self.sampling_points):
            if pt['risk'] == 'high':
                self.tree.item(str(i), tags=('high_risk',))
            elif pt['risk'] == 'medium':
                self.tree.item(str(i), tags=('medium_risk',))
            elif pt['risk'] == 'low':
                self.tree.item(str(i), tags=('low_risk',))

        total = len(self.sampling_points)
        done = sum(1 for p in self.sampling_points if p['turbidity'] is not None)
        high = sum(1 for p in self.sampling_points if p['risk'] == 'high')
        if done > 0:
            avg_t = sum(p['turbidity'] for p in self.sampling_points
                        if p['turbidity'] is not None) / done
            avg_str = f"{avg_t:.1f} NTU"
        else:
            avg_str = "-- NTU"

        self.stats_total.config(text=f"总计: {total} 点")
        self.stats_done.config(text=f"已检测: {done}")
        self.stats_high.config(text=f"高风险: {high}")
        self.stats_avg.config(text=f"均浊: {avg_str}")

    def _risk_label(self, risk):
        mapping = {'low': '低风险', 'medium': '中风险',
                   'high': '高风险', 'pending': '待检测'}
        return mapping.get(risk, '待检测')

    def on_row_select(self, event):
        sel = self.tree.selection()
        if not sel:
            self.selected_index = -1
            self.lbl_current_point.config(text="当前采样点: 未选中")
            self.lbl_reading.config(text="-- NTU", fg="#718093")
            self.lbl_risk_result.config(text="风险: 等待检测", fg="#718093")
            self._render_field_map()
            return

        self.selected_index = int(sel[0])
        pt = self.sampling_points[self.selected_index]
        self.lbl_current_point.config(text=f"当前采样点: {pt['point_id']}")

        if pt['turbidity'] is not None:
            self.lbl_reading.config(text=f"{pt['turbidity']:.1f} NTU",
                                    fg=self.COLOR_ACCENT)
            self.lbl_risk_result.config(
                text=f"风险: {self._risk_label(pt['risk'])}",
                fg=self.RISK_COLORS[pt['risk']])
        else:
            self.lbl_reading.config(text="-- NTU", fg="#718093")
            self.lbl_risk_result.config(text="风险: 等待检测", fg="#718093")

        # 重绘地图以高亮选中点
        self._render_field_map()

    # =========================================================
    # 数据导出
    # =========================================================

    def export_data(self):
        if not self.sampling_points:
            messagebox.showwarning("Warning", "无采集数据可导出。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            title="导出粗定检测数据")
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    '采样点编号', 'X(m)', 'Y(m)', '垄索引',
                    '浊度(NTU)', '风险等级', '检测时间'])
                for pt in self.sampling_points:
                    turb_val = f"{pt['turbidity']:.1f}" if pt['turbidity'] is not None else ''
                    writer.writerow([
                        pt['point_id'],
                        f"{pt['x_m']:.2f}",
                        f"{pt['y_m']:.2f}",
                        pt['ridge'],
                        turb_val,
                        self._risk_label(pt['risk']),
                        pt['read_time']
                    ])

            fname = file_path.replace('\\', '/').split('/')[-1]
            self.status_var.set(f"EXPORTED: 数据已写入 {fname}")
            messagebox.showinfo("导出成功",
                                f"已导出 {len(self.sampling_points)} 条记录至:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"文件写入异常: {e}")

    # =========================================================
    # 重置
    # =========================================================

    def clear_all(self):
        if messagebox.askyesno("确认清空", "确认清空全部检测数据？此操作不可撤销。"):
            self.stop_full_scan()
            self.sampling_points = []
            self.selected_index = -1
            self.pil_image = None
            self.photo_image = None
            self._disp_photo = None
            self.heatmap_photo = None
            self._overlay_circles = None
            self.field_polygon_m = []
            self.lbl_current_point.config(text="当前采样点: 未选中")
            self.lbl_reading.config(text="-- NTU", fg="#718093")
            self.lbl_risk_result.config(text="风险: 等待检测", fg="#718093")
            self.lbl_scan_progress.config(text="")
            self._refresh_all()
            self.status_var.set("SYS READY: 数据已清空，等待导入采样点坐标。")


if __name__ == "__main__":
    root = tk.Tk()
    app = FieldSensingModule(root)
    root.mainloop()
