# CAE 图片来源记录

本图集回溯本项目开发时的同一段本机聊天与输出文件，生成于 2026-09-28 至 2026-09-29，归档于 2026-09-30。来源为真实 SOLIDWORKS 2020 SP5 的窗口截图或 API 导出视口；本次只复制图片和完善文档，没有重新建模或求解。

全部 7 张不同的 PNG 图片均嵌入[中文 README](../../README.md#cae-仿真过程与结果图集)。`Pin_NoPen_1000N` 是存在自由运动的排错研究，不能作为有效工程结果；其他求解结果也受 README 和[验证记录](verification.md)中的工况假设与收敛限制约束。

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

`F001-highlight.png` 与 `geometry-preview.png` 的 SHA-256 完全相同，故仅展示一次；该预览不证明界面中的面高亮颜色。原生 BMP 视口输出与同阶段 PNG / 窗口截图呈现相同模型结果，不重复作为独立算例。用户提供的视频示例照片不属于本项目求解产物，未纳入图集。

## 原图完整性

归档图片与对应本机原文件逐字节一致，未裁剪、重绘或调整云图颜色和数值。以下 SHA-256 可用于核对下载文件。

| 图片 | SHA-256 |
| --- | --- |
| `geometry-preview.png` | `0ec288f1d5ae8a9265b8c7ca88cbd1ec72470379b75940fac10b501e5222ce6c` |
| `single-load-1000n-solidworks.png` | `72e834538cf2a6f899286021ce0d525fad33f0b7a213deed05471b1a6398a632` |
| `single-load-1000n-viewport.png` | `39e0733ac27dcdbb7d6bc43d7efa4d073c9ad585f78bca463931b8767f222f60` |
| `multiload-plan-solidworks.png` | `444dc83846bc6defaf8c429291337a61d0faf9eb8f2b20a1dc3aaacf006a3e2e` |
| `pin-contact-diagnostic-solidworks.png` | `9f5203347e72cf376f72e6e7010e9aa49551a9bd0ab6a7988bbb1d2f8a6ac27f` |
| `pin-guided-ures.png` | `bb72f7c0a759cbe29717b7e38d0908be0a2bba0cfedfb35abc9a22c9e6440367` |
| `pin-plan-solidworks.png` | `92177de041e4c82952e3773bfd6aab687d4ea96779915ee0344ba81a5faa514f` |
