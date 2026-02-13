#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
masking_tool_linux.py - Linux 서버용 마스킹 도구 (CLI)

GUI 없이 명령어만으로 동작하는 마스킹 도구.
argparse 서브커맨드 기반으로 모든 기능을 커맨드라인에서 실행 가능.

사용법:
  python3 masking_tool_linux.py <command> [options]

커맨드 목록:
  auto     - 특정 클래스 바운딩 박스 자동 마스킹
  bbox     - 지정 좌표 영역(x1,y1,x2,y2) 마스킹
  polygon  - 다각형 좌표 영역 마스킹
  save     - 이미지에서 마스킹 좌표 추출 → .npz 저장
  load     - .npz 마스킹 데이터를 이미지에 적용
  copy     - 한 이미지의 마스킹을 다른 이미지들에 복사
  clean    - 마스킹 영역과 겹치는 라벨 삭제
  info     - 이미지/npz 마스킹 정보 출력
  classes  - 사용 가능한 클래스 목록 출력
"""

import os
import sys
import argparse
import shutil
from pathlib import Path

# 무거운 라이브러리는 실제 사용 시 지연 임포트
_np = None
_Image = None
_cv2 = None
_HAS_CV2 = None
_natsorted = None


def _ensure_deps():
    """PIL, numpy 등 핵심 의존성을 지연 임포트."""
    global _np, _Image
    if _np is None:
        try:
            import numpy as np
            _np = np
        except ImportError:
            print("[오류] numpy 가 필요합니다: pip install numpy")
            sys.exit(1)
    if _Image is None:
        try:
            from PIL import Image
            _Image = Image
        except ImportError:
            print("[오류] Pillow 가 필요합니다: pip install Pillow")
            sys.exit(1)


def _ensure_cv2():
    """OpenCV 지연 임포트."""
    global _cv2, _HAS_CV2
    if _HAS_CV2 is None:
        try:
            import cv2
            _cv2 = cv2
            _HAS_CV2 = True
        except ImportError:
            _HAS_CV2 = False
    return _HAS_CV2


def _ensure_natsort():
    """natsort 지연 임포트 (없으면 기본 sorted 사용)."""
    global _natsorted
    if _natsorted is None:
        try:
            from natsort import natsorted
            _natsorted = natsorted
        except ImportError:
            _natsorted = sorted

# ──────────────────────────────────────────────
# YOLO 클래스 정의
# ──────────────────────────────────────────────
CLASS_NAMES = [
    "person", "slip", "head", "helmet", "gasmask", "Drum", "sitting",
    "bicycle", "car", "motorbike", "aeroplane",
    "bus", "train", "truck", "boat", "trafficlight",
    "firehydrant", "stop sign", "parking meter", "bench", "bird",
    "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "van", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut",
    "cake", "chair", "sofa", "pottedplant", "bed",
    "diningtable", "toilet", "tvmonitor", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book",
]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
MASK_COLOR = [255, 0, 255]


# ──────────────────────────────────────────────
# 공통 유틸리티
# ──────────────────────────────────────────────
def collect_images(folder):
    """폴더에서 이미지 파일 목록을 자연정렬하여 반환."""
    _ensure_natsort()
    files = []
    for f in Path(folder).iterdir():
        if f.suffix.lower() in IMAGE_EXTENSIONS:
            files.append(f)
    return _natsorted(files, key=lambda p: p.name)


def load_yolo_labels(label_path):
    """YOLO 형식 라벨 파일 로드."""
    labels = []
    if not os.path.exists(label_path):
        return labels
    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                class_id = int(parts[0])
                cx, cy, w, h = map(float, parts[1:5])
                labels.append([class_id, cx, cy, w, h])
    return labels


def save_yolo_labels(label_path, labels):
    """YOLO 형식 라벨 파일 저장."""
    with open(label_path, "w") as f:
        for lb in labels:
            f.write(f"{int(lb[0])} {lb[1]:.6f} {lb[2]:.6f} {lb[3]:.6f} {lb[4]:.6f}\n")


def yolo_to_abs(cx, cy, w, h, img_w, img_h):
    """YOLO 정규 좌표 → 절대 좌표 (x1, y1, x2, y2)."""
    x1 = int((cx - w / 2) * img_w)
    y1 = int((cy - h / 2) * img_h)
    x2 = int((cx + w / 2) * img_w)
    y2 = int((cy + h / 2) * img_h)
    x1 = max(0, min(x1, img_w - 1))
    y1 = max(0, min(y1, img_h - 1))
    x2 = max(0, min(x2, img_w - 1))
    y2 = max(0, min(y2, img_h - 1))
    return x1, y1, x2, y2


def save_image(arr, path):
    """numpy 배열을 이미지 파일로 저장."""
    img = _Image.fromarray(arr)
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        img.save(str(path), quality=95, optimize=True)
    else:
        img.save(str(path))


def backup_file(file_path, backup_base):
    """파일 백업. 이미 백업이 있으면 건너뜀."""
    if not os.path.exists(file_path):
        return
    os.makedirs(backup_base, exist_ok=True)
    dst = os.path.join(backup_base, os.path.basename(file_path))
    if not os.path.exists(dst):
        shutil.copy2(file_path, dst)


def detect_mask_pixels(arr):
    """이미지 배열에서 마젠타(255,0,255) 마스킹 픽셀 좌표 반환."""
    return _np.where(
        (arr[:, :, 0] == 255) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 255)
    )


def find_label_folder(image_folder):
    """이미지 폴더 기준으로 라벨 폴더 자동 탐색."""
    parent = Path(image_folder).parent
    candidates = [
        parent / "labels",
        Path(image_folder) / "labels",
        parent / "label",
    ]
    for p in candidates:
        if p.is_dir():
            return str(p)
    # txt 파일이 같은 폴더에 있는 경우
    if list(Path(image_folder).glob("*.txt")):
        return image_folder
    return None


def parse_coords(coord_str):
    """'x1,y1,x2,y2' 형태 문자열을 정수 튜플로 파싱."""
    parts = coord_str.replace(" ", "").split(",")
    return tuple(int(p) for p in parts)


def parse_polygon(coord_str):
    """'x1,y1,x2,y2,...,xn,yn' 형태를 [(x1,y1),(x2,y2),...] 로 파싱."""
    nums = [int(p) for p in coord_str.replace(" ", "").split(",")]
    if len(nums) % 2 != 0:
        raise ValueError("폴리곤 좌표는 짝수 개여야 합니다 (x,y 쌍)")
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]


# ──────────────────────────────────────────────
# 서브커맨드 구현
# ──────────────────────────────────────────────

# ── auto: 클래스 기반 자동 마스킹 ────────────
def cmd_auto(args):
    """특정 클래스의 바운딩 박스를 자동으로 마스킹."""
    _ensure_deps()
    image_folder = args.images
    label_folder = args.labels or find_label_folder(image_folder)
    output_folder = args.output or image_folder

    if not label_folder or not os.path.isdir(label_folder):
        print(f"[오류] 라벨 폴더를 찾을 수 없습니다: {label_folder}")
        return 1

    # 클래스 번호 파싱
    target_classes = []
    for s in args.classes.split(","):
        s = s.strip()
        if not s:
            continue
        num = int(s)
        if 0 <= num < len(CLASS_NAMES):
            target_classes.append(num)
            print(f"  클래스 {num}: {CLASS_NAMES[num]}")
        else:
            print(f"  [경고] 클래스 {num} 무시 (범위 초과)")

    if not target_classes:
        print("[오류] 유효한 클래스가 없습니다.")
        return 1

    os.makedirs(output_folder, exist_ok=True)
    image_files = collect_images(image_folder)
    if not image_files:
        print(f"[오류] 이미지 없음: {image_folder}")
        return 1

    print(f"\n총 {len(image_files)}개 이미지 처리 시작...")
    mask_color = MASK_COLOR
    processed = 0
    masked = 0

    for img_path in image_files:
        label_path = os.path.join(label_folder, img_path.stem + ".txt")
        output_path = os.path.join(output_folder, img_path.name)

        try:
            img = _Image.open(str(img_path)).convert("RGB")
            arr = _np.array(img)
            img_h, img_w = arr.shape[:2]
            labels = load_yolo_labels(label_path)

            count = 0
            for lb in labels:
                if int(lb[0]) in target_classes:
                    x1, y1, x2, y2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4], img_w, img_h)
                    arr[y1:y2, x1:x2] = mask_color
                    count += 1

            save_image(arr, output_path)

            if count > 0:
                masked += 1
                print(f"  [마스킹] {img_path.name} - {count}개 객체")

                # --remove-labels 옵션
                if args.remove_labels:
                    out_label = os.path.join(
                        output_folder if output_folder != image_folder else label_folder,
                        img_path.stem + ".txt",
                    )
                    remaining = [lb for lb in labels if int(lb[0]) not in target_classes]
                    save_yolo_labels(out_label, remaining)
            else:
                print(f"  [건너뜀] {img_path.name}")

            processed += 1
        except Exception as e:
            print(f"  [오류] {img_path.name}: {e}")

    print(f"\n완료: 처리 {processed}개 / 마스킹 {masked}개")
    print(f"결과 저장: {output_folder}")
    return 0


# ── bbox: 좌표 지정 사각형 마스킹 ────────────
def cmd_bbox(args):
    """지정한 절대 좌표 영역(x1,y1,x2,y2)을 마스킹."""
    _ensure_deps()
    x1, y1, x2, y2 = parse_coords(args.region)
    image_folder = args.images
    output_folder = args.output or image_folder

    os.makedirs(output_folder, exist_ok=True)
    image_files = collect_images(image_folder)
    if not image_files:
        print(f"[오류] 이미지 없음: {image_folder}")
        return 1

    mask_color = MASK_COLOR
    print(f"마스킹 영역: ({x1},{y1})-({x2},{y2})")
    print(f"총 {len(image_files)}개 이미지 처리...")

    for img_path in image_files:
        try:
            img = _Image.open(str(img_path)).convert("RGB")
            arr = _np.array(img)
            img_h, img_w = arr.shape[:2]

            # 이미지 범위 클리핑
            cx1 = max(0, min(x1, img_w - 1))
            cy1 = max(0, min(y1, img_h - 1))
            cx2 = max(0, min(x2, img_w - 1))
            cy2 = max(0, min(y2, img_h - 1))

            arr[cy1:cy2, cx1:cx2] = mask_color

            out_path = os.path.join(output_folder, img_path.name)
            save_image(arr, out_path)
            print(f"  [마스킹] {img_path.name}")
        except Exception as e:
            print(f"  [오류] {img_path.name}: {e}")

    # --remove-labels
    if args.remove_labels:
        label_folder = args.labels or find_label_folder(image_folder)
        if label_folder:
            _clean_labels_in_rect(label_folder, image_folder, output_folder,
                                  x1, y1, x2, y2, image_files)

    print("완료")
    return 0


# ── polygon: 다각형 좌표 마스킹 ──────────────
def cmd_polygon(args):
    """다각형 꼭짓점 좌표로 마스킹."""
    _ensure_deps()
    if not _ensure_cv2():
        print("[오류] 폴리곤 마스킹에는 opencv-python 이 필요합니다.")
        print("       pip install opencv-python")
        return 1

    points = parse_polygon(args.points)
    if len(points) < 3:
        print("[오류] 폴리곤은 최소 3개의 꼭짓점이 필요합니다.")
        return 1

    image_folder = args.images
    output_folder = args.output or image_folder

    os.makedirs(output_folder, exist_ok=True)
    image_files = collect_images(image_folder)
    if not image_files:
        print(f"[오류] 이미지 없음: {image_folder}")
        return 1

    mask_color = MASK_COLOR
    cv_pts = _np.array([points], dtype=_np.int32)
    print(f"폴리곤 꼭짓점 {len(points)}개: {points}")
    print(f"총 {len(image_files)}개 이미지 처리...")

    for img_path in image_files:
        try:
            img = _Image.open(str(img_path)).convert("RGB")
            arr = _np.array(img)
            img_h, img_w = arr.shape[:2]

            mask = _np.zeros((img_h, img_w), dtype=_np.uint8)
            _cv2.fillPoly(mask, cv_pts, 255)
            arr[mask == 255] = mask_color

            out_path = os.path.join(output_folder, img_path.name)
            save_image(arr, out_path)
            print(f"  [마스킹] {img_path.name}")
        except Exception as e:
            print(f"  [오류] {img_path.name}: {e}")

    # --remove-labels
    if args.remove_labels:
        label_folder = args.labels or find_label_folder(image_folder)
        if label_folder:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            _clean_labels_in_rect(label_folder, image_folder, output_folder,
                                  min(xs), min(ys), max(xs), max(ys), image_files)

    print("완료")
    return 0


# ── save: 마스킹 좌표 추출 → .npz 저장 ──────
def cmd_save(args):
    """이미 마스킹된 이미지에서 마젠타 픽셀 좌표를 추출하여 .npz로 저장."""
    _ensure_deps()
    image_path = args.image
    if not os.path.exists(image_path):
        print(f"[오류] 파일 없음: {image_path}")
        return 1

    img = _Image.open(image_path).convert("RGB")
    arr = _np.array(img)
    img_h, img_w = arr.shape[:2]

    ys, xs = detect_mask_pixels(arr)
    if ys.size == 0:
        print("[알림] 마스킹된 영역이 없습니다 (마젠타 픽셀 없음).")
        return 0

    stem = Path(image_path).stem
    out_dir = args.output_dir or str(Path(image_path).parent)
    os.makedirs(out_dir, exist_ok=True)
    npz_path = os.path.join(out_dir, f"{stem}_mask.npz")

    _np.savez_compressed(npz_path, masking_y=ys, masking_x=xs,
                        width=img_w, height=img_h)

    print(f"마스킹 저장 완료: {npz_path}")
    print(f"  이미지 크기: {img_w}x{img_h}")
    print(f"  마스킹 픽셀 수: {ys.size}")
    return 0


# ── load: .npz 마스킹 데이터 적용 ────────────
def cmd_load(args):
    """.npz 마스킹 파일을 이미지(들)에 적용."""
    _ensure_deps()
    npz_path = args.npz
    if not os.path.exists(npz_path):
        print(f"[오류] 파일 없음: {npz_path}")
        return 1

    data = _np.load(npz_path)
    ys = data["masking_y"]
    xs = data["masking_x"]
    saved_w = int(data["width"])
    saved_h = int(data["height"])
    mask_color = MASK_COLOR

    print(f"마스킹 로드: {npz_path}")
    print(f"  크기: {saved_w}x{saved_h}, 픽셀 수: {ys.size}")

    # 단일 이미지 또는 폴더
    target = args.target
    if os.path.isfile(target):
        targets = [Path(target)]
    elif os.path.isdir(target):
        targets = collect_images(target)
    else:
        print(f"[오류] 대상 없음: {target}")
        return 1

    output_folder = args.output or (str(Path(target).parent) if os.path.isfile(target) else target)
    os.makedirs(output_folder, exist_ok=True)

    applied = 0
    for img_path in targets:
        try:
            img = _Image.open(str(img_path)).convert("RGB")
            arr = _np.array(img)
            h, w = arr.shape[:2]

            if w != saved_w or h != saved_h:
                print(f"  [건너뜀] {img_path.name} - 크기 불일치 ({w}x{h} != {saved_w}x{saved_h})")
                continue

            if args.backup:
                backup_dir = os.path.join(str(img_path.parent.parent), "original_backup", "JPEGImages")
                backup_file(str(img_path), backup_dir)

            arr[ys, xs] = mask_color
            out_path = os.path.join(output_folder, img_path.name)
            save_image(arr, out_path)
            applied += 1
            print(f"  [적용] {img_path.name}")
        except Exception as e:
            print(f"  [오류] {img_path.name}: {e}")

    print(f"\n완료: {applied}개 이미지에 마스킹 적용")
    return 0


# ── copy: 한 이미지의 마스킹을 다른 이미지들에 복사 ──
def cmd_copy(args):
    """원본 이미지에서 마스킹을 추출하여 대상 이미지들에 동일하게 적용."""
    _ensure_deps()
    source = args.source
    if not os.path.exists(source):
        print(f"[오류] 원본 파일 없음: {source}")
        return 1

    src_img = _Image.open(source).convert("RGB")
    src_arr = _np.array(src_img)
    src_h, src_w = src_arr.shape[:2]

    ys, xs = detect_mask_pixels(src_arr)
    if ys.size == 0:
        print("[오류] 원본 이미지에 마스킹 영역이 없습니다.")
        return 1

    print(f"원본: {source} ({src_w}x{src_h}), 마스킹 픽셀: {ys.size}")

    target_folder = args.target_folder
    targets = collect_images(target_folder)

    # 범위 필터
    if args.start is not None or args.end is not None:
        start = args.start or 0
        end = args.end if args.end is not None else len(targets) - 1
        targets = targets[start:end + 1]

    if not targets:
        print("[오류] 대상 이미지 없음.")
        return 1

    output_folder = args.output or target_folder
    os.makedirs(output_folder, exist_ok=True)
    mask_color = MASK_COLOR
    label_folder = args.labels or find_label_folder(target_folder)

    print(f"대상: {len(targets)}개 이미지")
    applied = 0

    for img_path in targets:
        try:
            img = _Image.open(str(img_path)).convert("RGB")
            arr = _np.array(img)
            h, w = arr.shape[:2]

            if w != src_w or h != src_h:
                print(f"  [건너뜀] {img_path.name} - 크기 불일치")
                continue

            if args.backup:
                backup_dir = os.path.join(str(img_path.parent.parent), "original_backup", "JPEGImages")
                backup_file(str(img_path), backup_dir)

            arr[ys, xs] = mask_color
            out_path = os.path.join(output_folder, img_path.name)
            save_image(arr, out_path)

            # 겹치는 라벨 삭제
            if args.remove_labels and label_folder:
                lbl_path = os.path.join(label_folder, img_path.stem + ".txt")
                if os.path.exists(lbl_path):
                    labels = load_yolo_labels(lbl_path)
                    y_min, y_max = int(ys.min()), int(ys.max())
                    x_min, x_max = int(xs.min()), int(xs.max())
                    remaining = []
                    for lb in labels:
                        bx1, by1, bx2, by2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4], w, h)
                        if bx2 < x_min or bx1 > x_max or by2 < y_min or by1 > y_max:
                            remaining.append(lb)
                    save_yolo_labels(lbl_path, remaining)

            applied += 1
            print(f"  [복사] {img_path.name}")
        except Exception as e:
            print(f"  [오류] {img_path.name}: {e}")

    print(f"\n완료: {applied}개 이미지에 마스킹 복사")
    return 0


# ── clean: 마스킹 영역과 겹치는 라벨 삭제 ────
def cmd_clean(args):
    """마스킹된 영역(마젠타)과 겹치는 라벨을 삭제."""
    _ensure_deps()
    image_folder = args.images
    label_folder = args.labels or find_label_folder(image_folder)

    if not label_folder or not os.path.isdir(label_folder):
        print(f"[오류] 라벨 폴더를 찾을 수 없습니다.")
        return 1

    image_files = collect_images(image_folder)
    if not image_files:
        print(f"[오류] 이미지 없음: {image_folder}")
        return 1

    print(f"이미지: {len(image_files)}개, 라벨 폴더: {label_folder}")
    total_removed = 0

    for img_path in image_files:
        lbl_path = os.path.join(label_folder, img_path.stem + ".txt")
        if not os.path.exists(lbl_path):
            continue

        try:
            img = _Image.open(str(img_path)).convert("RGB")
            arr = _np.array(img)
            img_h, img_w = arr.shape[:2]

            ys, xs = detect_mask_pixels(arr)
            if ys.size == 0:
                continue

            y_min, y_max = int(ys.min()), int(ys.max())
            x_min, x_max = int(xs.min()), int(xs.max())

            labels = load_yolo_labels(lbl_path)
            remaining = []
            removed = 0

            for lb in labels:
                bx1, by1, bx2, by2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4], img_w, img_h)
                # 겹침 확인
                if bx2 < x_min or bx1 > x_max or by2 < y_min or by1 > y_max:
                    remaining.append(lb)
                else:
                    removed += 1

            if removed > 0:
                if args.backup:
                    backup_dir = os.path.join(str(img_path.parent.parent), "original_backup", "labels")
                    backup_file(lbl_path, backup_dir)
                save_yolo_labels(lbl_path, remaining)
                total_removed += removed
                print(f"  {img_path.name}: {removed}개 라벨 삭제 ({len(remaining)}개 유지)")

        except Exception as e:
            print(f"  [오류] {img_path.name}: {e}")

    print(f"\n완료: 총 {total_removed}개 라벨 삭제")
    return 0


# ── info: 마스킹 정보 출력 ───────────────────
def cmd_info(args):
    """이미지 또는 .npz 파일의 마스킹 정보 출력."""
    _ensure_deps()
    target = args.target

    if target.endswith(".npz"):
        if not os.path.exists(target):
            print(f"[오류] 파일 없음: {target}")
            return 1
        data = _np.load(target)
        ys = data["masking_y"]
        xs = data["masking_x"]
        w = int(data["width"])
        h = int(data["height"])
        print(f"파일: {target}")
        print(f"  이미지 크기: {w} x {h}")
        print(f"  마스킹 픽셀 수: {ys.size}")
        if ys.size > 0:
            print(f"  Y 범위: {ys.min()} ~ {ys.max()}")
            print(f"  X 범위: {xs.min()} ~ {xs.max()}")
            area_w = int(xs.max()) - int(xs.min())
            area_h = int(ys.max()) - int(ys.min())
            print(f"  바운딩 영역: ({xs.min()},{ys.min()}) - ({xs.max()},{ys.max()}) ({area_w}x{area_h})")
    else:
        if not os.path.exists(target):
            print(f"[오류] 파일 없음: {target}")
            return 1
        img = _Image.open(target).convert("RGB")
        arr = _np.array(img)
        h, w = arr.shape[:2]
        ys, xs = detect_mask_pixels(arr)

        print(f"파일: {target}")
        print(f"  이미지 크기: {w} x {h}")
        print(f"  마스킹 픽셀 수: {ys.size}")
        if ys.size > 0:
            print(f"  Y 범위: {ys.min()} ~ {ys.max()}")
            print(f"  X 범위: {xs.min()} ~ {xs.max()}")
            ratio = ys.size / (w * h) * 100
            print(f"  마스킹 비율: {ratio:.2f}%")

    return 0


# ── classes: 클래스 목록 출력 ────────────────
def cmd_classes(args):
    """사용 가능한 YOLO 클래스 목록 출력."""
    print("사용 가능한 클래스 목록:")
    print("-" * 30)
    for i, cls in enumerate(CLASS_NAMES):
        print(f"  {i:3d}: {cls}")
    print(f"\n총 {len(CLASS_NAMES)}개 클래스")
    return 0


# ── 내부 헬퍼 ────────────────────────────────
def _clean_labels_in_rect(label_folder, image_folder, output_folder,
                          x1, y1, x2, y2, image_files):
    """사각형 영역과 겹치는 라벨 삭제."""
    removed_total = 0
    for img_path in image_files:
        lbl_path = os.path.join(label_folder, img_path.stem + ".txt")
        if not os.path.exists(lbl_path):
            continue

        img = _Image.open(str(img_path))
        img_w, img_h = img.size

        labels = load_yolo_labels(lbl_path)
        remaining = []
        for lb in labels:
            bx1, by1, bx2, by2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4], img_w, img_h)
            if bx2 < x1 or bx1 > x2 or by2 < y1 or by1 > y2:
                remaining.append(lb)

        removed = len(labels) - len(remaining)
        if removed > 0:
            out_lbl = os.path.join(
                output_folder if output_folder != image_folder else label_folder,
                img_path.stem + ".txt",
            )
            save_yolo_labels(out_lbl, remaining)
            removed_total += removed

    if removed_total:
        print(f"  겹치는 라벨 {removed_total}개 삭제")


# ──────────────────────────────────────────────
# argparse 구성
# ──────────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(
        prog="masking_tool_linux",
        description="Linux 서버용 마스킹 도구 (CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 클래스 0(person), 8(car) 자동 마스킹
  python3 masking_tool_linux.py auto -i ./images -l ./labels -c 0,8

  # 특정 영역 사각형 마스킹
  python3 masking_tool_linux.py bbox -i ./images -r 100,50,400,300

  # 폴리곤 마스킹
  python3 masking_tool_linux.py polygon -i ./images -p 100,100,300,50,500,100,500,400,100,400

  # 마스킹 좌표를 .npz로 저장
  python3 masking_tool_linux.py save -f ./images/frame001.jpg

  # .npz 마스킹을 다른 이미지들에 적용
  python3 masking_tool_linux.py load -n ./frame001_mask.npz -t ./images/

  # 한 이미지의 마스킹을 범위 복사
  python3 masking_tool_linux.py copy -s ./images/frame001.jpg -t ./images/ --start 0 --end 100

  # 마스킹 영역과 겹치는 라벨 삭제
  python3 masking_tool_linux.py clean -i ./images -l ./labels

  # 마스킹 정보 확인
  python3 masking_tool_linux.py info frame001_mask.npz
  python3 masking_tool_linux.py info ./images/frame001.jpg

  # 클래스 목록 확인
  python3 masking_tool_linux.py classes
""",
    )

    sub = parser.add_subparsers(dest="command", help="실행할 커맨드")

    # ── auto ──
    p_auto = sub.add_parser("auto", help="특정 클래스 바운딩 박스 자동 마스킹")
    p_auto.add_argument("-i", "--images", required=True, help="이미지 폴더 경로")
    p_auto.add_argument("-l", "--labels", help="라벨 폴더 경로 (미지정 시 자동 탐색)")
    p_auto.add_argument("-o", "--output", help="출력 폴더 (미지정 시 원본 덮어쓰기)")
    p_auto.add_argument("-c", "--classes", required=True, help="마스킹할 클래스 번호 (쉼표 구분, 예: 0,8,21)")
    p_auto.add_argument("--remove-labels", action="store_true", help="마스킹된 클래스의 라벨도 삭제")

    # ── bbox ──
    p_bbox = sub.add_parser("bbox", help="지정 좌표 영역 사각형 마스킹")
    p_bbox.add_argument("-i", "--images", required=True, help="이미지 폴더 경로")
    p_bbox.add_argument("-r", "--region", required=True, help="마스킹 영역 (x1,y1,x2,y2)")
    p_bbox.add_argument("-o", "--output", help="출력 폴더")
    p_bbox.add_argument("-l", "--labels", help="라벨 폴더 경로")
    p_bbox.add_argument("--remove-labels", action="store_true", help="겹치는 라벨 삭제")

    # ── polygon ──
    p_poly = sub.add_parser("polygon", help="다각형 좌표 마스킹 (cv2 필요)")
    p_poly.add_argument("-i", "--images", required=True, help="이미지 폴더 경로")
    p_poly.add_argument("-p", "--points", required=True, help="폴리곤 좌표 (x1,y1,x2,y2,...,xn,yn)")
    p_poly.add_argument("-o", "--output", help="출력 폴더")
    p_poly.add_argument("-l", "--labels", help="라벨 폴더 경로")
    p_poly.add_argument("--remove-labels", action="store_true", help="겹치는 라벨 삭제")

    # ── save ──
    p_save = sub.add_parser("save", help="이미지에서 마스킹 좌표 추출 → .npz 저장")
    p_save.add_argument("-f", "--image", required=True, help="마스킹된 이미지 파일 경로")
    p_save.add_argument("-o", "--output-dir", help="npz 저장 폴더 (미지정 시 이미지와 같은 폴더)")

    # ── load ──
    p_load = sub.add_parser("load", help=".npz 마스킹 데이터를 이미지에 적용")
    p_load.add_argument("-n", "--npz", required=True, help=".npz 마스킹 파일 경로")
    p_load.add_argument("-t", "--target", required=True, help="대상 이미지 파일 또는 폴더")
    p_load.add_argument("-o", "--output", help="출력 폴더")
    p_load.add_argument("--backup", action="store_true", help="원본 백업 생성")

    # ── copy ──
    p_copy = sub.add_parser("copy", help="한 이미지의 마스킹을 다른 이미지들에 복사")
    p_copy.add_argument("-s", "--source", required=True, help="마스킹된 원본 이미지 경로")
    p_copy.add_argument("-t", "--target-folder", required=True, help="대상 이미지 폴더")
    p_copy.add_argument("-o", "--output", help="출력 폴더")
    p_copy.add_argument("-l", "--labels", help="라벨 폴더 경로")
    p_copy.add_argument("--start", type=int, help="시작 인덱스")
    p_copy.add_argument("--end", type=int, help="끝 인덱스")
    p_copy.add_argument("--backup", action="store_true", help="원본 백업 생성")
    p_copy.add_argument("--remove-labels", action="store_true", help="겹치는 라벨 삭제")

    # ── clean ──
    p_clean = sub.add_parser("clean", help="마스킹 영역과 겹치는 라벨 삭제")
    p_clean.add_argument("-i", "--images", required=True, help="이미지 폴더 경로")
    p_clean.add_argument("-l", "--labels", help="라벨 폴더 경로 (미지정 시 자동 탐색)")
    p_clean.add_argument("--backup", action="store_true", help="라벨 원본 백업")

    # ── info ──
    p_info = sub.add_parser("info", help="마스킹 정보 출력 (이미지 또는 .npz)")
    p_info.add_argument("target", help="이미지 또는 .npz 파일 경로")

    # ── classes ──
    sub.add_parser("classes", help="YOLO 클래스 목록 출력")

    return parser


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "auto": cmd_auto,
        "bbox": cmd_bbox,
        "polygon": cmd_polygon,
        "save": cmd_save,
        "load": cmd_load,
        "copy": cmd_copy,
        "clean": cmd_clean,
        "info": cmd_info,
        "classes": cmd_classes,
    }

    handler = dispatch.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
