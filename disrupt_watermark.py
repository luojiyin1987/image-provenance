#!/usr/bin/python3
"""Watermark disruption: break pixel-level invisible watermarks (SynthID etc.)
Usage: python3 disrupt_watermark.py input.jpg output.jpg [intensity]
  intensity: 1-5, default 3
"""
import sys, random, time
import numpy as np
from PIL import Image, ImageFilter

def disrupt_watermark(input_path, output_path, intensity=3):
    """Disrupt frequency-domain watermarks with minimal visual impact (NumPy accelerated)"""
    t0 = time.time()
    img = Image.open(input_path).convert('RGB')
    w, h = img.size
    
    # === Step 1: Slight geometric transform ===
    crop_pct = 0.003 * intensity  # 0.3% to 1.5%
    left = int(w * crop_pct)
    top = int(h * crop_pct)
    right = w - int(w * crop_pct * 0.7)
    bottom = h - int(h * crop_pct * 0.7)
    img = img.crop((left, top, right, bottom))
    img = img.resize((w, h), Image.LANCZOS)
    t1 = time.time()
    
    # === Step 2: Add subtle Gaussian noise (NumPy vectorized) ===
    noise_level = intensity * 2  # 2-10 pixel value range
    arr = np.array(img, dtype=np.int16)
    noise = np.random.randint(-noise_level, noise_level + 1, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    t2 = time.time()
    
    # === Step 3: Slight sharpen to recover from noise ===
    if intensity >= 3:
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=50, threshold=0))
    t3 = time.time()
    
    # === Step 4: Re-encode as JPEG with different quality ===
    quality = random.randint(88, 95)
    img.save(output_path, 'JPEG', quality=quality, optimize=True)
    t4 = time.time()
    
    result = {
        'crop_pct': f'{crop_pct*100:.2f}%',
        'noise_level': noise_level,
        'jpeg_quality': quality,
        'timing': {
            'crop_resize': f'{t1-t0:.2f}s',
            'noise': f'{t2-t1:.2f}s',
            'sharpen': f'{t3-t2:.2f}s',
            'encode': f'{t4-t3:.2f}s',
            'total': f'{t4-t0:.2f}s'
        }
    }
    return result

if __name__ == '__main__':
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    intensity = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    result = disrupt_watermark(input_path, output_path, intensity)
    import json
    print(json.dumps(result))
