// Entry point — wires upload UI, runs detections, renders results.

import { sha256, formatSize, getImageDims, escHtml } from './utils.js';
import { runAllDetections } from './detect.js';
import { CAMERA_PROFILES } from './cameras.js';
import { convertImage } from './convert.js';
import { disruptWatermark } from './watermark.js';
import { analyzeFrequency } from './frequency/index.js';
import { renderFrequencyPanel } from './frequency/panel.js';

let selectedProfile = 'iphone15pro';
let currentFile = null;
let currentBytes = null;
let lastFreqBytes = null, lastFreqResult = null;

// --- Camera grid ---
const grid = document.getElementById('cameraGrid');
Object.entries(CAMERA_PROFILES).forEach(([key, cam]) => {
    const div = document.createElement('div');
    div.className = 'camera-option' + (key === selectedProfile ? ' selected' : '');
    div.dataset.key = key;
    div.innerHTML = `<div class="icon">${cam.icon}</div><div class="name">${escHtml(cam.displayName)}</div><div class="model">${escHtml(cam.Make)}</div>`;
    div.onclick = () => {
        document.querySelectorAll('.camera-option').forEach(e => e.classList.remove('selected'));
        div.classList.add('selected');
        selectedProfile = key;
    };
    grid.appendChild(div);
});

// --- Upload handling ---
const uploadArea = document.getElementById('uploadArea');
const uploadInner = uploadArea.querySelector('.upload-inner');
const uploadOriginalHTML = uploadInner.innerHTML;
const fileInput = document.getElementById('fileInput');
uploadArea.addEventListener('click', (e) => {
    if (e.target.closest('input, button, a')) return;
    fileInput.click();
});
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', e => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

// Live intensity label
const wmRange = document.getElementById('wmIntensity');
const wmLabel = document.getElementById('wmIntensityVal');
if (wmRange && wmLabel) wmRange.addEventListener('input', () => { wmLabel.textContent = wmRange.value; });

async function handleFile(file) {
    currentFile = file;
    document.getElementById('results').classList.add('hidden');
    // Reset freq tab / cache so the new file doesn't show previous results.
    lastFreqBytes = null; lastFreqResult = null;
    const freqPanel = document.getElementById('freqPanel');
    if (freqPanel) freqPanel.innerHTML = `
        <button class="btn-primary" id="btnRunFreq">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            运行频域分析
        </button>
        <p class="panel-hint">
            提取 65 个频域特征:FFT 幅度谱、径向功率谱、相位一致性、LSB 偏置、小波子带能量……<br>
            在 Web Worker 中执行,不阻塞页面。耗时约 1-3 秒。
        </p>`;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === 'detect'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== 'detect'));
    uploadInner.innerHTML = '<div class="loading"><div class="spinner"></div>正在分析...</div>';

    try {
        const buffer = await file.arrayBuffer();
        const uint8 = new Uint8Array(buffer);
        currentBytes = uint8;
        const hashHex = await sha256(buffer);

        const fileType = file.type === 'image/png' ? 'PNG'
            : file.type === 'image/jpeg' ? 'JPEG'
            : file.type === 'image/webp' ? 'WebP' : (file.type || '未知');

        const { detections } = await runAllDetections(uint8);
        const dims = await getImageDims(file);

        document.getElementById('fileType').textContent = fileType;
        document.getElementById('fileSize').textContent = formatSize(file.size);
        document.getElementById('fileHash').textContent = hashHex;
        document.getElementById('previewImg').src = URL.createObjectURL(file);
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileDims').textContent = dims;

        const aiHits = detections.filter(d => d.hit && d.category !== 'edit');
        const editHits = detections.filter(d => d.hit && d.category === 'edit');
        const anyHit = aiHits.length > 0;
        document.getElementById('headerTitle').textContent = anyHit ? '发现 AI 来源凭证线索' : '未发现明显 AI 来源凭证';
        document.getElementById('headerSubtitle').textContent = anyHit
            ? '这张图可能保留了可验证来源或生成工具相关标记。'
            : editHits.length
                ? '未检出 AI 生成标记,但图片经过修图软件处理。'
                : '当前文件字节中没有检出典型 AI 生成标记。';
        const hb = document.getElementById('headerBadge');
        hb.textContent = anyHit ? '命中' : '未命中';
        hb.className = 'pill ' + (anyHit ? 'badge-hit' : 'badge-clean');

        const container = document.getElementById('detectionItems');
        container.innerHTML = '';
        detections.forEach(d => {
            const div = document.createElement('div');
            div.className = 'detection-item';
            const detailHtml = d.detail
                ? `<details class="detection-item-details"><summary>查看详情</summary><pre class="detection-item-detail">${escHtml(d.detail)}</pre></details>`
                : '';
            const confHtml = d.confidence ? `<span class="conf conf-${d.confidence}">${
                d.confidence === 'strong' ? '强证据' :
                d.confidence === 'medium' ? '中等' :
                d.confidence === 'info' ? '提示' : '弱'
            }</span>` : '';
            div.innerHTML = `
                <div class="detection-item-header">
                    <span class="detection-item-title">${escHtml(d.title)}${confHtml}</span>
                    <span class="badge ${d.badgeClass}">${escHtml(d.badgeText)}</span>
                </div>
                <div class="detection-item-desc">${escHtml(d.desc)}</div>
                ${detailHtml}
            `;
            container.appendChild(div);
        });

        document.getElementById('convertResult').style.display = 'none';
        document.getElementById('btnConvert').disabled = false;

        uploadInner.innerHTML = uploadOriginalHTML;
        document.getElementById('results').classList.remove('hidden');
    } catch (err) {
        uploadInner.innerHTML = `<div class="upload-text" style="color:var(--danger)">分析出错: ${escHtml(err.message)}</div>`;
    }
}

