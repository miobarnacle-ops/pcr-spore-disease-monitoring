import tkinter as tk
from tkinter import ttk
import random
import time

class SmartInspectionSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("基于DNA-PCR与多模态感知的智能巡检系统 V1.0")
        self.root.geometry("800x550")
        
        # 创建选项卡控件
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=10, expand=True, fill='both')
        
        # 初始化三大功能模块
        self.init_dashboard_tab()
        self.init_vision_tab()
        self.init_end_effector_tab()

    def init_dashboard_tab(self):
        """模块一：多模态数据监控大屏"""
        self.tab1 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab1, text="多模态环境数据监控")
        
        ttk.Label(self.tab1, text="实时环境与孢子浓度数据", font=("微软雅黑", 16, "bold")).pack(pady=20)
        
        # 模拟数据展示区
        self.data_frame = ttk.LabelFrame(self.tab1, text="当前系统状态")
        self.data_frame.pack(padx=20, pady=10, fill='x')
        
        self.temp_label = ttk.Label(self.data_frame, text="田间温度: -- ℃", font=("微软雅黑", 12))
        self.temp_label.grid(row=0, column=0, padx=20, pady=10)
        
        self.spore_label = ttk.Label(self.data_frame, text="空气孢子浓度: -- 个/m³", font=("微软雅黑", 12))
        self.spore_label.grid(row=0, column=1, padx=20, pady=10)
        
        self.warning_label = ttk.Label(self.data_frame, text="预警状态: 正常", foreground="green", font=("微软雅黑", 12, "bold"))
        self.warning_label.grid(row=0, column=2, padx=20, pady=10)

        # 刷新按钮
        ttk.Button(self.tab1, text="读取最新传感器数据", command=self.update_mock_data).pack(pady=20)

    def init_vision_tab(self):
        """模块二：YOLOv11 视觉检测模拟"""
        self.tab2 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab2, text="孢子图像智能识别")
        
        ttk.Label(self.tab2, text="YOLOv11 微观孢子识别引擎", font=("微软雅黑", 16, "bold")).pack(pady=20)
        
        # 占位图区域 (软著截图时可以替换为真实的病害图)
        self.canvas = tk.Canvas(self.tab2, width=400, height=250, bg="black")
        self.canvas.pack(pady=10)
        self.canvas.create_text(200, 125, text="等待导入显微摄像头画面...", fill="white", font=("微软雅黑", 12))
        
        self.result_label = ttk.Label(self.tab2, text="检测结果: 暂无", font=("微软雅黑", 12))
        self.result_label.pack(pady=10)
        
        ttk.Button(self.tab2, text="运行 YOLOv11 识别算法", command=self.run_fake_yolo).pack(pady=10)

    def init_end_effector_tab(self):
        """模块三：柔性端拾器与底盘控制"""
        self.tab3 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab3, text="底层硬件与端拾器控制")
        
        ttk.Label(self.tab3, text="系统机电联调与采样控制", font=("微软雅黑", 16, "bold")).pack(pady=20)
        
        control_frame = ttk.LabelFrame(self.tab3, text="端拾器动作指令下发")
        control_frame.pack(padx=20, pady=10, fill='both', expand=True)
        
        ttk.Label(control_frame, text="目标采样坐标 (X, Y, Z):").grid(row=0, column=0, padx=10, pady=20)
        ttk.Entry(control_frame, width=15).grid(row=0, column=1, padx=10, pady=20)
        
        # 端拾器动作按钮
        ttk.Button(control_frame, text="展开端拾器", command=lambda: print("指令: 端拾器展开")).grid(row=1, column=0, padx=10, pady=10)
        ttk.Button(control_frame, text="闭合采样", command=lambda: print("指令: 端拾器闭合采样")).grid(row=1, column=1, padx=10, pady=10)
        ttk.Button(control_frame, text="启动 DNA-PCR 分析液路", command=lambda: print("指令: 液路循环开启")).grid(row=1, column=2, padx=10, pady=10)

    # --- 以下为模拟数据的后台逻辑 ---
    def update_mock_data(self):
        temp = round(random.uniform(20.0, 35.0), 1)
        spore = random.randint(100, 5000)
        
        self.temp_label.config(text=f"田间温度: {temp} ℃")
        self.spore_label.config(text=f"空气孢子浓度: {spore} 个/m³")
        
        if spore > 4000:
            self.warning_label.config(text="预警状态: 高风险 (建议干预)", foreground="red")
        else:
            self.warning_label.config(text="预警状态: 正常", foreground="green")

    def run_fake_yolo(self):
        self.result_label.config(text="系统正在调用模型推理中...")
        self.root.update()
        time.sleep(1) # 模拟算法延迟
        diseases = ["小麦条锈病孢子 (置信度 94%)", "玉米大斑病孢子 (置信度 91%)", "未发现异常"]
        result = random.choice(diseases)
        self.result_label.config(text=f"检测结果: {result}")
        self.canvas.delete("all")
        self.canvas.create_text(200, 125, text=f"[病害边界框渲染完成]\n{result}", fill="lime", font=("微软雅黑", 12))

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartInspectionSystem(root)
    root.mainloop()