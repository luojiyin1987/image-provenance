#!/usr/bin/env python3
"""AI Image Detector - Backend API Server v3 (plain JSON, no SSE)"""
import os, json, subprocess, tempfile, hashlib, uuid, struct, re, base64, random, logging, time, traceback, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta
import cgi

UPLOAD_DIR = tempfile.mkdtemp()
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8810
LOG_DIR = os.path.join(STATIC_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Logging
from logging.handlers import RotatingFileHandler
logger = logging.getLogger('ai-detector')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(ch)
fh = RotatingFileHandler(os.path.join(LOG_DIR, 'server.log'), maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [%(thread)d] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(fh)
logger.info("=" * 60)
logger.info("AI Image Detector Server v3 starting up")

CAMERA_PROFILES = {
    "iphone15pro": {
        "Make": "Apple", "Model": "iPhone 15 Pro Max", "Software": "18.5",
        "LensModel": "iPhone 15 Pro Max back triple camera 6.765mm f/1.78",
        "FocalLength": "6.765 mm", "FNumber": "1.78", "ISO": "100",
        "ExposureTime": "1/120", "WhiteBalance": "Auto", "ColorSpace": "sRGB", "Flash": "No Flash",
    },
    "canonr5": {
        "Make": "Canon", "Model": "Canon EOS R5", "Software": "Adobe Lightroom Classic",
        "LensModel": "RF24-70mm F2.8 L IS USM", "LensMake": "Canon",
        "FocalLength": "35 mm", "FNumber": "2.8", "ISO": "400",
        "ExposureTime": "1/250", "WhiteBalance": "Auto", "ColorSpace": "sRGB", "Flash": "No Flash",
        "ExposureProgram": "Aperture priority", "MeteringMode": "Multi-segment",
        "Orientation": "Horizontal (normal)",
    },
    "sonya7iv": {
        "Make": "SONY", "Model": "ILCE-7M4", "Software": "Adobe Lightroom Classic",
        "LensModel": "FE 24-70mm F2.8 GM II", "LensMake": "Sony",
        "FocalLength": "50 mm", "FNumber": "2.8", "ISO": "200",
        "ExposureTime": "1/160", "WhiteBalance": "Auto", "ColorSpace": "sRGB", "Flash": "No Flash",
        "ExposureProgram": "Manual", "MeteringMode": "Multi-segment",
        "Orientation": "Horizontal (normal)",
    },
    "samsungs24": {
        "Make": "samsung", "Model": "SM-S9260", "Software": "S9260ZCU4AXK4",
        "LensModel": "Samsung Galaxy S24+ Rear Camera",
        "FocalLength": "6.3 mm", "FNumber": "1.8", "ISO": "80",
        "ExposureTime": "1/100", "WhiteBalance": "Auto", "ColorSpace": "sRGB", "Flash": "No Flash",
    },
    "xiaomi15": {
        "Make": "Xiaomi", "Model": "24129PN74C", "Software": "MIUI Camera",
        "LensModel": "Xiaomi 15 Pro Rear Main Camera",
        "FocalLength": "7.59 mm", "FNumber": "1.44", "ISO": "50",
        "ExposureTime": "1/200", "WhiteBalance": "Auto", "ColorSpace": "sRGB", "Flash": "No Flash",
    },
}


def strip_c2pa_jpeg(data: bytes) -> tuple:
    if data[:2] != b'\xff\xd8':
        return data, 0, 0
    result = bytearray(b'\xff\xd8')
    pos, removed, total_removed = 2, 0, 0
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            result.extend(data[pos:])
            break
        marker = data[pos + 1]
        if marker == 0xDA:
            result.extend(data[pos:])
            break
        if pos + 4 > len(data):
            result.extend(data[pos:])
            break
        seg_len = struct.unpack('>H', data[pos + 2: pos + 4])[0]
        seg_total = 2 + seg_len
        if marker == 0xEB:
            removed += 1
            total_removed += seg_total
            pos += seg_total
            continue
        result.extend(data[pos:pos + seg_total])
        pos += seg_total
    return bytes(result), removed, total_removed


def strip_c2pa_png(data: bytes) -> tuple:
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return data, 0, 0
    result = bytearray(data[:8])
    pos, removed, total_removed = 8, 0, 0
    c2pa_chunks = {b'caBX', b'C2PA', b'c2pa'}
    while pos + 8 <= len(data):
        chunk_len = struct.unpack('>I', data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_total = 12 + chunk_len
        if chunk_type in c2pa_chunks:
            removed += 1
            total_removed += chunk_total
        else:
            result.extend(data[pos:pos + chunk_total])
        pos += chunk_total
    return bytes(result), removed, total_removed


def parse_exif_metadata(filepath):
    try:
        result = subprocess.run(
            ['exiftool', '-json', '-G', '-n', '-a', '-u', '-struct', filepath],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data[0] if data else {}
    except:
        pass
    return {}


def detect_ai_markers(meta: dict) -> dict:
    all_text = json.dumps(meta, ensure_ascii=False).lower()
    results = {}
    if 'trainedalgorithmimedia' in all_text or 'trainedalgorithmicmedia' in all_text:
        results['c2pa_ai_marker'] = {'found': True, 'detail': 'IPTC DigitalSourceType = trainedAlgorithmicMedia'}
    for key, val in meta.items():
        val_str = str(val)
        if 'steps:' in val_str.lower() and 'sampler:' in val_str.lower():
            results['stable_diffusion'] = {'found': True, 'detail': f'Found SD parameters in {key}'}
        if 'negative prompt:' in val_str.lower():
            results['sd_negative_prompt'] = {'found': True, 'detail': f'Found "Negative prompt" in {key}'}
        if 'model hash:' in val_str.lower():
            results['sd_model_hash'] = {'found': True, 'detail': f'Found model hash in {key}'}
        if 'comfyui' in val_str.lower() and ('workflow' in key.lower() or 'nodes' in val_str.lower()):
            results['comfyui'] = {'found': True, 'detail': 'ComfyUI workflow detected'}
    mj_patterns = ['--v ', '--ar ', '--s ', '--q ', '--seed ', '--style ', '--chaos ']
    mj_hits = [p for p in mj_patterns if p in all_text]
    if len(mj_hits) >= 2:
        results['midjourney'] = {'found': True, 'detail': f'MJ parameters: {", ".join(mj_hits)}'}
    openai_kw = ['openai', 'dall-e', 'dall·e', 'dalle', 'gpt-image', 'chatgpt']
    openai_hits = [k for k in openai_kw if k in all_text]
    if openai_hits:
        results['openai'] = {'found': True, 'detail': f'OpenAI markers: {", ".join(openai_hits)}'}
    google_kw = ['google', 'synthid', 'gemini', 'imagen', 'nano banana', 'deepmind']
    google_hits = [k for k in google_kw if k in all_text]
    if google_hits:
        results['google'] = {'found': True, 'detail': f'Google markers: {", ".join(google_hits)}'}
    if 'firefly' in all_text and 'adobe' in all_text:
        results['adobe_firefly'] = {'found': True, 'detail': 'Adobe Firefly detected'}
    return results


def assess_authenticity(meta: dict, ai_markers: dict) -> dict:
    score = 50.0
    camera_signals = []
    ai_signals = []
    if ai_markers.get('c2pa_ai_marker', {}).get('found'):
        score -= 100; ai_signals.append('C2PA trainedAlgorithmicMedia 标记')
    if ai_markers.get('stable_diffusion', {}).get('found'):
        score -= 100; ai_signals.append('Stable Diffusion 生成参数')
    if ai_markers.get('midjourney', {}).get('found'):
        score -= 100; ai_signals.append('Midjourney 参数')
    if ai_markers.get('openai', {}).get('found'):
        score -= 100; ai_signals.append('OpenAI/DALL-E 标记')
    if ai_markers.get('comfyui', {}).get('found'):
        score -= 100; ai_signals.append('ComfyUI 工作流')
    if ai_markers.get('google', {}).get('found'):
        score -= 80; ai_signals.append('Google AI 标记')
    camera_checks = [
        ('EXIF:Make', 15, '相机厂商'), ('EXIF:Model', 15, '相机型号'),
        ('EXIF:FNumber', 5, '光圈值'), ('EXIF:ExposureTime', 5, '曝光时间'),
        ('EXIF:ISO', 5, 'ISO值'), ('EXIF:FocalLength', 5, '焦距'),
        ('EXIF:LensModel', 10, '镜头型号'), ('EXIF:LensMake', 5, '镜头厂商'),
        ('EXIF:ExposureProgram', 3, '曝光模式'), ('EXIF:MeteringMode', 3, '测光模式'),
        ('EXIF:WhiteBalance', 3, '白平衡'), ('EXIF:DateTimeOriginal', 5, '拍摄时间'),
        ('EXIF:Orientation', 2, '方向信息'), ('EXIF:GPSLatitude', 5, 'GPS坐标'),
    ]
    for tag, weight, desc in camera_checks:
        if tag in meta and meta[tag] is not None:
            score += weight; camera_signals.append(f'{desc}: {meta[tag]}')
    makernotes = [k for k in meta if 'MakerNotes' in k]
    if makernotes:
        score += 20; camera_signals.append(f'厂商私有数据 ({len(makernotes)} 条)')
    serial_tags = [k for k in meta if 'Serial' in k or 'serial' in k]
    for tag in serial_tags:
        if meta.get(tag):
            score += 10; camera_signals.append(f'设备序列号: {meta[tag]}'); break
    score = max(0, min(100, score))
    if score >= 80: verdict = 'very_likely_camera'
    elif score >= 60: verdict = 'likely_camera'
    elif score >= 40: verdict = 'uncertain'
    elif score >= 20: verdict = 'suspicious'
    else: verdict = 'likely_ai'
    return {'score': round(score), 'verdict': verdict, 'camera_signals': camera_signals, 'ai_signals': ai_signals}


class APIHandler(SimpleHTTPRequestHandler):

    def _log_request_start(self):
        self._req_start = time.time()
        self._req_ip = self.client_address[0]
        logger.info(f"REQ START | {self._req_ip} | {self.command} {self.path} | UA: {self.headers.get('User-Agent', '-')[:80]}")

    def _log_request_end(self, status_code=200, extra=''):
        elapsed = time.time() - self._req_start
        logger.info(f"REQ END   | {self._req_ip} | {self.command} {self.path} | {status_code} | {elapsed:.3f}s {extra}")

    def do_GET(self):
        self._log_request_start()
        if self.path == '/' or self.path == '/index.html':
            self.path = '/index.html'
            result = super().do_GET()
            self._log_request_end(200)
            return result
        elif self.path == '/api/profiles':
            self.send_json({k: {"Make": v["Make"], "Model": v["Model"]} for k, v in CAMERA_PROFILES.items()})
            self._log_request_end(200)
        elif self.path.startswith('/api/convert/image/'):
            self.handle_get_image()
        else:
            result = super().do_GET()
            self._log_request_end(200)
            return result

    def do_POST(self):
        self._log_request_start()
        if self.path == '/api/convert':
            self.handle_convert()
        elif self.path == '/api/analyze':
            self.handle_analyze()
        else:
            self.send_error(404)
            self._log_request_end(404)

    def handle_get_image(self):
        """Serve converted image by token"""
        try:
            token = self.path.split('/')[-1]
            img_path = os.path.join(UPLOAD_DIR, f"img_{token}.jpg")
            if not os.path.exists(img_path):
                self.send_json({"error": "Image not found or expired"}, 404)
                self._log_request_end(404, 'image not found')
                return
            with open(img_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
            self._log_request_end(200, f'image {len(data)}B')
        except Exception as e:
            self.send_json({"error": str(e)}, 500)
            self._log_request_end(500, f'image error: {str(e)[:100]}')

    def handle_convert(self):
        """Strip C2PA + metadata, add fake camera EXIF — plain JSON response"""
        try:
            content_type = self.headers.get('Content-Type', '')
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                    environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type})
            file_field = form['image']
            if not file_field.filename:
                self._log_request_end(400, 'no file')
                return self.send_json({"error": "No file"}, 400)

            profile_key = form.getfirst('profile', 'iphone15pro')
            disrupt_wm = form.getfirst('disrupt_watermark', '0') == '1'
            profile = CAMERA_PROFILES.get(profile_key, CAMERA_PROFILES['iphone15pro'])
            ext = os.path.splitext(file_field.filename)[1].lower() or '.jpg'
            raw_data = file_field.file.read()
            file_size = len(raw_data)

            logger.info(f"CONVERT START | file={file_field.filename} | size={file_size} | ext={ext} | profile={profile_key} | watermark={disrupt_wm}")

            # Step 1: C2PA Strip
            t0 = time.time()
            c2pa_removed = 0
            if ext in ['.jpg', '.jpeg']:
                raw_data, c2pa_removed, _ = strip_c2pa_jpeg(raw_data)
            elif ext == '.png':
                raw_data, c2pa_removed, _ = strip_c2pa_png(raw_data)
            logger.info(f"CONVERT STEP1 C2PA | removed={c2pa_removed} | elapsed={time.time()-t0:.3f}s")

            # Step 2: Save + strip metadata
            input_path = os.path.join(UPLOAD_DIR, f"clean_{uuid.uuid4().hex}{ext}")
            output_path = os.path.join(UPLOAD_DIR, f"output_{uuid.uuid4().hex}.jpg")
            with open(input_path, 'wb') as f:
                f.write(raw_data)

            t1 = time.time()
            if ext in ['.png', '.webp']:
                subprocess.run(['exiftool', '-all=', '-b', '-jpgfromraw', '-w', 'jpg', input_path], capture_output=True, timeout=30)
                converted = input_path + '.jpg'
                if os.path.exists(converted):
                    os.rename(converted, output_path)
                else:
                    subprocess.run(['exiftool', '-all=', '-overwrite_original', input_path], capture_output=True)
                    subprocess.run(['cp', input_path, output_path], capture_output=True)
            else:
                subprocess.run(['exiftool', '-all=', '-trailer:all=', '-overwrite_original', input_path], capture_output=True, timeout=30)
                subprocess.run(['cp', input_path, output_path], capture_output=True)
            logger.info(f"CONVERT STEP2 META | elapsed={time.time()-t1:.3f}s")

            # Step 3: Watermark disruption
            t2 = time.time()
            wm_result = None
            if disrupt_wm:
                logger.info("CONVERT STEP3 WATERMARK | starting")
                wm_script = os.path.join(STATIC_DIR, 'disrupt_watermark.py')
                wm_output = os.path.join(UPLOAD_DIR, f"wm_{uuid.uuid4().hex}.jpg")
                wm_proc = subprocess.run(['/usr/bin/python3', wm_script, output_path, wm_output, '3'], capture_output=True, text=True, timeout=300)
                if wm_proc.returncode == 0 and os.path.exists(wm_output):
                    wm_result = json.loads(wm_proc.stdout.strip())
                    os.replace(wm_output, output_path)
                    logger.info(f"CONVERT STEP3 WATERMARK | success: {wm_result}")
                else:
                    logger.warning(f"CONVERT STEP3 WATERMARK | failed: rc={wm_proc.returncode}")
                logger.info(f"CONVERT STEP3 WATERMARK | elapsed={time.time()-t2:.3f}s")
            else:
                logger.info("CONVERT STEP3 WATERMARK | skipped")

            # Step 4: EXIF Injection
            t3 = time.time()
            exif_args = []
            for key, val in profile.items():
                exif_args.append(f'-{key}={val}')
            random_dt = datetime.now() - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
            date_str = random_dt.strftime('%Y:%m:%d %H:%M:%S')
            exif_args.extend([f'-DateTimeOriginal={date_str}', f'-CreateDate={date_str}', f'-ModifyDate={date_str}', '-ICC_Profile<=/usr/share/color/icc/sRGB.icc'])
            subprocess.run(['exiftool', '-overwrite_original'] + exif_args + [output_path], capture_output=True, timeout=30)
            logger.info(f"CONVERT STEP4 EXIF | profile={profile_key} | elapsed={time.time()-t3:.3f}s")

            # Step 5: Verify + store image
            t4 = time.time()
            with open(output_path, 'rb') as f:
                output_data = f.read()

            verify_path = os.path.join(UPLOAD_DIR, f"verify_{uuid.uuid4().hex}.jpg")
            with open(verify_path, 'wb') as f:
                f.write(output_data)
            meta_result = subprocess.run(['exiftool', '-json', '-G', verify_path], capture_output=True, text=True, timeout=30)
            metadata = json.loads(meta_result.stdout) if meta_result.returncode == 0 else []
            _, remaining_c2pa, _ = strip_c2pa_jpeg(output_data)
            c2pa_clean = remaining_c2pa == 0

            for p in [input_path, output_path, verify_path]:
                if os.path.exists(p): os.unlink(p)

            total_elapsed = time.time() - t0
            logger.info(f"CONVERT DONE | total={total_elapsed:.3f}s | output={len(output_data)}B | file={file_field.filename}")

            # Store image for separate GET download
            img_token = uuid.uuid4().hex
            img_path = os.path.join(UPLOAD_DIR, f"img_{img_token}.jpg")
            with open(img_path, 'wb') as f:
                f.write(output_data)
            threading.Timer(600, lambda: os.path.exists(img_path) and os.unlink(img_path)).start()

            self.send_json({
                "success": True,
                "image_token": img_token,
                "metadata": metadata,
                "profile": profile_key,
                "c2pa_removed": c2pa_removed,
                "c2pa_clean": c2pa_clean,
                "watermark_disrupted": wm_result is not None,
                "watermark_details": wm_result,
                "output_size": len(output_data),
            })
            self._log_request_end(200, f'convert ok, {file_size}B, {total_elapsed:.2f}s')

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"CONVERT ERROR | {str(e)}\n{tb}")
            self.send_json({"error": str(e)}, 500)
            self._log_request_end(500, f'convert error: {str(e)[:100]}')

    def handle_analyze(self):
        """Full metadata analysis with AI detection"""
        try:
            content_type = self.headers.get('Content-Type', '')
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                    environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': content_type})
            file_field = form['image']
            ext = os.path.splitext(file_field.filename)[1].lower() or '.jpg'
            input_path = os.path.join(UPLOAD_DIR, f"analyze_{uuid.uuid4().hex}{ext}")
            raw = file_field.file.read()
            file_size = len(raw)
            logger.info(f"ANALYZE START | file={file_field.filename} | size={file_size}")
            with open(input_path, 'wb') as f:
                f.write(raw)
            t0 = time.time()
            meta = parse_exif_metadata(input_path)
            grouped = {}
            for key, val in meta.items():
                group = key.split(':')[0] if ':' in key else 'Info'
                grouped.setdefault(group, {})[key] = val
            ai_markers = detect_ai_markers(meta)
            authenticity = assess_authenticity(meta, ai_markers)
            os.unlink(input_path)
            elapsed = time.time() - t0
            logger.info(f"ANALYZE DONE | score={authenticity['score']} | elapsed={elapsed:.3f}s")
            self.send_json({"success": True, "metadata": meta, "grouped": grouped, "ai_markers": ai_markers, "authenticity": authenticity})
            self._log_request_end(200, f'analyze ok, {file_size}B, {elapsed:.2f}s')
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"ANALYZE ERROR | {str(e)}\n{tb}")
            self.send_json({"error": str(e)}, 500)
            self._log_request_end(500, f'analyze error: {str(e)[:100]}')

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    os.chdir(STATIC_DIR)
    server = ThreadingHTTPServer(('0.0.0.0', PORT), APIHandler)
    logger.info(f"Server v3 running on http://0.0.0.0:{PORT}")
    print(f"Server v3 running on http://0.0.0.0:{PORT}")
    server.serve_forever()