// --- Convert: strip C2PA + inject camera EXIF (task #7) ---
document.getElementById('btnConvert').addEventListener('click', async () => {
    if (!currentFile || !currentBytes) return;
    const btn = document.getElementById('btnConvert');
    const resultDiv = document.getElementById('convertResult');
    resultDiv.style.display = 'block';
    resultDiv.className = 'convert-result';
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div><br>正在处理...</div>';
    btn.disabled = true;

    try {
        const profile = CAMERA_PROFILES[selectedProfile];
        const disrupt = document.getElementById('chkDisruptWatermark')?.checked;
        const intensity = parseInt(document.getElementById('wmIntensity')?.value || '3', 10);
        let wmReport = null;
        const { blob, log } = await convertImage(currentBytes, currentFile.type, profile, {
            quality: 0.88 + Math.random() * 0.07,
            disruptWatermark: disrupt ? async (canvas) => {
                wmReport = await disruptWatermark(canvas, { intensity });
            } : null,
        });
        if (wmReport) {
            for (const l of wmReport.log) log.push('  · ' + l);
        }

        const url = URL.createObjectURL(blob);
        const origName = currentFile.name.replace(/\.[^.]+$/, '') || 'photo';
        const outName = `${origName}_${profile.Make}_${Date.now().toString(36)}.jpg`;

        resultDiv.innerHTML = `
            <div style="color:var(--success);font-weight:600;margin-bottom:10px">✅ 转换完成</div>
            <img src="${url}" alt="转换结果">
            <div style="font-size:12px;color:var(--text-muted);margin:8px 0;line-height:1.8">
                ${log.map(l => `• ${escHtml(l)}`).join('<br>')}
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                <a class="download-btn" href="${url}" download="${escHtml(outName)}">下载 (${formatSize(blob.size)})</a>
                <button class="btn-secondary" id="btnReanalyze">重新分析</button>
            </div>
        `;
        document.getElementById('btnReanalyze').onclick = async () => {
            const reFile = new File([blob], outName, { type: 'image/jpeg' });
            handleFile(reFile);
        };
    } catch (err) {
        resultDiv.className = 'convert-result error';
        resultDiv.innerHTML = `<div style="color:var(--danger);font-weight:600">转换失败: ${escHtml(err.message)}</div>`;
    } finally {
        btn.disabled = false;
    }
});

// --- Tab switching (delegated) ---
document.addEventListener('click', (ev) => {
    const btn = ev.target.closest && ev.target.closest('.tab-btn');
    if (!btn) return;
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== target));
});

// --- Frequency analysis trigger (event-delegated to survive panel re-renders) ---
document.addEventListener('click', async (ev) => {
    const btn = ev.target.closest && ev.target.closest('#btnRunFreq');
    if (!btn) return;
    if (!currentFile || !currentBytes) return;
    const panel = document.getElementById('freqPanel');
    if (lastFreqBytes === currentBytes && lastFreqResult) {
        renderFrequencyPanel(panel, lastFreqResult);
        return;
    }
    btn.disabled = true;
    panel.innerHTML = `
        <div class="loading"><div class="spinner"></div><br>
        <span id="freqStage">初始化...</span></div>`;
    try {
        const result = await analyzeFrequency(currentBytes, currentFile.type || 'image/jpeg', {
            onProgress: ({ stage, pct, info }) => {
                const el = document.getElementById('freqStage');
                if (el) el.textContent = `[${pct}%] ${stage}${info ? ' · ' + info : ''}`;
            },
        });
        lastFreqBytes = currentBytes;
        lastFreqResult = result;
        renderFrequencyPanel(panel, result);
    } catch (err) {
        panel.innerHTML = `<div style="color:var(--danger);font-weight:600;padding:16px">频域分析失败: ${escHtml(err.message)}</div>`;
    }
});

// --- Theme toggle (light/dark) ---
const themeToggle = document.getElementById('themeToggle');
if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        const current = document.documentElement.dataset.theme;
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        localStorage.setItem('theme', next);
        const meta = document.querySelector('meta[name="theme-color"]:not([media])');
        if (meta) meta.setAttribute('content', next === 'dark' ? '#0a0a0b' : '#ffffff');
    });
}
