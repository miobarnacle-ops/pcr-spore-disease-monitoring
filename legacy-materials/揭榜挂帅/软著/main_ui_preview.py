import tkinter as tk
from tkinter import ttk
import random
import math

class SmartInspectionSystemUI:
    def __init__(self, root):
        self.root = root
        self.root.title("基于DNA-PCR与多模态感知的智能巡检系统 V1.0")
        self.root.geometry("1000x700")
        self.root.configure(bg="#f0f0f0")

        # 顶部系统标题栏
        header_frame = tk.Frame(root, bg="#2c3e50", height=60)
        header_frame.pack(fill="x")
        tk.Label(header_frame, text="基于DNA-PCR与多模态感知的农业病害智能巡检系统", 
                 fg="white", bg="#2c3e50", font=("微软雅黑", 18, "bold")).pack(pady=15)

        # 创建多页式选项卡
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("微软雅黑", 12), padding=[15, 5])
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=10, padx=10, expand=True, fill='both')

        # 初始化五个核心模块
        self.create_tab_slam()
        self.create_tab_vision()
        self.create_tab_pcr()
        self.create_tab_prediction()
        self.create_tab_warning()

    def create_tab_slam(self):
        """模块一：北斗+SLAM定位与路径规划"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 北斗+SLAM定位 ")

        control_frame = ttk.Frame(tab)
        control_frame.pack(fill="x", padx=20, pady=10)
        
        ttk.Label(control_frame, text="实时坐标: 经度 116.397 E, 纬度 39.908 N", font=("微软雅黑", 12)).pack(side="left", padx=10)
        ttk.Label(control_frame, text="当前定位误差: 0.21米 (RTK Fix)", foreground="green", font=("微软雅黑", 12, "bold")).pack(side="left", padx=20)
        ttk.Button(control_frame, text="下发巡检轨迹").pack(side="right", padx=10)

        # 模拟电子地图与轨迹
        canvas = tk.Canvas(tab, bg="#e8f4f8", highlightthickness=1, relief="solid")
        canvas.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 绘制农田网格和轨迹
        for i in range(0, 1000, 50):
            canvas.create_line(i, 0, i, 600, fill="#d0e0e3", dash=(2, 2))
            canvas.create_line(0, i, 1000, i, fill="#d0e0e3", dash=(2, 2))
            
        canvas.create_line(100, 400, 300, 200, 600, 250, 800, 100, fill="#2980b9", width=4, dash=(5, 2))
        canvas.create_oval(790, 90, 810, 110, fill="#e74c3c", outline="white", width=2)
        canvas.create_text(800, 70, text="系统当前位置\n(端拾器待命)", font=("微软雅黑", 10, "bold"), fill="#c0392b")

    def create_tab_vision(self):
        """模块二：孢子图像智能识别"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 图像智能识别 ")

        # 视窗分屏
        img_frame = ttk.Frame(tab)
        img_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 左侧原图
        left_canvas = tk.Canvas(img_frame, bg="black", width=400, height=300)
        left_canvas.pack(side="left", padx=20)
        left_canvas.create_text(200, 150, text="[端拾器显微镜头回传原图]\n\n等待图像输入...", fill="white", font=("微软雅黑", 12))

        # 右侧AI识别图
        right_canvas = tk.Canvas(img_frame, bg="#1a1a1a", width=400, height=300)
        right_canvas.pack(side="right", padx=20)
        right_canvas.create_rectangle(150, 100, 250, 200, outline="lime", width=3)
        right_canvas.create_text(200, 90, text="小麦条锈病孢子 96.5%", fill="lime", font=("微软雅黑", 10))

        # 底部识别结果表格
        list_frame = ttk.LabelFrame(tab, text="YOLOv11 实时检测队列")
        list_frame.pack(fill="x", padx=20, pady=10)
        ttk.Label(list_frame, text="1. 检出目标: 小麦条锈病孢子 | 尺寸: 45μm | 综合准确率: 96.5% | 状态: 记入数据库", font=("微软雅黑", 11)).pack(anchor="w", padx=10, pady=5)
        ttk.Label(list_frame, text="2. 检出目标: 玉米大斑病孢子 | 尺寸: 60μm | 综合准确率: 92.1% | 状态: 记入数据库", font=("微软雅黑", 11)).pack(anchor="w", padx=10, pady=5)

    def create_tab_pcr(self):
        """模块三：DNA-PCR 检测测定"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" DNA-PCR检测 ")

        info_frame = ttk.Frame(tab)
        info_frame.pack(fill="x", padx=20, pady=10)
        ttk.Label(info_frame, text="样本编号: SP-20260615-001 | 采样机构: 柔性端拾器", font=("微软雅黑", 12)).pack(side="left")
        ttk.Label(info_frame, text="靶标测定: 小麦条锈病菌 (阳性)", foreground="red", font=("微软雅黑", 14, "bold")).pack(side="right")

        # 模拟PCR扩增曲线
        canvas = tk.Canvas(tab, bg="white", highlightthickness=1, relief="solid")
        canvas.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 绘制坐标轴
        canvas.create_line(50, 350, 850, 350, width=2) # X轴
        canvas.create_line(50, 350, 50, 50, width=2)   # Y轴
        canvas.create_text(450, 380, text="扩增循环数 (Cycles)", font=("微软雅黑", 12))
        canvas.create_text(20, 200, text="ΔRn", font=("微软雅黑", 12), angle=90)

        # 绘制S型曲线 (模拟PCR)
        points = []
        for x in range(0, 800, 10):
            cycle = x / 20
            # Logistic 增长曲线公式模拟 PCR
            y = 300 / (1 + math.exp(-0.3 * (cycle - 20)))
            points.append(50 + x)
            points.append(350 - y)
        
        canvas.create_line(points, fill="#e74c3c", width=3, smooth=True)
        # 阈值线
        canvas.create_line(50, 250, 850, 250, fill="#7f8c8d", dash=(4, 4), width=2)
        canvas.create_text(100, 240, text="阈值线", font=("微软雅黑", 10))
        canvas.create_text(450, 150, text="Ct值 = 20.5", font=("微软雅黑", 12, "bold"), fill="#c0392b")

    def create_tab_prediction(self):
        """模块四：孢子浓度动态预测"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 浓度动态预测 ")

        # 模拟折线图
        canvas = tk.Canvas(tab, bg="#f8f9fa", highlightthickness=1, relief="solid")
        canvas.pack(fill="both", expand=True, padx=20, pady=20)
        
        canvas.create_text(450, 30, text="空气孢子浓度与田间湿度耦合时序图 (历史 + 预测)", font=("微软雅黑", 14, "bold"))
        
        # X轴中线分割历史与预测
        canvas.create_line(450, 80, 450, 400, fill="#bdc3c7", dash=(5, 5), width=2)
        canvas.create_text(250, 380, text="过去 48 小时 (实测)", font=("微软雅黑", 12))
        canvas.create_text(650, 380, text="未来 72 小时 (预测)", font=("微软雅黑", 12))

        # 历史实线
        canvas.create_line(50, 300, 150, 280, 250, 310, 350, 200, 450, 150, fill="#2980b9", width=3)
        # 预测虚线 (指数上升)
        canvas.create_line(450, 150, 550, 120, 650, 80, 750, 60, 850, 40, fill="#e67e22", width=3, dash=(5, 5))

        ttk.Label(tab, text="预测模型输出: 当相对湿度持续高于85%时，孢子浓度将在48小时内呈指数级上升。", font=("微软雅黑", 12)).pack(pady=10)

    def create_tab_warning(self):
        """模块五：综合分析预警与决策"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 综合分析预警 ")

        # 顶部预警横幅
        warning_frame = tk.Frame(tab, bg="#c0392b")
        warning_frame.pack(fill="x", padx=20, pady=20)
        tk.Label(warning_frame, text="⚠️ 预警级别：高危 | 结合当前孢子浓度激增与PCR确诊，预测3-7天内A地块将爆发大规模病害！", 
                 fg="white", bg="#c0392b", font=("微软雅黑", 14, "bold"), pady=15).pack()

        # 底部决策面板
        decision_frame = ttk.LabelFrame(tab, text="多模态中枢决策输出")
        decision_frame.pack(fill="both", expand=True, padx=20, pady=10)

        instructions = [
            "1. 坐标锁定: 系统已标记高危发病病灶区 (经度 116.397, 纬度 39.908)。",
            "2. 采样复核: 已生成端拾器二次靶向采样工单，等待执行。",
            "3. 农技建议: 建议立刻开启通风设备降低田间湿度，并准备定点喷洒作业。",
            "4. 数据归档: DNA-PCR 图谱与 YOLOv11 影像已打包上传至云端病害数据库。"
        ]

        for i, text in enumerate(instructions):
            ttk.Label(decision_frame, text=text, font=("微软雅黑", 12)).pack(anchor="w", padx=20, pady=15)

        ttk.Button(decision_frame, text="一键下发执行工单").pack(pady=20)

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartInspectionSystemUI(root)
    root.mainloop()