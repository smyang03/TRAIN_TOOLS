"""
Label editing operations for delete, class change, and label-to-mask.
The UI avoids full reloads and only refreshes affected items on the
current page after file updates.
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image

from utils import convert_labels_to_jpegimages, make_path, read_label_file_lines, write_label_file


PROGRESS_FILE_THRESHOLD = 20
PROGRESS_BOX_THRESHOLD = 50


def _should_show_progress(file_count, box_count):
    return file_count >= PROGRESS_FILE_THRESHOLD or box_count >= PROGRESS_BOX_THRESHOLD


def _require_box_mode_for_label_edit(viewer):
    if viewer.box_image_var.get():
        return True
    tk.messagebox.showwarning(
        "박스 모드 필요",
        "개별 라벨 삭제, 변경, 마스킹은 Box Images 모드에서만 사용할 수 있습니다.",
    )
    return False


def delete_selected_labels(viewer):
    """Delete only the selected bounding boxes."""
    if not _require_box_mode_for_label_edit(viewer):
        return
    if not viewer.selected_image_labels:
        tk.messagebox.showwarning("선택 오류", "삭제할 이미지를 먼저 선택하세요.")
        return
    if not viewer.selected_label_info:
        tk.messagebox.showwarning("선택 오류", "삭제할 라벨을 먼저 선택하세요.")
        return

    current_class = viewer.class_selector.get()
    current_page = viewer.data_mgr.current_page
    total_boxes = sum(len(info["boxes"]) for info in viewer.selected_label_info)
    show_progress = _should_show_progress(len(viewer.selected_label_info), total_boxes)

    progress_window = None
    progress_label = None
    progress_bar = None
    status_label = None
    result_label = None

    if show_progress:
        progress_window = tk.Toplevel(viewer.root)
        progress_window.title("라벨 삭제 중")
        progress_window.geometry("400x200")
        progress_window.transient(viewer.root)
        progress_window.grab_set()

        progress_label = tk.Label(
            progress_window,
            text="선택한 바운딩 박스 삭제 중...",
            font=("Arial", 10, "bold"),
        )
        progress_label.pack(pady=(15, 5))
        tk.Label(progress_window, text=f"총 {total_boxes}개의 바운딩 박스를 삭제합니다.").pack(pady=5)

        progress_bar = ttk.Progressbar(progress_window, length=350)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(viewer.selected_label_info)

        status_label = tk.Label(progress_window, text="0/0 처리 완료")
        status_label.pack(pady=5)
        result_label = tk.Label(progress_window, text="")
        result_label.pack(pady=5)
        progress_window.update_idletasks()
    else:
        viewer.root.config(cursor="watch")
        viewer.root.update_idletasks()

    deleted_file_count = 0
    deleted_box_count = 0
    error_count = 0
    affected_label_paths = set()

    for i, label_info in enumerate(viewer.selected_label_info):
        try:
            label_path = label_info["path"]
            if show_progress:
                progress_bar["value"] = i + 1
                status_label.config(text=f"{i + 1}/{len(viewer.selected_label_info)} 처리 완료")
                result_label.config(text=f"삭제 파일: {deleted_file_count}, 오류: {error_count}")

            if not os.path.isfile(label_path):
                error_count += 1
                continue

            lines = read_label_file_lines(label_path)
            lines_with_newline = [line + "\n" for line in lines]
            indices_to_delete = {
                box["line_idx"]
                for box in label_info["boxes"]
                if "line_idx" in box and 0 <= box["line_idx"] < len(lines_with_newline)
            }
            if not indices_to_delete:
                continue

            new_lines = [
                line for idx, line in enumerate(lines_with_newline)
                if idx not in indices_to_delete
            ]
            write_label_file(label_path, new_lines)

            deleted_file_count += 1
            deleted_box_count += len(indices_to_delete)
            affected_label_paths.add(label_path)

            for idx in indices_to_delete:
                viewer.data_mgr.modified_labels["deleted"].add((os.path.normpath(label_path), idx))

        except Exception as e:
            error_count += 1
            print(f"라벨 삭제 중 오류 발생: {e}")

        if show_progress and (i % 25 == 0 or i == len(viewer.selected_label_info) - 1):
            progress_window.update_idletasks()

    for label_path in affected_label_paths:
        viewer.data_mgr.invalidate_label_cache(label_path)
    if affected_label_paths:
        viewer.data_mgr.refresh_label_data_cache(specific_paths=list(affected_label_paths))

    if show_progress:
        progress_label.config(text="바운딩 박스 삭제 완료")
        result_label.config(
            text=f"{deleted_file_count}개 파일에서 {deleted_box_count}개 박스 삭제 완료, 오류: {error_count}개"
        )

    viewer.show_status_message(f"{deleted_box_count}개 바운딩 박스 삭제 완료", duration=3000)
    viewer.deselect_all_images()
    _partial_refresh(viewer, affected_label_paths, current_class, current_page)

    viewer.root.config(cursor="")
    if progress_window and progress_window.winfo_exists():
        progress_window.destroy()


def change_class_labels(viewer):
    """Change only the class id of selected bounding boxes."""
    if not _require_box_mode_for_label_edit(viewer):
        return
    if not viewer.selected_image_labels:
        tk.messagebox.showwarning("선택 오류", "변경할 이미지를 먼저 선택하세요.")
        return
    if not viewer.selected_label_info:
        tk.messagebox.showwarning("선택 오류", "변경할 라벨을 먼저 선택하세요.")
        return

    viewer.changing_class = True
    total_boxes = sum(len(info["boxes"]) for info in viewer.selected_label_info)

    selected_class_ids = []
    for label_info in viewer.selected_label_info:
        for box in label_info["boxes"]:
            if "class_id" in box:
                selected_class_ids.append(box["class_id"])
    if not selected_class_ids:
        selected_class_ids = [0]

    from collections import Counter

    most_common_class = Counter(selected_class_ids).most_common(1)[0][0]

    change_dialog = tk.Toplevel(viewer.root)
    change_dialog.title("라벨 클래스 변경")
    change_dialog.geometry("400x300")
    change_dialog.transient(viewer.root)
    change_dialog.grab_set()

    target_class = tk.StringVar(value=str(most_common_class))

    ttk.Label(
        change_dialog,
        text=f"선택한 {total_boxes}개 바운딩 박스 클래스 변경",
        font=("Arial", 12, "bold"),
    ).pack(pady=(15, 10))

    unique_ids = sorted(set(selected_class_ids))
    ttk.Label(
        change_dialog,
        text=f"현재 선택 클래스: {', '.join(map(str, unique_ids))}",
        font=("Arial", 10),
    ).pack(pady=5)

    target_frame = ttk.Frame(change_dialog)
    target_frame.pack(fill="x", padx=20, pady=5)
    ttk.Label(target_frame, text="대상 클래스").pack(side="left", padx=(0, 5))
    class_list = [str(i) for i in range(10)] + ["직접 입력"]
    target_combo = ttk.Combobox(target_frame, textvariable=target_class, width=15)
    target_combo["values"] = class_list
    target_combo.set(str(most_common_class))
    target_combo.pack(side="left", padx=5)

    button_frame = ttk.Frame(change_dialog)
    button_frame.pack(fill="x", padx=20, pady=20)
    result_label = ttk.Label(change_dialog, text="")
    result_label.pack(pady=10)

    def on_target_selected(_event):
        if target_class.get() == "직접 입력":
            target_class.set("")

    target_combo.bind("<<ComboboxSelected>>", on_target_selected)

    def execute_change():
        tgt_class = target_class.get().strip()
        current_class = viewer.class_selector.get()
        current_page = viewer.data_mgr.current_page

        if not tgt_class:
            result_label.config(text="대상 클래스를 입력하세요.", foreground="red")
            return

        try:
            tgt_class_idx = int(tgt_class)
        except ValueError:
            result_label.config(text="클래스 ID는 정수여야 합니다.", foreground="red")
            return

        show_progress = _should_show_progress(len(viewer.selected_label_info), total_boxes)
        progress = None
        if show_progress:
            progress = ttk.Progressbar(change_dialog, orient="horizontal", length=350, mode="determinate")
            progress.pack(pady=10)
            progress["maximum"] = len(viewer.selected_label_info)
            change_dialog.update_idletasks()
        else:
            viewer.root.config(cursor="watch")
            viewer.root.update_idletasks()

        affected_paths = set()
        processed = 0
        changed_file_count = 0
        changed_box_count = 0

        for i, label_info in enumerate(viewer.selected_label_info):
            label_path = label_info["path"]
            if not os.path.isfile(label_path):
                continue
            try:
                lines = read_label_file_lines(label_path)
                lines_with_newline = [line + "\n" for line in lines]
                lines_to_change = {}

                for box in label_info["boxes"]:
                    if "line_idx" not in box:
                        continue
                    line_idx = box["line_idx"]
                    if 0 <= line_idx < len(lines_with_newline):
                        lines_to_change[line_idx] = tgt_class_idx
                        box["class_id"] = tgt_class_idx

                if not lines_to_change:
                    continue

                new_lines = []
                for line_idx, line in enumerate(lines_with_newline):
                    if line_idx not in lines_to_change:
                        new_lines.append(line)
                        continue

                    parts = line.strip().split()
                    if len(parts) >= 5:
                        parts[0] = str(lines_to_change[line_idx])
                        new_lines.append(" ".join(parts) + "\n")
                        changed_box_count += 1
                        viewer.data_mgr.modified_labels["class_changed"].add(
                            (os.path.normpath(label_path), line_idx)
                        )
                    else:
                        new_lines.append(line)

                write_label_file(label_path, new_lines)
                affected_paths.add(label_path)
                changed_file_count += 1

                processed += 1
                if show_progress:
                    progress["value"] = i + 1
                    result_label.config(
                        text=f"처리 중 {processed}/{len(viewer.selected_label_info)}, 변경 파일 {changed_file_count}",
                        foreground="blue",
                    )
                    if i % 25 == 0 or i == len(viewer.selected_label_info) - 1:
                        change_dialog.update_idletasks()
            except Exception as e:
                print(f"Error processing {label_path}: {e}")

        result_label.config(
            text=f"완료: {changed_file_count}개 파일에서 {changed_box_count}개 박스를 클래스 {tgt_class_idx}로 변경",
            foreground="green",
            font=("Arial", 10, "bold"),
        )
        viewer.show_status_message(f"클래스 변경 완료: {changed_box_count}개 박스", duration=3000)

        for label_path in affected_paths:
            viewer.data_mgr.invalidate_label_cache(label_path)
        if affected_paths:
            viewer.data_mgr.refresh_label_data_cache(specific_paths=list(affected_paths))

        viewer.deselect_all_images()
        viewer.changing_class = False
        _partial_refresh(viewer, affected_paths, current_class, current_page)

        viewer.root.config(cursor="")
        if changed_file_count > 0:
            viewer.root.after(800, change_dialog.destroy)

    ttk.Button(button_frame, text="변경", command=execute_change).pack(side="left", padx=5)
    ttk.Button(button_frame, text="취소", command=change_dialog.destroy).pack(side="right", padx=5)


def convert_label_to_mask(viewer):
    """Mask only the selected label boxes and remove those labels."""
    if not _require_box_mode_for_label_edit(viewer):
        return
    if not viewer.selected_image_labels:
        tk.messagebox.showwarning("선택 오류", "마스킹할 이미지를 먼저 선택하세요.")
        return
    if not viewer.selected_label_info:
        tk.messagebox.showwarning("선택 오류", "마스킹할 라벨을 먼저 선택하세요.")
        return

    total_boxes = sum(len(info["boxes"]) for info in viewer.selected_label_info)
    current_class = viewer.class_selector.get()
    current_page = viewer.data_mgr.current_page

    confirmation = tk.messagebox.askyesno(
        "라벨 마스킹 확인",
        (
            f"선택한 {len(viewer.selected_label_info)}개 이미지에서 "
            f"{total_boxes}개의 바운딩 박스를 마스킹으로 변경하시겠습니까?\n"
            "이 작업은 되돌릴 수 없습니다."
        ),
    )
    if not confirmation:
        return

    show_progress = _should_show_progress(len(viewer.selected_label_info), total_boxes)
    progress_window = None
    progress_label = None
    progress_bar = None
    status_label = None
    result_label_widget = None

    if show_progress:
        progress_window = tk.Toplevel(viewer.root)
        progress_window.title("라벨 마스킹 중")
        progress_window.geometry("400x200")
        progress_window.transient(viewer.root)
        progress_window.grab_set()

        progress_label = tk.Label(
            progress_window,
            text="선택한 바운딩 박스 마스킹 중...",
            font=("Arial", 10, "bold"),
        )
        progress_label.pack(pady=(15, 5))
        tk.Label(progress_window, text=f"총 {total_boxes}개의 바운딩 박스를 마스킹합니다.").pack(pady=5)

        progress_bar = ttk.Progressbar(progress_window, length=350)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(viewer.selected_label_info)

        status_label = tk.Label(progress_window, text="0/0 처리 완료")
        status_label.pack(pady=5)
        result_label_widget = tk.Label(progress_window, text="")
        result_label_widget.pack(pady=5)
        progress_window.update_idletasks()
    else:
        viewer.root.config(cursor="watch")
        viewer.root.update_idletasks()

    converted_count = 0
    error_count = 0
    affected_label_paths = set()

    for i, label_info in enumerate(viewer.selected_label_info):
        try:
            label_path = label_info["path"]
            if show_progress:
                progress_bar["value"] = i + 1
                status_label.config(text=f"{i + 1}/{len(viewer.selected_label_info)} 처리 완료")

            if not os.path.isfile(label_path):
                error_count += 1
                continue

            img_path = convert_labels_to_jpegimages(label_path)
            if not os.path.exists(img_path):
                img_path = img_path.replace(".jpg", ".png")
                if not os.path.exists(img_path):
                    error_count += 1
                    continue

            _create_backup(img_path, label_path)

            lines = read_label_file_lines(label_path)
            lines_with_newline = [line + "\n" for line in lines]
            box_line_indices = sorted(
                {box["line_idx"] for box in label_info["boxes"] if "line_idx" in box}
            )

            mask_boxes = []
            filtered_lines = []

            for line_idx, line in enumerate(lines_with_newline):
                parts = line.strip().split()
                if not parts:
                    filtered_lines.append(line)
                    continue
                if line_idx in box_line_indices:
                    try:
                        mask_boxes.append(
                            {
                                "x_center": float(parts[1]),
                                "y_center": float(parts[2]),
                                "width": float(parts[3]),
                                "height": float(parts[4]),
                            }
                        )
                    except (ValueError, IndexError):
                        filtered_lines.append(line)
                else:
                    filtered_lines.append(line)

            if not mask_boxes:
                continue

            img = Image.open(img_path)
            img_array = np.array(img)
            img_height, img_width = img_array.shape[:2]

            for box in mask_boxes:
                cx, cy, width, height = (
                    box["x_center"],
                    box["y_center"],
                    box["width"],
                    box["height"],
                )
                x1 = max(0, int((cx - width / 2) * img_width))
                y1 = max(0, int((cy - height / 2) * img_height))
                x2 = min(img_width, int((cx + width / 2) * img_width))
                y2 = min(img_height, int((cy + height / 2) * img_height))
                img_array[y1:y2, x1:x2] = [255, 0, 255]

            Image.fromarray(img_array).save(img_path)
            write_label_file(label_path, filtered_lines)

            for line_idx in box_line_indices:
                viewer.data_mgr.modified_labels["masking_changed"].add(
                    (os.path.normpath(label_path), line_idx)
                )

            affected_label_paths.add(label_path)
            viewer.data_mgr.invalidate_image_cache(img_path)
            converted_count += 1

        except Exception as e:
            print(f"라벨 마스킹 중 오류 발생 ({label_info.get('path', '?')}): {e}")
            error_count += 1

        if show_progress and (i % 25 == 0 or i == len(viewer.selected_label_info) - 1):
            progress_window.update_idletasks()

    for label_path in affected_label_paths:
        viewer.data_mgr.invalidate_label_cache(label_path)
    if affected_label_paths:
        viewer.data_mgr.refresh_label_data_cache(specific_paths=list(affected_label_paths))

    if show_progress:
        progress_label.config(text="라벨 마스킹 완료")
        result_label_widget.config(
            text=f"{converted_count}개 파일 마스킹 완료, 오류: {error_count}개"
        )

    viewer.show_status_message(f"{converted_count}개 파일 라벨 마스킹 완료", duration=3000)
    viewer.deselect_all_images()
    _partial_refresh(viewer, affected_label_paths, current_class, current_page)

    viewer.root.config(cursor="")
    if progress_window and progress_window.winfo_exists():
        progress_window.destroy()


def _create_backup(img_path, label_path):
    """Create one-time backups for the original image and label files."""
    backup_dir = "original_backup"
    img_backup_dir = os.path.join(backup_dir, "JPEGImages")
    label_backup_dir = os.path.join(backup_dir, "labels")
    os.makedirs(img_backup_dir, exist_ok=True)
    os.makedirs(label_backup_dir, exist_ok=True)

    img_backup = os.path.join(img_backup_dir, make_path(img_path))
    label_backup = os.path.join(label_backup_dir, make_path(label_path))

    os.makedirs(os.path.dirname(img_backup), exist_ok=True)
    os.makedirs(os.path.dirname(label_backup), exist_ok=True)

    if not os.path.exists(img_backup) and os.path.exists(img_path):
        try:
            shutil.copyfile(img_path, img_backup)
        except Exception as e:
            print(f"이미지 백업 실패: {e}")

    if not os.path.exists(label_backup) and os.path.exists(label_path):
        try:
            shutil.copyfile(label_path, label_backup)
        except Exception as e:
            print(f"라벨 백업 실패: {e}")


def _partial_refresh(viewer, affected_paths, current_class, current_page):
    """Refresh only the affected items on the current page."""
    viewer._updating_display = True

    if current_class != "Select Class":
        viewer.class_selector.set(current_class)

    viewer.data_mgr.current_page = (
        min(current_page, viewer.data_mgr.total_pages - 1)
        if viewer.data_mgr.total_pages > 0
        else 0
    )
    if viewer.data_mgr.current_page < 0:
        viewer.data_mgr.current_page = 0

    viewer._updating_display = False
    _refresh_affected_widgets(viewer, affected_paths)


def _refresh_affected_widgets(viewer, affected_paths):
    """Delegate to the viewer's current-page partial refresh path."""
    viewer.refresh_current_page_after_changes(affected_paths=affected_paths)
