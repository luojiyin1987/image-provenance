// Watermark disruption pipeline (Canvas port of disrupt_watermark.py).
//
// Four stages in the pixel domain:
//   1. Micro crop + resize (breaks geometry-aligned watermarks)
//   2. Gaussian noise in RGB (raises the noise floor the watermark fights)
//   3. Unsharp mask (restores apparent sharpness)
//   4. JPEG quality randomization — done by the caller via canvas.toBlob(0.88-0.95)
//
// Intensity 1–5 maps to progressively stronger disruption; defaults to 3.

const DEFAULT_INTENSITY = 3;

// Box-Muller transform: two uniform → two N(0,1) samples.
function gauss() {
    let u = Math.random(), v = Math.random();
    while (u <= 0) u = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Stage 1: crop a few pixels off each edge, then resample back to original size
// using the browser's native high-quality resampler (Lanczos-ish).
function cropAndRescale(srcCanvas, intensity) {
    const w = srcCanvas.width, h = srcCanvas.height;
    const pct = 0.003 * intensity;
    const left = Math.floor(w * pct);
    const top = Math.floor(h * pct);
    const right = w - Math.floor(w * pct * 0.7);
    const bottom = h - Math.floor(h * pct * 0.7);
    const cw = right - left, ch = bottom - top;
    const out = document.createElement('canvas');
    out.width = w; out.height = h;
    const ctx = out.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(srcCanvas, left, top, cw, ch, 0, 0, w, h);
    return { canvas: out, cropPct: pct };
}

// Stage 2: additive Gaussian noise, per-channel, clipped to 0-255.
function addGaussianNoise(canvas, intensity) {
    const ctx = canvas.getContext('2d');
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = img.data;
    const sigma = intensity * 2 / 1.6;   // matches Python ±noise_level range roughly
    for (let i = 0; i < data.length; i += 4) {
        data[i]   = Math.min(255, Math.max(0, data[i]   + Math.round(gauss() * sigma)));
        data[i+1] = Math.min(255, Math.max(0, data[i+1] + Math.round(gauss() * sigma)));
        data[i+2] = Math.min(255, Math.max(0, data[i+2] + Math.round(gauss() * sigma)));
        // alpha untouched
    }
    ctx.putImageData(img, 0, 0);
    return sigma;
}

// Stage 3: Unsharp mask. radius=1, amount ~0.5 (Python's percent=50).
// Blur via a separable 3x3 box filter (cheap, close enough for a 1-pixel radius).
function unsharpMask(canvas, amount = 0.5) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const img = ctx.getImageData(0, 0, w, h);
    const src = img.data;
    const blurred = new Uint8ClampedArray(src.length);

    // Horizontal blur
    const tmp = new Uint8ClampedArray(src.length);
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const i = (y * w + x) * 4;
            for (let c = 0; c < 3; c++) {
                const xm1 = x > 0 ? src[i - 4 + c] : src[i + c];
                const xp1 = x < w - 1 ? src[i + 4 + c] : src[i + c];
                tmp[i + c] = (xm1 + src[i + c] + xp1) / 3;
            }
            tmp[i + 3] = src[i + 3];
        }
    }
    // Vertical blur
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const i = (y * w + x) * 4;
            for (let c = 0; c < 3; c++) {
                const ym1 = y > 0 ? tmp[i - w * 4 + c] : tmp[i + c];
                const yp1 = y < h - 1 ? tmp[i + w * 4 + c] : tmp[i + c];
                blurred[i + c] = (ym1 + tmp[i + c] + yp1) / 3;
            }
            blurred[i + 3] = tmp[i + 3];
        }
    }
    // Out = src + amount * (src - blurred)
    for (let i = 0; i < src.length; i += 4) {
        for (let c = 0; c < 3; c++) {
            const v = src[i + c] + amount * (src[i + c] - blurred[i + c]);
            src[i + c] = v < 0 ? 0 : v > 255 ? 255 : v;
        }
    }
    ctx.putImageData(img, 0, 0);
}

// Public entry: applies stages 1-3 to `canvas` in place and returns a report.
// The caller is expected to handle stage 4 (JPEG re-encode with random q 88-95).
export async function disruptWatermark(canvas, options = {}) {
    const intensity = Math.max(1, Math.min(5, options.intensity ?? DEFAULT_INTENSITY));
    const log = [];

    const t0 = performance.now();
    const { canvas: scaled, cropPct } = cropAndRescale(canvas, intensity);
    // Copy back into the passed canvas (so caller sees mutation).
    canvas.getContext('2d').drawImage(scaled, 0, 0);
    const t1 = performance.now();
    log.push(`几何扰动: crop ${(cropPct * 100).toFixed(2)}% (${(t1-t0).toFixed(0)}ms)`);

    const sigma = addGaussianNoise(canvas, intensity);
    const t2 = performance.now();
    log.push(`高斯噪声: σ≈${sigma.toFixed(1)} (${(t2-t1).toFixed(0)}ms)`);

    if (intensity >= 3) {
        unsharpMask(canvas, 0.5);
        const t3 = performance.now();
        log.push(`锐化补偿 (${(t3-t2).toFixed(0)}ms)`);
    }

    // Let the caller decide JPEG quality. Recommend a random 88-95.
    const quality = 0.88 + Math.random() * 0.07;
    return { intensity, cropPct, sigma, jpegQuality: quality, log };
}
