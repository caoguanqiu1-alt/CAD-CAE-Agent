# 工程图建模展示与证据

这四个案例由用户按“提供过工程图，且已有建模成果”的标准确认选入。皮带轮、壳体和泵体来自“SW CODEX”聊天；093-1 阀体为该聊天回顾过的首次阀体建模案例，源图和结果在此前的建模会话中核对。

本页整理历史原生文件、建模记录和实际预览，未重新执行建模，也未补做当时尚未完成的几何。已有建模成果不等于图纸所有要求已逐项验收；完成范围与差异在每个案例中列明。

## 难度排序依据

| 顺序 | 案例 | 主要复杂度 |
| --- | --- | --- |
| 1 | 皮带轮 | 主体轴对称，尺寸关系集中；主要组合拉伸、切除与圆角。 |
| 2 | 093-1 阀体 | 包含放样过渡与不同方向的接口，需结合多个剖面安排孔道。 |
| 3 | ZZJS-2015 壳体 | 需同时处理均匀壁厚、内壁连接和曲面上的窗口、标牌与文字。 |
| 4 | ZZBLJT-01 泵体 | 多视图与多个剖面共同定义内部流道，还要核对前后方向并生成关联工程图。 |

该顺序用于展示特征与读图能力的递进，不是标准化难度评分或耗时排名。

## 1. 皮带轮

<table>
<tr><th width="50%">用户提供的工程图</th><th width="50%">真实 SOLIDWORKS 建模结果</th></tr>
<tr><td align="center"><a href="assets/pulley-drawing.png"><img src="assets/pulley-drawing.png" width="100%" alt="皮带轮原工程图"></a></td><td align="center"><a href="assets/pulley-model.png"><img src="assets/pulley-model.png" width="100%" alt="皮带轮的 SW2020 建模预览"></a></td></tr>
</table>

- **已有成果：** SW2020 参考重建已保存，1 个实体；主要尺寸和体积已检查。
- **范围与差异：** 8° 内侧斜壁尚未建立；采用凸台特征，未复现参考中的三个旋转特征。
- **本机核对的原生文件：** `皮带轮_SW2020_参考重建.SLDPRT`（158,941 字节）。
- **核对依据：** `皮带轮_建模说明.md`。
- **原生文件 SHA-256：** `a2124224c7373bc8041b0add4432862735b3ffab5e9e08848856f9ccec8ee439`。

## 2. 093-1 阀体

<table>
<tr><th width="50%">用户提供的工程图</th><th width="50%">真实 SOLIDWORKS 建模结果</th></tr>
<tr><td align="center"><a href="assets/valve-drawing.png"><img src="assets/valve-drawing.png" width="100%" alt="093-1 阀体原工程图"></a></td><td align="center"><a href="assets/valve-model.png"><img src="assets/valve-model.png" width="100%" alt="093-1 阀体的 SW2020 建模预览"></a></td></tr>
</table>

- **已有成果：** 真实 COM/MCP 建模已保存，1 个实体，重建成功；包围尺寸 75 × 56 × 75 mm。
- **范围与差异：** 未标注外形按用户允许合理补形；接口未生成实体螺纹，部分铸造内腔与圆角有简化。
- **本机核对的原生文件：** `ValveBody_093-1.SLDPRT`（276,762 字节）。
- **核对依据：** `ValveBody_093-1_读图核对.md`。
- **原生文件 SHA-256：** `a0756ae8e121902ead58df2cb5cce69075d5a3cc71415a6750d552dab7b3fcda`。

预览保留了当时显示的蓝色参考面；这是历史建模输出。记录中的“61 项特征树”包含基准及文件夹等项目，不应解释为 61 个实体建模特征。

## 3. ZZJS-2015 壳体

<table>
<tr><th width="50%">用户提供的工程图</th><th width="50%">真实 SOLIDWORKS 建模结果</th></tr>
<tr><td align="center"><a href="assets/housing-drawing.png"><img src="assets/housing-drawing.png" width="100%" alt="ZZJS-2015 壳体原工程图"></a></td><td align="center"><a href="assets/housing-model.png"><img src="assets/housing-model.png" width="100%" alt="ZZJS-2015 壳体的 SW2020 建模预览"></a></td></tr>
</table>

- **已有成果：** 原生重建模型已保存，1 个实体，重建检查通过；包含 2 mm 壁厚与内部结构。
- **范围与差异：** 用户停止任务前已保存；最终保存重开验证未完成，现有预览来自建模过程。
- **本机核对的原生文件：** `壳体_ZZJS2015_重建.SLDPRT`（1,093,753 字节）。
- **核对依据：** `壳体_建模核验.json / 会话停止时的交付记录`。
- **原生文件 SHA-256：** `94289c884b57d969f73b9c7915b586f10a4c92f22dd8ecb32aeeef77d30599c4`。

