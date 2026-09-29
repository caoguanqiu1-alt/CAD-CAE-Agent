# SolidWorks CAE Agent 原型

## 已实现和实跑的范围

AI 客户端负责理解任务、选择工况与工具调用；MCP 暴露执行能力；Windows 上的真实
SOLIDWORKS 2020 / Simulation 完成建模和有限元求解。单独启动 MCP 不会获得一个独立自主 Agent。

| 能力 | 当前验证范围 |
| --- | --- |
| 参数化建模 | SW2020 草图、拉伸/切除计划及实体几何检查 |
| 仿真几何 | 实体面、边、顶点及持久引用解析 |
| 静力分析 | 材料、固定约束、全局 XYZ 力向量、多个受力面 |
| 销轴接触 | 示例连杆及两根独立销轴；圆柱面无穿透接触 |
| 网格检查 | 3–6 档递减网格；位移与峰值应力分别比较 |
| 后处理 | URES(mm) 云图、反力、原生 CWR 归档、零件保存 |
| 失败处理 | 串行 COM、文档身份/未保存修改检查；不自动重放未知写入 |

销轴生成器限于已演示的 Y 轴孔几何；轴向限位与 Z 向导向来自工程假设。
任意零件的自动选面、自动识别真实安装方式、非线性材料和疲劳分析尚未验证。

## 安装

验证环境：Windows x64、Python 3.13.15、SOLIDWORKS 2020 SP5、可用的 Simulation 静力求解环境。
需要从自己的 SOLIDWORKS 安装目录读取 `sldworks`、`swconst`、`cosworks` 三个 Interop DLL。

```powershell
git clone https://github.com/caoguanqiu1-alt/solidworks-cae-agent.git
cd solidworks-cae-agent
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e .
$env:SW2020_INSTALL_DIR = 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS'
powershell -NoProfile -File .\simulation\build.ps1 -InstallDir $env:SW2020_INSTALL_DIR
```

将安装路径改为本机实际值。用相同环境变量启动 MCP；不要混用其他年份的 Interop DLL。
手动打开 SOLIDWORKS 和一个**另存的、干净的零件副本**后，再调用仿真工具。

## MCP 配置示例

把 `C:/path/to/solidworks-cae-agent` 替换为克隆目录：

```json
{
  "mcpServers": {
    "solidworks": {
      "command": "C:/path/to/solidworks-cae-agent/.venv/Scripts/python.exe",
      "args": ["C:/path/to/solidworks-cae-agent/src/utils/start_sw2020_stable.py", "--real", "--year", "2020"],
      "cwd": "C:/path/to/solidworks-cae-agent",
      "env": {"SW2020_INSTALL_DIR": "C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS", "PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

不同客户端配置格式可能不同；例如 Codex 使用 TOML。仓库 `.mcp.json` 通过 `deployment/run-sw2020-mcp.ps1` 启动相同的 SW2020 入口，应从项目目录加载它。已有连接须在客户端刷新后才能看到新增工具。
一次计划会运行多个求解过程，应按模型规模提高客户端工具超时；超时不代表写入或求解未发生，先检查状态再重试。
MCP 初始化和 `tools/list` 不应启动或连接 SOLIDWORKS COM。

## 最小调用流程

1. `sw_simulation_check` 检查实际版本、活动文档及 Simulation API。
2. `sw_simulation_inspect_geometry` 获取当前副本的面持久引用。
3. 结合安装方式定义材料、载荷与约束，按 [计划格式](SIMULATION_PHASE3.md) 组装输入。
4. `sw_simulation_run_plan` 运行多网格计划并保存结果；也可使用 `sw_simulation_general_step` 分步调试。
5. 分别检查位移变化、峰值应力变化、反力平衡和异常自由运动；不能只看求解器返回成功。

示例面 ID 不能直接套用到其他零件。原生 CAD/CWR 和机器路径留在本地；公开仓库提供截图与脱敏数值，不分发商业求解器组件。

## 验证

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.test_simulation_plan_contract tests.test_sw2020_plan_contract -v
# 只读回查已有算例；study 参数必须与本机文档中的研究名一致
& .\.venv\Scripts\python.exe tests/simulation_reconnect_live.py --document C:/examples/CAE_Agent_PinPlan.SLDPRT --study AgentPin_Guided --expected-ures 0.01121470332145691 --output C:/examples/reconnect.json
```

第二条命令仅适用于具有该结果的原生算例，可能切换活动研究页，不创建几何或重新求解。
离线测试不证明有限元物理正确性；详见 [验证范围](docs/cae/verification.md)。

## 归属与参赛状态

保留上游 MIT 许可和作者归属；本项目的新增贡献是 SW2020 有守卫的建模执行与 Simulation 扩展。
截至 2026-09-29，已在 Windows 本地完成 MCP/COM 验证，尚未部署到 DGX Spark，亦未声明获得赛事资格或完成参赛提交。
