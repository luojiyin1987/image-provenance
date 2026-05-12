# Image Provenance

AI 图片溯源分析工具。**100% 在浏览器里运行,图片从不离开你的设备。**

在线使用:**https://863401402.github.io/image-provenance/**

## 功能

**🔍 多层检测**
- **C2PA / Content Credentials** —— 识别 JUMBF 容器,读出 `DigitalSourceType`(`trainedAlgorithmicMedia` 等)
- **结构化元数据** —— 通过 `exifr` 解析 EXIF / XMP / IPTC / ICC,查找 AI 工具签名
- **厂商关键字** —— OpenAI、Google SynthID、Midjourney、Stable Diffusion、ComfyUI、Flux、Adobe Firefly
- **修图软件识别** —— Photoshop / Lightroom,独立分类(不算 AI)
- **字节级水印启发** —— LSB 偏差、高频比、邻接相关性,粗筛像素级隐形水印

**📊 频域分析**
在 Web Worker 中提取 65 个特征:
- FFT 幅度谱、径向功率谱、方向性能量
- 每通道相位一致性(SynthID 类水印的经典指征)
- LSB 偏置 + 字节直方图卡方检验
- Haar 小波 2 级分解的子带能量比
- 8×8 DCT 系数统计

UI 展示:viridis 热图 FFT + 对数径向曲线 + 12 条启发式规则的加权判定。

**🔄 图片转换**
- 字节级剥离 C2PA(JPEG APP11 / PNG C2PA chunks)
- Canvas 重编码擦除所有残余元数据
- 5 款相机 profile 注入伪 EXIF(iPhone 15 Pro Max、Canon R5、Sony A7 IV、Galaxy S24+、小米 15 Pro)
- 可选水印扰动:几何微变换 + 高斯噪声 + 锐化 + 随机质量重编码,强度 1-5

## 技术栈

零构建,单 HTML + ES Modules。依赖通过 CDN 按需动态 import:

- `exifr@7.1.3` — 元数据解析(仅在需要时加载)
- `piexifjs@1.0.6` — EXIF 注入(仅在转换时加载)

其余全部手写:FFT / DCT / DWT、JUMBF sniffer、C2PA 剥离、水印扰动、特征提取、打分。

## 本地运行

任何静态 HTTP server 即可:

```bash
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

> ES Modules + Web Worker 需要 HTTP 协议,`file://` 无法加载。

## 判定准确性说明

**这不是深度学习分类器**。基于 2024-2026 年的公开研究(Corvi 2023, Smudged Fingerprints 2026),**仅靠频域特征对现代扩散模型的二分类准确率约 70-85%**。本工具的价值在:

1. **强信号几乎不会错**:C2PA `trainedAlgorithmicMedia` 声明、EXIF `Software=Midjourney` 这类直接证据
2. **中等信号供参考**:厂商关键字、过度平滑、方向性异常,组合在一起才有说服力
3. **特征可视化**:让用户自己看 FFT 图、径向曲线,辅助判断,而不是盲信一个数字

真正的 SOTA(NPR、FIRE 等 CNN 方法)需要训练数据和模型部署,不在本项目范围。

## 伦理说明

水印扰动功能用于:
- **学术鲁棒性评估** —— 测试 SynthID、dwtDct 等水印在普通后处理下的残余率
- **隐私保护** —— 移除可能泄露处理轨迹的元数据
- **个人创作** —— 自己图片的再编辑

**不鼓励**用于虚假新闻传播、身份伪造、欺诈等场景。基于 WAVES (NeurIPS 2024) 等工作的学术共识:"研究水印破坏是完善水印系统的必要环节"。

## 许可

MIT
