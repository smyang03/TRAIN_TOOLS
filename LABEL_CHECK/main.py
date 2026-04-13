"""
Image Viewer main entry point.
YOLO label inspection tool.
Modules: utils, data_manager, label_operations, image_processor, ui_manager
"""
import sys
sys.setrecursionlimit(100000)

import tkinter as tk
from tkinter import TclError, filedialog, ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
import time
from datetime import datetime
from collections import Counter, defaultdict
import random
import gc
import copy
import threading
import queue

try:
    import psutil
except ImportError:
    pass

from data_manager import DataManager
from utils import (
    detect_file_encoding, convert_jpegimages_to_labels, convert_labels_to_jpegimages,
    get_image_path_from_label, make_path, calculate_iou, get_iou_color,
    check_boxes_overlap, parse_label_line, yolo_to_pixel,
    read_label_file_lines, write_label_file
)
import ui_manager
import image_processor as img_proc
import label_operations as label_ops


class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.rootpath = ""
        self.filename = ""
        self.current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.root.title("Image Viewer")

        # DataManager 초기화
        self.data_mgr = DataManager()

        self.selid = -1

        # 마스킹 관련 변수
        self.original_width = 0
        self.original_height = 0
        self.masking = None
        self.has_saved_masking = False
        self.maskingframewidth = 0
        self.maskingframeheight = 0
        self.ctrl_pressed = False

        # 선택 상태
        self.selected_image_labels = []
        self.selected_label_info = []
        self.checklist = []

        # 겹침 필터
        self.filter_stats = {"total": 0, "overlapping": 0, "non_overlapping": 0}

        self.shift_pressed = False
        self.caps_locked = False
        self.drag_start = None
        self.drag_rectangle = None
        self.multi_select_start = None
        self.last_drag_update = 0

        self.preview_window = None
        self.tooltip_window = None
        self.tooltip_timer = None

        self.changing_class = False
        self.strict_class_filtering = True

        self.ui_update_pending = False
        self.last_ui_update_time = time.time()
        self.memory_check_counter = 0
        self.ui_busy = False
        self._canvas_configure_after_id = None
        self._last_click_time = 0
        self._last_clicked_label = None

        # UI 구성
        ui_manager.setup_ui(self)

        self.status_bar = tk.Label(self.root, text="준비됨", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._setup_memory_monitoring()

    # ── 속성 프록시 (DataManager 연동) ──

    @property
    def image_paths(self):
        return self.data_mgr.image_paths

    @property
    def labels(self):
        return self.data_mgr.labels

    @property
    def labelsdata(self):
        return self.data_mgr.labelsdata

    @labelsdata.setter
    def labelsdata(self, value):
        self.data_mgr.labelsdata = value

    @property
    def label_cache(self):
        return self.data_mgr.label_cache

    @property
    def image_cache(self):
        return self.data_mgr.image_cache

    @property
    def overlap_cache(self):
        return self.data_mgr.overlap_cache

    @property
    def modified_labels(self):
        return self.data_mgr.modified_labels

    @property
    def current_page(self):
        return self.data_mgr.current_page

    @current_page.setter
    def current_page(self, value):
        self.data_mgr.current_page = value

    @property
    def total_pages(self):
        return self.data_mgr.total_pages

    @total_pages.setter
    def total_pages(self, value):
        self.data_mgr.total_pages = value

    @property
    def page_size(self):
        return self.data_mgr.page_size

    @page_size.setter
    def page_size(self, value):
        self.data_mgr.page_size = value

    @property
    def cache_limit(self):
        return self.data_mgr.cache_limit

    # ── UI 이벤트 핸들러 ──

    def on_class_selector_changed(self, *args):
        if not self._updating_display:
            self.update_display()

    def on_overlap_selector_changed(self, *args):
        if not self._updating_display:
            self.update_display()

    def on_class_changed(self, *args):
        pass  # trace_add 콜백 (on_class_selector_changed와 중복 방지)

    def toggle_all_selection(self):
        if self.selected_image_labels:
            self.deselect_all_images()
            self.selection_toggle_button.config(text="전체 선택")
            self.selection_state.set(False)
        else:
            self.select_all_images()
            self.selection_toggle_button.config(text="전체 해제")
            self.selection_state.set(True)

    def show_status_message(self, message, duration=3000):
        if hasattr(self, 'status_bar'):
            self.status_bar.config(text=message)
            self.root.after(duration, lambda: self.status_bar.config(text="준비됨"))

    def update_iou_value(self):
        self.iou_value_label.config(text=f"{self.iou_threshold_var.get():.2f}")
        self.data_mgr.reset_overlap_cache()
        self.update_display()

    def on_canvas_configure(self, event):
        if self._canvas_configure_after_id:
            self.root.after_cancel(self._canvas_configure_after_id)
        self._canvas_configure_after_id = self.root.after(80, self._apply_canvas_scrollregion)

    def _apply_canvas_scrollregion(self):
        self._canvas_configure_after_id = None
        if self.canvas.winfo_exists():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def style_popup(self, window, title=None, geometry=None):
        palette = getattr(ui_manager, "PALETTE", None)
        if title is not None:
            window.title(title)
        if geometry is not None:
            window.geometry(geometry)
        if palette:
            window.configure(bg=palette["panel"])
        window.transient(self.root)
        return window

    def style_popup_label(self, widget, *, size=10, bold=False, muted=False):
        palette = getattr(ui_manager, "PALETTE", None)
        if not palette:
            return
        widget.configure(
            bg=palette["panel"],
            fg=palette["muted"] if muted else palette["text"],
            font=("맑은 고딕", size, "bold" if bold else "normal"),
        )

    def style_popup_frame(self, frame):
        palette = getattr(ui_manager, "PALETTE", None)
        if palette:
            frame.configure(bg=palette["panel"])

    def style_popup_button(self, button, variant="default"):
        style_fn = getattr(ui_manager, "_style_button", None)
        if style_fn:
            style_fn(button, variant)

    def on_mousewheel(self, event):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def handle_left_click(self, event):
        if event.widget != self.root and isinstance(event.widget, tk.Label) and hasattr(event.widget, 'img_path'):
            return
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()
            self.preview_window = None

    # ── 키보드 이벤트 ──

    def on_key_press(self, event):
        if event.keysym in ('Control_L', 'Control_R'):
            self.ctrl_pressed = True
            if hasattr(self, 'ctrl_status_label'):
                self.ctrl_status_label.config(text="Ctrl: 🟩", fg="green")

    def on_key_release(self, event):
        if event.keysym in ('Control_L', 'Control_R'):
            self.ctrl_pressed = False
            if hasattr(self, 'ctrl_status_label'):
                self.ctrl_status_label.config(text="Ctrl: ⬛", fg="gray")

    def on_shift_press(self, event):
        self.shift_pressed = True

    def on_shift_release(self, event):
        self.shift_pressed = False

    def on_caps_lock_press(self, event):
        self.caps_locked = not self.caps_locked

    def on_caps_lock_release(self, event):
        pass

    # ── 데이터 로딩 ──

    def load_data(self):
        if self.data_mgr.data_loading:
            return

        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not file_path:
            return

        self.rootpath = os.path.dirname(file_path)
        self.filename = os.path.basename(file_path)
        self.current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.data_mgr.reset(file_path)

        self.selected_image_labels = []
        self.selected_label_info = []
        for widget in self.checklist:
            if widget.winfo_exists():
                widget.destroy()
        self.checklist = []
        self.filter_stats = {"total": 0, "overlapping": 0, "non_overlapping": 0}
        self.filter_info_label.config(text="")
        for widget in self.frame.winfo_children():
            widget.destroy()

        self.data_mgr.data_loading = True

        try:
            progress_window = tk.Toplevel(self.root)
            self.style_popup(progress_window, title="데이터 불러오는 중", geometry="440x170")
            pw = 440
            ph = 170
            px = int(self.root.winfo_x() + (self.root.winfo_width() - pw) / 2)
            py = int(self.root.winfo_y() + (self.root.winfo_height() - ph) / 2)
            progress_window.geometry(f"{pw}x{ph}+{px}+{py}")
            progress_window.grab_set()
            progress_window.resizable(False, False)

            container = tk.Frame(progress_window)
            self.style_popup_frame(container)
            container.pack(fill="both", expand=True, padx=18, pady=16)

            file_label = tk.Label(container, text="리스트 파일을 읽는 중...", anchor="w")
            self.style_popup_label(file_label, size=11, bold=True)
            file_label.pack(fill="x")

            progress_bar = ttk.Progressbar(container, length=390, mode="determinate")
            progress_bar.pack(fill="x", pady=(12, 8))

            status_label = tk.Label(container, text="잠시만 기다려 주세요.", anchor="w")
            self.style_popup_label(status_label, size=10, muted=True)
            status_label.pack(fill="x")

            progress_window.update()
            results_queue = queue.Queue()

            def worker():
                try:
                    image_paths, label_paths, total = self.data_mgr.load_file_list(file_path)
                    results_queue.put(("loaded", image_paths, label_paths, total))

                    def on_progress(processed, total_count, valid, invalid):
                        results_queue.put(("progress", processed, total_count, valid, invalid))

                    labelsdata, sorted_classes, valid, invalid = self.data_mgr.scan_classes(
                        label_paths, progress_callback=on_progress
                    )
                    results_queue.put((
                        "done",
                        image_paths,
                        label_paths,
                        labelsdata,
                        sorted_classes,
                        valid,
                        invalid,
                    ))
                except Exception as e:
                    results_queue.put(("error", e))

            threading.Thread(target=worker, daemon=True).start()

            def poll_results():
                if not progress_window.winfo_exists():
                    self.data_mgr.data_loading = False
                    return

                try:
                    while True:
                        message = results_queue.get_nowait()
                        msg_type = message[0]

                        if msg_type == "loaded":
                            _, image_paths, label_paths, total = message
                            self.data_mgr.image_paths = image_paths
                            self.data_mgr.labels = label_paths
                            progress_bar["maximum"] = max(total, 1)
                            file_label.config(text="클래스 정보를 분석하는 중...")
                            status_label.config(text=f"대상 파일: {total}개")
                        elif msg_type == "progress":
                            _, processed, total_count, valid, invalid = message
                            progress_bar["value"] = processed
                            status_label.config(
                                text=f"진행: {processed}/{total_count}  정상: {valid}  오류: {invalid}"
                            )
                        elif msg_type == "done":
                            (
                                _,
                                image_paths,
                                _label_paths,
                                labelsdata,
                                sorted_classes,
                                valid,
                                invalid,
                            ) = message
                            self.data_mgr.labelsdata = labelsdata
                            self.data_mgr.rebuild_class_lookup()

                            menu = self.class_dropdown["menu"]
                            menu.delete(0, "end")
                            for ci in sorted_classes:
                                ci_int = int(float(ci))
                                count = len(self.data_mgr.labelsdata[ci_int])
                                menu.add_command(
                                    label=f"Class {ci} ({count})",
                                    command=lambda idx=ci: self.class_selector.set(idx),
                                )

                            overlap_menu = self.overlap_class_dropdown["menu"]
                            overlap_menu.delete(0, "end")
                            overlap_menu.add_command(
                                label="?? ??",
                                command=lambda: self.overlap_class_selector.set("?? ??"),
                            )
                            for ci in sorted_classes:
                                ci_int = int(float(ci))
                                count = len(self.data_mgr.labelsdata[ci_int])
                                overlap_menu.add_command(
                                    label=f"Class {ci} ({count})",
                                    command=lambda idx=ci: self.overlap_class_selector.set(idx),
                                )

                            if sorted_classes:
                                self.data_mgr.current_page = 0
                                self._updating_display = True
                                self.class_selector.set(sorted_classes[0])
                                self._updating_display = False

                            ui_manager.update_pagination_controls(self)
                            self.update_display()
                            self.data_mgr.data_loading = False
                            file_label.config(text=f"불러오기 완료: 이미지 {len(image_paths)}개")
                            status_label.config(text=f"정상 파일 {valid}개, 오류 파일 {invalid}개")
                            self.root.after(900, progress_window.destroy)
                            return
                        elif msg_type == "error":
                            raise message[1]
                except queue.Empty:
                    self.root.after(40, poll_results)
                    return
                except Exception as e:
                    print(f"데이터 로드 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    self.data_mgr.data_loading = False
                    if progress_window.winfo_exists():
                        progress_window.destroy()

            poll_results()

        except Exception as e:
            print(f"데이터 로드 오류: {e}")
            import traceback
            traceback.print_exc()
            self.data_mgr.data_loading = False
            if 'progress_window' in locals() and progress_window.winfo_exists():
                progress_window.destroy()

    def update_display(self):
        """현재 선택된 조건으로 화면을 다시 렌더링합니다."""
        if hasattr(self, 'ui_busy') and self.ui_busy:
            return
        self.ui_busy = True

        try:
            self.status_bar.config(text="?? ?? ?...")
            self.root.config(cursor="watch")
            self.root.update_idletasks()

            if hasattr(self, 'show_only_similar') and self.show_only_similar and hasattr(self, 'current_filtered_labels'):
                for widget in self.frame.winfo_children():
                    widget.destroy()
                self._display_similar_labels()
                return

            view_state = self._get_standard_view_state()
            if not view_state:
                for widget in self.frame.winfo_children():
                    widget.destroy()
                return

            self._render_current_page(view_state, refresh_all=True)

        except Exception as e:
            print(f"?? ?? ??: {e}")
            import traceback
            traceback.print_exc()
            self.status_bar.config(text=f"??: {str(e)[:30]}...")
        finally:
            self.ui_busy = False

    def _get_standard_view_state(self):
        selected_class = self.class_selector.get()
        if selected_class == "Select Class":
            return None

        class_idx = int(float(selected_class))
        overlap_class = self.overlap_class_selector.get()
        overlap_filter = self.overlap_filter_var.get()

        class_images = self.data_mgr.get_class_images(class_idx)
        if not class_images:
            return None

        if overlap_class != "선택 안함":
            overlap_class_idx = int(float(overlap_class))
            class_images, self.filter_stats = self.filter_images_by_overlap(
                class_images, class_idx, overlap_class_idx)
            self._update_filter_stats()
        else:
            self.filter_stats = {"total": len(class_images), "overlapping": 0, "non_overlapping": 0}
            self.filter_info_label.config(text="")

        if not class_images:
            return {
                "class_idx": class_idx,
                "current_images": [],
                "start_idx": 0,
                "overlap_class": overlap_class,
                "overlap_filter": overlap_filter,
            }

        current_images, start_idx = self.data_mgr.get_page_data(class_images)
        return {
            "class_idx": class_idx,
            "current_images": current_images,
            "start_idx": start_idx,
            "overlap_class": overlap_class,
            "overlap_filter": overlap_filter,
        }

    def _get_visible_box_state(self, label_path, class_idx, overlap_class, overlap_filter):
        visible_box_indices = set()
        if overlap_class == "선택 안함":
            return None, visible_box_indices

        _, _, _, all_info = self.data_mgr.check_box_overlap(
            label_path, class_idx, int(overlap_class), self.iou_threshold_var.get())
        visible_box_indices = {info['box_index'] for info in all_info if info.get('has_overlap')}
        return all_info, visible_box_indices

    def _build_current_page_plan(self, view_state):
        plan = []
        current_row = 0
        current_col = 0
        box_mode = bool(self.box_image_var.get())

        for idx, label_path in enumerate(view_state['current_images']):
            img_path = get_image_path_from_label(label_path)
            if not img_path or not os.path.isfile(img_path) or not os.path.isfile(label_path):
                continue

            if box_mode:
                _, visible_box_indices = self._get_visible_box_state(
                    label_path,
                    view_state['class_idx'],
                    view_state['overlap_class'],
                    view_state['overlap_filter'],
                )
                lines = self.data_mgr.get_label_data(label_path)
                box_idx = 0
                boxes_processed = False

                for line_idx, line in enumerate(lines):
                    try:
                        parts = line.strip().split()
                        if len(parts) < 5:
                            continue
                        ci = int(float(parts[0]))
                        if ci != view_state['class_idx']:
                            continue

                        show_box = True
                        if view_state['overlap_class'] != "선택 안함":
                            has_overlap = box_idx in visible_box_indices
                            if view_state['overlap_filter'] == "겹치는 것만" and not has_overlap:
                                show_box = False
                            elif view_state['overlap_filter'] == "겹치지 않는 것만" and has_overlap:
                                show_box = False

                        if show_box:
                            plan.append({
                                "mode": "crop",
                                "label_path": label_path,
                                "row": current_row,
                                "col": current_col,
                                "class_idx": view_state['class_idx'],
                                "image_index": view_state['start_idx'] + idx,
                                "line_idx": line_idx,
                                "box_idx": box_idx,
                            })
                            boxes_processed = True
                            current_col += 1
                            if current_col >= 12:
                                current_col = 0
                                current_row += 2

                        box_idx += 1
                    except (ValueError, IndexError):
                        continue

                if boxes_processed:
                    continue

            plan.append({
                "mode": "full",
                "label_path": label_path,
                "row": current_row,
                "col": current_col,
                "image_index": view_state['start_idx'] + idx,
            })
            current_col += 1
            if current_col >= 5:
                current_col = 0
                current_row += 2

        return plan

    def _prepare_box_crop(self, img, left, top, right, bottom, size=(100, 100)):
        crop = img.crop((left, top, right, bottom))
        if not getattr(self, "keep_aspect_var", None) or not self.keep_aspect_var.get():
            return crop.resize(size)

        target_w, target_h = size
        src_w, src_h = crop.size
        if src_w <= 0 or src_h <= 0:
            return crop.resize(size)

        scale = min(target_w / src_w, target_h / src_h)
        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        resized = crop.resize((resized_w, resized_h), Image.LANCZOS)

        background_color = resized.getpixel((0, 0)) if resized_w > 0 and resized_h > 0 else (0, 0, 0)
        canvas = Image.new(resized.mode, size, background_color)
        offset_x = (target_w - resized_w) // 2
        offset_y = (target_h - resized_h) // 2
        canvas.paste(resized, (offset_x, offset_y))
        return canvas

    def _render_plan_item(self, item, display_order):
        label_path = item['label_path']
        img_path = get_image_path_from_label(label_path)
        if not img_path or not os.path.isfile(img_path) or not os.path.isfile(label_path):
            return None

        try:
            with Image.open(img_path) as img:
                if item['mode'] == 'crop':
                    lines = self.data_mgr.get_label_data(label_path)
                    current_box_idx = 0
                    for line_idx, line in enumerate(lines):
                        try:
                            parts = line.strip().split()
                            if len(parts) < 5:
                                continue
                            ci, xc, yc, w, h = map(float, parts[:5])
                            if int(ci) != item['class_idx']:
                                continue
                            if line_idx != item.get('line_idx'):
                                current_box_idx += 1
                                continue

                            if current_box_idx == item['box_idx']:
                                left = int((xc - w / 2) * img.width)
                                top = int((yc - h / 2) * img.height)
                                right = int((xc + w / 2) * img.width)
                                bottom = int((yc + h / 2) * img.height)
                                cropped = self._prepare_box_crop(img, left, top, right, bottom)
                                widget = img_proc.draw_boxes_on_image_crop(
                                    self,
                                    cropped,
                                    label_path,
                                    item['row'],
                                    item['col'],
                                    item['class_idx'],
                                    item['image_index'],
                                    item['line_idx'],
                                )
                                if widget is not None:
                                    widget.display_order = display_order
                                return widget
                            current_box_idx += 1
                        except (ValueError, IndexError):
                            continue
                    return None

                resized = img.resize((200, 200))
                widget = img_proc.draw_boxes_on_image(
                    self,
                    resized,
                    label_path,
                    item['row'],
                    item['col'],
                    item['image_index'],
                )
                if widget is not None:
                    widget.display_order = display_order
                return widget
        except Exception as e:
            print(f"Error processing image {img_path}: {e}")
            return None

    def _render_current_page(self, view_state, refresh_all=False, affected_paths=None):
        plan = self._build_current_page_plan(view_state)
        ui_manager.update_pagination_controls(self)

        for widget in self.frame.winfo_children():
            if not hasattr(widget, 'display_order'):
                widget.destroy()

        if not plan:
            for widget in self.frame.winfo_children():
                widget.destroy()
            tk.Label(self.frame, text="표시할 항목이 없습니다.",
                     font=("?? ??", 14), bg=self.frame.cget("bg"), fg="#5b6578").pack(pady=50)
            self._update_dataset_info()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            return

        if refresh_all or not affected_paths:
            for widget in self.frame.winfo_children():
                widget.destroy()
            start_order = 0
        else:
            normalized_paths = {os.path.normpath(path) for path in affected_paths}
            affected_orders = [
                item_idx for item_idx, item in enumerate(plan)
                if os.path.normpath(item['label_path']) in normalized_paths
            ]
            if not affected_orders:
                for widget in list(self.frame.winfo_children()):
                    if hasattr(widget, 'label_path') and os.path.normpath(widget.label_path) in normalized_paths:
                        widget.destroy()
                self._update_dataset_info()
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                self.root.after(100, lambda: ui_manager.refresh_bindings(self))
                self.frame.update_idletasks()
                return

            start_order = min(affected_orders)
            for widget in list(self.frame.winfo_children()):
                display_order = getattr(widget, 'display_order', 0)
                if display_order >= start_order:
                    widget.destroy()

        for item_idx, item in enumerate(plan[start_order:], start=start_order):
            self._render_plan_item(item, item_idx)

        self.root.config(cursor="")
        self._update_dataset_info()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.root.after(100, lambda: ui_manager.refresh_bindings(self))
        self.frame.update_idletasks()

    def refresh_current_page_after_changes(self, affected_paths=None):
        if hasattr(self, 'show_only_similar') and self.show_only_similar and hasattr(self, 'current_filtered_labels'):
            return

        view_state = self._get_standard_view_state()
        if not view_state:
            for widget in self.frame.winfo_children():
                widget.destroy()
            ui_manager.update_pagination_controls(self)
            self._update_dataset_info()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.root.config(cursor="")
            self.frame.update_idletasks()
            return

        self._render_current_page(view_state, refresh_all=not affected_paths, affected_paths=affected_paths)

    def _display_similar_labels(self):
        """유사 라벨 필터링 모드에서 이미지를 표시합니다."""
        current_images = self.current_filtered_labels.copy()
        total = len(current_images)
        self.data_mgr.total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total)
        page_images = current_images[start_idx:end_idx]

        self.filter_info_label.config(
            text=f"유사 라벨: 총 {total}개 중 {len(page_images)}개 표시")
        ui_manager.update_pagination_controls(self)

        current_row = 0
        current_col = 0

        for idx, label_path in enumerate(page_images):
            img_path = get_image_path_from_label(label_path)
            if not img_path or not os.path.isfile(img_path):
                continue
            try:
                with Image.open(img_path) as img:
                    if self.box_image_var.get():
                        selected_class = int(self.class_selector.get())
                        lines = self.data_mgr.get_label_data(label_path)
                        for line_idx, line in enumerate(lines):
                            try:
                                parts = line.strip().split()
                                if len(parts) < 5:
                                    continue
                                ci = int(float(parts[0]))
                                if ci != selected_class:
                                    continue
                                xc, yc, w, h = map(float, parts[1:5])
                                left = int((xc - w / 2) * img.width)
                                top = int((yc - h / 2) * img.height)
                                right = int((xc + w / 2) * img.width)
                                bottom = int((yc + h / 2) * img.height)
                                cropped = self._prepare_box_crop(img, left, top, right, bottom)
                                img_proc.draw_boxes_on_image_crop(
                                    self, cropped, label_path, current_row, current_col,
                                    selected_class, start_idx + idx, line_idx)
                                current_col += 1
                                if current_col >= 12:
                                    current_col = 0
                                    current_row += 2
                            except (ValueError, IndexError):
                                continue
                    else:
                        resized = img.resize((200, 200))
                        img_proc.draw_boxes_on_image(
                            self, resized, label_path, current_row, current_col, start_idx + idx)
                        current_col += 1
                        if current_col >= 5:
                            current_col = 0
                            current_row += 2
            except Exception as e:
                print(f"이미지 처리 오류: {e}")
                continue

        self.frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.root.config(cursor="")
        self.ui_busy = False

    # ── 라벨 작업 (모듈 위임) ──

    def delete_selected_labels(self):
        label_ops.delete_selected_labels(self)

    def change_class_labels(self):
        label_ops.change_class_labels(self)

    def convert_label_to_mask(self):
        label_ops.convert_label_to_mask(self)

    # ── 페이지네이션 ──

    def next_page(self):
        if self.data_mgr.current_page < self.data_mgr.total_pages - 1:
            self.data_mgr.current_page += 1
            self.update_display()

    def prev_page(self):
        if self.data_mgr.current_page > 0:
            self.data_mgr.current_page -= 1
            self.update_display()

    def go_to_entered_page(self):
        try:
            entered = int(self.page_entry.get())
            if 1 <= entered <= self.data_mgr.total_pages:
                self.data_mgr.current_page = entered - 1
                self.update_display()
            else:
                tk.messagebox.showwarning("페이지 오류",
                                          f"페이지 번호는 1부터 {self.data_mgr.total_pages}까지 입력 가능합니다.")
                ui_manager.update_pagination_controls(self)
        except ValueError:
            tk.messagebox.showwarning("입력 오류", "유효한 페이지 번호를 입력하세요.")
            ui_manager.update_pagination_controls(self)

    def apply_page_size(self):
        try:
            new_size = int(self.page_size_entry.get())
            if new_size > 0:
                self.data_mgr.page_size = new_size
                self.data_mgr.current_page = 0
                self.update_display()
        except ValueError:
            tk.messagebox.showwarning("입력 오류", "유효한 숫자를 입력하세요.")

    # ── 선택 관리 ──

    def select_all_images(self):
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Label) and hasattr(widget, 'label_path'):
                line_idx = getattr(widget, 'line_idx', None)
                if line_idx is not None and self._is_box_selected(widget.label_path, line_idx):
                    continue
                if line_idx is None and self._has_path_selection(widget.label_path):
                    continue

                if widget not in self.checklist:
                    self.checklist.append(widget)
                widget.config(highlightbackground="blue", highlightthickness=4)
                self._save_label_info_for_widget(widget)

        self._sync_selected_image_labels()
        self.update_selection_info()

    def deselect_all_images(self):
        for widget in self.checklist:
            if widget.winfo_exists():
                widget.config(highlightbackground="white", highlightthickness=4)
        self.selected_image_labels.clear()
        self.selected_label_info.clear()
        self.checklist.clear()
        self.update_selection_info()

    def update_selection_info(self):
        count = len(self.selected_image_labels)
        boxes = sum(len(info['boxes']) for info in self.selected_label_info)
        if boxes > 0:
            self.selection_info_label.config(text=f"Selected: {count} images, {boxes} boxes")
        else:
            self.selection_info_label.config(text=f"Selected Images: {count}")
        self._update_dataset_info()

    def _get_selected_info(self, label_path):
        return next((info for info in self.selected_label_info if info['path'] == label_path), None)

    def _has_path_selection(self, label_path):
        return self._get_selected_info(label_path) is not None

    def _is_box_selected(self, label_path, line_idx):
        info = self._get_selected_info(label_path)
        if not info:
            return False
        return any(box.get('line_idx') == line_idx for box in info['boxes'])

    def _sync_selected_image_labels(self):
        self.selected_image_labels = [info['path'] for info in self.selected_label_info]

    def _remove_selection_for_path(self, label_path):
        self.selected_label_info = [info for info in self.selected_label_info if info['path'] != label_path]
        self._sync_selected_image_labels()

    def _remove_selected_box(self, label_path, line_idx):
        info = self._get_selected_info(label_path)
        if not info:
            return
        info['boxes'] = [box for box in info['boxes'] if box.get('line_idx') != line_idx]
        if not info['boxes']:
            self.selected_label_info.remove(info)
        self._sync_selected_image_labels()

    def _save_label_info_for_widget(self, widget):
        """위젯에 연결된 라벨 정보를 selected_label_info에 저장합니다."""
        label_path = widget.label_path
        line_idx = getattr(widget, 'line_idx', None)
        selected_class = self.class_selector.get()

        existing = next((info for info in self.selected_label_info if info['path'] == label_path), None)

        if line_idx is not None:
            # 특정 박스
            lines = self.data_mgr.get_label_data(label_path)
            if 0 <= line_idx < len(lines):
                parts = lines[line_idx].strip().split()
                if len(parts) >= 5:
                    box = {
                        'class_id': int(float(parts[0])),
                        'x_center': float(parts[1]),
                        'y_center': float(parts[2]),
                        'width': float(parts[3]),
                        'height': float(parts[4]),
                        'line_idx': line_idx
                    }
                    if existing:
                        if not any(b.get('line_idx') == line_idx for b in existing['boxes']):
                            existing['boxes'].append(box)
                    else:
                        self.selected_label_info.append({'path': label_path, 'boxes': [box]})
        else:
            # 전체 이미지의 현재 클래스 박스
            if selected_class != "Select Class":
                class_idx = int(float(selected_class))
                lines = self.data_mgr.get_label_data(label_path)
                boxes = []
                for li, line in enumerate(lines):
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        try:
                            ci = int(float(parts[0]))
                            if ci == class_idx:
                                boxes.append({
                                    'class_id': ci,
                                    'x_center': float(parts[1]),
                                    'y_center': float(parts[2]),
                                    'width': float(parts[3]),
                                    'height': float(parts[4]),
                                    'line_idx': li
                                })
                        except (ValueError, IndexError):
                            continue
                if boxes:
                    if existing:
                        for box in boxes:
                            if not any(b.get('line_idx') == box['line_idx'] for b in existing['boxes']):
                                existing['boxes'].append(box)
                    else:
                        self.selected_label_info.append({'path': label_path, 'boxes': boxes})

    # ── 이미지 클릭 ──

    def on_image_click(self, label, label_path, event=None, img_path=None, line_idx=None):
        """박스 또는 이미지를 선택하거나 선택 해제합니다."""
        current_time = time.time()
        if hasattr(self, '_last_clicked_label') and self._last_clicked_label == label:
            if current_time - self._last_click_time < 0.3:
                return
        self._last_clicked_label = label
        self._last_click_time = current_time

        if line_idx is not None:
            is_selected = self._is_box_selected(label_path, line_idx)
        else:
            is_selected = self._has_path_selection(label_path)

        if is_selected:
            if label in self.checklist:
                self.checklist.remove(label)
            label.config(highlightbackground="white", highlightthickness=4)
            if line_idx is not None:
                self._remove_selected_box(label_path, line_idx)
            else:
                self._remove_selection_for_path(label_path)
        else:
            if label not in self.checklist:
                self.checklist.append(label)
            label.config(highlightbackground="blue", highlightthickness=4)
            self._save_label_info_for_widget(label)
            self._sync_selected_image_labels()

        self.update_selection_info()

    def setup_drag_select_events(self, label, label_path):
        """위젯에 클릭/드래그 이벤트를 바인딩합니다."""
        img_path = get_image_path_from_label(label_path)
        line_idx = getattr(label, 'line_idx', None)

        label.bind("<Button-1>", lambda e, l=label, lp=label_path, ip=img_path, li=line_idx:
                    self.on_image_click(l, lp, e, ip, li))

    def on_drag_start(self, event):
        self.drag_start = event

    def on_drag_motion(self, event):
        pass

    def on_drag_end(self, event):
        self.drag_start = None

    # ── 겹침 필터 ──

    def check_box_overlap(self, label_path, main_class_idx, target_class_idx):
        return self.data_mgr.check_box_overlap(
            label_path, main_class_idx, target_class_idx, self.iou_threshold_var.get())

    def filter_images_by_overlap(self, class_images, class_idx, overlap_class_idx):
        """겹침 조건에 따라 이미지를 필터링합니다."""
        overlap_filter = self.overlap_filter_var.get()
        if overlap_class_idx == "선택 안함":
            return class_images, {"total": len(class_images), "overlapping": 0, "non_overlapping": 0}

        filtered = []
        stats = {"total": len(class_images), "overlapping": 0, "non_overlapping": 0}

        for lp in class_images:
            has_ov, max_iou, _, _ = self.data_mgr.check_box_overlap(
                lp, class_idx, overlap_class_idx, self.iou_threshold_var.get())
            if has_ov:
                stats["overlapping"] += 1
            else:
                stats["non_overlapping"] += 1

            if overlap_filter == "겹치는 것만":
                if has_ov:
                    filtered.append((lp, max_iou))
            elif overlap_filter == "겹치지 않는 것만":
                if not has_ov:
                    filtered.append((lp, 0.0))
            else:
                filtered.append((lp, max_iou if has_ov else 0.0))

        if overlap_filter in ("겹치는 것만", "모두 보기"):
            filtered.sort(key=lambda x: x[1], reverse=True)

        return [f[0] for f in filtered], stats

    def _update_filter_stats(self):
        s = self.filter_stats
        if not s or s["total"] == 0:
            self.filter_info_label.config(text="")
            return
        self.filter_info_label.config(
            text=f"전체 {s['total']}개 | 겹침 {s['overlapping']}개 | 비겹침 {s['non_overlapping']}개"
        )

    def _update_dataset_info(self):
        total = len(self.data_mgr.image_paths)
        selected = len(self.selected_image_labels)
        pct = (selected / total * 100) if total > 0 else 0
        visible_items = sum(1 for widget in self.frame.winfo_children() if hasattr(widget, 'label_path'))
        modified = self.data_mgr.modified_labels
        deleted_count = len(modified.get('deleted', set()))
        changed_count = len(modified.get('class_changed', set()))
        masked_count = len(modified.get('masking_changed', set()))
        self.dataset_info_label.config(
            text=(
                f"전체:{total}  표시:{visible_items}  선택:{selected}({pct:.1f}%)  "
                f"삭제:{deleted_count}  변경:{changed_count}  마스킹:{masked_count}"
            )
        )

    # ── 기타 기능 ──

    def file_slice(self):
        """파일을 작은 조각으로 분할합니다."""
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not file_path:
            return

        dirpath = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        savepath = os.path.join(dirpath, "datalist")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            total_lines = len(lines)

            slice_dialog = tk.Toplevel(self.root)
            slice_dialog.title("파일 슬라이스 설정")
            slice_dialog.geometry("400x200")
            slice_dialog.transient(self.root)
            slice_dialog.grab_set()

            tk.Label(slice_dialog, text=f"파일: {filename}, 전체: {total_lines}줄",
                     font=("Arial", 10, "bold")).pack(pady=15)

            input_frame = tk.Frame(slice_dialog)
            input_frame.pack(pady=10)
            tk.Label(input_frame, text="슬라이스 크기:").pack(side=tk.LEFT)
            size_var = tk.StringVar(value="100")
            entry = tk.Entry(input_frame, textvariable=size_var, width=10)
            entry.pack(side=tk.LEFT, padx=5)

            result = {'confirmed': False, 'size': 100}

            def on_confirm():
                try:
                    s = int(size_var.get())
                    if s > 0:
                        result['confirmed'] = True
                        result['size'] = s
                        slice_dialog.destroy()
                except ValueError:
                    pass

            tk.Button(slice_dialog, text="확인", command=on_confirm).pack(pady=10)
            entry.bind("<Return>", lambda e: on_confirm())
            slice_dialog.wait_window()

            if not result['confirmed']:
                return

            lps = result['size']
            nf = (total_lines + lps - 1) // lps
            os.makedirs(savepath, exist_ok=True)

            remaining = list(lines)
            for i in range(nf):
                count = min(lps, len(remaining))
                if count == 0:
                    break
                sampled = random.sample(remaining, count)
                sampled_set = set(id(x) for x in sampled)
                with open(os.path.join(savepath, f'{filename}_{i}.txt'), 'w', encoding='utf-8') as out:
                    out.writelines(sampled)
                remaining = [x for x in remaining if id(x) not in sampled_set]

            self.show_status_message(f"슬라이스 완료: {nf}개 파일", duration=5000)

            import platform
            if platform.system() == "Windows":
                os.startfile(savepath)
        except Exception as e:
            print(f"파일 슬라이스 오류: {e}")

    def save_labeldata(self):
        """선택한 이미지 경로를 파일에 저장합니다."""
        if not self.selected_image_labels:
            return
        try:
            savepath = os.path.join(self.rootpath,
                                    f"{self.filename}_labelcheckdata{self.current_datetime}.txt")
            unique = set(self.selected_image_labels)
            mode = 'a' if os.path.isfile(savepath) else 'w'
            with open(savepath, mode, encoding='utf-8') as f:
                for lp in unique:
                    ip = get_image_path_from_label(lp)
                    f.write(f"{ip}\n")
            self.deselect_all_images()
            self.show_status_message(f"{len(unique)}개 파일 저장 완료: {os.path.basename(savepath)}")
        except Exception as e:
            print(f"저장 오류: {e}")

    def refresh_data(self):
        """데이터를 새로고침합니다."""
        self.data_mgr.label_cache.clear()
        self.data_mgr.image_cache.clear()
        self.data_mgr.overlap_cache.clear()
        self.update_display()
        self.show_status_message("데이터 리프레시 완료")

    def reset_view(self):
        """뷰를 초기 상태로 리셋합니다."""
        self.deselect_all_images()
        self.data_mgr.reset_overlap_cache()
        self.update_display()

    def refresh_current_view(self):
        """경량 화면 갱신 - 캐시 활용"""
        self.update_display()

    def refresh_bindings(self):
        ui_manager.refresh_bindings(self)

    # ── 전체 이미지 보기 ──

    def show_full_image(self, img_path, label_path, selected_line_idx=None):
        """전체 이미지를 새 창에 표시합니다."""
        try:
            detail_window = tk.Toplevel(self.root)
            self.style_popup(detail_window, title="전체 이미지 보기")
            ww, wh = 900, 700
            sx = (self.root.winfo_screenwidth() - ww) // 2
            sy = (self.root.winfo_screenheight() - wh) // 2
            detail_window.geometry(f"{ww}x{wh}+{sx}+{sy}")

            info_frame = tk.Frame(detail_window)
            self.style_popup_frame(info_frame)
            info_frame.pack(fill="x", padx=10, pady=5)
            tk.Label(info_frame, text=f"이미지: {os.path.basename(img_path)}", anchor="w").pack(side="left", padx=5)

            canvas_frame = tk.Frame(detail_window)
            canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
            canvas = tk.Canvas(canvas_frame)
            sb_y = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=sb_y.set)
            canvas.pack(side="left", fill="both", expand=True)
            sb_y.pack(side="right", fill="y")
            frame = tk.Frame(canvas, bg="#f4f7fb")
            canvas.create_window((0, 0), window=frame, anchor="nw")

            with Image.open(img_path) as img:
                dw = min(img.width, ww - 100)
                ratio = dw / img.width
                dh = int(img.height * ratio)
                display_img = img.copy().resize((dw, dh), Image.LANCZOS)

            # 박스 그리기
            draw = ImageDraw.Draw(display_img)
            selected_class = self.class_selector.get()
            class_idx = int(float(selected_class)) if selected_class != "Select Class" else -1

            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = ImageFont.load_default()

            lines = self.data_mgr.get_label_data(label_path)
            for i, line in enumerate(lines):
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    ci = int(float(parts[0]))
                    xc, yc, w, h = map(float, parts[1:5])
                    x1 = int((xc - w / 2) * display_img.width)
                    y1 = int((yc - h / 2) * display_img.height)
                    x2 = int((xc + w / 2) * display_img.width)
                    y2 = int((yc + h / 2) * display_img.height)

                    if selected_line_idx is not None and i == selected_line_idx:
                        color, thickness = "yellow", 3
                    elif ci == class_idx:
                        color, thickness = "red", 2
                    else:
                        color, thickness = "green", 1

                    draw.rectangle([x1, y1, x2, y2], outline=color, width=thickness)
                    text = f"Class: {ci}"
                    if selected_line_idx is not None and i == selected_line_idx:
                        text += " [SELECTED]"
                    bbox = draw.textbbox((x1, max(0, y1 - 20)), text, font=font)
                    draw.rectangle(bbox, fill="white")
                    draw.text((x1, max(0, y1 - 20)), text, fill=color, font=font)
                except (ValueError, IndexError):
                    continue

            photo = ImageTk.PhotoImage(display_img)
            img_label = tk.Label(frame, image=photo)
            img_label.image = photo
            img_label.pack(padx=10, pady=10)

            frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

            tk.Button(detail_window, text="닫기", command=detail_window.destroy, width=10).pack(pady=10)
            detail_window.bind("<Escape>", lambda e: detail_window.destroy())

        except Exception as e:
            print(f"Error showing full image: {e}")

    # ── 툴팁 ──

    def show_box_tooltip(self, label_widget, label_path, line_idx):
        if line_idx is None:
            return
        lines = self.data_mgr.get_label_data(label_path)
        if 0 <= line_idx < len(lines):
            parts = lines[line_idx].strip().split()
            if len(parts) >= 5:
                text = (f"클래스: {int(float(parts[0]))}\n"
                        f"중심: ({float(parts[1]):.4f}, {float(parts[2]):.4f})\n"
                        f"크기: {float(parts[3]):.4f} x {float(parts[4]):.4f}\n"
                        f"파일: {os.path.basename(label_path)}\n"
                        f"라인: {line_idx}")
                ui_manager.create_tooltip(self, label_widget, text)

    def create_tooltip(self, widget, text):
        ui_manager.create_tooltip(self, widget, text)

    def remove_tooltip(self):
        ui_manager.remove_tooltip(self)

    # ── 미리보기 ──

    def show_preview(self, img_path, label_path, x, y):
        """이미지 미리보기 (간략화)"""
        pass  # 필요시 구현

    # ── 유사 박스 (스텁) ──

    def add_similar_label_controls(self):
        """유사 라벨 컨트롤을 추가합니다."""
        pass  # 원본 기능 유지 필요 시 확장

    def select_similar_boxes(self):
        """유사 박스 처리"""
        self.show_status_message("유사 박스 처리 기능")

    # ── 메모리 모니터링 ──

    def _setup_memory_monitoring(self):
        self._initial_memory = self.data_mgr.get_memory_usage()
        self.root.after(60000, self._check_memory)

    def _check_memory(self):
        try:
            current = self.data_mgr.get_memory_usage()
            if current > 0 and self._initial_memory > 0:
                increase_pct = ((current - self._initial_memory) / self._initial_memory) * 100
                if increase_pct > 50 and current > 1024:
                    self.data_mgr.perform_memory_cleanup()
        except Exception:
            pass
        self.root.after(60000, self._check_memory)

    # ── 겹침 필터 UI 위임 ──

    def update_filter_stats(self):
        self._update_filter_stats()

    def update_dataset_info(self):
        self._update_dataset_info()

    def update_pagination_controls(self):
        ui_manager.update_pagination_controls(self)


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewer(root)
    root.mainloop()