展示图为保存前的外观核对预览，不是最终重开后的截图；模型和核验记录中可确认均匀壁厚、螺钉柱、加强筋、窗口及随形文字特征，但未完成最终保存重开验收。

## 4. ZZBLJT-01 泵体

<table>
<tr><th width="50%">用户提供的工程图</th><th width="50%">真实 SOLIDWORKS 建模结果</th></tr>
<tr><td align="center"><a href="assets/pump-drawing.png"><img src="assets/pump-drawing.png" width="100%" alt="ZZBLJT-01 泵体原工程图"></a></td><td align="center"><a href="assets/pump-model.png"><img src="assets/pump-model.png" width="100%" alt="ZZBLJT-01 泵体的 SW2020 建模预览"></a></td></tr>
</table>

- **已有成果：** 快速重建已保存，1 个连续实体，重建成功；另完成四视图参考工程图和 10 项关联尺寸核验。
- **范围与差异：** 部分铸造过渡、B–B 流道截面与 C–C 台阶有简化；工程图对应快速重建版。
- **本机核对的原生文件：** `泵体_ZZBLJT01_快速重建.SLDPRT`（370,285 字节）。
- **核对依据：** `泵体_重建说明.md / 泵体_最终快照.json / 泵体_工程图_交付说明.md`。
- **原生文件 SHA-256：** `16f2825ed465ad840568da6b44063add6c0af70cb1a0fcc67658f4f7949d8ee7`。

泵体工程图包含前视、后视、等轴测及 A–A 剖视；10 项关联尺寸的读取记录与目标值一致。螺纹为装饰螺纹，HT200 为材料要求文字；参考工程图仍需制造前复核。

## 图片来源与完整性

原工程图由用户提供，原有图号、机构名称和水印均保留；这些图片是建模参考，不能据此认定原图由本项目创作。三维预览来自本机真实 SW2020 输出。所有展示图片按原始字节复制，未重绘、裁剪或改变模型外观。两张已丢失的临时图（壳体、泵体）及阀体原图，从对应历史会话保留的图片数据恢复。

| 仓库图片 | 原文件名 | 大小（字节） | SHA-256 |
| --- | --- | ---: | --- |
| [`pulley-drawing.png`](assets/pulley-drawing.png) | `codex-clipboard-d33faaa3-91b2-49d3-889b-f49421a8a765.png` | 551575 | `480fe593dfe4696c7b0f08eea1285374453e2d69689c5bb16cdec1c32f5dbece` |
| [`pulley-model.png`](assets/pulley-model.png) | `皮带轮_SW2020_预览.png` | 172922 | `22c2509446af26d6229939069cb0b7ac5fd9883e7b0acac91c63fea0a4bc0657` |
| [`valve-drawing.png`](assets/valve-drawing.png) | `valve-drawing.png` | 177727 | `5496da9a42fec162b1d659fc2a008fb9a571d50d83e20f97b22eb29af2c68da9` |
| [`valve-model.png`](assets/valve-model.png) | `ValveBody_093-1.png` | 153495 | `78e2c969f4276b7dc6a5bb7135731acd5aafc0d13bc7aa28e9a74a11ad53a2e6` |
| [`housing-drawing.png`](assets/housing-drawing.png) | `codex-clipboard-ee36bef2-40ab-4715-919d-003253706b8f.png` | 2875331 | `ee57767ebbbdbf327a0e9a6990a9f155127f652962985c787bffda76ff446b25` |
| [`housing-model.png`](assets/housing-model.png) | `壳体_外观核对2.png` | 134913 | `0ecf70ca875dd1a7f292f9c636f84b1a432b1d35882551710d58830084ca1027` |
| [`pump-drawing.png`](assets/pump-drawing.png) | `codex-clipboard-783e63f7-d60e-4f85-b5d9-4f01ecc9d4ae.png` | 397337 | `53a763c198c04ceb06d835205c0f8c044a337a02cdaec85685a668a71fa04237` |
| [`pump-model.png`](assets/pump-model.png) | `泵体_三维.png` | 142538 | `96441f2c9d5cf9c08e5fbc99f5e7ddb09fd849f005970078470096c03ebaaf74` |

图片机器可读清单：[assets/manifest.json](assets/manifest.json)。
