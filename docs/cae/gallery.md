# CAE 图片来源记录

本图集回溯本项目开发时的同一段本机聊天与输出文件，原图生成于 2026-09-28 至 2026-09-29，归档于 2026-09-30；2026-09-30 另补充一张真实网格显示截图。来源为真实 SOLIDWORKS 2020 SP5 的窗口截图或 API 导出视口，没有重新建模或求解。

共归档 8 张 PNG 图片。[中文 README](../../README.md#cae-仿真过程与结果图集)展示其中 6 张：同次单载荷的无色标导出图及近似的 3 mm 平滑接触云图改为原图链接，接触结果旁增加带网格边线的截图。`Pin_NoPen_1000N` 是存在自由运动的排错研究，不能作为有效工程结果；其他求解结果也受 README 和[验证记录](verification.md)中的工况假设与收敛限制约束。

## 文件对应关系

| 仓库图片 | 本机输出原文件名 | 内容 |
| --- | --- | --- |
| [geometry-preview.png](assets/geometry-preview.png) | `geometry-preview.png` | 求解前几何预览；无有限元结果 |
| [single-load-1000n-solidworks.png](assets/single-load-1000n-solidworks.png) | `合位移云图_SOLIDWORKS截图.png` | `Tension_1000N`，3 mm 网格，URES 0.007041338 mm |
| [single-load-1000n-viewport.png](assets/single-load-1000n-viewport.png) | `合位移云图_1000N.png` | 同次拉伸求解的视口导出；未显示色标 |
| [multiload-plan-solidworks.png](assets/multiload-plan-solidworks.png) | `CAE_Agent_Planned_双载荷截图.png` | `AgentPlan_2load`，3 mm 网格，URES 0.139222473 mm |
| [pin-contact-diagnostic-solidworks.png](assets/pin-contact-diagnostic-solidworks.png) | `PinContact_SOLIDWORKS截图.png` | `Pin_NoPen_1000N`，4 mm 网格；异常工况 |
| [pin-guided-ures.png](assets/pin-guided-ures.png) | `PinGuided_2mm_SOLIDWORKS截图.png` | `Pin_Guided_1000N`，2 mm 网格，URES 0.011234013 mm |
| [pin-plan-solidworks.png](assets/pin-plan-solidworks.png) | `CAE_Agent_PinPlan_接触截图.png` | `AgentPin_Guided`，3 mm 网格，URES 0.011214703 mm |
| [pin-plan-mesh-solidworks.png](assets/pin-plan-mesh-solidworks.png) | `pin-plan-mesh-solidworks-focused.png` | 同一 3 mm 原生结果；开启单元边线并放大视图，2026-09-30 新截 |

`F001-highlight.png` 与 `geometry-preview.png` 的 SHA-256 完全相同，故仅展示一次；该预览不证明界面中的面高亮颜色。原生 BMP 视口输出与同阶段 PNG / 窗口截图呈现相同模型结果，不重复作为独立算例。用户提供的视频示例照片不属于本项目求解产物，未纳入图集。

## 原图完整性

归档图片与对应本机原文件逐字节一致，未裁剪、重绘或调整云图颜色和数值。以下 SHA-256 可用于核对下载文件。

网格显示图在 `CAE_Agent_PinPlan.SLDPRT` 及其 `.CWR` 的临时副本上，通过真实 API 的 [SetPlotSettings](https://help.solidworks.com/2020/English/api/swsimulationapi/SolidWorks.Interop.cosworks~SolidWorks.Interop.cosworks.ICWResults~SetPlotSettings.html) 将边界显示设为本机枚举 `swsPlotBoundaryMesh=2`，并回读核实。原生窗口捕获保留 URES(mm) 色标；表面的三角边线用于展示体网格，不能据此判断网格质量或收敛。节点 51,985、单元 33,407、URES 0.01121470332145691 mm 均与归档的 3 mm 结果一致，原零件和原 `.CWR` 哈希不变；详见[脱敏核验记录](mesh-display-verification.json)。

| 图片 | SHA-256 |
| --- | --- |
| `geometry-preview.png` | `0ec288f1d5ae8a9265b8c7ca88cbd1ec72470379b75940fac10b501e5222ce6c` |
| `single-load-1000n-solidworks.png` | `72e834538cf2a6f899286021ce0d525fad33f0b7a213deed05471b1a6398a632` |
| `single-load-1000n-viewport.png` | `39e0733ac27dcdbb7d6bc43d7efa4d073c9ad585f78bca463931b8767f222f60` |
| `multiload-plan-solidworks.png` | `444dc83846bc6defaf8c429291337a61d0faf9eb8f2b20a1dc3aaacf006a3e2e` |
| `pin-contact-diagnostic-solidworks.png` | `9f5203347e72cf376f72e6e7010e9aa49551a9bd0ab6a7988bbb1d2f8a6ac27f` |
| `pin-guided-ures.png` | `bb72f7c0a759cbe29717b7e38d0908be0a2bba0cfedfb35abc9a22c9e6440367` |
| `pin-plan-solidworks.png` | `92177de041e4c82952e3773bfd6aab687d4ea96779915ee0344ba81a5faa514f` |
| `pin-plan-mesh-solidworks.png` | `5c3218d8b654c2b5da0108fbb0c6e9d189b6562bf49c6a50f0e1c64f9053de40` |
