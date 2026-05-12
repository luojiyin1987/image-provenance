# Image Provenance

[![Pages](https://img.shields.io/badge/demo-online-2ea44f)](https://863401402.github.io/image-provenance/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Client-side](https://img.shields.io/badge/100%25-client--side-0071e3)](#)
[![Build](https://img.shields.io/badge/build-zero-lightgrey)](#)

> AI 图片溯源分析工具。**100% 在浏览器里跑,图片从不离开你的设备。**

👉 [**打开在线演示**](https://863401402.github.io/image-provenance/)

---

把一张图丢进来,告诉你它是 AI 生成的还是真实相机拍的,以及能找到多少来源线索。没有后端、没有上传、没有服务器日志 —— 所有分析发生在你的浏览器里。

## 能做什么

### 🔍 多层溯源检测

- **C2PA / Content Credentials** —— 识别 JUMBF 容器,读出 `DigitalSourceType` 字段(`trainedAlgorithmicMedia` 即明确声明 AI)
- **结构化元数据** —— 通过 `exifr` 解析 EXIF / XMP / IPTC / ICC 各字段,查找 AI 工具签名
- **厂商指纹** —— OpenAI / DALL·E、Google SynthID / Gemini、Midjourney、Stable Diffusion / ComfyUI / Flux、Adobe Firefly
- **修图软件** —— Photoshop / Lightroom 单独归类,不算 AI
- **像素级水印启发** —— LSB 偏差、高频比、邻接相关性粗筛

每条检测结果带 **强 / 中 / 弱 / 提示** 四档置信度,点击可展开字节级证据。

### 📊 频域分析

在 Web Worker 里提取 **65 个频域特征**:

| 类别 | 特征 |
|---|---|
| 频谱能量 | DC、低/中/高频比、谱斜率、平坦度、谱熵 |
| 子带细分 | 7 个径向频带的能量分布 |
| 径向 / 方向 | 径向对称性、主方向、各向异性强度 |
| 相位 | 三通道相位一致性 *(SynthID 类水印的经典指征)* |
| 位平面 | LSB 偏置、邻接 LSB 相关性、直方图卡方 |
| 像素统计 | 三通道均值/标准差/偏度/峰度、通道间相关 |
| 空间相关 | 水平/垂直/对角相邻相关、2-bit/4-bit 相关断裂 |
| 小波 | Haar 2 级分解,LL/LH/HL/HH 能量与比例 |
| DCT | 8×8 块系数均值、标准差、零比例、块间方差 |

UI 展示:viridis 热图 FFT 谱、对数径向曲线、12 条启发式规则的加权判定与证据链。

### 🔄 去标记 + 伪装相机

- 字节级剥离 C2PA(JPEG APP11 段、PNG `caBX` / `C2PA` chunks)
- Canvas 重编码擦除所有残余元数据
- 5 款相机 profile(iPhone 15 Pro Max、Canon R5、Sony A7 IV、Galaxy S24+、小米 15 Pro)注入伪 EXIF
- 可选水印扰动:几何微变换 → 高斯噪声 → 锐化 → 随机质量重编码,强度 1–5 可调
- **🔍 一键重新分析**:看看刚处理完的图还能不能被检测出来

## 技术栈

**零构建,单 HTML + ES Modules。** 依赖全部通过 CDN 按需动态 import:

- [`exifr@7.1.3`](https://github.com/MikeKovarik/exifr) — 元数据解析(打开图片时加载)
- [`piexifjs@1.0.6`](https://github.com/hMatoba/piexifjs) — EXIF 注入(点击"转换"时加载)

其余全部手写,零运行时依赖:FFT / DCT / DWT、JUMBF sniffer、C2PA 字节剥离、水印扰动、特征提取、启发式打分。

## 本地运行

```bash
git clone https://github.com/863401402/image-provenance
cd image-provenance
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

ES Modules + Web Worker 需要 HTTP 协议,`file://` 打不开。

## 准确性说明(请阅读)

**这不是深度学习分类器**。基于 2024-2026 年公开研究([Corvi et al. 2023](https://arxiv.org/abs/2304.06408)、Smudged Fingerprints 2026),**仅靠频域特征对现代扩散模型(SD、SDXL、Flux、DALL-E 3、Gemini)的二分类准确率约 70-85%**。真正的 SOTA(NPR、FIRE、UnivFD 等 CNN 方法)需要训练数据和模型部署,不在本项目范围。

本工具的实际价值在三个层次:

1. **强信号几乎不会错** —— C2PA `trainedAlgorithmicMedia` 声明、EXIF `Software=Midjourney` 这类直接证据
2. **中等信号供参考** —— 厂商关键字、过度平滑、方向性异常,组合起来才有说服力
3. **特征可视化** —— 让你自己看 FFT 图和径向曲线,辅助判断,而不是盲信一个数字

不要把结果当作权威判定。

## 伦理说明

**水印扰动**功能设计用于:

- 学术鲁棒性评估(测试 SynthID、dwtDct 等水印在普通后处理下的残余率)
- 隐私保护(移除可能泄露处理轨迹的元数据)
- 个人创作再编辑

**不鼓励**用于虚假新闻、身份伪造、欺诈。立场参考 [WAVES (NeurIPS 2024)](https://arxiv.org/abs/2401.08573) 的学术共识:研究水印破坏是完善水印系统的必要环节。

## 浏览器兼容性

- Chrome / Edge 90+ ✅
- Firefox 90+ ✅
- Safari 15+ ✅
- 移动端浏览器 ✅(会自动降采样到 768×768 以控制耗时)

需要:ES Modules、Web Workers、`createImageBitmap`、`OffscreenCanvas` 可选。

## 项目结构

```
index.html                主页面 + 样式
src/
├── main.js               入口:上传 / 分发 / 渲染
├── utils.js              SHA-256、格式化、DOM 辅助
├── detect.js             检测聚合器,输出带置信度的检测卡片
├── metadata.js           exifr + JUMBF sniffer
├── markers.js            7 类厂商签名规则表
├── watermark-detect.js   字节级水印启发式
├── convert.js            C2PA 剥离 + Canvas 重编码 + EXIF 注入
├── watermark.js          Canvas 水印扰动流水线
├── cameras.js            5 款相机 profile
└── frequency/
    ├── transforms.js     FFT / DCT / DWT
    ├── features.js       65 特征提取
    ├── score.js          启发式打分
    ├── worker.js         Web Worker 入口
    ├── index.js          主线程调度器
    └── panel.js          频域 UI 渲染
```

~2000 行 JS,无运行时依赖,无构建步骤。

## 许可

[MIT](LICENSE)
