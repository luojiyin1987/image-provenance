# AI Image Detector

AI 图片溯源检测工具。上传一张图片,分析它是否由 AI 生成,以及可能的生成模型。

## 功能

- **元数据分析**:读取 EXIF / XMP / ICC / C2PA 等字段,识别 AI 生成器签名
- **频域特征**:FFT、DCT 分析,检测 AI 生成模型常见的频率指纹
- **水印检测与干扰**:支持 SynthID 等不可见水印的检测与扰动(`disrupt_watermark.py`)
- **Web UI**:拖拽上传,一键出报告

## 运行

```bash
python3 server.py
```

默认监听 `http://localhost:8810`,用浏览器打开即可使用。

## 水印干扰工具

```bash
python3 disrupt_watermark.py input.jpg output.jpg [intensity]
```

`intensity` 取值 1-5,默认 3。对像素级不可见水印做频域扰动,视觉影响最小化。

## 文件结构

- `server.py` — HTTP 服务端 + 检测逻辑
- `index.html` — 前端单页界面
- `disrupt_watermark.py` — 水印干扰独立脚本
- `docs/frequency_features.md` — 频域特征说明

## 依赖

- Python 3.8+
- NumPy、Pillow
- 可选:`exiftool`(用于更完整的元数据提取)

## 许可

MIT
