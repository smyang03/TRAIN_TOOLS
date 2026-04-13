"""
유틸리티 모듈 - 경로 변환, 인코딩 감지, IoU 계산 등 공통 함수
"""
import os


def detect_file_encoding(file_path):
    """파일 인코딩을 감지합니다."""
    encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read(100)
                return encoding
        except UnicodeDecodeError:
            continue
    return 'utf-8'


def convert_jpegimages_to_labels(img_path):
    """
    JPEGImages 경로를 labels 경로로 변환 (.jpg → .txt)
    백슬래시와 슬래시 경로 모두 처리
    """
    if not img_path:
        return ""
    if "\\JPEGImages\\" in img_path:
        label_path = img_path.replace("\\JPEGImages\\", "\\labels\\")
    elif "/JPEGImages/" in img_path:
        label_path = img_path.replace("/JPEGImages/", "/labels/")
    else:
        label_path = img_path.replace("JPEGImages", "labels")
    label_path = label_path.replace(".jpg", ".txt").replace(".png", ".txt")
    return label_path


def convert_labels_to_jpegimages(label_path):
    """
    labels 경로를 JPEGImages 경로로 변환 (.txt → .jpg)
    백슬래시와 슬래시 경로 모두 처리
    """
    if not label_path:
        return ""
    if "\\labels\\" in label_path:
        img_path = label_path.replace("\\labels\\", "\\JPEGImages\\")
    elif "/labels/" in label_path:
        img_path = label_path.replace("/labels/", "/JPEGImages/")
    else:
        img_path = label_path.replace("labels", "JPEGImages")
    img_path = img_path.replace(".txt", ".jpg")
    return img_path


def get_image_path_from_label(label_path):
    """라벨 경로로부터 이미지 경로를 안전하게 생성합니다."""
    if not label_path:
        return None
    img_path = convert_labels_to_jpegimages(label_path)
    if img_path.endswith(".txt"):
        jpg_path = img_path.replace(".txt", ".jpg")
        if os.path.exists(jpg_path):
            return jpg_path
        png_path = img_path.replace(".txt", ".png")
        if os.path.exists(png_path):
            return png_path
        return jpg_path
    if not os.path.exists(img_path):
        png_path = img_path.replace(".jpg", ".png")
        if os.path.exists(png_path):
            return png_path
    return img_path


def make_path(path):
    """경로에서 파일명을 안전하게 추출합니다."""
    if not path or not isinstance(path, str):
        return ""
    try:
        path = os.path.normpath(path)
        basename = os.path.basename(path)
        if '..' in basename:
            basename = basename.replace('..', '')
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            basename = basename.replace(char, '_')
        return basename
    except Exception:
        return os.path.basename(path) if path else ""


def calculate_iou(box1, box2):
    """
    두 박스 간의 IoU(Intersection over Union)를 계산합니다.
    Args:
        box1: (x1, y1, x2, y2) 형식의 박스 좌표
        box2: (x1, y1, x2, y2) 형식의 박스 좌표
    Returns:
        float: IoU 값 (0~1 사이)
    """
    if box1 is None or box2 is None:
        return 0.0
    if len(box1) != 4 or len(box2) != 4:
        return 0.0
    for val in list(box1) + list(box2):
        if not isinstance(val, (int, float)):
            return 0.0

    x1_1, y1_1, x2_1, y2_1 = box1
    if x1_1 > x2_1:
        x1_1, x2_1 = x2_1, x1_1
    if y1_1 > y2_1:
        y1_1, y2_1 = y2_1, y1_1

    x1_2, y1_2, x2_2, y2_2 = box2
    if x1_2 > x2_2:
        x1_2, x2_2 = x2_2, x1_2
    if y1_2 > y2_2:
        y1_2, y2_2 = y2_2, y1_2

    epsilon = 1e-6
    if (x2_1 - x1_1 <= epsilon or y2_1 - y1_1 <= epsilon or
            x2_2 - x1_2 <= epsilon or y2_2 - y1_2 <= epsilon):
        return 0.0

    x_left = max(x1_1, x1_2)
    y_top = max(y1_1, y1_2)
    x_right = min(x2_1, x2_2)
    y_bottom = min(y2_1, y2_2)

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
    box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)

    if box1_area <= epsilon or box2_area <= epsilon:
        return 0.0

    union_area = box1_area + box2_area - intersection_area
    iou = intersection_area / union_area if union_area > epsilon else 0.0
    return max(0.0, min(1.0, iou))


def check_boxes_overlap(box1, box2):
    """두 박스가 겹치는지 확인합니다."""
    if box1[2] <= box2[0] or box1[0] >= box2[2] or box1[3] <= box2[1] or box1[1] >= box2[3]:
        return False
    return True


def get_iou_color(iou_value):
    """IoU 값에 따른 색상 반환"""
    if iou_value <= 0:
        return "gray"
    if iou_value < 0.3:
        return "yellow"
    elif iou_value < 0.5:
        return "orange"
    elif iou_value < 0.7:
        return "red"
    else:
        return "purple"


def parse_label_line(line):
    """라벨 파일의 한 줄을 파싱합니다.
    Returns:
        dict or None: {'class_id': int, 'x_center': float, 'y_center': float, 'width': float, 'height': float}
    """
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        return {
            'class_id': int(float(parts[0])),
            'x_center': float(parts[1]),
            'y_center': float(parts[2]),
            'width': float(parts[3]),
            'height': float(parts[4])
        }
    except (ValueError, IndexError):
        return None


def yolo_to_pixel(x_center, y_center, width, height, img_width, img_height):
    """YOLO 정규화 좌표를 픽셀 좌표로 변환합니다.
    Returns:
        tuple: (x1, y1, x2, y2) 픽셀 좌표
    """
    x1 = int((x_center - width / 2) * img_width)
    y1 = int((y_center - height / 2) * img_height)
    x2 = int((x_center + width / 2) * img_width)
    y2 = int((y_center + height / 2) * img_height)
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(img_width, x2)
    y2 = min(img_height, y2)
    return x1, y1, x2, y2


def read_label_file_lines(label_path):
    """라벨 파일을 읽어 줄 목록을 반환합니다. 인코딩 자동 감지."""
    if not os.path.isfile(label_path):
        return []
    encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
    for encoding in encodings_to_try:
        try:
            with open(label_path, 'r', encoding=encoding) as f:
                return [line.strip() for line in f.readlines()]
        except UnicodeDecodeError:
            continue
    return []


def write_label_file(label_path, lines):
    """라벨 파일을 안전하게 씁니다 (임시 파일 사용)."""
    tmp_path = label_path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        # 원자적 교체
        if os.path.exists(label_path):
            os.replace(tmp_path, label_path)
        else:
            os.rename(tmp_path, label_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
