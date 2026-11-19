"""Find the streamer's facecam automatically, like the big clipping sites do.

We sample frames from the clip, detect faces, keep the face that stays in the same place
(the webcam — game characters move around), and return a crop box around head and shoulders.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import ffmpeg_bin

PANEL_RATIO = 1080 / 960          # width / height of the facecam panel (top half of the Short)
MODEL = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"  # YuNet, MIT


def _frames(video: Path, start: float, end: float, count: int, width: int = 640):
    import numpy as np
    span = max(0.5, end - start)
    for i in range(count):
        t = start + span * (i + 0.5) / count
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video),
               "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        out = subprocess.run(cmd, capture_output=True, timeout=60).stdout
        if out:
            height = len(out) // (width * 3)
            if height:
                yield np.frombuffer(out[: width * height * 3], dtype=np.uint8).reshape(height, width, 3)


def detect(video: Path, start: float, end: float, src_w: int, src_h: int, samples: int = 16) -> dict | None:
    """Return the facecam crop as fractions of the frame: {x, y, w, h}, or None if no steady face."""
    try:
        import cv2
    except ImportError:
        return None
    detector = None
    found = []   # (cx, cy, size) as fractions of the frame
    frame_count = 0
    for img in _frames(video, start, end, samples):
        frame_count += 1
        h, w = img.shape[:2]
        if detector is None:
            detector = cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), 0.5, 0.3, 50)
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        for face in (faces if faces is not None else []):
            x, y, fw, fh = face[:4]
            if fh < h * 0.04:          # ignore tiny faces (crowds, far NPCs)
                continue
            found.append(((x + fw / 2) / w, (y + fh / 2) / h, fh / h))
    if not found or not frame_count:
        return None

    # group detections that sit in the same place; the webcam face is the steadiest group
    groups: list[list[tuple]] = []
    for f in found:
        for g in groups:
            if abs(g[0][0] - f[0]) < 0.06 and abs(g[0][1] - f[1]) < 0.08:
                g.append(f)
                break
        else:
            groups.append([f])
    best = max(groups, key=len)
    if len(best) < max(2, frame_count // 6):
        return None
    cx = sorted(f[0] for f in best)[len(best) // 2]
    cy = sorted(f[1] for f in best)[len(best) // 2]
    size = sorted(f[2] for f in best)[len(best) // 2]
    return crop_box(cx, cy, size, src_w, src_h)


def crop_box(cx: float, cy: float, face_h: float, src_w: int, src_h: int, zoom: float = 1.0) -> dict:
    """Head-and-shoulders box around a face, in the facecam panel's shape, kept inside the frame."""
    ar = src_w / max(1, src_h)
    box_h = min(1.0, face_h * 2.4 / zoom)            # face fills ~40% of the panel height            # face takes ~40% of the panel height
    box_w = box_h * PANEL_RATIO / ar                  # same shape as the panel (in pixels)
    if box_w > 1.0:
        box_w, box_h = 1.0, ar / PANEL_RATIO
    x = min(max(0.0, cx - box_w / 2), 1.0 - box_w)
    y = min(max(0.0, cy - box_h * 0.42), 1.0 - box_h)  # face a little above the middle
    return {k: round(float(v), 4) for k, v in
            {"x": x, "y": y, "w": box_w, "h": box_h, "cx": cx, "cy": cy, "face": face_h}.items()}
