#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
masking_tool_linux.py - Linux용 마스킹 도구 (GUI)

기능:
  - 바운딩 박스(사각형) 마스킹
  - 자유형 마우스 브러시 마스킹
  - 폴리곤 마스킹
  - Label → Mask 변환
  - 마스킹 저장/불러오기 (.npz)
  - 마스킹 일괄 복사 (프레임 범위)
  - 겹치는 라벨 자동 삭제
  - 줌 인/아웃
  - 이미지 탐색 (이전/다음)

사용법:
  python3 masking_tool_linux.py
"""

import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import numpy as np
from pathlib import Path
from natsort import natsorted

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

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
MASK_COLOR = [255, 0, 255]  # magenta


# ──────────────────────────────────────────────
# 유틸리티 함수
# ──────────────────────────────────────────────
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
            class_id = int(lb[0])
            cx, cy, w, h = lb[1], lb[2], lb[3], lb[4]
            f.write(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")


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


def collect_images(folder):
    """폴더에서 이미지 파일 목록을 자연정렬하여 반환."""
    files = []
    for f in Path(folder).iterdir():
        if f.suffix.lower() in IMAGE_EXTENSIONS:
            files.append(f)
    return natsorted(files, key=lambda p: p.name)


# ──────────────────────────────────────────────
# 메인 GUI 클래스
# ──────────────────────────────────────────────
class MaskingToolLinux:
    """Linux용 마스킹 도구 GUI."""

    # ── 초기화 ──────────────────────────────
    def __init__(self, root):
        self.root = root
        self.root.title("Masking Tool (Linux)")
        self.root.geometry("1400x900")

        # 이미지 / 라벨 경로
        self.image_folder = ""
        self.label_folder = ""
        self.image_list = []
        self.current_index = 0

        # 원본 / 작업 배열
        self.original_img_array = None  # 백업 (undo 용)
        self.current_img_array = None   # 현재 작업 배열
        self.img_width = 0
        self.img_height = 0

        # 마스킹 상태
        self.is_masking_dirty = False
        self.masking = None             # (y_indices, x_indices) - 저장된 마스킹 좌표
        self.masking_frame_width = 0
        self.masking_frame_height = 0
        self.has_saved_masking = False

        # 모드 플래그
        self.mode = "none"  # none / bbox / brush / polygon / label2mask

        # bbox 마스킹
        self.bbox_start = None
        self.bbox_rect_id = None

        # 브러시 마스킹
        self.brush_size = 5

        # 폴리곤 마스킹
        self.polygon_points = []        # 캔버스 좌표
        self.polygon_line_ids = []
        self.polygon_point_ids = []
        self.is_polygon_closed = False

        # 라벨 데이터
        self.labels = []
        self.selected_label_idx = -1

        # 줌
        self.zoom_ratio = 1.0

        # 캔버스 이미지 참조 보관
        self._photo = None

        # GUI 생성
        self._build_gui()
        self._bind_keys()

    # ── GUI 구성 ────────────────────────────
    def _build_gui(self):
        # ── 상단 메뉴 바 ──
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="폴더 열기 (Open Folder)", command=self._open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="종료 (Quit)", command=self.root.quit)
        menubar.add_cascade(label="파일", menu=file_menu)
        self.root.config(menu=menubar)

        # ── 전체 레이아웃 ──
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 좌측 패널 (도구)
        left_panel = ttk.Frame(main_frame, width=260)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left_panel.pack_propagate(False)

        # 우측 캔버스
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.canvas = tk.Canvas(canvas_frame, bg="gray20", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ── 좌측 패널 위젯 ──
        # 폴더 열기
        ttk.Button(left_panel, text="폴더 열기", command=self._open_folder).pack(fill=tk.X, pady=2)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 이미지 네비게이션
        nav_frame = ttk.Frame(left_panel)
        nav_frame.pack(fill=tk.X, pady=2)
        ttk.Button(nav_frame, text="<< 이전 (W)", command=self._prev_image).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(nav_frame, text="다음 (E) >>", command=self._next_image).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.file_label = ttk.Label(left_panel, text="파일: -", wraplength=240)
        self.file_label.pack(fill=tk.X, pady=2)
        self.index_label = ttk.Label(left_panel, text="(0 / 0)")
        self.index_label.pack(fill=tk.X)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 마스킹 모드
        ttk.Label(left_panel, text="마스킹 모드", font=("", 10, "bold")).pack(anchor=tk.W)

        self.mode_var = tk.StringVar(value="none")
        modes = [
            ("선택 없음 (none)", "none"),
            ("사각형 마스킹 (M)", "bbox"),
            ("브러시 마스킹 (N)", "brush"),
            ("폴리곤 마스킹 (P)", "polygon"),
            ("Label → Mask", "label2mask"),
        ]
        for text, val in modes:
            ttk.Radiobutton(left_panel, text=text, variable=self.mode_var, value=val,
                            command=self._on_mode_change).pack(anchor=tk.W)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 브러시 크기
        brush_frame = ttk.Frame(left_panel)
        brush_frame.pack(fill=tk.X, pady=2)
        ttk.Label(brush_frame, text="브러시 크기:").pack(side=tk.LEFT)
        self.brush_var = tk.IntVar(value=5)
        ttk.Spinbox(brush_frame, from_=1, to=50, textvariable=self.brush_var, width=5).pack(side=tk.LEFT, padx=4)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 줌
        zoom_frame = ttk.Frame(left_panel)
        zoom_frame.pack(fill=tk.X, pady=2)
        ttk.Label(zoom_frame, text="줌:").pack(side=tk.LEFT)
        ttk.Button(zoom_frame, text="-", width=3, command=self._zoom_out).pack(side=tk.LEFT, padx=2)
        self.zoom_label = ttk.Label(zoom_frame, text="100%")
        self.zoom_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(zoom_frame, text="+", width=3, command=self._zoom_in).pack(side=tk.LEFT, padx=2)
        ttk.Button(zoom_frame, text="Fit", width=4, command=self._zoom_fit).pack(side=tk.LEFT, padx=2)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 마스킹 저장 / 불러오기
        ttk.Label(left_panel, text="마스킹 데이터", font=("", 10, "bold")).pack(anchor=tk.W)
        ttk.Button(left_panel, text="마스킹 저장 (S)", command=self._save_masking).pack(fill=tk.X, pady=2)
        ttk.Button(left_panel, text="마스킹 불러오기 (L)", command=self._load_masking).pack(fill=tk.X, pady=2)
        ttk.Button(left_panel, text="마스킹 초기화 (Ctrl+Z)", command=self._undo_masking).pack(fill=tk.X, pady=2)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 일괄 복사
        ttk.Label(left_panel, text="마스킹 일괄 복사", font=("", 10, "bold")).pack(anchor=tk.W)
        range_frame = ttk.Frame(left_panel)
        range_frame.pack(fill=tk.X, pady=2)
        ttk.Label(range_frame, text="시작:").pack(side=tk.LEFT)
        self.copy_start_var = tk.IntVar(value=0)
        ttk.Spinbox(range_frame, from_=0, to=99999, textvariable=self.copy_start_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(range_frame, text="끝:").pack(side=tk.LEFT)
        self.copy_end_var = tk.IntVar(value=0)
        ttk.Spinbox(range_frame, from_=0, to=99999, textvariable=self.copy_end_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_panel, text="범위에 마스킹 복사", command=self._copy_masking_to_range).pack(fill=tk.X, pady=2)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 옵션 체크박스
        self.remove_overlap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(left_panel, text="마스킹 시 겹치는 라벨 삭제",
                        variable=self.remove_overlap_var).pack(anchor=tk.W)

        self.show_labels_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left_panel, text="라벨 표시",
                        variable=self.show_labels_var,
                        command=self._refresh_display).pack(anchor=tk.W)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # 라벨 목록
        ttk.Label(left_panel, text="라벨 목록", font=("", 10, "bold")).pack(anchor=tk.W)
        self.label_listbox = tk.Listbox(left_panel, height=8, font=("monospace", 9))
        self.label_listbox.pack(fill=tk.BOTH, expand=True, pady=2)
        self.label_listbox.bind("<<ListboxSelect>>", self._on_label_select)

        # 하단 상태바
        self.status_var = tk.StringVar(value="폴더를 열어주세요.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ── 키 바인딩 ───────────────────────────
    def _bind_keys(self):
        self.root.bind("<Key-w>", lambda e: self._prev_image())
        self.root.bind("<Key-e>", lambda e: self._next_image())
        self.root.bind("<Key-m>", lambda e: self._set_mode("bbox"))
        self.root.bind("<Key-n>", lambda e: self._set_mode("brush"))
        self.root.bind("<Key-p>", lambda e: self._set_mode("polygon"))
        self.root.bind("<Key-s>", lambda e: self._save_masking())
        self.root.bind("<Key-l>", lambda e: self._load_masking())
        self.root.bind("<Key-h>", lambda e: self._close_polygon())
        self.root.bind("<Control-z>", lambda e: self._undo_masking())
        self.root.bind("<Key-plus>", lambda e: self._zoom_in())
        self.root.bind("<Key-equal>", lambda e: self._zoom_in())
        self.root.bind("<Key-minus>", lambda e: self._zoom_out())
        self.root.bind("<Escape>", lambda e: self._cancel_current())

        # 캔버스 마우스 이벤트
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        # Linux 스크롤 (Button-4/5)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_in())
        self.canvas.bind("<Button-5>", lambda e: self._zoom_out())

    # ── 폴더 열기 ───────────────────────────
    def _open_folder(self):
        folder = filedialog.askdirectory(title="이미지 폴더 선택")
        if not folder:
            return

        # 이미지 폴더
        self.image_folder = folder
        self.image_list = collect_images(folder)

        if not self.image_list:
            messagebox.showwarning("경고", "이미지 파일을 찾을 수 없습니다.")
            return

        # 라벨 폴더 자동 탐지
        parent = Path(folder).parent
        possible_labels = [
            Path(folder).parent / "labels",
            Path(folder) / "labels",
            Path(folder).parent / "label",
        ]
        self.label_folder = ""
        for p in possible_labels:
            if p.is_dir():
                self.label_folder = str(p)
                break

        if not self.label_folder:
            # 같은 폴더에 txt 파일이 있으면 그곳을 라벨 폴더로 사용
            txt_files = list(Path(folder).glob("*.txt"))
            if txt_files:
                self.label_folder = folder
            else:
                resp = filedialog.askdirectory(title="라벨 폴더 선택 (없으면 취소)")
                self.label_folder = resp if resp else folder

        self.current_index = 0
        self._load_current_image()
        self.status_var.set(f"폴더 열림: {folder}  |  라벨: {self.label_folder}  |  이미지 {len(self.image_list)}개")

    # ── 이미지 로드 ─────────────────────────
    def _load_current_image(self):
        if not self.image_list:
            return

        # 이전 이미지 변경사항 저장
        self._auto_save_dirty()

        img_path = self.image_list[self.current_index]

        try:
            img = Image.open(str(img_path)).convert("RGB")
        except Exception as ex:
            messagebox.showerror("오류", f"이미지를 열 수 없습니다:\n{ex}")
            return

        self.original_img_array = np.array(img).copy()
        self.current_img_array = np.array(img).copy()
        self.img_height, self.img_width = self.current_img_array.shape[:2]
        self.is_masking_dirty = False

        # 라벨 로드
        label_path = os.path.join(self.label_folder, img_path.stem + ".txt")
        self.labels = load_yolo_labels(label_path)
        self.selected_label_idx = -1

        # 폴리곤 초기화
        self._reset_polygon()

        # 줌 fit
        self._zoom_fit()

        # UI 갱신
        self.file_label.config(text=f"파일: {img_path.name}")
        self.index_label.config(text=f"({self.current_index + 1} / {len(self.image_list)})")
        self._update_label_listbox()

    # ── 디스플레이 갱신 ─────────────────────
    def _refresh_display(self):
        if self.current_img_array is None:
            return

        # 줌 적용
        display_w = max(1, int(self.img_width * self.zoom_ratio))
        display_h = max(1, int(self.img_height * self.zoom_ratio))

        pil_img = Image.fromarray(self.current_img_array)
        pil_img = pil_img.resize((display_w, display_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(pil_img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)
        self.canvas.config(scrollregion=(0, 0, display_w, display_h))

        # 라벨 표시
        if self.show_labels_var.get():
            self._draw_labels()

        # 폴리곤 미리보기
        if self.polygon_points and self.mode == "polygon":
            self._draw_polygon_preview()

    def _draw_labels(self):
        """캔버스에 YOLO 라벨 바운딩 박스 표시."""
        for i, lb in enumerate(self.labels):
            class_id = int(lb[0])
            x1, y1, x2, y2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4],
                                           self.img_width, self.img_height)
            # 줌 적용
            vx1 = int(x1 * self.zoom_ratio)
            vy1 = int(y1 * self.zoom_ratio)
            vx2 = int(x2 * self.zoom_ratio)
            vy2 = int(y2 * self.zoom_ratio)

            color = "lime" if i == self.selected_label_idx else "cyan"
            self.canvas.create_rectangle(vx1, vy1, vx2, vy2, outline=color, width=2)
            cls_text = CLASS_NAMES[class_id] if class_id < len(CLASS_NAMES) else str(class_id)
            self.canvas.create_text(vx1 + 2, vy1 - 2, anchor=tk.SW,
                                    text=f"{class_id}:{cls_text}", fill=color,
                                    font=("monospace", 9, "bold"))

    def _draw_polygon_preview(self):
        """폴리곤 점/선 미리보기."""
        pts = self.polygon_points
        for i, (px, py) in enumerate(pts):
            r = 4
            self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                    fill="yellow", outline="red")
            if i > 0:
                self.canvas.create_line(pts[i - 1][0], pts[i - 1][1], px, py,
                                        fill="yellow", width=2)
        if self.is_polygon_closed and len(pts) >= 3:
            self.canvas.create_line(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1],
                                    fill="yellow", width=2, dash=(4, 4))

    def _update_label_listbox(self):
        self.label_listbox.delete(0, tk.END)
        for i, lb in enumerate(self.labels):
            class_id = int(lb[0])
            cls_text = CLASS_NAMES[class_id] if class_id < len(CLASS_NAMES) else str(class_id)
            self.label_listbox.insert(tk.END, f"[{i}] {class_id}:{cls_text}  ({lb[1]:.3f},{lb[2]:.3f},{lb[3]:.3f},{lb[4]:.3f})")

    # ── 좌표 변환 ───────────────────────────
    def _view_to_orig(self, vx, vy):
        """캔버스(뷰) 좌표 → 원본 이미지 좌표."""
        ox = int(vx / self.zoom_ratio)
        oy = int(vy / self.zoom_ratio)
        ox = max(0, min(ox, self.img_width - 1))
        oy = max(0, min(oy, self.img_height - 1))
        return ox, oy

    def _orig_to_view(self, ox, oy):
        """원본 이미지 좌표 → 캔버스(뷰) 좌표."""
        return int(ox * self.zoom_ratio), int(oy * self.zoom_ratio)

    # ── 모드 변경 ───────────────────────────
    def _set_mode(self, mode_name):
        self._cancel_current()
        self.mode = mode_name
        self.mode_var.set(mode_name)
        self.status_var.set(f"모드: {mode_name}")

    def _on_mode_change(self):
        self._cancel_current()
        self.mode = self.mode_var.get()
        self.status_var.set(f"모드: {self.mode}")

    def _cancel_current(self):
        """현재 진행 중인 작업 취소."""
        if self.bbox_rect_id:
            self.canvas.delete(self.bbox_rect_id)
            self.bbox_rect_id = None
        self.bbox_start = None
        if self.mode != "polygon":
            self._reset_polygon()
        self._refresh_display()

    # ── 캔버스 마우스 이벤트 ────────────────
    def _on_canvas_press(self, event):
        if self.current_img_array is None:
            return

        x, y = event.x, event.y

        if self.mode == "bbox":
            self.bbox_start = (x, y)

        elif self.mode == "brush":
            self._apply_brush(x, y)

        elif self.mode == "polygon":
            self._add_polygon_point(x, y)

        elif self.mode == "label2mask":
            self._label_to_mask_at(x, y)

    def _on_canvas_drag(self, event):
        if self.current_img_array is None:
            return

        x, y = event.x, event.y

        if self.mode == "bbox" and self.bbox_start:
            if self.bbox_rect_id:
                self.canvas.delete(self.bbox_rect_id)
            sx, sy = self.bbox_start
            self.bbox_rect_id = self.canvas.create_rectangle(
                sx, sy, x, y, outline="magenta", width=2, dash=(4, 4))

        elif self.mode == "brush":
            self._apply_brush(x, y)

    def _on_canvas_release(self, event):
        if self.current_img_array is None:
            return

        x, y = event.x, event.y

        if self.mode == "bbox" and self.bbox_start:
            sx, sy = self.bbox_start
            self._apply_bbox_masking(sx, sy, x, y)
            if self.bbox_rect_id:
                self.canvas.delete(self.bbox_rect_id)
                self.bbox_rect_id = None
            self.bbox_start = None

    def _on_mouse_wheel(self, event):
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    # ── 사각형 마스킹 ──────────────────────
    def _apply_bbox_masking(self, vx1, vy1, vx2, vy2):
        """뷰 좌표로 받은 사각형 영역에 마스킹 적용."""
        ox1, oy1 = self._view_to_orig(min(vx1, vx2), min(vy1, vy2))
        ox2, oy2 = self._view_to_orig(max(vx1, vx2), max(vy1, vy2))

        if ox2 <= ox1 or oy2 <= oy1:
            return

        self.current_img_array[oy1:oy2, ox1:ox2] = MASK_COLOR
        self.is_masking_dirty = True

        if self.remove_overlap_var.get():
            self._remove_overlapping_labels((ox1, oy1, ox2, oy2))

        self._refresh_display()
        self.status_var.set(f"사각형 마스킹 적용: ({ox1},{oy1})-({ox2},{oy2})")

    # ── 브러시 마스킹 ──────────────────────
    def _apply_brush(self, vx, vy):
        """브러시로 점 마스킹."""
        ox, oy = self._view_to_orig(vx, vy)
        bs = max(1, int(self.brush_var.get() / self.zoom_ratio))
        y1 = max(0, oy - bs)
        y2 = min(self.img_height, oy + bs)
        x1 = max(0, ox - bs)
        x2 = min(self.img_width, ox + bs)
        self.current_img_array[y1:y2, x1:x2] = MASK_COLOR
        self.is_masking_dirty = True
        self._refresh_display()

    # ── 폴리곤 마스킹 ─────────────────────
    def _add_polygon_point(self, vx, vy):
        """폴리곤에 점 추가."""
        if self.is_polygon_closed:
            # 닫힌 상태에서 클릭하면 적용 후 초기화
            self._apply_polygon_masking()
            return

        self.polygon_points.append((vx, vy))
        self._refresh_display()
        self.status_var.set(f"폴리곤 점 {len(self.polygon_points)}개 (H키로 닫기)")

    def _close_polygon(self):
        """폴리곤 닫기."""
        if len(self.polygon_points) < 3:
            self.status_var.set("폴리곤을 닫으려면 최소 3개의 점이 필요합니다.")
            return
        self.is_polygon_closed = True
        self._refresh_display()
        self.status_var.set("폴리곤이 닫혔습니다. 클릭하면 마스킹이 적용됩니다.")

    def _apply_polygon_masking(self):
        """폴리곤 영역에 마스킹 적용."""
        if len(self.polygon_points) < 3:
            return

        if not HAS_CV2:
            messagebox.showwarning("경고", "폴리곤 마스킹에는 OpenCV(cv2)가 필요합니다.\npip install opencv-python")
            return

        # 캔버스 좌표 → 원본 좌표
        orig_pts = []
        for vx, vy in self.polygon_points:
            ox, oy = self._view_to_orig(vx, vy)
            orig_pts.append([ox, oy])

        mask = np.zeros((self.img_height, self.img_width), dtype=np.uint8)
        cv_pts = np.array([orig_pts], dtype=np.int32)
        cv2.fillPoly(mask, cv_pts, 255)

        self.current_img_array[mask == 255] = MASK_COLOR
        self.is_masking_dirty = True

        if self.remove_overlap_var.get():
            # 폴리곤 바운딩 박스로 근사하여 겹치는 라벨 삭제
            xs = [p[0] for p in orig_pts]
            ys = [p[1] for p in orig_pts]
            self._remove_overlapping_labels((min(xs), min(ys), max(xs), max(ys)))

        self._reset_polygon()
        self._refresh_display()
        self.status_var.set("폴리곤 마스킹 적용 완료")

    def _reset_polygon(self):
        self.polygon_points = []
        self.is_polygon_closed = False

    # ── Label → Mask ───────────────────────
    def _label_to_mask_at(self, vx, vy):
        """클릭 위치의 라벨을 마스킹으로 변환."""
        ox, oy = self._view_to_orig(vx, vy)
        hit_idx = -1

        for i, lb in enumerate(self.labels):
            x1, y1, x2, y2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4],
                                           self.img_width, self.img_height)
            if x1 <= ox <= x2 and y1 <= oy <= y2:
                hit_idx = i
                break  # 첫 번째 히트 사용

        if hit_idx < 0:
            self.status_var.set("해당 위치에 라벨이 없습니다.")
            return

        lb = self.labels[hit_idx]
        x1, y1, x2, y2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4],
                                       self.img_width, self.img_height)
        self.current_img_array[y1:y2, x1:x2] = MASK_COLOR
        self.is_masking_dirty = True

        cls_text = CLASS_NAMES[int(lb[0])] if int(lb[0]) < len(CLASS_NAMES) else str(int(lb[0]))

        # 라벨 삭제
        del self.labels[hit_idx]
        self._save_current_labels()
        self._update_label_listbox()
        self._refresh_display()
        self.status_var.set(f"라벨 [{hit_idx}] {cls_text} → 마스킹 변환 완료")

    # ── 겹치는 라벨 삭제 ───────────────────
    def _remove_overlapping_labels(self, mask_rect):
        """mask_rect (x1,y1,x2,y2) 원본좌표와 겹치는 라벨 삭제."""
        mx1, my1, mx2, my2 = mask_rect
        to_delete = []

        for i, lb in enumerate(self.labels):
            x1, y1, x2, y2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4],
                                           self.img_width, self.img_height)
            # 겹침 확인
            if not (x2 < mx1 or x1 > mx2 or y2 < my1 or y1 > my2):
                to_delete.append(i)

        if to_delete:
            for idx in reversed(to_delete):
                del self.labels[idx]
            self._save_current_labels()
            self._update_label_listbox()
            self.status_var.set(f"겹치는 라벨 {len(to_delete)}개 삭제됨")

    # ── 라벨 목록 선택 ─────────────────────
    def _on_label_select(self, event):
        sel = self.label_listbox.curselection()
        if sel:
            self.selected_label_idx = sel[0]
        else:
            self.selected_label_idx = -1
        self._refresh_display()

    # ── 마스킹 저장 (.npz) ─────────────────
    def _save_masking(self):
        if self.current_img_array is None:
            self.status_var.set("저장할 이미지가 없습니다.")
            return

        # 마젠타 픽셀 좌표 추출
        arr = self.current_img_array
        mask_pixels = np.where(
            (arr[:, :, 0] == 255) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 255)
        )

        if mask_pixels[0].size == 0:
            self.status_var.set("마스킹된 영역이 없습니다.")
            return

        self.masking = (mask_pixels[0], mask_pixels[1])
        self.masking_frame_width = self.img_width
        self.masking_frame_height = self.img_height
        self.has_saved_masking = True

        # .npz 파일로 저장
        img_path = self.image_list[self.current_index]
        mask_file = os.path.join(self.label_folder, f"{img_path.stem}_mask.npz")
        np.savez_compressed(
            mask_file,
            masking_y=mask_pixels[0],
            masking_x=mask_pixels[1],
            width=self.img_width,
            height=self.img_height,
        )

        # 이미지 파일에도 반영
        self._save_current_image()
        self.is_masking_dirty = False

        self.status_var.set(f"마스킹 저장 완료: {mask_file}")

    # ── 마스킹 불러오기 (.npz) ──────────────
    def _load_masking(self):
        if self.current_img_array is None:
            self.status_var.set("이미지가 로드되지 않았습니다.")
            return

        img_path = self.image_list[self.current_index]
        mask_file = os.path.join(self.label_folder, f"{img_path.stem}_mask.npz")

        if not os.path.exists(mask_file):
            self.status_var.set(f"마스킹 파일을 찾을 수 없습니다: {mask_file}")
            return

        data = np.load(mask_file)
        saved_w = int(data["width"])
        saved_h = int(data["height"])

        if saved_w != self.img_width or saved_h != self.img_height:
            messagebox.showwarning(
                "경고",
                f"마스킹 크기 불일치!\n"
                f"저장됨: {saved_w}x{saved_h}\n"
                f"현재: {self.img_width}x{self.img_height}",
            )
            return

        self.masking = (data["masking_y"], data["masking_x"])
        self.masking_frame_width = saved_w
        self.masking_frame_height = saved_h
        self.has_saved_masking = True

        # 원본에서 다시 로드 후 마스킹 적용
        img = Image.open(str(img_path)).convert("RGB")
        self.current_img_array = np.array(img)
        self.current_img_array[self.masking[0], self.masking[1]] = MASK_COLOR
        self.is_masking_dirty = True

        if self.remove_overlap_var.get():
            # 마스킹 영역 바운딩 박스
            y_min, y_max = int(self.masking[0].min()), int(self.masking[0].max())
            x_min, x_max = int(self.masking[1].min()), int(self.masking[1].max())
            self._remove_overlapping_labels((x_min, y_min, x_max, y_max))

        self._refresh_display()
        self.status_var.set(f"마스킹 불러오기 완료: {mask_file}")

    # ── 마스킹 초기화 (Undo) ───────────────
    def _undo_masking(self):
        if self.original_img_array is None:
            return
        self.current_img_array = self.original_img_array.copy()
        self.is_masking_dirty = False
        self._refresh_display()
        self.status_var.set("마스킹 초기화 (원본 복원)")

    # ── 마스킹 일괄 복사 ──────────────────
    def _copy_masking_to_range(self):
        if not self.has_saved_masking or self.masking is None:
            messagebox.showinfo("안내", "먼저 마스킹을 저장(S)해 주세요.")
            return

        start = self.copy_start_var.get()
        end = self.copy_end_var.get()
        if start > end or end >= len(self.image_list):
            messagebox.showwarning("경고", f"유효한 범위를 입력하세요. (0 ~ {len(self.image_list) - 1})")
            return

        count = 0
        errors = []

        # 진행 표시 창
        progress_win = tk.Toplevel(self.root)
        progress_win.title("마스킹 복사 진행 중...")
        progress_win.geometry("400x100")
        progress_win.transient(self.root)
        progress_label = ttk.Label(progress_win, text="준비 중...")
        progress_label.pack(pady=10)
        progress_bar = ttk.Progressbar(progress_win, maximum=end - start + 1)
        progress_bar.pack(fill=tk.X, padx=20)

        for idx in range(start, end + 1):
            img_path = self.image_list[idx]
            progress_label.config(text=f"처리 중: {img_path.name} ({idx - start + 1}/{end - start + 1})")
            progress_bar["value"] = idx - start + 1
            progress_win.update()

            try:
                img = Image.open(str(img_path)).convert("RGB")
                arr = np.array(img)
                h, w = arr.shape[:2]

                if w != self.masking_frame_width or h != self.masking_frame_height:
                    errors.append(f"{img_path.name}: 크기 불일치 ({w}x{h})")
                    continue

                # 백업
                backup_dir = os.path.join(str(img_path.parent.parent), "original_backup", "JPEGImages")
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = os.path.join(backup_dir, img_path.name)
                if not os.path.exists(backup_path):
                    shutil.copy2(str(img_path), backup_path)

                # 마스킹 적용
                arr[self.masking[0], self.masking[1]] = MASK_COLOR

                # 저장
                out_img = Image.fromarray(arr)
                ext = img_path.suffix.lower()
                if ext in (".jpg", ".jpeg"):
                    out_img.save(str(img_path), quality=95, optimize=True)
                else:
                    out_img.save(str(img_path))

                # .npz 저장
                mask_npz = os.path.join(self.label_folder, f"{img_path.stem}_mask.npz")
                np.savez_compressed(
                    mask_npz,
                    masking_y=self.masking[0],
                    masking_x=self.masking[1],
                    width=self.masking_frame_width,
                    height=self.masking_frame_height,
                )

                # 겹치는 라벨 삭제
                if self.remove_overlap_var.get():
                    label_path = os.path.join(self.label_folder, f"{img_path.stem}.txt")
                    if os.path.exists(label_path):
                        labels = load_yolo_labels(label_path)
                        y_min, y_max = int(self.masking[0].min()), int(self.masking[0].max())
                        x_min, x_max = int(self.masking[1].min()), int(self.masking[1].max())
                        filtered = []
                        for lb in labels:
                            bx1, by1, bx2, by2 = yolo_to_abs(lb[1], lb[2], lb[3], lb[4], w, h)
                            if bx2 < x_min or bx1 > x_max or by2 < y_min or by1 > y_max:
                                filtered.append(lb)
                        save_yolo_labels(label_path, filtered)

                count += 1

            except Exception as ex:
                errors.append(f"{img_path.name}: {ex}")

        progress_win.destroy()

        msg = f"마스킹 복사 완료: {count}개 이미지 처리됨"
        if errors:
            msg += f"\n\n오류 {len(errors)}건:\n" + "\n".join(errors[:10])
        messagebox.showinfo("결과", msg)

        # 현재 이미지 다시 로드
        self._load_current_image()

    # ── 이미지 / 라벨 저장 ─────────────────
    def _save_current_image(self):
        """현재 이미지 배열을 파일로 저장."""
        if self.current_img_array is None:
            return
        img_path = self.image_list[self.current_index]

        # 백업
        backup_dir = os.path.join(str(img_path.parent.parent), "original_backup", "JPEGImages")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, img_path.name)
        if not os.path.exists(backup_path):
            shutil.copy2(str(img_path), backup_path)

        out_img = Image.fromarray(self.current_img_array)
        ext = img_path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            out_img.save(str(img_path), quality=95, optimize=True)
        else:
            out_img.save(str(img_path))

    def _save_current_labels(self):
        """현재 라벨을 파일로 저장."""
        if not self.image_list:
            return
        img_path = self.image_list[self.current_index]
        label_path = os.path.join(self.label_folder, f"{img_path.stem}.txt")

        # 라벨 백업
        backup_dir = os.path.join(str(img_path.parent.parent), "original_backup", "labels")
        os.makedirs(backup_dir, exist_ok=True)
        backup_label = os.path.join(backup_dir, f"{img_path.stem}.txt")
        if os.path.exists(label_path) and not os.path.exists(backup_label):
            shutil.copy2(label_path, backup_label)

        save_yolo_labels(label_path, self.labels)

    def _auto_save_dirty(self):
        """변경사항이 있으면 자동 저장."""
        if self.is_masking_dirty and self.current_img_array is not None:
            self._save_current_image()
            self.is_masking_dirty = False

    # ── 이미지 네비게이션 ──────────────────
    def _prev_image(self):
        if not self.image_list:
            return
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def _next_image(self):
        if not self.image_list:
            return
        if self.current_index < len(self.image_list) - 1:
            self.current_index += 1
            self._load_current_image()

    # ── 줌 ──────────────────────────────────
    def _zoom_in(self):
        self.zoom_ratio = min(5.0, self.zoom_ratio * 1.2)
        self.zoom_label.config(text=f"{int(self.zoom_ratio * 100)}%")
        self._refresh_display()

    def _zoom_out(self):
        self.zoom_ratio = max(0.1, self.zoom_ratio / 1.2)
        self.zoom_label.config(text=f"{int(self.zoom_ratio * 100)}%")
        self._refresh_display()

    def _zoom_fit(self):
        """캔버스에 맞게 줌 조정."""
        self.root.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 1 or ch <= 1 or self.img_width <= 0 or self.img_height <= 0:
            self.zoom_ratio = 1.0
        else:
            ratio_w = cw / self.img_width
            ratio_h = ch / self.img_height
            self.zoom_ratio = min(ratio_w, ratio_h, 3.0)

        self.zoom_label.config(text=f"{int(self.zoom_ratio * 100)}%")
        self._refresh_display()


# ──────────────────────────────────────────────
# 엔트리 포인트
# ──────────────────────────────────────────────
def main():
    root = tk.Tk()
    app = MaskingToolLinux(root)

    # 종료 시 저장
    def on_closing():
        app._auto_save_dirty()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
