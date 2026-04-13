"""
이미지 처리 모듈 - 박스 그리기, 크롭 이미지 처리, 상태 표시
"""
import os
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
from collections import defaultdict

from utils import (
    get_image_path_from_label, calculate_iou, get_iou_color,
    parse_label_line, yolo_to_pixel, read_label_file_lines
)


def draw_status_indicator(image, modified_labels, label_path, line_idx=None):
    """이미지의 오른쪽 상단에 작업 상태를 표시하는 동그라미 indicator를 그립니다."""
    label_key = (os.path.normpath(label_path), line_idx) if line_idx is not None else (os.path.normpath(label_path), None)

    indicators = []
    if label_key in modified_labels.get('deleted', set()):
        indicators.append('red')
    if label_key in modified_labels.get('masking_changed', set()):
        indicators.append('yellow')
    if label_key in modified_labels.get('class_changed', set()):
        indicators.append('blue')

    if not indicators:
        return

    draw = ImageDraw.Draw(image)
    circle_radius = 8
    margin = 5
    x_start = image.width - margin - circle_radius
    y_pos = margin + circle_radius

    for i, color in enumerate(indicators):
        x_pos = x_start - (i * (circle_radius * 2 + 3))
        circle_bbox = [
            x_pos - circle_radius, y_pos - circle_radius,
            x_pos + circle_radius, y_pos + circle_radius
        ]
        draw.ellipse(circle_bbox, fill=color, outline='white', width=2)


