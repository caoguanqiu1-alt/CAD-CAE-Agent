# CAD-CAE Agent — SolidWorks 建模与仿真

**中文文档 V2（2026-09-29）· 仿真图集更新于 2026-09-30**

本项目基于 [andrewbartels1/SolidworksMCP-python](https://github.com/andrewbartels1/SolidworksMCP-python) 的 MIT 开源代码，扩展了在 **SOLIDWORKS 2020 SP5** 上运行的参数化建模和 Simulation 静力分析流程。保留上游版权及许可证；[上游英文说明](README.en.md)单独存档。

## CAE 仿真过程与结果图集

以下 7 张不同的图片来自本项目开发过程中的同一段本机验证记录，包括几何检查、单载荷求解、多载荷计划、接触排错和导向后的接触求解。原始图片直接归档，未修改模型、云图颜色或数值；原文件名和 SHA-256 见[图片来源记录](docs/cae/gallery.md)。

云图显示的是**合位移 URES，单位 mm**，蓝色位移小、红色位移大。**各图使用自己的色标范围，不能仅凭颜色比较位移大小，也不能把颜色当作强度安全程度。** 图中左侧的二维尺寸图是零件内原有的参考图片。

### 1. 求解前的几何检查

API 导出的双孔连杆模型预览。该阶段识别了 12 个面、20 条边、8 个顶点，并检查持久引用在保存重开后仍可恢复；此图尚无有限元结果。选面阶段另存的预览与此图内容及文件哈希相同，合并展示；这张导出图不证明界面高亮颜色。

![求解前的双孔连杆几何预览](docs/cae/assets/geometry-preview.png)

### 2. 单载荷：1000 N 轴向拉伸

大孔内壁固定，小孔内壁沿全局 +X 方向施加总力 **1000 N**；材料为 6061-T6 库参数、线弹性各向同性，名义网格 **3 mm**。最大合位移为 **0.007041338 mm（约 7.04 μm）**，截图变形比例为 1 倍。此简化工况未模拟销轴接触，也未做网格收敛检查。

![1000 N 轴向拉伸的 SOLIDWORKS 结果树与合位移云图](docs/cae/assets/single-load-1000n-solidworks.png)

同一次求解的视口导出图如下；它没有色标，数值以带 URES(mm) 图例的上图和 API 回读记录为准。

![同一次 1000 N 拉伸求解的视口导出图](docs/cae/assets/single-load-1000n-viewport.png)

### 3. 多载荷：一次 MCP 计划完成三档网格求解

大孔内壁固定；小孔内壁与小端上环面分别施加全局 XYZ 力 **(600, 50, 25) N**、**(400, −50, −25) N**，合外力为 (+1000, 0, 0) N。截图为 `AgentPlan_2load` 的 **3 mm** 网格结果，最大 URES 为 **0.139222473 mm**。5 / 4 / 3 mm 网格的位移相邻变化约 **0.277% / 0.203%**，满足本次 1% 判据；峰值应力未达到同一判据。载荷分布与上一工况不同，两者不是同一工况的网格对比。

![双载荷计划的 SOLIDWORKS 合位移云图](docs/cae/assets/multiload-plan-solidworks.png)

### 4. 接触排错：缺少限位的初始研究

**以下为异常工况记录，不作为有效工程结果。** 连杆和两根独立销轴共 3 个实体，设置 2 组无穿透接触，大销轴固定、小销轴受 +X 1000 N。截图来自 `Pin_NoPen_1000N` 的 **4 mm** 网格，最大 URES 约 **0.373 mm**。后续 3 / 2 mm 网格位移升至约 **52.032 / 31.793 mm**，暴露出未限制的自由运动；求解器返回成功不能证明工况有效。

![缺少限位的销轴接触排错截图，结果不可用于设计判断](docs/cae/assets/pin-contact-diagnostic-solidworks.png)

### 5. 销轴接触：补充轴向限位与外部导向

在示例安装假设下增加两个轴向限位和一个 Z 向导向，保留两组无穿透接触及 +X **1000 N** 载荷。截图为 `Pin_Guided_1000N` 的 **2 mm** 网格结果，最大 URES 为 **0.011234013 mm**。4 / 3 / 2 mm 网格位移相邻变化约 **0.240% / 0.172%**，满足 1% 判据；峰值应力仍未收敛。

![2 mm 网格下带限位和导向的销轴接触合位移云图](docs/cae/assets/pin-guided-ures.png)

### 6. 销轴接触：完整计划执行与保存重开复核

在另一份三实体副本上，通过一次 `sw_simulation_run_plan` 调用完成材料、约束、两组接触和 **5 / 4 / 3 mm** 网格求解。截图为 `AgentPin_Guided` 的 **3 mm** 网格，最大 URES 为 **0.011214703 mm**；位移相邻变化约 **0.269% / 0.239%**，满足 1% 判据，峰值应力未达到同一判据。保存、关闭并重新打开后，接触、边界对象和位移结果均已回读复核。

![单次 MCP 计划完成的三实体销轴接触合位移云图](docs/cae/assets/pin-plan-solidworks.png)

1000 N、零间隙、无摩擦及外部导向均为示例假设，以上图片用于展示真实执行过程，不能据此完成实际设备的强度定型。各档网格的完整数值与限制见[CAE 验证记录](docs/cae/verification.md)。

## 从 API 绘图到 CAD-CAE Agent

最初的本机目标是通过 C# COM API 直接控制 SOLIDWORKS，生成 `Sketch1 → Boss-Extrude1`，并检查一个 100 × 60 × 10 mm 零件。现在的流程由 AI 客户端规划，MCP 暴露工具，Windows 上的 SOLIDWORKS COM 与 Simulation 执行建模、求解和结果回读。MCP 是工具接口；单独启动 MCP 不会形成独立自主的 Agent。

详细的时间线、证据和差异见 [API 绘图到 CAD-CAE Agent：版本 V2](docs/API绘图到CAD-CAE-Agent_演进_V2.md)。

## 项目概览

本项目以可检查的迭代流程组织 SOLIDWORKS 自动化：

1. 描述几何或工程意图，明确尺寸、材料、载荷和约束。
2. 由 AI 客户端制定建模或仿真步骤。
3. 调用 MCP 工具，由 COM API 在真实 SOLIDWORKS 中执行。
4. 回读特征树、实体、研究、求解结果和输出文件。
5. 对失败或异常结果定位原因，再修正计划。

上游提供 Python MCP 服务、COM/VBA 适配与安全封装，以及草图、建模、工程图、分析、导出、自动化、模板和宏工具；可选的 Agent 编排与提示词测试代码位于 `src/solidworks_mcp/agents/`。本仓库增加了 SW2020 稳定入口、建模守卫和 Simulation 静力扩展。上游的功能目录与本仓库的**实测范围**应分别阅读。

## 已实现与验证

| 能力 | 本机证据 |
| --- | --- |
| 直接 COM 建模 | 实测创建、重建并保存 `Sketch1 → Boss-Extrude1`；几何为 100 × 60 × 10 mm，体积 60,000 mm³。 |
| MCP 建模 | SW2020 真实模式下完成工具调用、实体与特征回读；工具发现保持 COM 延迟连接。 |
| 静力分析 | 本机 SW2020 SP5 / Simulation 完成多载荷、多网格、URES(mm) 云图及原生结果归档。 |
| 销轴接触 | 三实体、两组无穿透接触；位移相邻网格变化低于 1%，峰值应力未达到同一收敛标准。 |
| 重新连接 | 两次新 stdio 连接均发现 149 个工具，其中 8 个为仿真工具；原生研究和结果可回读。 |

本机验证细节：[安装与演示](README_CAE.md) · [仿真计划接口](SIMULATION_PHASE3.md) · [数值和限制](docs/cae/verification.md) · [SW2020 兼容性](SW2020_COMPAT.md)。

## 当前边界

- Mock 适配器的输出是模拟值，不能作为工程结论。
- 实时 3D 视口流、逐检查点的干涉验证、流体分析及本静力扩展范围外的仿真类型尚未验证；简单 SimulationXpress 拓扑优化也不属于已验证能力。
- 示例销轴工况的 1000 N 载荷、零间隙、无摩擦和外部导向是建模假设。位移收敛不能证明峰值应力、局部接触压力、疲劳或真实设备安全性。
- 不能将示例面 ID、约束和载荷直接套用到其他零件；任意零件自动选面和自动识别实际安装方式尚未验证。

## 环境与快速开始

真实 COM 自动化需要 Windows、Python 3.13+、Git，以及已合法安装的 SOLIDWORKS。**本仓库的新增能力实测于 SW2020 SP5；上游徽章中的其他年份不代表本仓库已逐一验证。** Linux/WSL 可用于文档、测试和 Mock 模式，不能直接执行 Windows COM 自动化。

```powershell
git clone https://github.com/caoguanqiu1-alt/CAD-CAE-Agent.git
cd CAD-CAE-Agent
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e .
$env:SW2020_INSTALL_DIR = 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS'
powershell -NoProfile -File .\simulation\build.ps1 -InstallDir $env:SW2020_INSTALL_DIR
```

将安装目录改为自己的实际路径。真实执行使用 `src/utils/start_sw2020_stable.py --real --year 2020`；MCP 初始化与工具列表不应启动 SOLIDWORKS，首次实际工具调用才连接 COM。Simulation 还需要本机可用的 SOLIDWORKS Simulation 与对应 Interop DLL。完整 MCP 配置和调用步骤见 [中文安装与演示说明](README_CAE.md)；上游通用客户端配置、开发命令及功能开关见 [英文原文](README.en.md)。

项目持续开发，接口、文档和安装步骤可能调整。SOLIDWORKS、Simulation 及其 Interop DLL 不随仓库分发。

## 文档与许可

- [上游文档站](https://andrewbartels1.github.io/SolidworksMCP-python/) · [本仓库上游英文说明](README.en.md) · [上游西班牙文说明](README.es-ES.md)
- [工具目录](docs/user-guide/tool-catalog) · [架构](docs/user-guide/architecture.md) · [Agent 与提示词测试](docs/agents/agents-and-testing.md)
- MIT License，见 [LICENSE](LICENSE)。