def draw_boxes_on_image_crop(viewer, image, label_path, row, col, class_index, img_index, line_idx=None):
    """
    크롭된 이미지에 정보를 그리고 위젯을 생성합니다.
    Returns: 생성된 tk.Label 위젯 또는 None
    """
    data_mgr = viewer.data_mgr
    draw = ImageDraw.Draw(image)
    overlap_class = viewer.overlap_class_selector.get()

    text_color = "red"
    border_color = "black"
    iou_value = 0.0
    show_iou = False

    # 라벨 데이터 읽기
    lines = data_mgr.get_label_data(label_path)
    all_boxes = []
    same_class_boxes = []

    for i, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) >= 5:
            try:
                box_class = int(float(parts[0]))
                box_info = {
                    'line_idx': i,
                    'class': box_class,
                    'x': float(parts[1]),
                    'y': float(parts[2]),
                    'w': float(parts[3]),
                    'h': float(parts[4])
                }
                all_boxes.append(box_info)
                if box_class == class_index:
                    same_class_boxes.append(box_info)
            except (ValueError, IndexError):
                continue

    # 현재 박스 찾기
    current_box = None
    if line_idx is not None:
        current_box = next((box for box in same_class_boxes if box['line_idx'] == line_idx), None)
        if current_box is None and 0 <= line_idx < len(same_class_boxes):
            current_box = same_class_boxes[line_idx]

    # 겹침 클래스 IoU 처리
    if overlap_class != "선택 안함" and current_box:
        try:
            overlap_class_idx = int(float(overlap_class))
            target_boxes = [box for box in all_boxes if box['class'] == overlap_class_idx]

            current_coords = (
                current_box['x'] - current_box['w'] / 2,
                current_box['y'] - current_box['h'] / 2,
                current_box['x'] + current_box['w'] / 2,
                current_box['y'] + current_box['h'] / 2
            )

            for target_box in target_boxes:
                target_coords = (
                    target_box['x'] - target_box['w'] / 2,
                    target_box['y'] - target_box['h'] / 2,
                    target_box['x'] + target_box['w'] / 2,
                    target_box['y'] + target_box['h'] / 2
                )
                iou = calculate_iou(current_coords, target_coords)
                if iou >= viewer.iou_threshold_var.get():
                    show_iou = True
                    iou_value = max(iou_value, iou)
                    text_color = get_iou_color(iou)
                    border_color = text_color

                    # 상대좌표 변환 후 박스 그리기
                    curr_x1 = current_coords[0]
                    curr_y1 = current_coords[1]
                    rel_x1 = (target_coords[0] - curr_x1) / current_box['w']
                    rel_y1 = (target_coords[1] - curr_y1) / current_box['h']
                    rel_x2 = (target_coords[2] - curr_x1) / current_box['w']
                    rel_y2 = (target_coords[3] - curr_y1) / current_box['h']

                    px1 = max(0, min(int(rel_x1 * image.width), image.width - 1))
                    py1 = max(0, min(int(rel_y1 * image.height), image.height - 1))
                    px2 = max(0, min(int(rel_x2 * image.width), image.width - 1))
                    py2 = max(0, min(int(rel_y2 * image.height), image.height - 1))

                    if px2 > px1 and py2 > py1:
                        draw.rectangle((px1, py1, px2, py2), outline="blue", width=2)
                        draw.text((px1 + 2, py1 + 2), f"IoU:{iou:.2f}", fill="blue")
        except Exception as e:
            print(f"겹침 박스 처리 중 오류: {e}")

    # 텍스트 정보 출력
    if show_iou:
        draw.text((5, 5), f"IoU: {iou_value:.2f}", fill=text_color)
        draw.text((5, 20), f"No: {img_index}", fill=text_color)
    else:
        draw.text((5, 5), f"No: {img_index}", fill=text_color)

    if current_box:
        y_pos = 35 if show_iou else 20
        actual_line_idx = current_box['line_idx']
        draw.text((5, y_pos), f"Line: {actual_line_idx} (Class: {current_box['class']})", fill=text_color)

    # 상태 indicator
    bind_line_idx = current_box['line_idx'] if current_box else line_idx
    draw_status_indicator(image, data_mgr.modified_labels, label_path, bind_line_idx)

    # 라벨 위젯 생성
    try:
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(viewer.frame, image=photo, bg="white")
        label.image = photo
        label.label_path = label_path

        if current_box:
            label.line_idx = current_box['line_idx']
        elif line_idx is not None:
            label.line_idx = line_idx

        label.config(relief="solid", bd=0, highlightbackground=border_color, highlightthickness=4)
        label.grid(row=row, column=col, padx=10, pady=10)

        img_path = get_image_path_from_label(label_path)
        bind_line_idx = current_box['line_idx'] if current_box else line_idx

        viewer.setup_drag_select_events(label, label_path)
        label.bind("<Button-3>", lambda event, ip=img_path, lp=label_path, li=bind_line_idx:
                   viewer.show_full_image(ip, lp, li))
        label.bind("<Enter>", lambda event, l=label:
                   viewer.show_box_tooltip(l, label_path, bind_line_idx))
        label.bind("<Leave>", lambda event: viewer.remove_tooltip())

        return label
    except Exception as e:
        print(f"이미지 라벨 생성 실패 ({label_path}): {e}")
        return None


def draw_boxes_on_image(viewer, image, label_path, row, col, image_index):
    """전체 이미지에 바운딩 박스를 그리고 위젯을 생성합니다."""
    data_mgr = viewer.data_mgr
    draw = ImageDraw.Draw(image)
    img_path = get_image_path_from_label(label_path)

    selected_class = int(viewer.class_selector.get())
    overlap_class = viewer.overlap_class_selector.get()

    box_overlap_data = {}
    overlapping_pairs = []

    if overlap_class != "선택 안함":
        overlap_class_idx = int(overlap_class)
        has_overlap, max_iou, detailed_info, all_boxes_info = data_mgr.check_box_overlap(
            label_path, selected_class, overlap_class_idx, viewer.iou_threshold_var.get())
        for box_info in all_boxes_info:
            box_overlap_data[box_info['box_index']] = box_info
            if box_info['has_overlap']:
                for ob in box_info['overlapping_boxes']:
                    overlapping_pairs.append({
                        'main_box': (selected_class, box_info['box_index']),
                        'target_box': (overlap_class_idx, ob['target_box_index']),
                        'iou': ob['iou']
                    })

    try:
        boxes_by_class = defaultdict(list)
        lines = data_mgr.get_label_data(label_path)

        for i, line in enumerate(lines):
            parts = line.split()
            if not parts or len(parts) < 5:
                continue
            try:
                class_index, x_center, y_center, width, height = map(float, parts[:5])
                width_px = width * image.width
                height_px = height * image.height
                x_center_px = x_center * image.width
                y_center_px = y_center * image.height

                x0 = x_center_px - (width_px / 2)
                y0 = y_center_px - (height_px / 2)
                x1 = x_center_px + (width_px / 2)
                y1 = y_center_px + (height_px / 2)

                boxes_by_class[int(class_index)].append({
                    "coords": [x0, y0, x1, y1],
                    "class": int(class_index),
                    "index": i,
                    "center": (x_center_px, y_center_px)
                })
            except (ValueError, IndexError):
                continue

        for class_id, boxes in boxes_by_class.items():
            for box_idx, box in enumerate(boxes):
                color = "green"
                w = 2
                show_iou = False
                iou_val = 0.0
                overlap_id = None

                if class_id == selected_class:
                    if overlap_class != "선택 안함" and box_idx in box_overlap_data:
                        oi = box_overlap_data[box_idx]
                        if oi['has_overlap']:
                            iou_val = oi['max_iou']
                            color = get_iou_color(iou_val)
                            w = 4
                            show_iou = True
                            for pi, pair in enumerate(overlapping_pairs):
                                if pair['main_box'][1] == box_idx:
                                    overlap_id = pi + 1
                        else:
                            color = "red"
                            w = 3
                    else:
                        color = "red"
                        w = 3
                elif overlap_class != "선택 안함" and class_id == int(overlap_class):
                    color = "blue"
                    w = 3
                    for pi, pair in enumerate(overlapping_pairs):
                        if pair['target_box'][1] == box_idx:
                            iou_val = pair['iou']
                            color = "purple"
                            w = 4
                            show_iou = True
                            overlap_id = pi + 1
                            break

                draw.rectangle(box["coords"], outline=color, width=w)
                text_y = box["coords"][1]
                draw.text((box["coords"][0], text_y), f"Class: {class_id}", fill=color)
                text_y += 15
                if overlap_id is not None:
                    draw.text((box["coords"][0], text_y), f"Pair: #{overlap_id}", fill=color)
                    text_y += 15
                if show_iou:
                    draw.text((box["coords"][0], text_y), f"IoU: {iou_val:.2f}", fill=color)

        # 연결선 그리기
        for pair in overlapping_pairs:
            mb_class, mb_idx = pair['main_box']
            tb_class, tb_idx = pair['target_box']
            if (mb_class in boxes_by_class and tb_class in boxes_by_class and
                    len(boxes_by_class[mb_class]) > mb_idx and len(boxes_by_class[tb_class]) > tb_idx):
                main_box = boxes_by_class[mb_class][mb_idx]
                target_box = boxes_by_class[tb_class][tb_idx]
                mc = main_box["center"]
                tc = target_box["center"]
                color = get_iou_color(pair['iou'])
                ll = ((tc[0] - mc[0]) ** 2 + (tc[1] - mc[1]) ** 2) ** 0.5
                if ll > 0:
                    dx = (tc[0] - mc[0]) / ll
                    dy = (tc[1] - mc[1]) / ll
                    for d in range(0, int(ll), 10):
                        x = int(mc[0] + dx * d)
                        y = int(mc[1] + dy * d)
                        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)

        if image_index is not None:
            draw.text((10, 10), f"No: {image_index}", fill="white",
                      stroke_width=2, stroke_fill="black")

    except Exception as e:
        print(f"Error drawing boxes for {label_path}: {e}")

    draw_status_indicator(image, data_mgr.modified_labels, label_path, None)

    photo = ImageTk.PhotoImage(image)
    label = tk.Label(viewer.frame, image=photo, bg="white")
    label.image = photo
    label.label_path = label_path
    label.config(relief="solid", bd=0)
    label.grid(row=row, column=col, padx=10, pady=10)

    viewer.setup_drag_select_events(label, label_path)
    label.bind("<Button-3>", lambda event, ip=img_path, lp=label_path:
               viewer.show_full_image(ip, lp, None))

    return label
