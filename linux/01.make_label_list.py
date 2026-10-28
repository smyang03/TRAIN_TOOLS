import traceback
import numpy as np
import os.path
import random
import shutil
from pathlib import Path
import sys
import os
import re
import logging
from collections import defaultdict

# 리눅스에서 방향키, 백스페이스 등의 입력을 제대로 처리하기 위한 readline import
try:
    import readline
    # readline 설정 - 리눅스에서 더 나은 입력 편집 기능 제공
    readline.parse_and_bind('set editing-mode emacs')  # Emacs 스타일 편집
    readline.parse_and_bind('set enable-keypad on')    # 방향키 지원
except ImportError:
    # Windows 환경에서는 readline이 없을 수 있음
    pass
except Exception as e:
    # readline 설정 실패 시 무시 (기본 동작 사용)
    print(f"Warning: readline 설정 실패 - {e}")

# 원본 input 함수를 먼저 저장 (무한 재귀 방지)
import builtins
_original_input = builtins.input

def safe_input(prompt):
    """
    안전한 입력 함수 - ANSI escape sequence 제거
    리눅스에서 방향키 입력 시 발생하는 문제 해결
    """
    try:
        # 저장된 원본 input 함수 사용
        user_input = _original_input(prompt)
        # ANSI escape sequence 제거 (방향키 등의 특수 문자)
        # \x1b는 ESC 문자, \[는 [, A-Z는 명령어
        ansi_escape = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
        cleaned_input = ansi_escape.sub('', user_input)
        return cleaned_input.strip()
    except EOFError:
        return ""
    except KeyboardInterrupt:
        raise

# 전역적으로 input 함수를 safe_input으로 오버라이드
builtins.input = safe_input

# 로깅 설정
def setup_logging(output_path):
    """로깅 설정"""
    log_path = os.path.join(output_path, 'processing.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def get_default_input_path():
    """플랫폼에 맞는 기본 입력 경로 반환"""
    import os
    import sys
    
    # 운영체제 확인
    if os.name == 'nt' or sys.platform.startswith('win'):  # Windows
        return 'Z:\\08_Train\\02_GT\\AirForce'
    else:  # Linux, macOS 등
        return '/path/to/your/data/AirForce'  # 리눅스 경로로 변경 필요

def get_default_output_path(input_path):
    """입력 경로 기반으로 기본 출력 경로 생성"""
    return os.path.join(input_path, 'output')

def get_label_path_from_image(image_path):
    """
    이미지 경로에서 라벨 경로를 생성하는 개선된 함수
    다양한 디렉토리 구조를 지원
    """
    # 방법 1: JPEGImages -> labels 치환
    if 'JPEGImages' in image_path:
        label_path = image_path.replace('JPEGImages', 'labels').replace('.jpg', '.txt')
        return label_path
    
    # 방법 2: 상위 디렉토리의 labels 폴더 사용
    directory = os.path.dirname(image_path)
    filename = os.path.basename(image_path)
    base_filename = os.path.splitext(filename)[0] + '.txt'
    
    # 현재 디렉토리에서 상위로 올라가면서 labels 디렉토리 찾기
    current_dir = directory
    while current_dir and current_dir != os.path.dirname(current_dir):
        parent_dir = os.path.dirname(current_dir)
        labels_dir = os.path.join(parent_dir, 'labels')
        
        if os.path.exists(labels_dir):
            # 원본 이미지의 하위 디렉토리 구조를 labels에도 반영
            relative_path = os.path.relpath(directory, os.path.dirname(labels_dir))
            if relative_path.startswith('JPEGImages'):
                relative_path = relative_path.replace('JPEGImages', 'labels', 1)
            else:
                relative_path = os.path.join('labels', os.path.basename(directory))
            
            final_label_dir = os.path.join(parent_dir, relative_path)
            label_path = os.path.join(final_label_dir, base_filename)
            return label_path
        
        current_dir = parent_dir
    
    # 방법 3: 같은 디렉토리에 labels 폴더 생성
    labels_dir = os.path.join(directory, 'labels')
    label_path = os.path.join(labels_dir, base_filename)
    return label_path

def count_jpg_files(path):
    """입력 경로의 전체 jpg 파일 수를 계산"""
    total = 0
    for root, _, files in os.walk(path):
        total += sum(1 for f in files if f.lower().endswith(('.jpg', '.jpeg')))
    return total

def collect_image_files_from_source(input_source, keyword=None):
    """
    폴더 경로 또는 파일 리스트(.txt)에서 이미지 파일 목록 수집

    Args:
        input_source: 폴더 경로 또는 이미지 경로가 담긴 .txt 파일 경로
        keyword: 파일명 필터링 키워드 (None이면 모든 파일 포함)

    Returns:
        (image_files, filtered_cnt):
            image_files  - 수집된 이미지 경로 리스트
            filtered_cnt - 키워드 필터링으로 제외된 파일 수
    """
    image_files = []
    filtered_cnt = 0

    if os.path.isdir(input_source):
        # 폴더 순회
        for root, _, files in os.walk(input_source):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg')):
                    if keyword and keyword not in file:
                        filtered_cnt += 1
                        continue
                    image_files.append(os.path.join(root, file))
    elif os.path.isfile(input_source) and input_source.lower().endswith('.txt'):
        # 파일 리스트 읽기
        try:
            with open(input_source, 'r', encoding='utf-8') as f:
                for line in f:
                    path = line.strip()
                    if not path or path.startswith('#'):
                        continue
                    if path.lower().endswith(('.jpg', '.jpeg')):
                        if keyword and keyword not in os.path.basename(path):
                            filtered_cnt += 1
                            continue
                        image_files.append(path)
        except Exception as e:
            print(f"파일 리스트 읽기 오류: {e}")

    return image_files, filtered_cnt

def print_class_statistics(obj_annotation, title):
    """클래스별 통계 출력"""
    print(f"\n{title}:")
    print(f"전체 어노테이션 수: {int(obj_annotation[0])}")
    for i in range(1, len(obj_annotation)):
        if obj_annotation[i] > 0:  # 0보다 큰 값만 출력
            print(f"클래스 {i-1}: {int(obj_annotation[i])}개")

def get_folder_stats_key(input_source, image_path):
    """폴더별 통계에 사용할 경로 키 생성"""
    if os.path.isdir(input_source):
        rel_dir = os.path.relpath(os.path.dirname(image_path), input_source)
        if rel_dir == '.':
            return '(root)'
        return rel_dir.replace(os.sep, '/')

    return os.path.basename(os.path.dirname(image_path)) or '(root)'

def print_folder_statistics(folder_stats, title="폴더별 수량 통계"):
    """폴더별 처리 수량 출력"""
    if not folder_stats:
        return

    print(f"\n{title}:")
    for folder_name in sorted(folder_stats.keys()):
        folder_stat = folder_stats[folder_name]
        print(f"  {folder_name}: {folder_stat['total']}개 파일 | "
              f"어노테이션 {folder_stat['annotations']}개 | "
              f"라벨 없음 {folder_stat['no_label']}개 | "
              f"빈 라벨 {folder_stat['empty_label']}개 | "
              f"에러 {folder_stat['error']}개")

def create_empty_label(label_path, logger=None):
    """빈 라벨 파일 생성"""
    try:
        os.makedirs(os.path.dirname(label_path), exist_ok=True)
        with open(label_path, 'w', encoding='utf-8') as f:
            pass  # 빈 파일 생성
        if logger:
            logger.debug(f"빈 라벨 파일 생성: {label_path}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"라벨 파일 생성 실패 {label_path}: {e}")
        return False

def validate_paths(image_path, label_path, logger=None):
    """경로 유효성 검증"""
    issues = []
    
    if not os.path.exists(image_path):
        issues.append(f"이미지 파일 없음: {image_path}")
    
    if not os.path.exists(os.path.dirname(label_path)):
        try:
            os.makedirs(os.path.dirname(label_path), exist_ok=True)
            if logger:
                logger.debug(f"라벨 디렉토리 생성: {os.path.dirname(label_path)}")
        except Exception as e:
            issues.append(f"라벨 디렉토리 생성 실패: {e}")
    
    return issues

try:
    from PIL import Image as _PILImage
except ImportError:  # PIL 없으면 픽셀 환산 없이 비율 통계만 표시
    _PILImage = None

import unicodedata
from collections import Counter

SIZE_AREA_BOUNDS = [0.01, 0.03, 0.10, 0.30]     # √(w×h) 비율 구간 경계
SIZE_HEIGHT_BOUNDS = [0.02, 0.05, 0.10, 0.25]   # 높이 비율 구간 경계
SIZE_SHAPE_BOUNDS = [0.5, 0.9, 1.1, 2.0]        # 세로/가로(px) 구간 경계
SIZE_AREA_NAMES = ['tiny', 'small', 'medium', 'large', 'xlarge']
SIZE_SHAPE_NAMES = ['가로로 긴', '가로형', '정사각형', '세로형', '세로로 긴']


def _disp_width(text):
    """cmd 출력 폭 계산 (한글 등 전각 문자는 2칸)"""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in str(text))


def _pad(text, width, align='left'):
    """전각 문자를 고려한 패딩"""
    text = str(text)
    gap = max(width - _disp_width(text), 0)
    return text + ' ' * gap if align == 'left' else ' ' * gap + text


def _render_table(headers, rows, aligns=None, indent='  '):
    """헤더/행 리스트를 열 폭 맞춘 표 문자열 리스트로 변환"""
    aligns = aligns or ['right'] * len(headers)
    widths = [_disp_width(h) for h in headers]
    for row in rows:
        if row is None:
            continue
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _disp_width(cell))
    sep = ' | '
    out = [indent + sep.join(_pad(h, widths[i], aligns[i]) for i, h in enumerate(headers))]
    out.append(indent + '-' * (sum(widths) + len(sep) * (len(widths) - 1)))
    for row in rows:
        if row is None:  # 구분선
            out.append(out[1])
            continue
        out.append(indent + sep.join(_pad(c, widths[i], aligns[i]) for i, c in enumerate(row)))
    return out


def parse_percent_bounds(text, default):
    """'1,3,10,30' 형식(%)을 오름차순 비율 리스트로 변환. 비어 있으면 기본값"""
    text = (text or '').strip()
    if not text:
        return list(default)
    values = sorted({float(v.strip()) / 100.0 for v in text.split(',') if v.strip()})
    if not values or values[0] <= 0 or values[-1] >= 1:
        raise ValueError("구간 경계는 0~100 사이 % 값이어야 합니다")
    return values


def read_image_size(image_path):
    """이미지 해상도 (W, H). 헤더만 읽으므로 빠름. 실패 시 None"""
    if _PILImage is None:
        return None
    try:
        with _PILImage.open(image_path) as im:
            return im.size
    except Exception:
        return None


def _bucket_index(value, bounds):
    for i, b in enumerate(bounds):
        if value < b:
            return i
    return len(bounds)


def _new_agg():
    return {'n': 0, 'w': 0.0, 'h': 0.0, 'pn': 0, 'pw': 0.0, 'ph': 0.0,
            'pmin': None, 'pmax': None}


def _agg_add(agg, w, h, pw=None, ph=None, pval=None):
    agg['n'] += 1
    agg['w'] += w
    agg['h'] += h
    if pw is not None:
        agg['pn'] += 1
        agg['pw'] += pw
        agg['ph'] += ph
        agg['pmin'] = pval if agg['pmin'] is None else min(agg['pmin'], pval)
        agg['pmax'] = pval if agg['pmax'] is None else max(agg['pmax'], pval)


def new_size_stats(area_bounds=None, height_bounds=None):
    """객체 크기 통계 누적용 구조 생성"""
    area_bounds = list(area_bounds or SIZE_AREA_BOUNDS)
    height_bounds = list(height_bounds or SIZE_HEIGHT_BOUNDS)
    return {
        'area_bounds': area_bounds,
        'height_bounds': height_bounds,
        'area': [_new_agg() for _ in range(len(area_bounds) + 1)],
        'area_total': _new_agg(),
        'height': [_new_agg() for _ in range(len(height_bounds) + 1)],
        'height_total': _new_agg(),
        'shape': [0] * (len(SIZE_SHAPE_BOUNDS) + 1),
        'shape_sum': 0.0,
        'shape_n': 0,
        'class': defaultdict(lambda: {
            'all': _new_agg(),
            'area_cnt': [0] * (len(area_bounds) + 1),
            'height_cnt': [0] * (len(height_bounds) + 1),
        }),
        'resolution': Counter(),
        'no_resolution_images': 0,
        'abnormal_cnt': 0,
        'min_box': None,   # (√면적비, w, h, pw, ph)
        'max_box': None,
    }


def add_image_sizes(size_stats, image_path, boxes):
    """
    이미지 한 장의 박스들을 크기 통계에 누적
    boxes: [(class_id, cx, cy, w, h), ...] (YOLO 정규화 좌표)
    """
    if not boxes:
        return
    res = read_image_size(image_path)
    if res:
        size_stats['resolution'][res] += 1
    else:
        size_stats['no_resolution_images'] += 1

    for class_id, cx, cy, w, h in boxes:
        if w <= 0 or h <= 0:
            size_stats['abnormal_cnt'] += 1
            continue
        eps = 1e-3
        if (cx - w / 2 < -eps or cy - h / 2 < -eps or
                cx + w / 2 > 1 + eps or cy + h / 2 > 1 + eps):
            size_stats['abnormal_cnt'] += 1  # 이미지 밖으로 나간 박스 (집계는 계속)

        side = (w * h) ** 0.5
        pw = ph = pside = None
        if res:
            pw, ph = w * res[0], h * res[1]
            pside = (pw * ph) ** 0.5

        ai = _bucket_index(side, size_stats['area_bounds'])
        hi = _bucket_index(h, size_stats['height_bounds'])
        _agg_add(size_stats['area'][ai], w, h, pw, ph, pside)
        _agg_add(size_stats['area_total'], w, h, pw, ph, pside)
        _agg_add(size_stats['height'][hi], w, h, pw, ph, ph)
        _agg_add(size_stats['height_total'], w, h, pw, ph, ph)

        cls = size_stats['class'][class_id]
        _agg_add(cls['all'], w, h, pw, ph, pside)
        cls['area_cnt'][ai] += 1
        cls['height_cnt'][hi] += 1

        # 형태는 px 기준 (해상도 없으면 비율 기준)
        aspect = (ph / pw) if res else (h / w)
        size_stats['shape'][_bucket_index(aspect, SIZE_SHAPE_BOUNDS)] += 1
        size_stats['shape_sum'] += aspect
        size_stats['shape_n'] += 1

        box = (side, w, h, pw, ph)
        if size_stats['min_box'] is None or side < size_stats['min_box'][0]:
            size_stats['min_box'] = box
        if size_stats['max_box'] is None or side > size_stats['max_box'][0]:
            size_stats['max_box'] = box


def _fmt_pct(v):
    return f"{v * 100:.1f}%"


def _bound_label(i, bounds, name=None):
    if i == 0:
        rng = f"<{bounds[0] * 100:g}%"
    elif i == len(bounds):
        rng = f"≥{bounds[-1] * 100:g}%"
    else:
        rng = f"{bounds[i - 1] * 100:g}~{bounds[i] * 100:g}%"
    return f"{name} ({rng})" if name else rng


def _avg_ratio_wh(agg):
    if not agg['n']:
        return '-'
    return f"{_fmt_pct(agg['w'] / agg['n'])} × {_fmt_pct(agg['h'] / agg['n'])}"


def _avg_px_wh(agg):
    if not agg['pn']:
        return '-'
    return f"{agg['pw'] / agg['pn']:.0f} × {agg['ph'] / agg['pn']:.0f}"


def _px_range(agg):
    if agg['pmin'] is None:
        return '-'
    return f"{agg['pmin']:.0f} ~ {agg['pmax']:.0f}"


def _box_text(box):
    if box is None:
        return '-'
    _, w, h, pw, ph = box
    text = f"{_fmt_pct(w)} × {_fmt_pct(h)}"
    if pw is not None:
        text += f" ({pw:.0f} × {ph:.0f} px)"
    return text


def build_size_report(size_stats):
    """객체 크기 통계 리포트 라인 리스트"""
    total = size_stats['area_total']['n']
    lines = []
    if total == 0:
        return ["", "[객체 크기 통계]", "  유효한 박스가 없습니다."]

    def share(n):
        return _fmt_pct(n / total) if total else '0.0%'

    area_bounds = size_stats['area_bounds']
    height_bounds = size_stats['height_bounds']
    use_names = len(area_bounds) + 1 == len(SIZE_AREA_NAMES)

    # 1) 면적 기준
    rows = []
    for i, agg in enumerate(size_stats['area']):
        name = SIZE_AREA_NAMES[i] if use_names else None
        rows.append([_bound_label(i, area_bounds, name), f"{agg['n']:,}", share(agg['n']),
                     _avg_ratio_wh(agg), _avg_px_wh(agg), _px_range(agg)])
    t = size_stats['area_total']
    rows += [None, ['전체', f"{t['n']:,}", '100%', _avg_ratio_wh(t), _avg_px_wh(t), _px_range(t)]]
    lines += ["", "[객체 크기 통계] (구간 기준: 비율 √(w×h), 픽셀 = 이미지 해상도 반영 실측)"]
    lines += _render_table(['구간', '수량', '비율', '평균 w×h (비율)', '평균 W×H (px)', 'px 범위(√면적)'],
                           rows, ['left', 'right', 'right', 'right', 'right', 'right'])
    lines.append(f"  최소: {_box_text(size_stats['min_box'])}  /  최대: {_box_text(size_stats['max_box'])}")

    # 2) 클래스별 면적 기준
    rows = []
    for cid in sorted(size_stats['class']):
        c = size_stats['class'][cid]
        rows.append([str(cid), f"{c['all']['n']:,}", _avg_ratio_wh(c['all']), _avg_px_wh(c['all'])]
                    + [f"{v:,}" for v in c['area_cnt']])
    bucket_heads = [SIZE_AREA_NAMES[i] if use_names else _bound_label(i, area_bounds)
                    for i in range(len(area_bounds) + 1)]
    lines += ["", "[클래스별 크기 통계]"]
    lines += _render_table(['클래스', '수량', '평균 w×h (비율)', '평균 W×H (px)'] + bucket_heads, rows)

    # 3) 세로(높이) 기준
    rows = []
    for i, agg in enumerate(size_stats['height']):
        avg_h = _fmt_pct(agg['h'] / agg['n']) if agg['n'] else '-'
        avg_ph = f"{agg['ph'] / agg['pn']:.0f}" if agg['pn'] else '-'
        rows.append([_bound_label(i, height_bounds), f"{agg['n']:,}", share(agg['n']),
                     avg_h, avg_ph, _px_range(agg)])
    t = size_stats['height_total']
    rows += [None, ['전체', f"{t['n']:,}", '100%', _fmt_pct(t['h'] / t['n']),
                    f"{t['ph'] / t['pn']:.0f}" if t['pn'] else '-', _px_range(t)]]
    lines += ["", "[세로(높이) 기준 크기 통계] (구간 기준: 높이 비율 h = 박스높이 / 이미지높이)"]
    lines += _render_table(['구간', '수량', '비율', '평균 h (비율)', '평균 높이 (px)', 'px 범위'],
                           rows, ['left', 'right', 'right', 'right', 'right', 'right'])

    # 4) 클래스별 세로 기준
    rows = []
    for cid in sorted(size_stats['class']):
        c = size_stats['class'][cid]['all']
        cnt = size_stats['class'][cid]['height_cnt']
        rows.append([str(cid), _fmt_pct(c['h'] / c['n']) if c['n'] else '-',
                     f"{c['ph'] / c['pn']:.0f}" if c['pn'] else '-'] + [f"{v:,}" for v in cnt])
    lines += ["", "[클래스별 세로 기준]"]
    lines += _render_table(['클래스', '평균 h (비율)', '평균 높이 (px)'] +
                           [_bound_label(i, height_bounds) for i in range(len(height_bounds) + 1)], rows)

    # 5) 형태
    rows = []
    for i, n in enumerate(size_stats['shape']):
        if i == 0:
            rng = f"<{SIZE_SHAPE_BOUNDS[0]:g}"
        elif i == len(SIZE_SHAPE_BOUNDS):
            rng = f"≥{SIZE_SHAPE_BOUNDS[-1]:g}"
        else:
            rng = f"{SIZE_SHAPE_BOUNDS[i - 1]:g}~{SIZE_SHAPE_BOUNDS[i]:g}"
        rows.append([f"{SIZE_SHAPE_NAMES[i]} ({rng})", f"{n:,}", share(n)])
    basis = 'h_px / w_px' if size_stats['resolution'] else 'h / w (해상도 미확인, 비율 기준)'
    lines += ["", f"[객체 형태 (세로/가로 = {basis})]"]
    lines += _render_table(['구간', '수량', '비율'], rows, ['left', 'right', 'right'])
    if size_stats['shape_n']:
        lines.append(f"  평균 세로/가로: {size_stats['shape_sum'] / size_stats['shape_n']:.2f}")

    # 6) 해상도
    res_total = sum(size_stats['resolution'].values())
    lines += ["", "[이미지 해상도 분포] (박스가 있는 이미지 기준)"]
    for (rw, rh), n in size_stats['resolution'].most_common():
        lines.append(f"  {_pad(f'{rw}×{rh}', 11)} : {n:>8,}장 ({_fmt_pct(n / res_total)})")
    if size_stats['no_resolution_images']:
        lines.append(f"  해상도 읽기 실패: {size_stats['no_resolution_images']:,}장 (픽셀 값에서 제외)")
    if size_stats['abnormal_cnt']:
        lines.append(f"  이상 박스 (크기 0 또는 이미지 밖): {size_stats['abnormal_cnt']:,}개")
    return lines


def build_dataset_report(stats, input_path, keyword=None):
    """create_complete_dataset_list 통계로 상세 리포트 문자열 생성 (cmd 출력/txt 저장 공용)"""
    def pct(n, d):
        return f"{n / d * 100:.1f}%" if d else "0.0%"

    total = stats['total_cnt']
    listed = stats['labeled_cnt'] + stats['background_cnt']
    total_ann = int(stats['total_annotations'])
    obj = stats['obj_annotation']
    cls_img = stats['class_image_cnt']
    bar = "=" * 70

    lines = [
        bar,
        " 데이터셋 상세 리포트",
        bar,
        f"입력 경로: {input_path}",
    ]
    if keyword:
        lines.append(f"키워드 필터: '{keyword}' (제외 {stats.get('filtered_cnt', 0)}개)")
    lines += [
        "",
        "[요약]",
        f"  전체 이미지           : {total:>10,}개",
        f"  리스트 등록 이미지    : {listed:>10,}개",
        f"  라벨 있는 이미지      : {stats['labeled_cnt']:>10,}개 ({pct(stats['labeled_cnt'], listed)})",
        f"  배경 이미지(어노 0개) : {stats['background_cnt']:>10,}개 ({pct(stats['background_cnt'], listed)})",
        f"  전체 어노테이션       : {total_ann:>10,}개",
        f"  이미지당 평균 어노    : {total_ann / stats['labeled_cnt'] if stats['labeled_cnt'] else 0:>10.2f}개 (라벨 있는 이미지 기준)",
        f"  이미지당 최대 어노    : {stats['max_annotations']:>10,}개",
        f"  에러(리스트 제외)     : {stats['error_cnt']:>10,}개",
        "",
        "[배경 이미지 상세]",
        f"  라벨 파일 없음 -> 빈 라벨 생성 : {stats['no_label_cnt']:,}개",
        # empty_label_cnt에는 방금 생성한 빈 라벨도 포함되므로 제외
        f"  기존 빈 라벨 파일              : {max(stats['empty_label_cnt'] - stats['no_label_cnt'], 0):,}개",
        f"  유효 어노테이션 없는 라벨      : {stats['invalid_only_cnt']:,}개",
        f"  무시된 잘못된 라인 수          : {stats['invalid_line_cnt']:,}개",
        "",
        "[클래스별 통계]",
        f"  {'클래스':>6} | {'어노테이션':>10} | {'비율':>6} | {'포함 이미지':>10}",
        "  " + "-" * 46,
    ]
    for i in range(1, len(obj)):
        if obj[i] > 0:
            lines.append(f"  {i - 1:>6} | {int(obj[i]):>10,} | {pct(obj[i], total_ann):>6} | {int(cls_img[i]):>10,}")

    lines += [
        "",
        "[폴더별 통계]",
        "  폴더 | 이미지 | 라벨있음 | 배경 | 어노테이션 | 라벨없음(생성) | 빈라벨 | 에러",
    ]
    for name in sorted(stats['folder_stats']):
        fs = stats['folder_stats'][name]
        lines.append(f"  {name} | {fs['total']:,} | {fs.get('labeled', 0):,} | {fs.get('background', 0):,} | "
                     f"{fs['annotations']:,} | {fs['no_label']:,} | {fs['empty_label']:,} | {fs['error']:,}")
    if stats.get('size_stats'):
        lines += build_size_report(stats['size_stats'])
    lines.append(bar)
    return "\n".join(lines)


def create_complete_dataset_list(input_path, output_path, keyword=None, output_prefix=None,
                                 size_options=None):
    """
    입력 경로의 모든 이미지 파일을 하나의 리스트로 생성하는 함수

    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 저장 경로
        keyword: 파일명 필터링 키워드 (None이면 모든 파일 포함, 한글/특수문자 지원)
        output_prefix: 출력 파일명 prefix (여러 폴더 일괄 처리시 폴더명 구분용)
        size_options: 객체 크기 분석 옵션 {'area_bounds': [...], 'height_bounds': [...]} (None이면 미실행)
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"전체 데이터셋 리스트 생성 시작: {input_path}")
    if keyword:
        logger.info(f"파일명 필터 키워드: '{keyword}'")
    if output_prefix:
        logger.info(f"출력 파일 prefix: '{output_prefix}'")

    # 결과 파일 경로 설정 (prefix가 있으면 파일명에 추가)
    if output_prefix:
        complete_list_path = output_path / f'{output_prefix}_complete_dataset.txt'
        complete_annotation_path = output_path / f'{output_prefix}_complete_annotation.txt'
        folder_stats_path = output_path / f'{output_prefix}_folder_stats.txt'
        error_log_path = output_path / f'{output_prefix}_errors.txt'
        report_path = output_path / f'{output_prefix}_dataset_report.txt'
    else:
        complete_list_path = output_path / 'complete_dataset.txt'
        complete_annotation_path = output_path / 'complete_annotation.txt'
        folder_stats_path = output_path / 'folder_stats.txt'
        error_log_path = output_path / 'errors.txt'
        report_path = output_path / 'dataset_report.txt'
    
    # 통계 변수 초기화
    obj_annotation = np.zeros(90)
    
    stats = {
        'total_cnt': 0,           # 전체 처리한 파일 수
        'no_label_cnt': 0,        # 라벨 파일이 없는 이미지
        'empty_label_cnt': 0,     # 어노테이션이 없는 이미지
        'error_cnt': 0,           # 에러 발생 수
        'total_annotations': 0,   # 총 어노테이션 수
        'created_labels': 0,      # 새로 생성된 라벨 파일
        'obj_annotation': obj_annotation,
        'path_issues': [],        # 경로 문제 목록
        'filtered_cnt': 0,        # 키워드 필터링으로 제외된 파일 수
        'labeled_cnt': 0,         # 어노테이션이 1개 이상 있는 이미지
        'background_cnt': 0,      # 어노테이션 0개 이미지 (배경)
        'invalid_only_cnt': 0,    # 라벨 내용은 있으나 유효 어노테이션이 없는 이미지
        'invalid_line_cnt': 0,    # 형식 오류/범위 밖 클래스로 무시된 라인 수
        'max_annotations': 0,     # 이미지 1장 최대 어노테이션 수
        'class_image_cnt': np.zeros(90),  # 클래스별 등장 이미지 수
        'size_stats': (new_size_stats(size_options.get('area_bounds'), size_options.get('height_bounds'))
                       if size_options is not None else None),
        'folder_stats': defaultdict(lambda: {
            'total': 0,
            'annotations': 0,
            'no_label': 0,
            'empty_label': 0,
            'error': 0,
            'labeled': 0,
            'background': 0,
        }),
    }
    
    # 파일 리스트 초기화
    with open(complete_list_path, 'w', encoding='utf-8') as f:
        pass  # 파일 초기화
    
    # 에러 로그 파일 초기화
    with open(error_log_path, 'w', encoding='utf-8') as f:
        f.write("에러 로그\n")
        f.write("=" * 50 + "\n")
    
    # 전체 파일 수 계산 (폴더 또는 파일 리스트 지원)
    all_files, filtered_cnt = collect_image_files_from_source(input_path, keyword)
    stats['filtered_cnt'] = filtered_cnt
    total_files = len(all_files)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")

    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 입력 경로 순회
    logger.info(f"전체 {total_files}개 파일 처리 시작...")

    for full_path in all_files:
        stats['total_cnt'] += 1
        progress = (stats['total_cnt'] / total_files) * 100

        label_path = get_label_path_from_image(full_path)
        folder_key = get_folder_stats_key(input_path, full_path)
        folder_stat = stats['folder_stats'][folder_key]
        folder_stat['total'] += 1

        # 경로 유효성 검증
        path_issues = validate_paths(full_path, label_path, logger)
        if path_issues:
            stats['path_issues'].extend(path_issues)
            with open(error_log_path, 'a', encoding='utf-8') as f:
                f.write(f"경로 문제 - {full_path}:\n")
                for issue in path_issues:
                    f.write(f"  {issue}\n")

        # 라벨 파일 존재 확인 및 처리
        if not os.path.isfile(label_path):
            if create_empty_label(label_path, logger):
                stats['created_labels'] += 1
                stats['no_label_cnt'] += 1
                folder_stat['no_label'] += 1
            else:
                stats['error_cnt'] += 1
                folder_stat['error'] += 1
                continue

        # 어노테이션 처리
        current_annotation = np.zeros(90)
        boxes = []  # 객체 크기 분석용 (class_id, cx, cy, w, h)
        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:  # 빈 파일 처리
                    stats['empty_label_cnt'] += 1
                    folder_stat['empty_label'] += 1
                else:
                    for line_num, line in enumerate(lines, 1):
                        line = line.strip()
                        if not line:
                            continue

                        split_line = line.split()
                        if len(split_line) < 5:  # YOLO 형식은 최소 5개 값 필요
                            logger.warning(f"잘못된 어노테이션 형식 {label_path}:{line_num} - {line}")
                            stats['invalid_line_cnt'] += 1
                            continue

                        try:
                            class_id = int(float(split_line[0]))
                            if class_id < 0 or class_id >= 89:  # 클래스 ID 범위 검증
                                logger.warning(f"잘못된 클래스 ID {label_path}:{line_num} - {class_id}")
                                stats['invalid_line_cnt'] += 1
                                continue

                            current_annotation[0] += 1  # 전체 어노테이션 카운트
                            current_annotation[class_id + 1] += 1  # 클래스별 카운트
                        except (ValueError, IndexError) as e:
                            logger.warning(f"어노테이션 파싱 오류 {label_path}:{line_num} - {e}")
                            stats['invalid_line_cnt'] += 1
                            continue

                        if stats['size_stats'] is not None:
                            try:
                                boxes.append((class_id,) + tuple(float(v) for v in split_line[1:5]))
                            except ValueError:
                                pass

                    if current_annotation[0] == 0:
                        stats['invalid_only_cnt'] += 1

        except Exception as e:
            logger.error(f"라벨 파일 처리 오류 {label_path}: {e}")
            stats['error_cnt'] += 1
            folder_stat['error'] += 1
            with open(error_log_path, 'a', encoding='utf-8') as f:
                f.write(f"라벨 처리 오류 - {label_path}: {e}\n")
            continue

        # 결과 저장 - UTF-8로 인코딩
        with open(complete_list_path, 'a', encoding='utf-8') as f:
            f.write(f"{full_path}\n")

        stats['obj_annotation'] += current_annotation
        stats['total_annotations'] += current_annotation[0]
        folder_stat['annotations'] += int(current_annotation[0])
        if current_annotation[0] > 0:
            stats['labeled_cnt'] += 1
            folder_stat['labeled'] += 1
            stats['class_image_cnt'] += (current_annotation > 0)
            stats['max_annotations'] = max(stats['max_annotations'], int(current_annotation[0]))
        else:
            stats['background_cnt'] += 1
            folder_stat['background'] += 1
        if boxes:
            add_image_sizes(stats['size_stats'], full_path, boxes)

        # 진행률 표시 (1000개마다 로그)
        if stats['total_cnt'] % 1000 == 0:
            logger.info(f"진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files})")

        print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
              f"처리: {stats['total_cnt']} | "
              f"어노테이션: {stats['total_annotations']} | "
              f"라벨 없음: {stats['no_label_cnt']} | "
              f"빈 라벨: {stats['empty_label_cnt']}", end='')
    
    print("\n")  # 진행률 표시 줄바꿈
    
    # 최종 통계 저장
    np.savetxt(complete_annotation_path, stats['obj_annotation'], fmt='%2d',
               delimiter=',', header='complete dataset annotation')

    # 폴더별 수량 통계 저장 및 출력
    with open(folder_stats_path, 'w', encoding='utf-8') as f:
        f.write("폴더별 수량 통계\n")
        f.write("=" * 80 + "\n")
        f.write("폴더\t파일수\t어노테이션수\t라벨없음\t빈라벨\t에러\n")
        for folder_name in sorted(stats['folder_stats'].keys()):
            folder_stat = stats['folder_stats'][folder_name]
            f.write(f"{folder_name}\t{folder_stat['total']}\t"
                    f"{folder_stat['annotations']}\t"
                    f"{folder_stat['no_label']}\t"
                    f"{folder_stat['empty_label']}\t"
                    f"{folder_stat['error']}\n")

    print_folder_statistics(stats['folder_stats'])
    
    # 경로 문제 요약 저장
    if stats['path_issues']:
        path_issues_path = output_path / 'path_issues_summary.txt'
        with open(path_issues_path, 'w', encoding='utf-8') as f:
            f.write(f"경로 문제 요약 (총 {len(stats['path_issues'])}개)\n")
            f.write("=" * 50 + "\n")
            for issue in stats['path_issues']:
                f.write(f"{issue}\n")
    
    report_text = build_dataset_report(stats, input_path, keyword)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text + "\n")
    print("\n" + report_text)
    stats['report_path'] = str(report_path)

    logger.info("전체 데이터셋 리스트 생성 완료")
    logger.info(f"상세 리포트 저장: {report_path}")
    logger.info(f"처리된 파일: {stats['total_cnt']}개")
    logger.info(f"생성된 라벨: {stats['created_labels']}개")
    logger.info(f"에러 발생: {stats['error_cnt']}개")
    logger.info(f"폴더별 수량 통계 저장: {folder_stats_path}")

    return stats

def find_images_without_class(input_path, output_path, target_class):
    """
    특정 클래스가 없는 이미지 파일을 찾아 리스트 생성

    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 저장 경로
        target_class: 확인할 클래스 ID (0~88)

    Returns:
        stats: 처리 통계 딕셔너리
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"클래스 {target_class} 없는 이미지 검색 시작: {input_path}")

    # 결과 파일 경로 설정
    missing_class_list_path = output_path / f'missing_class_{target_class}.txt'
    has_class_list_path = output_path / f'has_class_{target_class}.txt'
    error_log_path = output_path / 'errors.txt'

    # 통계 변수 초기화
    stats = {
        'total_cnt': 0,              # 전체 처리한 파일 수
        'missing_class_cnt': 0,      # 대상 클래스가 없는 이미지
        'has_class_cnt': 0,          # 대상 클래스가 있는 이미지
        'no_label_cnt': 0,           # 라벨 파일이 없는 이미지
        'empty_label_cnt': 0,        # 어노테이션이 없는 이미지 (배경)
        'error_cnt': 0,              # 에러 발생 수
        'target_class': target_class,
    }

    # 파일 리스트 초기화
    with open(missing_class_list_path, 'w', encoding='utf-8') as f:
        f.write(f"# 클래스 {target_class}가 없는 이미지 파일 목록\n")

    with open(has_class_list_path, 'w', encoding='utf-8') as f:
        f.write(f"# 클래스 {target_class}가 있는 이미지 파일 목록\n")

    # 에러 로그 파일 초기화
    with open(error_log_path, 'w', encoding='utf-8') as f:
        f.write("에러 로그\n")
        f.write("=" * 50 + "\n")

    # 전체 파일 수 계산 (폴더 또는 파일 리스트 지원)
    all_files, _ = collect_image_files_from_source(input_path)
    total_files = len(all_files)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")

    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 입력 경로 순회
    logger.info(f"전체 {total_files}개 파일 처리 시작...")

    for full_path in all_files:
        stats['total_cnt'] += 1
        progress = (stats['total_cnt'] / total_files) * 100

        label_path = get_label_path_from_image(full_path)

        # 라벨 파일 존재 확인
        if not os.path.isfile(label_path):
            stats['no_label_cnt'] += 1
            stats['missing_class_cnt'] += 1
            with open(missing_class_list_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")
            with open(error_log_path, 'a', encoding='utf-8') as f:
                f.write(f"라벨 파일 없음 - {full_path}\n")
            continue

        # 라벨 파일에서 클래스 확인
        has_target_class = False
        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:  # 빈 파일 처리 (배경 이미지)
                    stats['empty_label_cnt'] += 1
                    stats['missing_class_cnt'] += 1
                    with open(missing_class_list_path, 'a', encoding='utf-8') as mf:
                        mf.write(f"{full_path}\n")
                else:
                    for line_num, line in enumerate(lines, 1):
                        line = line.strip()
                        if not line:
                            continue

                        split_line = line.split()
                        if len(split_line) < 5:  # YOLO 형식은 최소 5개 값 필요
                            logger.warning(f"잘못된 어노테이션 형식 {label_path}:{line_num} - {line}")
                            continue

                        try:
                            class_id = int(float(split_line[0]))
                            if class_id == target_class:
                                has_target_class = True
                                break
                        except (ValueError, IndexError) as e:
                            logger.warning(f"어노테이션 파싱 오류 {label_path}:{line_num} - {e}")
                            continue

                    # 결과에 따라 분류
                    if has_target_class:
                        stats['has_class_cnt'] += 1
                        with open(has_class_list_path, 'a', encoding='utf-8') as f:
                            f.write(f"{full_path}\n")
                    else:
                        stats['missing_class_cnt'] += 1
                        with open(missing_class_list_path, 'a', encoding='utf-8') as f:
                            f.write(f"{full_path}\n")

        except Exception as e:
            logger.error(f"라벨 파일 처리 오류 {label_path}: {e}")
            stats['error_cnt'] += 1
            with open(error_log_path, 'a', encoding='utf-8') as f:
                f.write(f"라벨 처리 오류 - {label_path}: {e}\n")
            continue

        # 진행률 표시 (1000개마다 로그)
        if stats['total_cnt'] % 1000 == 0:
            logger.info(f"진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files})")

        print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
              f"클래스 없음: {stats['missing_class_cnt']} | "
              f"클래스 있음: {stats['has_class_cnt']}", end='')

    print("\n")  # 진행률 표시 줄바꿈

    logger.info(f"클래스 {target_class} 검색 완료")
    logger.info(f"전체 파일: {stats['total_cnt']}개")
    logger.info(f"클래스 없음: {stats['missing_class_cnt']}개")
    logger.info(f"클래스 있음: {stats['has_class_cnt']}개")

    return stats

def find_missing_labels(input_path, output_path):
    """
    JPEGImages에 이미지는 있지만 labels에 대응하는 txt 파일이 없는 데이터 리스트를 생성하는 함수

    Args:
        input_path: 입력 데이터셋 경로 (JPEGImages 폴더가 포함된 상위 경로)
        output_path: 출력 저장 경로

    Returns:
        stats: 처리 통계 딕셔너리
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"라벨 미존재 이미지 검색 시작: {input_path}")

    # 결과 파일 경로 설정
    missing_label_list_path = output_path / 'missing_labels.txt'
    has_label_list_path = output_path / 'has_labels.txt'
    missing_label_detail_path = output_path / 'missing_labels_detail.txt'

    # 통계 변수 초기화
    stats = {
        'total_cnt': 0,              # 전체 처리한 이미지 파일 수
        'missing_label_cnt': 0,      # 라벨 파일이 없는 이미지 수
        'has_label_cnt': 0,          # 라벨 파일이 있는 이미지 수
        'error_cnt': 0,              # 에러 발생 수
        'dir_stats': defaultdict(lambda: {'total': 0, 'missing': 0}),  # 디렉토리별 통계
    }

    # 파일 리스트 초기화
    with open(missing_label_list_path, 'w', encoding='utf-8') as f:
        f.write("# JPEGImages에 이미지는 있지만 labels에 txt 파일이 없는 목록\n")

    with open(has_label_list_path, 'w', encoding='utf-8') as f:
        f.write("# JPEGImages에 이미지가 있고 labels에 txt 파일도 있는 목록\n")

    with open(missing_label_detail_path, 'w', encoding='utf-8') as f:
        f.write("# 라벨 미존재 이미지 상세 정보\n")
        f.write("# 형식: 이미지경로 | 예상라벨경로\n")
        f.write("=" * 80 + "\n")

    # 전체 파일 수 계산 (폴더 또는 파일 리스트 지원)
    all_files, _ = collect_image_files_from_source(input_path)
    total_files = len(all_files)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")

    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 입력 경로 순회
    logger.info(f"전체 {total_files}개 파일 처리 시작...")

    for full_path in all_files:
        stats['total_cnt'] += 1
        progress = (stats['total_cnt'] / total_files) * 100

        label_path = get_label_path_from_image(full_path)

        # 디렉토리별 통계를 위한 경로 추출 (폴더 입력이면 상대경로, 파일 리스트면 상위 디렉토리명 사용)
        if os.path.isdir(input_path):
            rel_dir = os.path.relpath(os.path.dirname(full_path), input_path)
        else:
            rel_dir = os.path.basename(os.path.dirname(full_path))
        stats['dir_stats'][rel_dir]['total'] += 1

        # 라벨 파일 존재 확인
        if not os.path.isfile(label_path):
            stats['missing_label_cnt'] += 1
            stats['dir_stats'][rel_dir]['missing'] += 1

            with open(missing_label_list_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")

            with open(missing_label_detail_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path} | {label_path}\n")
        else:
            stats['has_label_cnt'] += 1
            with open(has_label_list_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")

        # 진행률 표시 (1000개마다 로그)
        if stats['total_cnt'] % 1000 == 0:
            logger.info(f"진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files})")

        print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
              f"라벨 없음: {stats['missing_label_cnt']} | "
              f"라벨 있음: {stats['has_label_cnt']}", end='')

    print("\n")  # 진행률 표시 줄바꿈

    # 디렉토리별 통계 로그 및 파일 출력
    if stats['missing_label_cnt'] > 0:
        with open(missing_label_detail_path, 'a', encoding='utf-8') as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write("# 디렉토리별 라벨 미존재 통계\n")
            f.write("=" * 80 + "\n")
            for dir_name in sorted(stats['dir_stats'].keys()):
                dir_stat = stats['dir_stats'][dir_name]
                if dir_stat['missing'] > 0:
                    f.write(f"{dir_name}: {dir_stat['missing']}/{dir_stat['total']}개 "
                            f"({dir_stat['missing']/dir_stat['total']*100:.1f}%)\n")

    logger.info(f"라벨 미존재 이미지 검색 완료")
    logger.info(f"전체 파일: {stats['total_cnt']}개")
    logger.info(f"라벨 없음: {stats['missing_label_cnt']}개")
    logger.info(f"라벨 있음: {stats['has_label_cnt']}개")

    return stats

def create_limited_dataset(input_path, output_path, num_files, keyword=None, background_only=False, target_classes=None, class_filter_mode='or'):
    """
    전체 데이터셋에서 지정된 개수의 파일을 파일명 패턴 분포에 맞게 선택하여 리스트 생성

    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 저장 경로
        num_files: 선택할 파일 개수
        keyword: 파일명 필터링 키워드 (None이면 모든 파일 포함, 한글/특수문자 지원)
        background_only: True일 경우 배경 이미지(어노테이션 없음)만 추출
        target_classes: 필터링할 클래스 ID 리스트 (None이면 모든 클래스 포함)
        class_filter_mode: 'and' - 모든 클래스 포함 이미지만 선택, 'or' - 각 클래스별 균등 분배
    """
    import random
    import numpy as np
    from pathlib import Path
    from collections import defaultdict
    
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"제한된 데이터셋 생성 시작: {num_files}개 파일")
    if keyword:
        logger.info(f"파일명 필터 키워드: '{keyword}'")
    if background_only:
        logger.info("배경 이미지(어노테이션 없음)만 추출 모드")
    if target_classes:
        logger.info(f"클래스 필터링: {target_classes} (모드: {class_filter_mode})")
    
    # 결과 파일 경로 설정
    limited_list_path = output_path / 'limited_dataset.txt'
    limited_annotation_path = output_path / 'limited_annotation.txt'
    
    # 통계 변수 초기화
    obj_annotation = np.zeros(90)
    
    stats = {
        'total_cnt': 0,           # 전체 처리한 파일 수
        'selected_cnt': 0,        # 선택된 파일 수
        'no_label_cnt': 0,        # 라벨 파일이 없는 이미지
        'empty_label_cnt': 0,     # 어노테이션이 없는 이미지
        'error_cnt': 0,           # 에러 발생 수
        'total_annotations': 0,   # 선택된 파일의 총 어노테이션 수
        'created_labels': 0,      # 새로 생성된 라벨 파일
        'obj_annotation': obj_annotation,
        'group_stats': {},        # 그룹별 통계 추가
        'filtered_cnt': 0,        # 키워드 필터링으로 제외된 파일 수
    }
    
    # 전체 파일 리스트 수집 (폴더 또는 파일 리스트 지원)
    print(f"입력 경로에서 이미지 파일 찾는 중...")
    all_files, filtered_cnt = collect_image_files_from_source(input_path, keyword)
    stats['filtered_cnt'] = filtered_cnt

    total_available = len(all_files)
    logger.info(f"총 {total_available}개의 이미지 파일 발견")

    # 배경 이미지만 필터링
    if background_only:
        print(f"배경 이미지(어노테이션 없음)만 필터링 중...")
        background_files = []
        for i, full_path in enumerate(all_files):
            if (i + 1) % 100 == 0:
                print(f"\r배경 필터링 진행률: {(i+1)/len(all_files)*100:.1f}% ({i+1}/{len(all_files)})", end='')

            label_path = get_label_path_from_image(full_path)
            is_background = False

            if not os.path.isfile(label_path):
                is_background = True
            else:
                try:
                    with open(label_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if not lines or all(not line.strip() for line in lines):
                            is_background = True
                except Exception:
                    pass

            if is_background:
                background_files.append(full_path)

        print(f"\r배경 필터링 완료: {len(background_files)}/{len(all_files)}개 배경 이미지 발견     ")
        all_files = background_files
        total_available = len(all_files)
        logger.info(f"배경 이미지 필터링 완료: {total_available}개")

    # 클래스 필터링
    if target_classes:
        print(f"클래스 필터링 중 (모드: {class_filter_mode})...")

        # 각 파일의 클래스 정보 수집
        file_classes = {}  # {file_path: set(class_ids)}
        for i, full_path in enumerate(all_files):
            if (i + 1) % 100 == 0:
                print(f"\r클래스 분석 진행률: {(i+1)/len(all_files)*100:.1f}% ({i+1}/{len(all_files)})", end='')

            label_path = get_label_path_from_image(full_path)
            classes_in_file = set()

            if os.path.isfile(label_path):
                try:
                    with open(label_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        for line in lines:
                            split_line = line.strip().split()
                            if split_line and len(split_line) >= 5:
                                try:
                                    class_id = int(float(split_line[0]))
                                    if 0 <= class_id < 89:
                                        classes_in_file.add(class_id)
                                except (ValueError, IndexError):
                                    continue
                except Exception:
                    pass

            if classes_in_file:  # 클래스가 있는 파일만 저장
                file_classes[full_path] = classes_in_file

        print(f"\r클래스 분석 완료: {len(file_classes)}개 파일에서 클래스 발견     ")

        if class_filter_mode == 'and':
            # AND 모드: 모든 지정 클래스가 포함된 파일만 선택
            target_set = set(target_classes)
            filtered_files = []

            for file_path, classes in file_classes.items():
                if target_set.issubset(classes):  # 모든 target_classes가 포함되어 있는지 확인
                    filtered_files.append(file_path)

            all_files = filtered_files
            logger.info(f"AND 모드 필터링: {len(all_files)}개 파일이 모든 클래스 {target_classes} 포함")
            print(f"AND 모드 필터링 완료: {len(all_files)}개 파일이 클래스 {target_classes}를 모두 포함")

        elif class_filter_mode == 'or':
            # OR 모드: 각 클래스별로 균등하게 파일 분배
            class_files = {cls: [] for cls in target_classes}  # {class_id: [file_paths]}

            # 각 클래스별로 파일 분류
            for file_path, classes in file_classes.items():
                for cls in target_classes:
                    if cls in classes:
                        class_files[cls].append(file_path)

            # 각 클래스별 파일 수 로깅
            for cls, files in class_files.items():
                logger.info(f"클래스 {cls}: {len(files)}개 파일")
                print(f"클래스 {cls}: {len(files)}개 파일")

            # 각 클래스당 선택할 파일 수 계산
            files_per_class = num_files // len(target_classes)
            remainder = num_files % len(target_classes)

            # 각 클래스별로 파일 선택 (OR 모드에서는 그룹화 없이 바로 선택)
            selected_files = []
            for i, cls in enumerate(target_classes):
                # 나머지는 앞쪽 클래스에 분배
                count_to_select = files_per_class + (1 if i < remainder else 0)

                available_files = class_files[cls]
                if len(available_files) == 0:
                    logger.warning(f"클래스 {cls}에 해당하는 파일이 없습니다.")
                    continue

                # 등간격 샘플링
                if count_to_select > len(available_files):
                    count_to_select = len(available_files)
                    logger.warning(f"클래스 {cls}: 요청 파일 수보다 가용 파일이 적음 ({len(available_files)}개)")

                indices = np.linspace(0, len(available_files) - 1, count_to_select, dtype=int)
                sampled_files = [available_files[idx] for idx in indices]
                selected_files.extend(sampled_files)

                logger.info(f"클래스 {cls}: {count_to_select}개 파일 선택")

            # OR 모드에서는 선택된 파일로 all_files를 대체하고,
            # 이후 그룹화/샘플링을 건너뛰기 위해 플래그 설정
            all_files = selected_files
            logger.info(f"OR 모드 필터링 완료: 총 {len(all_files)}개 파일 선택")
            print(f"OR 모드 필터링 완료: 총 {len(all_files)}개 파일 선택")

        total_available = len(all_files)

    if total_available == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None
    
    # 요청한 파일 수가 전체 파일 수보다 많은 경우 처리
    if num_files > total_available:
        print(f"경고: 요청한 파일 수({num_files})가 가용 파일 수({total_available})보다 많습니다.")
        choice = input("전체 가용 파일을 사용하시겠습니까? (y/n): ")
        if choice.lower() != 'y':
            return None
        num_files = total_available

    # OR 모드에서는 이미 파일 선택이 완료되었으므로 그룹화 건너뛰기
    if target_classes and class_filter_mode == 'or':
        selected_files = all_files
        group_counts = {}
    else:
        # 파일 그룹화 (자동 감지)
        groups = defaultdict(list)

        # 샘플 파일로 패턴 감지
        sample_size = min(50, len(all_files))
        sample_files = random.sample(all_files, sample_size)
        sample_names = [os.path.basename(f) for f in sample_files]

        # 패턴 시도
        patterns = [
            (r'Auto_([\d\.]+)-\d+_(\d+)_', '아이피_날짜'),
            (r'(\[\d\])[\w_-]+', '접두어'),
            (r'(\d{14})', '날짜시간'),
            (r'_(\d+)_(\d+)_(\d+)\.jpg$', '일련번호')
        ]

        best_pattern = None
        best_success_rate = 0

        for pattern, pattern_name in patterns:
            success_count = 0
            for name in sample_names:
                if re.search(pattern, name):
                    success_count += 1

            success_rate = success_count / sample_size
            if success_rate > best_success_rate:
                best_success_rate = success_rate
                best_pattern = pattern

        # 최적 패턴으로 그룹화
        if best_pattern and best_success_rate > 0.5:
            for file_path in all_files:
                file_name = os.path.basename(file_path)
                match = re.search(best_pattern, file_name)
                if match:
                    group_key = '_'.join(match.groups())
                    groups[group_key].append(file_path)
                else:
                    groups['기타'].append(file_path)
        else:
            # 패턴이 불분명하면 파일명 접두어로 그룹화
            for file_path in all_files:
                file_name = os.path.basename(file_path)
                prefix = file_name[:min(15, len(file_name))]
                groups[prefix].append(file_path)

        logger.info(f"파일명 패턴에 따라 {len(groups)}개의 그룹으로 분류")

        # 각 그룹에서 비율에 맞게 샘플링
        selected_files = []
        group_counts = {}

        total_files = sum(len(files) for files in groups.values())

        for group_name, files in groups.items():
            group_ratio = len(files) / total_files
            group_sample_count = int(num_files * group_ratio)

            if group_sample_count == 0 and len(files) > 0:
                group_sample_count = 1

            if group_sample_count > len(files):
                group_sample_count = len(files)

            # 등간격 샘플링으로 전체 데이터에서 균등하게 분산 추출
            if group_sample_count > 0:
                indices = np.linspace(0, len(files) - 1, group_sample_count, dtype=int)
                sampled_files = [files[i] for i in indices]
            else:
                sampled_files = []

            selected_files.extend(sampled_files)
            group_counts[group_name] = group_sample_count

        # 반올림 오차 조정
        if len(selected_files) < num_files:
            remaining = num_files - len(selected_files)
            remaining_files = [f for group in groups.values() for f in group if f not in selected_files]
            if remaining_files:
                additional = random.sample(remaining_files, min(remaining, len(remaining_files)))
                selected_files.extend(additional)
        elif len(selected_files) > num_files:
            selected_files = random.sample(selected_files, num_files)

        stats['group_stats'] = group_counts
    
    # 선택된 파일 처리
    with open(limited_list_path, 'w', encoding='utf-8') as f:
        pass
    
    logger.info(f"{len(selected_files)}개 파일 처리 시작...")
    
    for i, full_path in enumerate(selected_files):
        stats['total_cnt'] += 1
        stats['selected_cnt'] += 1
        progress = (i + 1) / len(selected_files) * 100
        
        # 라벨 파일 경로
        label_path = get_label_path_from_image(full_path)
        
        # 라벨 파일 존재 확인 및 처리
        if not os.path.isfile(label_path):
            if create_empty_label(label_path, logger):
                stats['created_labels'] += 1
                stats['no_label_cnt'] += 1
            else:
                stats['error_cnt'] += 1
                continue
        
        # 어노테이션 처리
        current_annotation = np.zeros(90)
        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    stats['empty_label_cnt'] += 1
                else:
                    for line in lines:
                        split_line = line.strip().split()
                        if not split_line or len(split_line) < 5:
                            continue
                        try:
                            class_id = int(float(split_line[0]))
                            if 0 <= class_id < 89:
                                current_annotation[0] += 1
                                current_annotation[class_id + 1] += 1
                        except (ValueError, IndexError):
                            continue
        except Exception as e:
            logger.error(f"어노테이션 처리 오류 {label_path}: {e}")
            stats['error_cnt'] += 1
            continue
        
        # 결과 저장
        with open(limited_list_path, 'a', encoding='utf-8') as f:
            f.write(f"{full_path}\n")
        
        stats['obj_annotation'] += current_annotation
        stats['total_annotations'] += current_annotation[0]
        
        print(f"\r진행률: {progress:.1f}% ({i+1}/{len(selected_files)}) | "
              f"처리: {stats['selected_cnt']} | "
              f"어노테이션: {stats['total_annotations']} | "
              f"라벨 없음: {stats['no_label_cnt']} | "
              f"빈 라벨: {stats['empty_label_cnt']}", end='')
    
    print("\n")
    
    # 최종 통계 저장
    np.savetxt(limited_annotation_path, stats['obj_annotation'], fmt='%2d', 
               delimiter=',', header='limited dataset annotation')
    
    # 그룹별 선택 통계 저장
    group_stats_path = output_path / 'group_distribution.txt'
    with open(group_stats_path, 'w', encoding='utf-8') as f:
        f.write("파일명 패턴별 선택 파일 통계:\n")
        for group_name, count in stats['group_stats'].items():
            total_in_group = len(groups[group_name])
            f.write(f"{group_name}: {count}/{total_in_group} ({count/total_in_group*100:.1f}%)\n")
    
    logger.info("제한된 데이터셋 생성 완료")
    return stats

def create_balanced_class_dataset(input_path, output_path, num_files, target_classes):
    """
    클래스 분포와 DB 분포를 균등하게 맞춰서 제한된 데이터셋 생성

    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 저장 경로
        num_files: 선택할 총 파일 개수
        target_classes: 균등화할 클래스 ID 리스트 (예: [0, 1, 2, 3])

    Returns:
        stats: 처리 통계 딕셔너리
    """
    import random
    import numpy as np
    from pathlib import Path
    from collections import defaultdict

    def extract_db_name(image_path, input_path):
        """이미지 경로에서 DB 폴더명 추출"""
        try:
            rel_path = os.path.relpath(image_path, input_path)
            # 첫 번째 폴더명을 DB 이름으로 사용
            db_name = rel_path.split(os.sep)[0]
            return db_name
        except:
            return "unknown"

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"클래스 분포 균등화 데이터셋 생성 시작: {num_files}개 파일")
    logger.info(f"균등화 대상 클래스: {target_classes}")

    # 결과 파일 경로 설정
    balanced_list_path = output_path / 'balanced_dataset.txt'
    balanced_annotation_path = output_path / 'balanced_annotation.txt'
    balanced_stats_path = output_path / 'balanced_stats.txt'

    # 통계 변수 초기화
    obj_annotation = np.zeros(90)

    stats = {
        'total_cnt': 0,
        'selected_cnt': 0,
        'error_cnt': 0,
        'total_annotations': 0,
        'obj_annotation': obj_annotation,
        'class_stats': {},  # 클래스별 선택된 이미지 수
        'class_distribution': {},  # 전체 클래스 분포
        'db_distribution': {},  # DB별 분포
    }

    # 1단계: 전체 이미지 수집 (폴더 또는 파일 리스트 지원)
    print(f"입력 경로에서 이미지 파일 찾는 중...")
    all_files, _ = collect_image_files_from_source(input_path)

    total_available = len(all_files)
    logger.info(f"총 {total_available}개의 이미지 파일 발견")

    if total_available == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 2단계: 각 이미지가 포함하는 클래스 및 DB 분석
    print(f"\n각 이미지의 클래스 및 DB 정보 분석 중...")
    # {class_id: {db_name: [image_paths]}} 구조
    class_db_to_images = defaultdict(lambda: defaultdict(list))
    image_class_count = defaultdict(int)  # 각 클래스를 포함하는 이미지 개수
    db_set = set()  # 발견된 모든 DB 이름

    for i, image_path in enumerate(all_files):
        if (i + 1) % 100 == 0:
            print(f"\r진행률: {(i+1)/total_available*100:.1f}% ({i+1}/{total_available})", end='')

        # DB 이름 추출
        db_name = extract_db_name(image_path, input_path)
        db_set.add(db_name)

        label_path = get_label_path_from_image(image_path)

        if not os.path.isfile(label_path):
            continue

        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    continue

                # 이 이미지가 포함하는 클래스 수집
                image_classes = set()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 5:
                        class_id = int(parts[0])
                        image_classes.add(class_id)

                # 각 클래스별, DB별로 이미지 기록
                for class_id in image_classes:
                    if class_id in target_classes:
                        class_db_to_images[class_id][db_name].append(image_path)
                        image_class_count[class_id] += 1

        except Exception as e:
            logger.warning(f"라벨 파일 읽기 실패: {label_path} - {e}")
            continue

    print(f"\r클래스 및 DB 분석 완료: 100.0%                    ")

    # 발견된 DB 출력
    print(f"\n발견된 DB: {sorted(db_set)}")
    logger.info(f"발견된 DB 개수: {len(db_set)}, DB 목록: {sorted(db_set)}")

    # 클래스별 분포 출력
    print(f"\n클래스별 이미지 분포:")
    for class_id in sorted(target_classes):
        count = image_class_count.get(class_id, 0)
        stats['class_distribution'][class_id] = count
        print(f"  클래스 {class_id}: {count}개 이미지")

        # 클래스별 DB 분포도 출력
        if class_id in class_db_to_images:
            for db_name in sorted(class_db_to_images[class_id].keys()):
                db_count = len(class_db_to_images[class_id][db_name])
                print(f"    └─ {db_name}: {db_count}개")

    if not class_db_to_images:
        logger.error("균등화 대상 클래스를 포함하는 이미지가 없습니다.")
        return None

    # 3단계: 클래스별 + DB별 균등 샘플링
    print(f"\n클래스별 + DB별 균등 샘플링 시작...")
    selected_images = set()

    # 각 클래스, 각 DB에서 이미지를 랜덤하게 섞기
    for class_id in target_classes:
        for db_name in class_db_to_images[class_id]:
            random.shuffle(class_db_to_images[class_id][db_name])

    # 각 클래스, 각 DB별 인덱스 관리
    class_db_indices = defaultdict(lambda: defaultdict(int))

    # 목표 개수에 도달할 때까지 반복 (라운드 로빈)
    round_num = 0
    while len(selected_images) < num_files:
        added_this_round = 0

        # 각 클래스를 순회
        for class_id in target_classes:
            if len(selected_images) >= num_files:
                break

            # 이 클래스의 각 DB를 순회
            db_names = sorted(class_db_to_images[class_id].keys())
            for db_name in db_names:
                if len(selected_images) >= num_files:
                    break

                # 이 클래스, 이 DB에서 아직 선택할 이미지가 있는지 확인
                images_in_class_db = class_db_to_images[class_id][db_name]
                current_index = class_db_indices[class_id][db_name]

                if current_index < len(images_in_class_db):
                    image_path = images_in_class_db[current_index]

                    # 중복 체크 후 추가
                    if image_path not in selected_images:
                        selected_images.add(image_path)
                        added_this_round += 1

                    class_db_indices[class_id][db_name] += 1

        round_num += 1

        # 더 이상 추가할 이미지가 없으면 종료
        if added_this_round == 0:
            logger.warning(f"목표 개수({num_files})에 도달하지 못했습니다. 선택된 개수: {len(selected_images)}")
            break

    selected_files = list(selected_images)
    logger.info(f"{len(selected_files)}개 이미지 선택 완료 (Round: {round_num})")

    # 4단계: 선택된 이미지의 클래스별, DB별 통계
    selected_class_count = defaultdict(int)
    selected_db_count = defaultdict(int)
    selected_class_db_count = defaultdict(lambda: defaultdict(int))

    for image_path in selected_files:
        # DB 이름 추출
        db_name = extract_db_name(image_path, input_path)
        selected_db_count[db_name] += 1

        label_path = get_label_path_from_image(image_path)

        if not os.path.isfile(label_path):
            continue

        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                image_classes = set()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 5:
                        class_id = int(parts[0])
                        image_classes.add(class_id)

                for class_id in image_classes:
                    if class_id in target_classes:
                        selected_class_count[class_id] += 1
                        selected_class_db_count[class_id][db_name] += 1
        except:
            pass

    print(f"\n선택된 이미지의 클래스별 분포:")
    for class_id in sorted(target_classes):
        count = selected_class_count.get(class_id, 0)
        stats['class_stats'][class_id] = count
        percentage = count / len(selected_files) * 100 if selected_files else 0
        print(f"  클래스 {class_id}: {count}개 ({percentage:.1f}%)")

        # 클래스별 DB 분포 출력
        for db_name in sorted(selected_class_db_count[class_id].keys()):
            db_count = selected_class_db_count[class_id][db_name]
            print(f"    └─ {db_name}: {db_count}개")

    print(f"\n선택된 이미지의 DB별 분포:")
    for db_name in sorted(selected_db_count.keys()):
        count = selected_db_count[db_name]
        stats['db_distribution'][db_name] = count
        percentage = count / len(selected_files) * 100 if selected_files else 0
        print(f"  {db_name}: {count}개 ({percentage:.1f}%)")

    # 5단계: 선택된 파일 처리 및 저장
    print(f"\n선택된 파일 처리 중...")
    with open(balanced_list_path, 'w', encoding='utf-8') as f:
        pass

    for i, full_path in enumerate(selected_files):
        if (i + 1) % 100 == 0:
            print(f"\r처리 진행률: {(i+1)/len(selected_files)*100:.1f}% ({i+1}/{len(selected_files)})", end='')

        stats['total_cnt'] += 1
        stats['selected_cnt'] += 1

        # 라벨 파일 경로
        label_path = get_label_path_from_image(full_path)

        # 어노테이션 처리
        current_annotation = np.zeros(90)
        try:
            if os.path.isfile(label_path):
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split()
                        if len(parts) >= 5:
                            class_id = int(parts[0])
                            if 0 <= class_id < 90:
                                current_annotation[class_id] += 1
                                stats['obj_annotation'][class_id] += 1
                                stats['total_annotations'] += 1
        except Exception as e:
            logger.warning(f"어노테이션 처리 실패: {label_path} - {e}")
            stats['error_cnt'] += 1

        # 리스트 파일에 추가
        with open(balanced_list_path, 'a', encoding='utf-8') as f:
            f.write(full_path + '\n')

        # 어노테이션 파일에 추가
        with open(balanced_annotation_path, 'a', encoding='utf-8') as f:
            annotation_str = ' '.join(map(str, current_annotation.astype(int)))
            f.write(f"{full_path} {annotation_str}\n")

    print(f"\r처리 완료: 100.0%                    ")

    # 통계 파일 저장
    with open(balanced_stats_path, 'w', encoding='utf-8') as f:
        f.write("=== 클래스 분포 균등화 데이터셋 통계 ===\n\n")
        f.write(f"총 선택된 파일 수: {stats['selected_cnt']}\n")
        f.write(f"총 어노테이션 수: {stats['total_annotations']}\n")
        f.write(f"에러 발생 수: {stats['error_cnt']}\n\n")

        f.write("전체 클래스 분포 (분석 전):\n")
        for class_id in sorted(target_classes):
            count = stats['class_distribution'].get(class_id, 0)
            f.write(f"  클래스 {class_id}: {count}개\n")

        f.write("\n선택된 데이터의 클래스 분포:\n")
        for class_id in sorted(target_classes):
            count = stats['class_stats'].get(class_id, 0)
            percentage = count / stats['selected_cnt'] * 100 if stats['selected_cnt'] > 0 else 0
            f.write(f"  클래스 {class_id}: {count}개 ({percentage:.1f}%)\n")

            # 클래스별 DB 분포
            if class_id in selected_class_db_count:
                for db_name in sorted(selected_class_db_count[class_id].keys()):
                    db_count = selected_class_db_count[class_id][db_name]
                    f.write(f"    └─ {db_name}: {db_count}개\n")

        f.write("\n선택된 데이터의 DB 분포:\n")
        for db_name in sorted(stats['db_distribution'].keys()):
            count = stats['db_distribution'][db_name]
            percentage = count / stats['selected_cnt'] * 100 if stats['selected_cnt'] > 0 else 0
            f.write(f"  {db_name}: {count}개 ({percentage:.1f}%)\n")

    logger.info("클래스 분포 균등화 데이터셋 생성 완료")
    return stats

def parse_expand_target(user_input, base_count):
    """
    증강 목표 입력값을 최종 목표 개수로 변환

    지원 형식:
        '300'   -> 최종 총 300장
        '3x'    -> 최종 총 base_count * 3 장
        '3배'   -> 최종 총 base_count * 3 장
        '2.5x'  -> 최종 총 base_count * 2.5 장 (내림)

    Returns:
        (target_count, err_msg) - 실패 시 (None, 오류메시지)
    """
    if not user_input:
        return None, "입력값이 비어 있습니다."

    text = user_input.strip().lower().replace(' ', '')
    is_multiplier = False

    for suffix in ('배', 'x', '*'):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            is_multiplier = True
            break

    try:
        value = float(text)
    except ValueError:
        return None, f"올바른 숫자 형식이 아닙니다: '{user_input}' (예: 300, 3x, 3배)"

    if value <= 0:
        return None, "0보다 큰 값을 입력해야 합니다."

    if is_multiplier:
        target_count = int(base_count * value)
    else:
        target_count = int(value)

    if target_count <= 0:
        return None, "계산된 목표 개수가 0입니다."

    return target_count, None


def collect_file_class_counts(image_files, logger=None):
    """
    이미지별 클래스 인스턴스 수 집계

    Returns:
        (file_class_counts, missing_label_files)
            file_class_counts   - {image_path: {class_id: 인스턴스 수}}
            missing_label_files - 라벨 파일이 없는 이미지 경로 리스트
    """
    file_class_counts = {}
    missing_label_files = []

    total = len(image_files)
    for i, img_path in enumerate(image_files):
        if total and (i + 1) % 200 == 0:
            print(f"\r라벨 분석 진행률: {(i+1)/total*100:.1f}% ({i+1}/{total})", end='')

        label_path = get_label_path_from_image(img_path)
        counts = defaultdict(int)

        if not os.path.isfile(label_path):
            missing_label_files.append(img_path)
        else:
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        split_line = line.strip().split()
                        if not split_line or len(split_line) < 5:
                            continue
                        try:
                            class_id = int(float(split_line[0]))
                        except (ValueError, IndexError):
                            continue
                        if 0 <= class_id < 89:
                            counts[class_id] += 1
            except Exception as e:
                if logger:
                    logger.error(f"라벨 읽기 오류 {label_path}: {e}")

        file_class_counts[img_path] = dict(counts)

    if total:
        print(f"\r라벨 분석 완료: {total}개 파일 분석                    ")

    return file_class_counts, missing_label_files


def parse_class_id_list(user_input):
    """
    클래스 ID 입력 문자열을 정수 리스트로 변환

    지원 형식:
        '0'        -> [0]
        '0,2,5'    -> [0, 2, 5]
        '0-3'      -> [0, 1, 2, 3]
        '0-2,7'    -> [0, 1, 2, 7]

    Returns:
        (class_ids, err_msg) - 실패 시 (None, 오류메시지)
    """
    if not user_input or not user_input.strip():
        return None, "클래스 ID를 입력해야 합니다."

    class_ids = []
    for token in user_input.replace(' ', '').split(','):
        if not token:
            continue

        if '-' in token:  # 범위 입력 (예: 0-3)
            start_text, _, end_text = token.partition('-')
            try:
                start, end = int(start_text), int(end_text)
            except ValueError:
                return None, f"올바른 클래스 ID 형식이 아닙니다: '{token}' (예: 0,2,5 또는 0-3)"
            if start > end:
                start, end = end, start
            candidates = list(range(start, end + 1))
        else:
            try:
                candidates = [int(token)]
            except ValueError:
                return None, f"올바른 클래스 ID 형식이 아닙니다: '{token}' (예: 0,2,5 또는 0-3)"

        for class_id in candidates:
            if not (0 <= class_id < 89):
                return None, f"클래스 ID 범위를 벗어났습니다: {class_id} (사용 가능: 0~88)"
            if class_id not in class_ids:
                class_ids.append(class_id)

    if not class_ids:
        return None, "클래스 ID를 입력해야 합니다."

    return class_ids, None


def select_files_by_target_classes(base_files, file_class_counts, target_classes, match_mode='any'):
    """
    지정한 클래스가 포함된 이미지만 골라낸다

    Args:
        base_files: 원본 이미지 경로 리스트
        file_class_counts: {image_path: {class_id: 인스턴스 수}}
        target_classes: 대상 클래스 ID 리스트
        match_mode: 'any' - 하나라도 포함(OR) / 'all' - 모두 포함(AND)

    Returns:
        (matched_files, skipped_files)
    """
    target_set = set(target_classes)
    matched, skipped = [], []

    for img_path in base_files:
        classes = set((file_class_counts.get(img_path) or {}).keys())
        if match_mode == 'all':
            hit = bool(target_set) and target_set.issubset(classes)
        else:
            hit = bool(target_set & classes)

        (matched if hit else skipped).append(img_path)

    return matched, skipped


def build_duplication_plan(base_files, need_copies, file_class_counts=None, balance_classes=False):
    """
    원본 파일별 복제 횟수 결정

    Args:
        base_files: 원본 이미지 경로 리스트
        need_copies: 추가로 만들어야 할 복사본 수
        file_class_counts: {image_path: {class_id: 인스턴스 수}}
        balance_classes: True면 인스턴스 수가 적은 클래스를 포함한 이미지를 우선 복제

    Returns:
        {image_path: 복제 횟수} (0인 항목은 포함하지 않음)
    """
    plan = defaultdict(int)
    n = len(base_files)

    if need_copies <= 0 or n == 0:
        return dict(plan)

    if balance_classes and file_class_counts:
        # 클래스별 현재 인스턴스 수 / 클래스별 후보 파일 목록
        class_counts = defaultdict(int)
        class_to_files = defaultdict(list)

        for img_path in base_files:
            for class_id, cnt in (file_class_counts.get(img_path) or {}).items():
                class_counts[class_id] += cnt
                class_to_files[class_id].append(img_path)

        if class_counts:
            class_ptr = defaultdict(int)
            for _ in range(need_copies):
                # 가장 인스턴스 수가 적은 클래스부터 채운다
                weakest = min(sorted(class_counts.keys()), key=lambda c: class_counts[c])
                candidates = class_to_files.get(weakest)
                if not candidates:
                    break

                # 후보 파일을 순환하며 고르게 선택
                pick = candidates[class_ptr[weakest] % len(candidates)]
                class_ptr[weakest] += 1

                plan[pick] += 1
                for class_id, cnt in (file_class_counts.get(pick) or {}).items():
                    class_counts[class_id] += cnt

            assigned = sum(plan.values())
            if assigned >= need_copies:
                return dict(plan)
            # 클래스 정보로 다 채우지 못한 경우 나머지는 균등 분배로 보충
            need_copies -= assigned

    # 균등 분배: 전체에 base_repeat회씩, 나머지는 등간격으로 1회 추가
    base_repeat = need_copies // n
    remainder = need_copies % n

    if base_repeat:
        for img_path in base_files:
            plan[img_path] += base_repeat

    if remainder:
        step = n / remainder
        used = set()
        for k in range(remainder):
            idx = int(k * step) % n
            while idx in used:
                idx = (idx + 1) % n
            used.add(idx)
            plan[base_files[idx]] += 1

    return dict(plan)


def build_duplicate_paths(img_path, label_path, dup_index, placement, output_root, taken_paths):
    """
    복사본 이미지/라벨 경로 생성 (파일명만 변경, 확장자/구조 유지)

    Args:
        placement: 'inplace' - 원본과 같은 폴더, 'new' - output_root 아래 새 폴더
        taken_paths: 이번 실행에서 이미 예약된 경로 집합 (중복 방지)
    """
    directory, filename = os.path.split(img_path)
    stem, ext = os.path.splitext(filename)

    if placement == 'inplace':
        img_dir = directory
        label_dir = os.path.dirname(label_path)
    else:
        # 원본의 JPEGImages 이하 구조를 유지해야 labels 매핑이 그대로 동작한다
        if 'JPEGImages' in img_path:
            rel_dir = os.path.dirname(img_path.rsplit('JPEGImages', 1)[1]).strip('/\\')
        else:
            rel_dir = os.path.basename(directory)

        img_dir = os.path.join(output_root, 'JPEGImages', rel_dir) if rel_dir \
            else os.path.join(output_root, 'JPEGImages')
        label_dir = os.path.join(output_root, 'labels', rel_dir) if rel_dir \
            else os.path.join(output_root, 'labels')

    # 파일명 충돌 회피 (이전 실행 결과 / 같은 이름의 다른 원본)
    n = dup_index
    for _ in range(100000):
        new_stem = f"{stem}_dup{n:03d}"
        new_img = os.path.join(img_dir, new_stem + ext)
        new_label = os.path.join(label_dir, new_stem + '.txt')

        if new_img not in taken_paths and not os.path.exists(new_img) and not os.path.exists(new_label):
            taken_paths.add(new_img)
            return new_img, new_label
        n += 1

    return None, None


def replicate_file(src, dst, copy_mode, logger=None):
    """
    파일 1개 복제. hardlink/symlink 실패 시 실제 복사로 폴백

    Returns:
        실제 사용된 방식 문자열 ('copy'/'hardlink'/'symlink'), 실패 시 None
    """
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        if copy_mode == 'hardlink':
            try:
                os.link(src, dst)
                return 'hardlink'
            except (OSError, NotImplementedError, AttributeError) as e:
                if logger:
                    logger.debug(f"하드링크 실패, 복사로 대체: {e}")

        elif copy_mode == 'symlink':
            try:
                os.symlink(os.path.abspath(src), dst)
                return 'symlink'
            except (OSError, NotImplementedError, AttributeError) as e:
                if logger:
                    logger.debug(f"심볼릭 링크 실패, 복사로 대체: {e}")

        shutil.copy2(src, dst)
        return 'copy'

    except Exception as e:
        if logger:
            logger.error(f"파일 복제 실패 {src} -> {dst}: {e}")
        return None


def expand_dataset_by_duplication(input_source, output_path, target_input,
                                  placement='new', copy_mode='copy',
                                  balance_classes=False, include_original_in_list=True,
                                  auto_confirm=False, keyword=None,
                                  target_classes=None, class_match_mode='any'):
    """
    이미지/라벨을 파일명만 바꿔 복제해 데이터셋 수량을 목표치까지 늘리는 함수

    Args:
        input_source: 이미지 폴더 또는 이미지 경로 리스트(.txt)
        output_path: 결과(리스트/통계) 저장 경로. placement='new'면 복사본도 이 아래에 생성
        target_input: 목표 수량 문자열 ('300', '3x', '3배')
        placement: 'new' - 새 폴더에 복사본 생성 / 'inplace' - 원본과 같은 폴더에 생성
        copy_mode: 'copy'(실제 복사) / 'hardlink' / 'symlink' / 'list'(파일 생성 없이 리스트만 중복)
        balance_classes: True면 인스턴스가 적은 클래스를 우선 복제
        include_original_in_list: 최종 리스트에 원본 포함 여부
        auto_confirm: True면 실행 전 확인 프롬프트 생략
        keyword: 파일명 필터 키워드
        target_classes: 증강 대상 클래스 ID 리스트 (None이면 전체 DB 증강).
                        지정하면 해당 클래스가 포함된 이미지만 복제하고,
                        목표 수량도 '증강 대상 수량' 기준으로 계산한다.
        class_match_mode: 'any' - 대상 클래스를 하나라도 포함(OR)
                          'all' - 대상 클래스를 모두 포함(AND)

    Returns:
        stats 딕셔너리 (취소/실패 시 None)
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_path)
    logger.info(f"데이터셋 증강 복제 시작: 목표='{target_input}', 배치={placement}, 방식={copy_mode}")

    # ── 1. 원본 수집 ────────────────────────────────────────────────
    print("입력 경로에서 이미지 파일 찾는 중...")
    base_files, filtered_cnt = collect_image_files_from_source(input_source, keyword)
    base_files.sort()

    base_count = len(base_files)
    if base_count == 0:
        print("오류: 입력 경로에 이미지 파일이 없습니다.")
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    print(f"원본 이미지: {base_count}개 (키워드 제외: {filtered_cnt}개)")
    logger.info(f"원본 이미지 {base_count}개 수집")

    # ── 2. 라벨 분석 (클래스 통계 / 클래스 필터 / 균형 복제용) ──────
    print("라벨 파일 분석 중...")
    file_class_counts, missing_label_files = collect_file_class_counts(base_files, logger)

    if missing_label_files:
        print(f"경고: 라벨 파일이 없는 이미지 {len(missing_label_files)}개 → 복사본은 빈 라벨로 생성됩니다.")
        logger.warning(f"라벨 미존재 이미지 {len(missing_label_files)}개")

    before_class_counts = defaultdict(int)
    for counts in file_class_counts.values():
        for class_id, cnt in counts.items():
            before_class_counts[class_id] += cnt

    # ── 3. 증강 대상 선별 (특정 클래스가 포함된 DB만 증강) ──────────
    if target_classes:
        target_classes = sorted(set(target_classes))
        mode_text = '모두 포함(AND)' if class_match_mode == 'all' else '하나라도 포함(OR)'

        dup_base_files, skipped_files = select_files_by_target_classes(
            base_files, file_class_counts, target_classes, class_match_mode)

        print(f"클래스 필터: {target_classes} - {mode_text}")
        print(f"증강 대상 이미지: {len(dup_base_files)}개 / 증강 제외: {len(skipped_files)}개")
        logger.info(f"클래스 필터 {target_classes}({class_match_mode}): "
                    f"대상 {len(dup_base_files)}개, 제외 {len(skipped_files)}개")

        if not dup_base_files:
            print("오류: 지정한 클래스를 포함한 이미지가 없습니다.")
            print("→ 클래스 ID 또는 매칭 모드(OR/AND)를 다시 확인하세요.")
            logger.error("클래스 필터 결과가 비어 있어 작업을 중단합니다.")
            return None
    else:
        dup_base_files = base_files
        skipped_files = []

    dup_base_count = len(dup_base_files)

    # ── 4. 목표 수량 계산 (클래스 필터 시 '증강 대상 수량' 기준) ────
    target_count, err_msg = parse_expand_target(target_input, dup_base_count)
    if err_msg:
        print(f"오류: {err_msg}")
        return None

    need_copies = target_count - dup_base_count
    if need_copies <= 0:
        base_label = "증강 대상 수량" if target_classes else "원본 수량"
        print(f"목표 수량({target_count})이 {base_label}({dup_base_count}) 이하입니다.")
        print("→ 수량을 줄이려면 메뉴 2(제한된 데이터셋 생성)를 사용하세요.")
        logger.warning(f"목표 수량이 {base_label} 이하여서 작업을 중단합니다.")
        return None

    # ── 5. 복제 계획 수립 ───────────────────────────────────────────
    plan = build_duplication_plan(dup_base_files, need_copies, file_class_counts, balance_classes)
    planned_copies = sum(plan.values())

    repeat_values = [plan.get(f, 0) for f in dup_base_files]
    min_repeat = min(repeat_values) if repeat_values else 0
    max_repeat = max(repeat_values) if repeat_values else 0

    # 예상 디스크 사용량 (실제 복사 모드에서만 의미 있음)
    sample = dup_base_files[:min(50, dup_base_count)]
    sample_bytes = 0
    sample_ok = 0
    for f in sample:
        try:
            sample_bytes += os.path.getsize(f)
            sample_ok += 1
        except OSError:
            continue
    avg_bytes = (sample_bytes / sample_ok) if sample_ok else 0
    est_gb = avg_bytes * planned_copies / (1024 ** 3)

    print(f"\n{'='*60}")
    print("증강 복제 계획")
    print(f"{'='*60}")
    print(f"원본 수량      : {base_count}개")
    if target_classes:
        print(f"클래스 필터    : {target_classes} - "
              f"{'모두 포함(AND)' if class_match_mode == 'all' else '하나라도 포함(OR)'}")
        print(f"증강 대상 수량 : {dup_base_count}개 (증강 제외 {len(skipped_files)}개)")
        print(f"목표 수량      : {target_count}개 "
              f"({target_count/dup_base_count:.2f}배, 증강 대상 기준)")
    else:
        print(f"목표 수량      : {target_count}개 ({target_count/dup_base_count:.2f}배)")
    print(f"생성할 복사본  : {planned_copies}개")
    print(f"파일별 복제 횟수: 최소 {min_repeat}회 ~ 최대 {max_repeat}회")
    print(f"복제 배분      : {'클래스 균형 우선' if balance_classes else '전체 균등'}")
    print(f"복사본 위치    : {'원본과 동일 폴더 (in-place)' if placement == 'inplace' else str(output_path / 'duplicated')}")
    print(f"복제 방식      : {copy_mode}")
    if copy_mode == 'copy':
        print(f"예상 디스크    : 약 {est_gb:.2f} GB (이미지 기준)")
    elif copy_mode == 'list':
        print("예상 디스크    : 0 (파일 생성 없이 리스트에만 중복 기록)")
    print(f"{'='*60}")

    if not auto_confirm:
        confirm = input("위 계획대로 진행할까요? (y/n): ").strip().lower()
        if confirm != 'y':
            print("작업을 취소했습니다.")
            logger.info("사용자가 작업을 취소했습니다.")
            return None

    # ── 6. 복제 실행 ────────────────────────────────────────────────
    dup_root = str(output_path / 'duplicated') if placement == 'new' else None

    expanded_list_path = output_path / 'expanded_dataset.txt'
    duplicated_list_path = output_path / 'duplicated_only.txt'
    created_files_path = output_path / 'created_files.txt'
    duplication_map_path = output_path / 'duplication_map.txt'
    expanded_annotation_path = output_path / 'expanded_annotation.txt'
    expansion_stats_path = output_path / 'expansion_stats.txt'

    stats = {
        'base_cnt': base_count,
        'dup_base_cnt': dup_base_count,
        'skipped_cnt': len(skipped_files),
        'target_classes': list(target_classes) if target_classes else None,
        'class_match_mode': class_match_mode if target_classes else None,
        'target_cnt': target_count,
        'planned_copies': planned_copies,
        'created_cnt': 0,
        'created_label_cnt': 0,
        'empty_label_cnt': 0,
        'error_cnt': 0,
        'mode_counts': defaultdict(int),
        'before_class_counts': dict(before_class_counts),
        'after_class_counts': {},
        'placement': placement,
        'copy_mode': copy_mode,
        'balance_classes': balance_classes,
        'output_path': str(output_path),
    }

    duplicated_entries = []   # (원본, 복사본)
    created_files = []        # 롤백용: 실제로 만들어진 모든 파일
    taken_paths = set()
    after_class_counts = defaultdict(int, before_class_counts)

    processed = 0
    for img_path in dup_base_files:
        repeat = plan.get(img_path, 0)
        if repeat <= 0:
            continue

        label_path = get_label_path_from_image(img_path)
        label_exists = os.path.isfile(label_path)

        for k in range(1, repeat + 1):
            processed += 1

            if copy_mode == 'list':
                # 파일을 만들지 않고 리스트에만 중복 경로를 기록
                duplicated_entries.append((img_path, img_path))
                stats['created_cnt'] += 1
                stats['mode_counts']['list'] += 1
            else:
                new_img, new_label = build_duplicate_paths(
                    img_path, label_path, k, placement, dup_root, taken_paths)

                if not new_img:
                    logger.error(f"복사본 경로 생성 실패: {img_path}")
                    stats['error_cnt'] += 1
                    continue

                used_mode = replicate_file(img_path, new_img, copy_mode, logger)
                if not used_mode:
                    stats['error_cnt'] += 1
                    continue

                created_files.append(new_img)
                stats['created_cnt'] += 1
                stats['mode_counts'][used_mode] += 1

                # 라벨도 같은 이름으로 복제 (없으면 빈 라벨 생성)
                if label_exists:
                    label_mode = replicate_file(label_path, new_label, copy_mode, logger)
                    if label_mode:
                        created_files.append(new_label)
                        stats['created_label_cnt'] += 1
                    else:
                        stats['error_cnt'] += 1
                else:
                    if create_empty_label(new_label, logger):
                        created_files.append(new_label)
                        stats['empty_label_cnt'] += 1
                    else:
                        stats['error_cnt'] += 1

                duplicated_entries.append((img_path, new_img))

            # 클래스 통계 누적
            for class_id, cnt in (file_class_counts.get(img_path) or {}).items():
                after_class_counts[class_id] += cnt

            if processed % 20 == 0 or processed == planned_copies:
                print(f"\r복제 진행률: {processed/planned_copies*100:.1f}% "
                      f"({processed}/{planned_copies}) | 생성: {stats['created_cnt']} | "
                      f"에러: {stats['error_cnt']}", end='')

    print()
    stats['after_class_counts'] = dict(after_class_counts)

    # ── 7. 결과 파일 저장 ───────────────────────────────────────────
    with open(expanded_list_path, 'w', encoding='utf-8') as f:
        if include_original_in_list:
            for img_path in base_files:
                f.write(f"{img_path}\n")
        for _, dup_path in duplicated_entries:
            f.write(f"{dup_path}\n")

    with open(duplicated_list_path, 'w', encoding='utf-8') as f:
        for _, dup_path in duplicated_entries:
            f.write(f"{dup_path}\n")

    with open(duplication_map_path, 'w', encoding='utf-8') as f:
        f.write("# 원본경로\t복사본경로\n")
        for src, dup_path in duplicated_entries:
            f.write(f"{src}\t{dup_path}\n")

    with open(created_files_path, 'w', encoding='utf-8') as f:
        f.write("# 이번 작업으로 생성된 파일 목록 (롤백용 - 메뉴 14의 '복제 취소'에서 사용)\n")
        for path in created_files:
            f.write(f"{path}\n")

    # 클래스 통계를 기존 포맷(90칸 배열)으로도 저장
    obj_annotation = np.zeros(90)
    for class_id, cnt in after_class_counts.items():
        if 0 <= class_id < 89:
            obj_annotation[class_id + 1] = cnt
    obj_annotation[0] = sum(after_class_counts.values())
    np.savetxt(expanded_annotation_path, obj_annotation, fmt='%2d',
               delimiter=',', header='expanded dataset annotation')
    stats['obj_annotation'] = obj_annotation

    final_total = (base_count if include_original_in_list else 0) + len(duplicated_entries)

    with open(expansion_stats_path, 'w', encoding='utf-8') as f:
        f.write("=== 데이터셋 증강 복제 통계 ===\n\n")
        f.write(f"입력 경로       : {input_source}\n")
        f.write(f"출력 경로       : {output_path}\n")
        f.write(f"복사본 위치     : {'원본과 동일 폴더 (in-place)' if placement == 'inplace' else dup_root}\n")
        f.write(f"복제 방식       : {copy_mode}\n")
        f.write(f"복제 배분       : {'클래스 균형 우선' if balance_classes else '전체 균등'}\n")
        if target_classes:
            f.write(f"증강 대상 클래스: {target_classes} "
                    f"({'모두 포함(AND)' if class_match_mode == 'all' else '하나라도 포함(OR)'})\n")
        else:
            f.write("증강 대상 클래스: 전체 (필터 없음)\n")
        f.write("\n")
        f.write(f"원본 수량       : {base_count}개\n")
        if target_classes:
            f.write(f"증강 대상 수량  : {dup_base_count}개 (증강 제외 {len(skipped_files)}개)\n")
        f.write(f"목표 수량       : {target_count}개\n")
        f.write(f"생성한 복사본   : {stats['created_cnt']}개\n")
        f.write(f"복제한 라벨     : {stats['created_label_cnt']}개\n")
        f.write(f"빈 라벨 생성    : {stats['empty_label_cnt']}개\n")
        f.write(f"에러            : {stats['error_cnt']}개\n")
        f.write(f"최종 리스트 수량: {final_total}개 (원본 포함: {'예' if include_original_in_list else '아니오'})\n\n")

        f.write("클래스별 인스턴스 수 (증강 전 → 증강 후):\n")
        all_classes = sorted(set(before_class_counts) | set(after_class_counts))
        for class_id in all_classes:
            before = before_class_counts.get(class_id, 0)
            after = after_class_counts.get(class_id, 0)
            ratio = (after / before) if before else 0
            f.write(f"  클래스 {class_id}: {before} → {after} ({ratio:.2f}배)\n")

    logger.info(f"증강 복제 완료: 복사본 {stats['created_cnt']}개, 최종 {final_total}개")
    stats['final_total'] = final_total
    return stats


def rollback_duplication(created_files_path):
    """
    created_files.txt에 기록된 파일만 삭제해 증강 작업을 되돌리는 함수

    Returns:
        (deleted_cnt, missing_cnt, error_cnt) / 실패 시 None
    """
    if not os.path.isfile(created_files_path):
        print(f"오류: 파일을 찾을 수 없습니다: {created_files_path}")
        return None

    targets = []
    try:
        with open(created_files_path, 'r', encoding='utf-8') as f:
            for line in f:
                path = line.strip()
                if not path or path.startswith('#'):
                    continue
                targets.append(path)
    except Exception as e:
        print(f"오류: 목록 파일 읽기 실패: {e}")
        return None

    if not targets:
        print("삭제할 파일이 없습니다.")
        return (0, 0, 0)

    existing = [p for p in targets if os.path.isfile(p)]
    print(f"\n삭제 대상: 기록 {len(targets)}개 중 실제 존재 {len(existing)}개")
    for path in existing[:5]:
        print(f"  예시: {path}")
    if len(existing) > 5:
        print(f"  ... 외 {len(existing) - 5}개")

    confirm = input(f"\n위 {len(existing)}개 파일을 삭제할까요? (yes 입력 시 삭제): ").strip().lower()
    if confirm != 'yes':
        print("삭제를 취소했습니다.")
        return None

    deleted_cnt = 0
    missing_cnt = 0
    error_cnt = 0
    touched_dirs = set()

    for path in targets:
        if not os.path.isfile(path):
            missing_cnt += 1
            continue
        try:
            os.remove(path)
            deleted_cnt += 1
            touched_dirs.add(os.path.dirname(path))
        except Exception as e:
            print(f"\n삭제 실패 {path}: {e}")
            error_cnt += 1

    # 비어버린 디렉토리 정리 (하위부터)
    for directory in sorted(touched_dirs, key=len, reverse=True):
        try:
            if os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)
        except OSError:
            pass

    print(f"\n삭제 완료: {deleted_cnt}개 | 이미 없음: {missing_cnt}개 | 실패: {error_cnt}개")
    return (deleted_cnt, missing_cnt, error_cnt)


def extract_background_images(input_path, output_path):
    """어노테이션이 없는 배경 이미지만 추출하는 함수"""
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"배경 이미지 추출 시작: {input_path}")
    
    # 결과 파일 경로 설정
    background_list_path = output_path / 'background_dataset.txt'
    
    # 통계 변수 초기화
    stats = {
        'total_cnt': 0,
        'background_cnt': 0,
        'error_cnt': 0,
    }
    
    # 파일 초기화
    with open(background_list_path, 'w', encoding='utf-8') as f:
        pass
    
    # 전체 파일 수 계산 (폴더 또는 파일 리스트 지원)
    all_files, _ = collect_image_files_from_source(input_path)
    total_files = len(all_files)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")

    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 입력 경로 순회
    for full_path in all_files:
        stats['total_cnt'] += 1
        progress = (stats['total_cnt'] / total_files) * 100

        label_path = get_label_path_from_image(full_path)

        # 라벨 파일 존재 확인 및 처리
        is_background = False

        if not os.path.isfile(label_path):
            is_background = True
        else:
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if not lines:
                        is_background = True
            except Exception as e:
                logger.error(f"라벨 처리 오류 {label_path}: {e}")
                stats['error_cnt'] += 1
                continue

        # 배경 이미지인 경우 목록에 추가
        if is_background:
            stats['background_cnt'] += 1
            with open(background_list_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")

        print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
              f"처리: {stats['total_cnt']} | "
              f"배경 이미지: {stats['background_cnt']}", end='')
    
    print("\n")
    logger.info("배경 이미지 추출 완료")
    return stats

def _stratified_split(files, train_rate, file_classes):
    """
    클래스 조합 기준 stratified split.
    같은 이미지가 train/valid에 중복되지 않으면서
    각 클래스 조합 그룹에서 비율을 유지.
    - 파일이 1장인 그룹: train으로 배정 (valid 불가)
    - 파일이 2장 이상인 그룹: train_rate 비율로 분할, 최소 1장씩 보장
    """
    groups = defaultdict(list)
    for path in files:
        classes = file_classes.get(path, frozenset())
        group_key = ','.join(str(c) for c in sorted(classes)) if classes else 'background'
        groups[group_key].append(path)

    train_files, valid_files = [], []
    for group_key in sorted(groups.keys()):
        group_files = groups[group_key]
        random.shuffle(group_files)
        if len(group_files) == 1:
            train_files.extend(group_files)
        else:
            n = max(1, min(int(len(group_files) * train_rate), len(group_files) - 1))
            train_files.extend(group_files[:n])
            valid_files.extend(group_files[n:])

    return train_files, valid_files


def _auto_split(all_files, train_rate, seed=42, file_classes=None):
    """
    폴더 구조 자동 감지 후 최적 분할 방식 적용.
    file_classes가 주어지면 클래스 조합 기준 stratified split 수행.
    - 하위 폴더 여러 개: 폴더별 stratified 분할 후 합산
    - 단일 폴더: 전체 stratified 분할
    seed 고정으로 재현성 보장.
    """
    random.seed(seed)
    source_dirs = set(os.path.dirname(f) for f in all_files)

    if len(source_dirs) > 1:
        dir_groups = defaultdict(list)
        for path in all_files:
            dir_groups[os.path.dirname(path)].append(path)

        train_files, valid_files = [], []
        for src in sorted(dir_groups.keys()):
            t, v = _stratified_split(dir_groups[src], train_rate, file_classes or {})
            train_files.extend(t)
            valid_files.extend(v)
        mode = f"다중 폴더 {len(source_dirs)}개 → 폴더별 클래스 조합 stratified 분할"
    else:
        train_files, valid_files = _stratified_split(list(all_files), train_rate, file_classes or {})
        mode = "단일 폴더 → 클래스 조합 stratified 분할"

    return train_files, valid_files, mode


def _collect_file_classes(all_files):
    """라벨 파일을 읽어 각 이미지의 클래스 집합을 반환. {path: frozenset(class_ids)}"""
    file_classes = {}
    total = len(all_files)
    for i, path in enumerate(all_files):
        if (i + 1) % 500 == 0 or (i + 1) == total:
            print(f"\r클래스 정보 수집: {i+1}/{total}", end='')
        label_path = get_label_path_from_image(path)
        classes = set()
        if os.path.isfile(label_path):
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            try:
                                class_id = int(float(parts[0]))
                                if 0 <= class_id < 89:
                                    classes.add(class_id)
                            except (ValueError, IndexError):
                                pass
            except Exception:
                pass
        file_classes[path] = frozenset(classes)
    print()
    return file_classes


def _read_label_counts(image_path):
    """Return YOLO annotation counts for one image as {class_id: count}."""
    counts = defaultdict(int)
    label_path = get_label_path_from_image(image_path)
    if not os.path.isfile(label_path):
        return counts
    try:
        with open(label_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    class_id = int(float(parts[0]))
                except (ValueError, IndexError):
                    continue
                if 0 <= class_id < 89:
                    counts[class_id] += 1
    except (OSError, UnicodeError):
        pass
    return counts


def _select_annotation_balanced(records, target_count, target_class_counts,
                                seed=42, phase='균형 샘플링'):
    """Select exactly target_count records while following class annotation quotas.

    A class-deficit driven sampler is used instead of sampling each class separately,
    because one image may contain several classes. This avoids duplicate image paths
    and handles multi-label images naturally.
    """
    if target_count >= len(records):
        return list(records)
    if target_count <= 0:
        return []

    rng = random.Random(seed)
    buckets = defaultdict(list)
    for idx, record in enumerate(records):
        for class_id in record['counts']:
            buckets[class_id].append(idx)

    selected = set()
    selected_counts = defaultdict(int)
    class_ids = sorted(target_class_counts)
    active_classes = set(class_ids)

    while len(selected) < target_count and active_classes:
        # Do not rebuild a filtered copy of a large class bucket on every round.
        # A 600k-image DB can otherwise become effectively O(images * target).
        candidates = [c for c in active_classes
                      if selected_counts[c] < target_class_counts[c]]
        if not candidates:
            break
        class_id = max(
            candidates,
            key=lambda c: ((target_class_counts[c] - selected_counts[c]) /
                           max(1, target_class_counts[c]), rng.random()))

        # Evaluate a small random candidate window. It keeps 100k-image datasets
        # fast while preferring images that fill the remaining class deficits.
        bucket = buckets[class_id]
        window = []
        max_attempts = min(max(64, len(bucket) * 2), 256)
        for _ in range(max_attempts):
            candidate = bucket[rng.randrange(len(bucket))]
            if candidate not in selected and candidate not in window:
                window.append(candidate)
                if len(window) == 32:
                    break
        if not window:
            active_classes.discard(class_id)
            continue

        def candidate_score(i):
            score = 0.0
            for c, amount in records[i]['counts'].items():
                deficit = max(0, target_class_counts.get(c, 0) - selected_counts[c])
                score += min(amount, deficit) / max(1, target_class_counts.get(c, 1))
            return score + rng.random() * 1e-6
        chosen = max(window, key=candidate_score)
        selected.add(chosen)
        for c, amount in records[chosen]['counts'].items():
            selected_counts[c] += amount
        if len(selected) % 1000 == 0 or len(selected) == target_count:
            print(f"\r{phase}: {len(selected)}/{target_count}",
                  end='', flush=True)

    if selected:
        print(flush=True)

    # Fill the remaining image slots (mostly background-only images).
    remaining = [i for i in range(len(records)) if i not in selected]
    rng.shuffle(remaining)
    selected.update(remaining[:target_count - len(selected)])
    print(f"\r{phase}: {len(selected)}/{target_count}", flush=True)
    return [records[i] for i in sorted(selected)]


def _annotation_balanced_limited_dataset(input_path, output_path, num_files,
                                         train_rate=0.8, seed=42):
    """Create limited train/valid lists with class-wise annotation proportions."""
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    all_files, _ = collect_image_files_from_source(input_path)
    if not all_files:
        raise ValueError('입력 데이터에서 JPG/JPEG 이미지를 찾지 못했습니다.')

    records = []
    total_counts = defaultdict(int)
    for i, image_path in enumerate(all_files, 1):
        counts = _read_label_counts(image_path)
        records.append({'path': image_path, 'counts': dict(counts)})
        for class_id, amount in counts.items():
            total_counts[class_id] += amount
        if i % 500 == 0 or i == len(all_files):
            print(f'\r어노테이션 분석: {i}/{len(all_files)}',
                  end='', flush=True)
    print(flush=True)

    target_count = min(int(num_files), len(records))
    target_counts = {
        c: int(round(amount * target_count / len(records)))
        for c, amount in total_counts.items()
    }
    print(f'전체 균형 선택 시작: {target_count}장', flush=True)
    selected = _select_annotation_balanced(
        records, target_count, target_counts, seed, '전체 균형 선택')
    selected_counts = defaultdict(int)
    for record in selected:
        for c, amount in record['counts'].items():
            selected_counts[c] += amount

    train_count = int(round(target_count * train_rate))
    valid_count = target_count - train_count
    valid_rate = 1.0 - train_rate
    valid_targets = {c: int(round(amount * valid_rate))
                     for c, amount in selected_counts.items()}
    # VALID is the smaller split, so balance it first. TRAIN becomes the
    # complement; this prevents the large TRAIN selection from swallowing
    # additional instances of multi-label classes.
    print(f'VALID 균형 선택 시작: {valid_count}장', flush=True)
    valid_records = _select_annotation_balanced(
        selected, valid_count, valid_targets, seed + 1, 'VALID 균형 선택')
    valid_paths = {r['path'] for r in valid_records}
    train_records = [r for r in selected if r['path'] not in valid_paths]

    train_path = output_path / 'train.txt'
    valid_path = output_path / 'valid.txt'
    train_annotation_path = output_path / 'train_annotation.txt'
    valid_annotation_path = output_path / 'val_annotation.txt'
    train_annotation = np.zeros(90, dtype=int)
    valid_annotation = np.zeros(90, dtype=int)

    def write_split(path, annotation, split_records):
        with open(path, 'w', encoding='utf-8') as f:
            for record in split_records:
                f.write(record['path'] + '\n')
                for c, amount in record['counts'].items():
                    annotation[c + 1] += amount
                    annotation[0] += amount

    print('TRAIN/VALID 리스트 및 annotation 통계 저장 중...', flush=True)
    write_split(train_path, train_annotation, train_records)
    write_split(valid_path, valid_annotation, valid_records)
    np.savetxt(train_annotation_path, train_annotation, fmt='%d', delimiter=',',
               header='train annotation')
    np.savetxt(valid_annotation_path, valid_annotation, fmt='%d', delimiter=',',
               header='valid annotation')

    info_path = output_path / 'limited_balanced_info.txt'
    with open(info_path, 'w', encoding='utf-8') as f:
        f.write('=== 제한 수량 클래스별 어노테이션 균형 생성 결과 ===\n')
        f.write(f'입력 이미지 수: {len(records)}\n')
        f.write(f'선택 이미지 수: {len(selected)}\n')
        f.write(f'TRAIN 이미지 수: {len(train_records)}\n')
        f.write(f'VALID 이미지 수: {len(valid_records)}\n')
        f.write(f'TRAIN 비율: {train_rate:.4f}\n')
        f.write(f'시드: {seed}\n\n')
        f.write('class,total_selected,train,valid,train_ratio\n')
        for c in sorted(selected_counts):
            total = selected_counts[c]
            train = int(train_annotation[c + 1])
            ratio = train / total if total else 0
            f.write(f'{c},{total},{train},{int(valid_annotation[c + 1])},{ratio:.6f}\n')

    return {
        'selected_cnt': len(selected),
        'train_img_cnt': len(train_records),
        'valid_img_cnt': len(valid_records),
        'train_annotations': int(train_annotation[0]),
        'valid_annotations': int(valid_annotation[0]),
        'train_annotation': train_annotation,
        'valid_annotation': valid_annotation,
        'output_path': str(output_path),
    }


def _print_valid_class_warnings(valid_files, file_classes, min_threshold=10):
    """valid set 클래스별 분포 출력. min_threshold 미만이면 경고."""
    class_counts = defaultdict(int)
    background_cnt = 0
    for path in valid_files:
        classes = file_classes.get(path, frozenset())
        if classes:
            for cls in classes:
                class_counts[cls] += 1
        else:
            background_cnt += 1

    print("\nvalid 클래스별 분포:")
    has_warning = False
    for cls in sorted(class_counts.keys()):
        cnt = class_counts[cls]
        if cnt < min_threshold:
            print(f"  클래스 {cls}: {cnt}장  ⚠ ({min_threshold}장 미만 - 검증 신뢰도 낮음)")
            has_warning = True
        else:
            print(f"  클래스 {cls}: {cnt}장")
    if background_cnt:
        print(f"  배경:     {background_cnt}장")
    if not has_warning:
        print("  (모든 클래스 정상)")
    print()


def process_dataset(input_path, output_path, train_rate=0.8, skip_rate=0, seed=42):
    """데이터셋을 처리하고 train/validation 세트로 분할하는 함수"""
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_path)
    logger.info(f"데이터셋 처리 시작: {input_path}")

    # 전체 파일 수집
    all_files, _ = collect_image_files_from_source(input_path)
    logger.info(f"전체 수집된 파일 수: {len(all_files)}")

    # skip_rate 사전 적용
    if skip_rate > 0:
        random.seed(seed)
        keep_count = int(len(all_files) * (1 - skip_rate))
        all_files = random.sample(all_files, keep_count)
        logger.info(f"스킵 후 파일 수: {len(all_files)}")

    # 클래스 정보 수집 (stratified split용)
    print("클래스 정보 수집 중...")
    file_classes = _collect_file_classes(all_files)

    # 폴더 구조 자동 감지 + 클래스 조합 stratified 분할
    train_files, valid_files, split_mode = _auto_split(all_files, train_rate, seed, file_classes)
    logger.info(f"분할 방식: {split_mode}")
    logger.info(f"학습: {len(train_files)}개, 검증: {len(valid_files)}개")
    print(f"\n분할 방식: {split_mode}")
    print(f"학습: {len(train_files)}개 | 검증: {len(valid_files)}개")
    _print_valid_class_warnings(valid_files, file_classes)

    # 결과 파일 경로 설정
    val_path = output_path / 'valid.txt'
    train_path = output_path / 'train.txt'
    train_annotation_path = output_path / 'train_annotation.txt'
    val_annotation_path = output_path / 'val_annotation.txt'
    error_path = output_path / 'error_path.txt'

    # 통계 변수 초기화
    obj_annotation = np.zeros(90)
    obj_annotation_val = np.zeros(90)
    obj_annotation_train = np.zeros(90)

    stats = {
        'total_cnt': 0,
        'skip_cnt': 0,
        'error_cnt': 0,
        'train_img_cnt': 0,
        'valid_img_cnt': 0,
        'total_annotations': 0,
        'train_annotations': 0,
        'valid_annotations': 0,
        'obj_annotation': obj_annotation,
        'obj_annotation_train': obj_annotation_train,
        'obj_annotation_val': obj_annotation_val,
        'train_no_label': 0,
        'valid_no_label': 0,
        'train_empty_label': 0,
        'valid_empty_label': 0,
        'created_labels': 0,
        'split_mode': split_mode,
    }

    # 출력 파일 초기화
    with open(train_path, 'w', encoding='utf-8') as f:
        pass
    with open(val_path, 'w', encoding='utf-8') as f:
        pass
    with open(error_path, 'w', encoding='utf-8') as f:
        f.write("에러 로그\n")

    # 분할된 목록에 is_train 플래그 결합 후 어노테이션 처리
    total_files = len(train_files) + len(valid_files)
    all_split = [(f, True) for f in train_files] + [(f, False) for f in valid_files]

    for full_path, is_train in all_split:
        stats['total_cnt'] += 1
        progress = stats['total_cnt'] / total_files * 100

        label_path = get_label_path_from_image(full_path)

        no_label = False
        empty_label = False

        if not os.path.isfile(label_path):
            if create_empty_label(label_path, logger):
                stats['created_labels'] += 1
                no_label = True
                if is_train:
                    stats['train_no_label'] += 1
                else:
                    stats['valid_no_label'] += 1
            else:
                stats['error_cnt'] += 1
                continue

        current_annotation = np.zeros(90)
        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    empty_label = True
                    if is_train:
                        stats['train_empty_label'] += 1
                    else:
                        stats['valid_empty_label'] += 1
                else:
                    for line in lines:
                        split_line = line.strip().split()
                        if not split_line or len(split_line) < 5:
                            continue
                        try:
                            class_id = int(float(split_line[0]))
                            if 0 <= class_id < 89:
                                current_annotation[0] += 1
                                current_annotation[class_id + 1] += 1
                        except (ValueError, IndexError):
                            continue

        except Exception as e:
            logger.error(f"어노테이션 처리 오류 {label_path}: {e}")
            stats['error_cnt'] += 1
            with open(error_path, 'a', encoding='utf-8') as f:
                f.write(f"{label_path}: {e}\n")
            continue

        if is_train:
            with open(train_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")
        else:
            with open(val_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")

        stats['obj_annotation'] += current_annotation
        if is_train:
            stats['obj_annotation_train'] += current_annotation
            stats['train_img_cnt'] += 1
            stats['train_annotations'] += current_annotation[0]
        else:
            stats['obj_annotation_val'] += current_annotation
            stats['valid_img_cnt'] += 1
            stats['valid_annotations'] += current_annotation[0]

        stats['total_annotations'] = stats['train_annotations'] + stats['valid_annotations']

        if stats['total_cnt'] % 1000 == 0:
            logger.info(f"진행률: {progress:.1f}%")

        print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
              f"학습: {stats['train_img_cnt']}(어노테이션: {stats['train_annotations']}) | "
              f"검증: {stats['valid_img_cnt']}(어노테이션: {stats['valid_annotations']}) | "
              f"전체 어노테이션: {stats['total_annotations']}", end='')

    print("\n")

    np.savetxt(train_annotation_path, stats['obj_annotation_train'], fmt='%2d',
               delimiter=',', header='train annotation')
    np.savetxt(val_annotation_path, stats['obj_annotation_val'], fmt='%2d',
               delimiter=',', header='valid annotation')

    logger.info("데이터셋 처리 완료")
    logger.info(f"학습: {stats['train_img_cnt']}, 검증: {stats['valid_img_cnt']}")

    return stats

def filter_dataset_by_class(list_path, output_path, target_classes):
    """리스트 파일에서 특정 클래스가 포함된 이미지만 추출하는 함수"""
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"클래스 필터링 시작: {target_classes}")
    
    # 결과 파일 경로 설정
    filtered_list_path = output_path / 'filtered_dataset.txt'
    filtered_annotation_path = output_path / 'filtered_annotation.txt'
    class_counts_path = output_path / 'class_counts.txt'
    
    # 통계 변수 초기화
    obj_annotation = np.zeros(90)
    
    stats = {
        'total_lines': 0,           
        'filtered_count': 0,        
        'no_label_count': 0,        
        'empty_label_count': 0,     
        'error_count': 0,           
        'total_annotations': 0,     
        'target_annotations': 0,    
        'obj_annotation': obj_annotation,
        'class_counts': {class_id: 0 for class_id in target_classes}
    }
    
    # 파일 초기화
    with open(filtered_list_path, 'w', encoding='utf-8') as f:
        pass
    
    # 경로 목록 파일 읽기
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            file_paths = f.readlines()
        
        total_paths = len(file_paths)
        stats['total_lines'] = total_paths
        logger.info(f"총 {total_paths}개의 경로가 발견되었습니다.")
        
        if total_paths == 0:
            logger.error("경로 목록 파일이 비어 있습니다.")
            return None
        
        # 각 경로 처리
        for i, path in enumerate(file_paths):
            path = path.strip()
            if not path:
                continue
            
            progress = ((i + 1) / total_paths) * 100
            
            # 이미지 경로에서 라벨 경로 생성
            if path.endswith('.jpg'):
                img_path = path
                label_path = get_label_path_from_image(path)
            else:
                continue
            
            # 라벨 파일 존재 확인
            if not os.path.isfile(label_path):
                stats['no_label_count'] += 1
                continue
            
            # 라벨 파일 읽기 및 클래스 확인
            contains_target_class = False
            current_annotation = np.zeros(90)
            
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                    if not lines:
                        stats['empty_label_count'] += 1
                        continue
                    
                    for line in lines:
                        split_line = line.strip().split()
                        if not split_line or len(split_line) < 5:
                            continue
                        
                        try:
                            class_id = int(float(split_line[0]))
                            current_annotation[0] += 1
                            current_annotation[class_id + 1] += 1
                            
                            if class_id in target_classes:
                                contains_target_class = True
                                stats['class_counts'][class_id] += 1
                                stats['target_annotations'] += 1
                        except (ValueError, IndexError):
                            continue
            
            except Exception as e:
                logger.error(f"라벨 처리 오류 {label_path}: {e}")
                stats['error_count'] += 1
                continue
            
            # 타겟 클래스가 포함된 경우 추가
            if contains_target_class:
                stats['filtered_count'] += 1
                with open(filtered_list_path, 'a', encoding='utf-8') as f:
                    f.write(f"{img_path}\n")
                
                # 어노테이션 통계 업데이트
                stats['obj_annotation'] += current_annotation
                stats['total_annotations'] += current_annotation[0]
            
            # 진행 상황 출력
            print(f"\r진행률: {progress:.1f}% ({i+1}/{total_paths}) | "
                  f"필터링됨: {stats['filtered_count']} | "
                  f"타겟 어노테이션: {stats['target_annotations']} | "
                  f"처리: {i+1}", end='')
        
        print("\n")
        
        # 최종 통계 저장
        np.savetxt(filtered_annotation_path, stats['obj_annotation'], fmt='%2d', 
                   delimiter=',', header='filtered dataset annotation')
        
        # 클래스별 카운트 저장
        with open(class_counts_path, 'w', encoding='utf-8') as f:
            f.write("필터링된 클래스별 통계:\n")
            for class_id in sorted(stats['class_counts'].keys()):
                count = stats['class_counts'][class_id]
                f.write(f"클래스 {class_id}: {count}개\n")
        
        logger.info("클래스 필터링 완료")
        
    except Exception as e:
        logger.error(f"리스트 파일 처리 중 오류 발생: {e}")
        return None
    
    return stats

def create_class_separated_lists(list_path, output_path):
    """
    리스트 파일에서 클래스별로 이미지 리스트를 분리하여 저장하는 함수
    각 클래스가 포함된 이미지들을 class_0.txt, class_1.txt 등으로 저장
    배경 이미지(어노테이션 없음)는 background.txt로 저장
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"클래스별 리스트 분리 시작: {list_path}")

    # 클래스별 이미지 리스트 저장용 딕셔너리
    class_images = defaultdict(list)
    background_images = []  # 배경 이미지 (어노테이션 없음)

    # 통계 변수 초기화
    stats = {
        'total_lines': 0,
        'processed': 0,
        'no_label_count': 0,
        'empty_label_count': 0,
        'background_count': 0,
        'error_count': 0,
        'class_counts': defaultdict(int),
        'class_image_counts': defaultdict(int),
    }

    # 경로 목록 파일 읽기
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            file_paths = f.readlines()

        total_paths = len(file_paths)
        stats['total_lines'] = total_paths
        logger.info(f"총 {total_paths}개의 경로가 발견되었습니다.")

        if total_paths == 0:
            logger.error("경로 목록 파일이 비어 있습니다.")
            return None

        # 각 경로 처리
        for i, path in enumerate(file_paths):
            path = path.strip()
            if not path:
                continue

            progress = ((i + 1) / total_paths) * 100

            # 이미지 경로에서 라벨 경로 생성
            if path.endswith('.jpg') or path.endswith('.jpeg'):
                img_path = path
                label_path = get_label_path_from_image(path)
            else:
                continue

            # 라벨 파일 존재 확인
            if not os.path.isfile(label_path):
                stats['no_label_count'] += 1
                continue

            # 라벨 파일 읽기 및 클래스 수집
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                    # 이미지에 포함된 클래스들
                    image_classes = set()

                    if not lines:
                        # 빈 라벨 파일 = 배경 이미지
                        stats['empty_label_count'] += 1
                        background_images.append(img_path)
                        stats['background_count'] += 1
                        stats['processed'] += 1
                    else:
                        # 라벨 파싱
                        for line in lines:
                            split_line = line.strip().split()
                            if not split_line or len(split_line) < 5:
                                continue

                            try:
                                class_id = int(float(split_line[0]))
                                if class_id < 0 or class_id >= 89:
                                    continue

                                image_classes.add(class_id)
                                stats['class_counts'][class_id] += 1
                            except (ValueError, IndexError):
                                continue

                        # 클래스가 하나도 없으면 배경 이미지
                        if not image_classes:
                            background_images.append(img_path)
                            stats['background_count'] += 1
                        else:
                            # 각 클래스 리스트에 이미지 경로 추가
                            for class_id in image_classes:
                                class_images[class_id].append(img_path)
                                stats['class_image_counts'][class_id] += 1

                        stats['processed'] += 1

            except Exception as e:
                logger.error(f"라벨 처리 오류 {label_path}: {e}")
                stats['error_count'] += 1
                continue

            # 진행 상황 출력
            print(f"\r진행률: {progress:.1f}% ({i+1}/{total_paths}) | "
                  f"처리: {stats['processed']} | "
                  f"배경: {stats['background_count']} | "
                  f"라벨 없음: {stats['no_label_count']}", end='')

        print("\n")

        # 클래스별 리스트 파일 저장
        logger.info(f"클래스별 리스트 파일 저장 중... ({len(class_images)}개 클래스)")

        for class_id in sorted(class_images.keys()):
            class_list_path = output_path / f'class_{class_id}.txt'
            with open(class_list_path, 'w', encoding='utf-8') as f:
                for img_path in class_images[class_id]:
                    f.write(f"{img_path}\n")

            logger.info(f"클래스 {class_id}: {len(class_images[class_id])}개 이미지 저장 -> {class_list_path}")

        # 배경 이미지 리스트 저장
        if background_images:
            background_list_path = output_path / 'background.txt'
            with open(background_list_path, 'w', encoding='utf-8') as f:
                for img_path in background_images:
                    f.write(f"{img_path}\n")

            logger.info(f"배경 이미지: {len(background_images)}개 저장 -> {background_list_path}")

        # 통계 저장
        stats_path = output_path / 'class_separation_stats.txt'
        with open(stats_path, 'w', encoding='utf-8') as f:
            f.write("클래스별 리스트 분리 통계\n")
            f.write("=" * 50 + "\n")
            f.write(f"전체 처리 항목: {stats['total_lines']}\n")
            f.write(f"성공적으로 처리: {stats['processed']}\n")
            f.write(f"라벨 없음: {stats['no_label_count']}\n")
            f.write(f"빈 라벨: {stats['empty_label_count']}\n")
            f.write(f"배경 이미지: {stats['background_count']}\n")
            f.write(f"에러 발생: {stats['error_count']}\n")
            f.write("\n클래스별 통계:\n")
            f.write("-" * 50 + "\n")

            for class_id in sorted(class_images.keys()):
                f.write(f"클래스 {class_id}:\n")
                f.write(f"  - 포함된 이미지 수: {stats['class_image_counts'][class_id]}\n")
                f.write(f"  - 어노테이션 총 개수: {stats['class_counts'][class_id]}\n")

            if background_images:
                f.write(f"\n배경 이미지:\n")
                f.write(f"  - 총 개수: {len(background_images)}\n")

        logger.info("클래스별 리스트 분리 완료")

        # 결과 요약 출력
        print("\n클래스별 리스트 분리 완료!")
        print(f"총 {len(class_images)}개 클래스 발견")
        for class_id in sorted(class_images.keys()):
            print(f"클래스 {class_id}: {stats['class_image_counts'][class_id]}개 이미지")
        if background_images:
            print(f"배경 이미지: {len(background_images)}개")

    except Exception as e:
        logger.error(f"리스트 파일 처리 중 오류 발생: {e}")
        return None

    return stats

def validate_dataset_from_list(list_path, output_path):
    """텍스트 파일에 나열된 경로들을 기준으로 jpg 파일과 txt 파일의 존재 여부를 확인하는 함수"""
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"데이터셋 검증 시작: {list_path}")
    
    # 결과 파일 경로 설정
    validation_result_path = output_path / 'validation_result.txt'
    validation_annotation_path = output_path / 'validation_annotation.txt'
    class_stats_path = output_path / 'class_statistics.txt'
    missing_jpg_list_path = output_path / 'missing_jpg.txt'
    missing_txt_list_path = output_path / 'missing_txt.txt'
    complete_pairs_path = output_path / 'complete_pairs.txt'
    both_missing_path = output_path / 'both_missing.txt'
    annotation_details_path = output_path / 'annotation_details.txt'
    
    # 통계 변수 초기화
    obj_annotation = np.zeros(90)
    
    stats = {
        'total_lines': 0,
        'valid_pairs': 0,
        'jpg_only': 0,
        'txt_only': 0,
        'both_missing': 0,
        'error_cnt': 0,
        'empty_txt_cnt': 0,
        'total_annotations': 0,
        'obj_annotation': obj_annotation,
        'file_annotations': {},
    }
    
    # 파일 초기화
    for file_path in [missing_jpg_list_path, missing_txt_list_path, complete_pairs_path, both_missing_path, annotation_details_path]:
        with open(file_path, 'w', encoding='utf-8') as f:
            pass
    
    # 상세 어노테이션 파일 헤더 작성
    with open(annotation_details_path, 'w', encoding='utf-8') as f:
        f.write("파일경로,총어노테이션수,클래스별카운트\n")
    
    # 경로 목록 파일 읽기
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            file_paths = f.readlines()
        
        total_paths = len(file_paths)
        stats['total_lines'] = total_paths
        logger.info(f"총 {total_paths}개의 경로가 발견되었습니다.")
        
        if total_paths == 0:
            logger.error("경로 목록 파일이 비어 있습니다.")
            return None
        
        # 각 경로 처리
        for i, path in enumerate(file_paths):
            path = path.strip()
            if not path:
                continue
            
            progress = ((i + 1) / total_paths) * 100
            
            # 경로에서 jpg 및 txt 파일 경로 생성
            if path.endswith('.jpg'):
                jpg_path = path
                txt_path = get_label_path_from_image(path)
            elif path.endswith('.txt'):
                txt_path = path
                # txt에서 jpg 경로 역추적 (복잡하므로 간단히 처리)
                jpg_path = path.replace('labels', 'JPEGImages').replace('.txt', '.jpg')
            else:
                jpg_path = path
                txt_path = get_label_path_from_image(path)
            
            # 파일 존재 여부 확인
            jpg_exists = os.path.isfile(jpg_path)
            txt_exists = os.path.isfile(txt_path)
            
            # 상태에 따른 처리
            if jpg_exists and txt_exists:
                stats['valid_pairs'] += 1
                with open(complete_pairs_path, 'a', encoding='utf-8') as f:
                    f.write(f"{jpg_path}\n")
                
                # 어노테이션 처리
                current_annotation = np.zeros(90)
                try:
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        txt_lines = f.readlines()
                        if not txt_lines:
                            stats['empty_txt_cnt'] += 1
                        else:
                            for line in txt_lines:
                                split_line = line.strip().split()
                                if not split_line or len(split_line) < 5:
                                    continue
                                try:
                                    class_id = int(float(split_line[0]))
                                    if 0 <= class_id < 89:
                                        current_annotation[0] += 1
                                        current_annotation[class_id + 1] += 1
                                except (ValueError, IndexError):
                                    continue
                    
                    # 파일별 어노테이션 정보 저장
                    stats['file_annotations'][jpg_path] = current_annotation.copy()
                    
                    # 상세 어노테이션 정보 파일에 추가
                    class_counts = []
                    for j in range(1, len(current_annotation)):
                        if current_annotation[j] > 0:
                            class_counts.append(f"{j-1}:{int(current_annotation[j])}")
                    
                    with open(annotation_details_path, 'a', encoding='utf-8') as f:
                        f.write(f"{jpg_path},{int(current_annotation[0])},{';'.join(class_counts)}\n")
                    
                except Exception as e:
                    logger.error(f"어노테이션 처리 오류 {txt_path}: {e}")
                    stats['error_cnt'] += 1
                    continue
                
                stats['obj_annotation'] += current_annotation
                stats['total_annotations'] += current_annotation[0]
                
            elif jpg_exists and not txt_exists:
                stats['jpg_only'] += 1
                with open(missing_txt_list_path, 'a', encoding='utf-8') as f:
                    f.write(f"{jpg_path}\n")
                    
            elif not jpg_exists and txt_exists:
                stats['txt_only'] += 1
                with open(missing_jpg_list_path, 'a', encoding='utf-8') as f:
                    f.write(f"{txt_path}\n")
                    
            else:
                stats['both_missing'] += 1
                with open(both_missing_path, 'a', encoding='utf-8') as f:
                    f.write(f"{path}\n")
                
            print(f"\r진행률: {progress:.1f}% ({i+1}/{total_paths}) | "
                  f"정상: {stats['valid_pairs']} | "
                  f"jpg만: {stats['jpg_only']} | "
                  f"txt만: {stats['txt_only']} | "
                  f"모두 없음: {stats['both_missing']}", end='')
        
        print("\n")
        
        # 최종 통계 저장
        np.savetxt(validation_annotation_path, stats['obj_annotation'], fmt='%2d', 
                delimiter=',', header='validation dataset annotation')
        
        # 클래스별 통계 저장
        with open(class_stats_path, 'w', encoding='utf-8') as f:
            f.write("클래스별 어노테이션 통계:\n")
            f.write(f"전체 어노테이션 수: {int(stats['obj_annotation'][0])}\n")
            for j in range(1, len(stats['obj_annotation'])):
                if stats['obj_annotation'][j] > 0:
                    percentage = (stats['obj_annotation'][j] / stats['obj_annotation'][0]) * 100 if stats['obj_annotation'][0] > 0 else 0
                    f.write(f"클래스 {j-1}: {int(stats['obj_annotation'][j])}개 ({percentage:.2f}%)\n")
        
        # 결과 저장
        with open(validation_result_path, 'w', encoding='utf-8') as f:
            f.write("\n경로 목록 파일 검증 완료!\n")
            f.write(f"전체 항목 수: {stats['total_lines']}\n")
            f.write(f"\n파일 상태 통계:\n")
            f.write(f"- 정상 (jpg/txt 모두 있음): {stats['valid_pairs']}개 ({stats['valid_pairs']/stats['total_lines']*100:.1f}%)\n")
            f.write(f"- jpg 파일만 있음: {stats['jpg_only']}개 ({stats['jpg_only']/stats['total_lines']*100:.1f}%)\n")
            f.write(f"- txt 파일만 있음: {stats['txt_only']}개 ({stats['txt_only']/stats['total_lines']*100:.1f}%)\n")
            f.write(f"- 모두 없음: {stats['both_missing']}개 ({stats['both_missing']/stats['total_lines']*100:.1f}%)\n")
            f.write(f"- 비어있는 txt 파일: {stats['empty_txt_cnt']}개\n")
            f.write(f"- 에러 발생: {stats['error_cnt']}개\n")
            
            f.write(f"\n어노테이션 통계:\n")
            f.write(f"전체 어노테이션 수: {int(stats['obj_annotation'][0])}\n")
            for j in range(1, len(stats['obj_annotation'])):
                if stats['obj_annotation'][j] > 0:
                    percentage = (stats['obj_annotation'][j] / stats['obj_annotation'][0]) * 100 if stats['obj_annotation'][0] > 0 else 0
                    f.write(f"클래스 {j-1}: {int(stats['obj_annotation'][j])}개 ({percentage:.2f}%)\n")
        
        logger.info("데이터셋 검증 완료")
        
    except Exception as e:
        logger.error(f"경로 목록 파일 처리 중 오류 발생: {e}")
        return None
    
    return stats

def process_dataset_advanced(input_path, output_path, train_rate=0.8, skip_rate=0,
                        filter_by_class=False, target_classes=None,
                        exclude_background=False, combined_filter=False, seed=42):
    """데이터셋을 처리하고 train/validation 세트로 분할하는 고급 함수"""
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_path)
    logger.info(f"고급 데이터셋 처리 시작: {input_path}")

    # 전체 파일 수집
    all_files, _ = collect_image_files_from_source(input_path)
    logger.info(f"전체 수집된 파일 수: {len(all_files)}")

    # skip_rate 사전 적용
    if skip_rate > 0:
        random.seed(seed)
        keep_count = int(len(all_files) * (1 - skip_rate))
        all_files = random.sample(all_files, keep_count)
        logger.info(f"스킵 후 파일 수: {len(all_files)}")

    total_files = len(all_files)

    # 결과 파일 경로 설정
    val_path = output_path / 'valid.txt'
    train_path = output_path / 'train.txt'
    train_annotation_path = output_path / 'train_annotation.txt'
    val_annotation_path = output_path / 'val_annotation.txt'
    filtered_path = output_path / 'filtered_list.txt'
    excluded_path = output_path / 'excluded_list.txt'

    # 통계 변수 초기화
    obj_annotation = np.zeros(90)
    obj_annotation_val = np.zeros(90)
    obj_annotation_train = np.zeros(90)

    stats = {
        'total_cnt': 0,
        'processed_cnt': 0,
        'skip_cnt': 0,
        'filtered_cnt': 0,
        'excluded_cnt': 0,
        'error_cnt': 0,
        'train_img_cnt': 0,
        'valid_img_cnt': 0,
        'total_annotations': 0,
        'train_annotations': 0,
        'valid_annotations': 0,
        'obj_annotation': obj_annotation,
        'obj_annotation_train': obj_annotation_train,
        'obj_annotation_val': obj_annotation_val,
        'train_no_label': 0,
        'valid_no_label': 0,
        'train_empty_label': 0,
        'valid_empty_label': 0,
        'created_labels': 0,
        'class_filtered': 0,
        'background_excluded': 0,
        'target_class_annotations': 0,
        'split_mode': '',
    }

    # 출력 파일 초기화
    for p in [train_path, val_path, filtered_path, excluded_path]:
        with open(p, 'w', encoding='utf-8') as f:
            pass

    # ── 패스 1: 필터링 + 어노테이션 캐싱 ──────────────────────────────
    filtered_files = []
    file_cache = {}   # {path: {'annotation': np.array, 'no_label': bool, 'empty_label': bool}}
    file_classes = {} # {path: frozenset(class_ids)} - stratified split용

    print(f"필터링 중... (전체 {total_files}개)")
    for full_path in all_files:
        stats['total_cnt'] += 1
        progress = stats['total_cnt'] / total_files * 100

        label_path = get_label_path_from_image(full_path)

        no_label = False
        empty_label = False

        if not os.path.isfile(label_path):
            if create_empty_label(label_path, logger):
                stats['created_labels'] += 1
                no_label = True
            else:
                stats['error_cnt'] += 1
                with open(excluded_path, 'a', encoding='utf-8') as f:
                    f.write(f"{full_path}\n")
                stats['excluded_cnt'] += 1
                continue

        current_annotation = np.zeros(90)
        contains_target_class = False

        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    empty_label = True
                else:
                    for line in lines:
                        split_line = line.strip().split()
                        if not split_line or len(split_line) < 5:
                            continue
                        try:
                            class_id = int(float(split_line[0]))
                            if 0 <= class_id < 89:
                                current_annotation[0] += 1
                                current_annotation[class_id + 1] += 1
                                if filter_by_class and class_id in target_classes:
                                    contains_target_class = True
                                    stats['target_class_annotations'] += 1
                        except (ValueError, IndexError):
                            continue
        except Exception as e:
            logger.error(f"어노테이션 처리 오류 {label_path}: {e}")
            stats['error_cnt'] += 1
            continue

        # 필터링 조건 적용
        include_file = True
        if filter_by_class and not combined_filter:
            include_file = contains_target_class
            if contains_target_class:
                stats['class_filtered'] += 1
        if exclude_background and not combined_filter:
            if empty_label or current_annotation[0] == 0:
                include_file = False
                stats['background_excluded'] += 1
        if combined_filter:
            include_file = contains_target_class and not (empty_label or current_annotation[0] == 0)
            if contains_target_class:
                stats['class_filtered'] += 1
            if empty_label or current_annotation[0] == 0:
                stats['background_excluded'] += 1

        if include_file:
            filtered_files.append(full_path)
            file_cache[full_path] = {
                'annotation': current_annotation,
                'no_label': no_label,
                'empty_label': empty_label,
            }
            # stratified split을 위한 클래스 집합 기록
            classes = set()
            for idx in range(1, len(current_annotation)):
                if current_annotation[idx] > 0:
                    classes.add(idx - 1)
            file_classes[full_path] = frozenset(classes)
            stats['filtered_cnt'] += 1
            with open(filtered_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")
        else:
            stats['excluded_cnt'] += 1
            with open(excluded_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")

        print(f"\r필터링: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
              f"선택: {stats['filtered_cnt']} | 제외: {stats['excluded_cnt']}", end='')

    print("\n")

    # ── 폴더 구조 자동 감지 + 클래스 조합 stratified 분할 ────────────
    train_files, valid_files, split_mode = _auto_split(filtered_files, train_rate, seed, file_classes)
    stats['split_mode'] = split_mode
    logger.info(f"분할 방식: {split_mode}")
    logger.info(f"학습: {len(train_files)}개, 검증: {len(valid_files)}개")
    print(f"분할 방식: {split_mode}")
    print(f"학습: {len(train_files)}개 | 검증: {len(valid_files)}개")
    _print_valid_class_warnings(valid_files, file_classes)

    # ── 패스 2: 캐시 기반 통계 집계 및 파일 기록 ─────────────────────
    total_split = len(train_files) + len(valid_files)
    all_split = [(f, True) for f in train_files] + [(f, False) for f in valid_files]

    for i, (full_path, is_train) in enumerate(all_split, 1):
        progress = i / total_split * 100
        cached = file_cache[full_path]
        current_annotation = cached['annotation']
        no_label = cached['no_label']
        empty_label = cached['empty_label']

        if no_label:
            if is_train:
                stats['train_no_label'] += 1
            else:
                stats['valid_no_label'] += 1
        if empty_label:
            if is_train:
                stats['train_empty_label'] += 1
            else:
                stats['valid_empty_label'] += 1

        if is_train:
            with open(train_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")
        else:
            with open(val_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")

        stats['obj_annotation'] += current_annotation
        if is_train:
            stats['obj_annotation_train'] += current_annotation
            stats['train_img_cnt'] += 1
            stats['train_annotations'] += current_annotation[0]
        else:
            stats['obj_annotation_val'] += current_annotation
            stats['valid_img_cnt'] += 1
            stats['valid_annotations'] += current_annotation[0]

        stats['total_annotations'] = stats['train_annotations'] + stats['valid_annotations']
        stats['processed_cnt'] += 1

        print(f"\r기록 중: {progress:.1f}% ({i}/{total_split}) | "
              f"학습: {stats['train_img_cnt']} | "
              f"검증: {stats['valid_img_cnt']}", end='')

    print("\n")

    # 최종 통계 저장
    np.savetxt(train_annotation_path, stats['obj_annotation_train'], fmt='%2d', 
               delimiter=',', header='train annotation')
    np.savetxt(val_annotation_path, stats['obj_annotation_val'], fmt='%2d', 
               delimiter=',', header='valid annotation')
    
    # 필터링 정보 저장
    filter_info_path = output_path / 'filter_info.txt'
    with open(filter_info_path, 'w', encoding='utf-8') as f:
        f.write("=== 고급 데이터셋 처리 설정 정보 ===\n")
        f.write(f"입력 경로: {input_path}\n")
        f.write(f"출력 경로: {output_path}\n")
        f.write(f"학습 비율: {train_rate:.2f}\n")
        f.write(f"스킵 비율: {skip_rate:.2f}\n")
        f.write(f"분할 방식: {stats['split_mode']}\n")
        
        f.write("\n=== 필터링 설정 ===\n")
        f.write(f"클래스 필터링: {'활성화' if filter_by_class else '비활성화'}\n")
        if filter_by_class:
            f.write(f"대상 클래스: {target_classes}\n")
        f.write(f"배경 이미지 제외: {'활성화' if exclude_background else '비활성화'}\n")
        f.write(f"복합 필터링: {'활성화' if combined_filter else '비활성화'}\n")
        
        f.write("\n=== 처리 결과 통계 ===\n")
        f.write(f"전체 파일 수: {stats['total_cnt']}\n")
        f.write(f"스킵된 파일 수: {stats['skip_cnt']}\n")
        f.write(f"처리된 파일 수: {stats['processed_cnt']}\n")
        f.write(f"필터링으로 선택된 파일 수: {stats['filtered_cnt']}\n")
        f.write(f"필터링으로 제외된 파일 수: {stats['excluded_cnt']}\n")
        f.write(f"클래스 필터링으로 선택된 파일 수: {stats['class_filtered']}\n")
        f.write(f"배경으로 제외된 파일 수: {stats['background_excluded']}\n")
        f.write(f"학습 이미지 수: {stats['train_img_cnt']}\n")
        f.write(f"검증 이미지 수: {stats['valid_img_cnt']}\n")
        
        f.write("\n=== 어노테이션 통계 ===\n")
        f.write(f"총 어노테이션 수: {stats['total_annotations']}\n")
        f.write(f"학습 어노테이션 수: {stats['train_annotations']}\n")
        f.write(f"검증 어노테이션 수: {stats['valid_annotations']}\n")
        if filter_by_class:
            f.write(f"대상 클래스 어노테이션 수: {stats['target_class_annotations']}\n")
        
        # 클래스별 통계 작성
        f.write("\n=== 클래스별 통계 ===\n")
        f.write(f"전체 어노테이션 수: {int(stats['obj_annotation'][0])}\n")
        for i in range(1, len(stats['obj_annotation'])):
            if stats['obj_annotation'][i] > 0:
                f.write(f"클래스 {i-1}: {int(stats['obj_annotation'][i])}개\n")
    
    logger.info("고급 데이터셋 처리 완료")
    return stats

PAIR_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp')
PAIR_IGNORE_TXT = {'classes.txt', 'class.txt', 'obj.names'}
PAIR_MOVE_LOG_NAME = 'pair_move_log.tsv'


def _path_key(path):
    """대소문자/구분자 차이를 무시한 비교용 경로 키"""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _is_under(path, root):
    """path가 root 하위(또는 동일)인지 확인"""
    try:
        return os.path.commonpath([_path_key(path), _path_key(root)]) == _path_key(root)
    except ValueError:  # 서로 다른 드라이브
        return False


def _candidate_label_paths(image_path):
    """
    이미지에 대응할 수 있는 라벨 경로 후보 목록
    1) .../JPEGImages/.../a.jpg -> .../labels/.../a.txt (마지막 JPEGImages 세그먼트 치환)
    2) 이미지와 같은 폴더의 a.txt
    3) get_label_path_from_image() 규칙
    """
    stem = os.path.splitext(image_path)[0]
    seen = set()

    def _new(c):
        k = _path_key(c)
        if k in seen:
            return False
        seen.add(k)
        return True

    parts = stem.replace('\\', '/').split('/')
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() in ('jpegimages', 'images'):
            c = os.path.normpath('/'.join(parts[:i] + ['labels'] + parts[i + 1:]) + '.txt')
            if _new(c):
                yield c
            break
    c = os.path.normpath(stem + '.txt')
    if _new(c):
        yield c
    # 파일시스템 탐색이 필요한 기존 규칙은 마지막에만 시도
    try:
        legacy = get_label_path_from_image(image_path)
        if legacy.lower().endswith('.txt'):
            c = os.path.normpath(legacy)
            if _new(c):
                yield c
    except Exception:
        pass


def _scan_image_label_folder(input_path, exclude_dirs=()):
    """
    폴더를 순회해 이미지/라벨 후보 파일 수집
    - 라벨 후보: 경로에 'labels' 폴더가 포함된 .txt 이거나, 이미지와 같은 폴더에 있는 .txt
      (train.txt 같은 리스트 파일이 라벨로 오인되지 않도록 제한)
    """
    images = []
    txt_files = []
    image_dirs = set()
    exclude_keys = [_path_key(d) for d in exclude_dirs if d]

    for root, dirs, files in os.walk(input_path):
        if any(_is_under(root, ex) for ex in exclude_keys):
            dirs[:] = []
            continue
        has_image = False
        for name in files:
            lower = name.lower()
            full = os.path.join(root, name)
            if lower.endswith(PAIR_IMAGE_EXTS):
                images.append(full)
                has_image = True
            elif lower.endswith('.txt') and lower not in PAIR_IGNORE_TXT:
                txt_files.append(full)
        if has_image:
            image_dirs.add(_path_key(root))

    labels = []
    for txt in txt_files:
        segs = [s.lower() for s in txt.replace('\\', '/').split('/')[:-1]]
        if 'labels' in segs or _path_key(os.path.dirname(txt)) in image_dirs:
            labels.append(txt)
    return images, labels


def analyze_image_label_pairs(input_path, exclude_dirs=()):
    """
    이미지-라벨 매칭 분석

    Returns:
        dict: matched(list of (img, label)), image_only(list), label_only(list),
              empty_label_cnt, total_images, total_labels
    """
    images, labels = _scan_image_label_folder(input_path, exclude_dirs)
    label_by_key = {_path_key(p): p for p in labels}
    claimed = set()
    matched = []
    image_only = []

    for img in sorted(images):
        found = None
        for cand in _candidate_label_paths(img):
            k = _path_key(cand)
            if k in label_by_key and k not in claimed:
                found = label_by_key[k]
                claimed.add(k)
                break
        if found:
            matched.append((img, found))
        else:
            image_only.append(img)

    label_only = sorted(p for k, p in label_by_key.items() if k not in claimed)

    empty_label_cnt = 0
    for _, lbl in matched:
        try:
            if os.path.getsize(lbl) == 0:
                empty_label_cnt += 1
        except OSError:
            pass

    return {
        'matched': matched,
        'image_only': image_only,
        'label_only': label_only,
        'empty_label_cnt': empty_label_cnt,
        'total_images': len(images),
        'total_labels': len(labels),
    }


def _unique_dest(path):
    """이동 대상 경로가 이미 있으면 _dup1, _dup2 ... 를 붙인 경로 반환"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base}_dup{n}{ext}"):
        n += 1
    return f"{base}_dup{n}{ext}"


def _write_path_list(path, header, items):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# {header}\n")
        for item in items:
            f.write(f"{item}\n")


def separate_unmatched_pairs(input_path, move_root, do_move=True):
    """
    이미지/라벨 폴더 전체 분석 후 매칭 안 되는 파일을 move_root로 분리 이동

    move_root/
      images_without_label/<입력 기준 상대경로>
      labels_without_image/<입력 기준 상대경로>
      matched_images.txt, image_only.txt, label_only.txt, pair_report.txt
      pair_move_log.tsv (원본경로<TAB>이동경로, 복원용)
    """
    input_path = os.path.abspath(input_path)
    move_root = os.path.abspath(move_root)
    if _is_under(input_path, move_root):
        print("오류: 이동 경로는 입력 경로와 같거나 입력 경로의 상위 폴더일 수 없습니다.")
        return None
    os.makedirs(move_root, exist_ok=True)

    print("\n분석 중... (파일이 많으면 시간이 걸릴 수 있습니다)")
    result = analyze_image_label_pairs(input_path, exclude_dirs=[move_root])
    matched = result['matched']
    image_only = result['image_only']
    label_only = result['label_only']

    # 폴더별 통계
    dir_stats = defaultdict(lambda: {'matched': 0, 'image_only': 0, 'label_only': 0})

    def _dir_key(p):
        rel = os.path.relpath(os.path.dirname(p), input_path)
        return '(root)' if rel == '.' else rel.replace(os.sep, '/')

    for img, _ in matched:
        dir_stats[_dir_key(img)]['matched'] += 1
    for img in image_only:
        dir_stats[_dir_key(img)]['image_only'] += 1
    for lbl in label_only:
        dir_stats[_dir_key(lbl)]['label_only'] += 1

    # 리포트/리스트 저장
    _write_path_list(os.path.join(move_root, 'matched_images.txt'),
                     '이미지-라벨 매칭된 정상 이미지 목록 (분석 시점 원본 경로)',
                     [img for img, _ in matched])
    _write_path_list(os.path.join(move_root, 'image_only.txt'),
                     '라벨 없는 이미지 목록 (분석 시점 원본 경로)', image_only)
    _write_path_list(os.path.join(move_root, 'label_only.txt'),
                     '이미지 없는 라벨 목록 (분석 시점 원본 경로)', label_only)

    lines = [
        "=== 이미지/라벨 매칭 분석 결과 ===",
        f"입력 경로: {input_path}",
        f"전체 이미지 파일: {result['total_images']}개",
        f"전체 라벨 파일: {result['total_labels']}개",
        f"정상 DB (이미지-라벨 매칭): {len(matched)}쌍 (빈 라벨 {result['empty_label_cnt']}개 포함)",
        f"라벨 없는 이미지: {len(image_only)}개",
        f"이미지 없는 라벨: {len(label_only)}개",
        "",
        "폴더별 통계 (매칭 / 라벨없는이미지 / 이미지없는라벨):",
    ]
    for d in sorted(dir_stats):
        s = dir_stats[d]
        mark = '  <-- 불일치' if s['image_only'] or s['label_only'] else ''
        lines.append(f"  {d}: {s['matched']} / {s['image_only']} / {s['label_only']}{mark}")
    report = "\n".join(lines)
    with open(os.path.join(move_root, 'pair_report.txt'), 'w', encoding='utf-8') as f:
        f.write(report + "\n")
    print("\n" + report)

    stats = {
        'total_images': result['total_images'],
        'total_labels': result['total_labels'],
        'matched_cnt': len(matched),
        'empty_label_cnt': result['empty_label_cnt'],
        'image_only_cnt': len(image_only),
        'label_only_cnt': len(label_only),
        'moved_cnt': 0,
        'move_error_cnt': 0,
        'move_root': move_root,
    }

    unmatched_total = len(image_only) + len(label_only)
    if unmatched_total == 0:
        print("\n불일치 파일이 없습니다. 이동할 파일이 없습니다.")
        return stats
    if not do_move:
        print("\n분석만 수행했습니다 (파일 이동 없음).")
        return stats

    print(f"\n이동 위치:")
    print(f"  라벨 없는 이미지 -> {os.path.join(move_root, 'images_without_label')}")
    print(f"  이미지 없는 라벨 -> {os.path.join(move_root, 'labels_without_image')}")
    confirm = input(f"\n불일치 파일 {unmatched_total}개를 이동할까요? (yes 입력 시 이동): ").strip().lower()
    if confirm != 'yes':
        print("이동을 취소했습니다. (분석 결과 파일은 저장됨)")
        return stats

    log_path = os.path.join(move_root, PAIR_MOVE_LOG_NAME)
    log_exists = os.path.exists(log_path)
    plan = ([(p, 'images_without_label') for p in image_only] +
            [(p, 'labels_without_image') for p in label_only])

    with open(log_path, 'a', encoding='utf-8') as log:
        if not log_exists:
            log.write("# 원본경로\t이동경로 (복원 시 사용)\n")
        for i, (src, sub) in enumerate(plan, 1):
            rel = os.path.relpath(src, input_path)
            dst = _unique_dest(os.path.join(move_root, sub, rel))
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                log.write(f"{src}\t{dst}\n")
                log.flush()
                stats['moved_cnt'] += 1
            except Exception as e:
                print(f"\n이동 실패 {src}: {e}")
                stats['move_error_cnt'] += 1
            if i % 500 == 0 or i == len(plan):
                print(f"\r이동 진행: {i}/{len(plan)}", end='', flush=True)
    print()

    print(f"\n이동 완료: {stats['moved_cnt']}개 | 실패: {stats['move_error_cnt']}개")
    print(f"이동 기록: {log_path}")
    return stats


def restore_moved_pairs(log_path):
    """pair_move_log.tsv 를 읽어 이동했던 파일을 원래 위치로 되돌림"""
    if os.path.isdir(log_path):
        log_path = os.path.join(log_path, PAIR_MOVE_LOG_NAME)
    if not os.path.isfile(log_path):
        print(f"오류: 이동 기록 파일을 찾을 수 없습니다: {log_path}")
        return None

    entries = []
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line or line.startswith('#') or '\t' not in line:
                continue
            src, dst = line.split('\t', 1)
            entries.append((src, dst))

    if not entries:
        print("복원할 기록이 없습니다.")
        return (0, 0, 0)

    confirm = input(f"\n{len(entries)}개 파일을 원래 위치로 되돌릴까요? (yes 입력 시 복원): ").strip().lower()
    if confirm != 'yes':
        print("복원을 취소했습니다.")
        return None

    restored = skipped = errors = 0
    remaining = []
    for src, dst in reversed(entries):
        if not os.path.exists(dst):
            skipped += 1
            continue
        if os.path.exists(src):
            print(f"건너뜀 (원래 위치에 이미 파일 존재): {src}")
            skipped += 1
            remaining.append((src, dst))
            continue
        try:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(dst, src)
            restored += 1
        except Exception as e:
            print(f"복원 실패 {dst}: {e}")
            errors += 1
            remaining.append((src, dst))

    # 복원된 항목은 기록에서 제거 (남은 항목만 유지)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("# 원본경로\t이동경로 (복원 시 사용)\n")
        for src, dst in reversed(remaining):
            f.write(f"{src}\t{dst}\n")

    print(f"\n복원 완료: {restored}개 | 건너뜀: {skipped}개 | 실패: {errors}개")
    return (restored, skipped, errors)


def test_path_generation():
    """경로 생성 함수 테스트"""
    test_cases = [
        "Z:\\08_Train\\02_GT\\SafetyEnv\\7class\\LGD\\FP\\JPEGImages\\0001_LGD_TR_FSlip_Crack602_20160324\\1.jpg",
        "Z:\\08_Train\\02_GT\\AirForce\\JPEGImages\\test\\image1.jpg",
        "/home/user/data/JPEGImages/subdir/image2.jpg",
        "C:\\data\\images\\test.jpg"
    ]
    
    print("=== 경로 생성 테스트 ===")
    for test_path in test_cases:
        label_path = get_label_path_from_image(test_path)
        print(f"이미지: {test_path}")
        print(f"라벨:   {label_path}")
        print("-" * 80)

def validate_input_source(input_source):
    """
    입력 경로/파일 유효성 검증

    Returns:
        (is_valid, error_msg):
            is_valid  - True면 유효한 입력
            error_msg - 오류 메시지 (is_valid=False 일 때만 의미 있음)
    """
    if not os.path.exists(input_source):
        return False, f"오류: 입력한 경로가 존재하지 않습니다: {input_source}"
    if os.path.isfile(input_source):
        if not input_source.lower().endswith('.txt'):
            return False, f"오류: 파일 리스트 입력은 .txt 파일이어야 합니다: {input_source}"
    return True, ""


def main():
    try:
        # 경로 생성 테스트 실행
        test_path_generation()
        
        while True:
            print("\n=== 데이터셋 처리 프로그램 ===")
            print("1. 데이터셋 처리 및 train/valid 분할")
            print("2. 제한된 데이터셋 생성 (사용자 지정 개수)")
            print("3. 전체 데이터셋 리스트 생성")
            print("4. 리스트 파일 검증 (jpg/txt 파일 존재 확인)")
            print("5. 배경 이미지 추출 (어노테이션 없는 이미지)")
            print("6. 특정 클래스 포함 이미지 필터링")
            print("7. 고급 데이터셋 처리 (필터링 옵션 포함)")
            print("8. 경로 생성 테스트")
            print("9. 클래스별 리스트 파일 분리 (NEW!)")
            print("10. 파일명 키워드 필터링 리스트 생성 (NEW!)")
            print("11. 특정 클래스 없는 파일 리스트 생성 (NEW!)")
            print("12. 클래스 분포 균등화 데이터셋 생성 (NEW!)")
            print("13. 라벨 미존재 이미지 리스트 생성 (NEW!)")
            print("14. DB 증강 복제 - 목표 수량까지 파일 복사로 늘리기 (NEW!)")
            print("15. 제한 수량 + 클래스별 TRAIN/VALID 균형 리스트 생성 (NEW!)")
            print("16. 이미지/라벨 매칭 검사 + 불일치 파일 분리 이동 (NEW!)")
            print("17. 종료")

            choice = input("\n작업을 선택하세요 (1-17): ")
            
            if choice == '1':
                # 데이터셋 처리 기능
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)
                    
                try:
                    train_rate = float(input("학습 데이터 비율을 입력하세요 (기본값 0.8: Enter): ") or 0.8)
                    if not (0 < train_rate < 1):
                        print("오류: 학습 비율은 0과 1 사이여야 합니다")
                        continue

                    skip_rate = float(input("데이터 스킵 비율을 입력하세요 (기본값 0.0: Enter): ") or 0.0)
                    if not (0 <= skip_rate < 1):
                        print("오류: 스킵 비율은 0과 1 사이여야 합니다")
                        continue

                    seed = int(input("랜덤 시드를 입력하세요 (기본값 42: Enter): ") or 42)

                except ValueError:
                    print("오류: 올바른 숫자를 입력하세요")
                    continue

                valid_rate = 1.0 - train_rate
                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"학습 비율: {train_rate:.1%}")
                print(f"검증 비율: {valid_rate:.1%}")
                print(f"스킵 비율: {skip_rate:.1%}")
                print(f"랜덤 시드: {seed}")

                try:
                    stats = process_dataset(input_path, output_path, train_rate, skip_rate, seed)

                    # 결과 출력
                    print("\n처리 완료!")
                    print(f"분할 방식: {stats['split_mode']}")
                    print(f"총 이미지 수: {stats['total_cnt']}")
                    print(f"학습 이미지 수: {stats['train_img_cnt']}")
                    print(f"검증 이미지 수: {stats['valid_img_cnt']}")
                    print(f"에러 발생 수: {stats['error_cnt']}")

                    print_class_statistics(stats['obj_annotation'], "전체 클래스별 통계")
                    
                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()
                    
            elif choice == '2':
                # 제한된 데이터셋 생성 기능
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)
                
                try:
                    num_files = int(input("선택할 파일 개수를 입력하세요 (예: 100, 200 등): "))
                    if num_files <= 0:
                        print("오류: 파일 개수는 1 이상이어야 합니다.")
                        continue

                except ValueError:
                    print("오류: 올바른 숫자를 입력하세요")
                    continue

                # 배경 이미지만 추출할지 선택
                background_choice = input("배경 이미지(어노테이션 없음)만 추출하시겠습니까? (y/n, 기본값 n: Enter): ").strip().lower()
                background_only = background_choice == 'y'

                # 클래스 필터링 옵션
                target_classes = None
                class_filter_mode = 'or'

                class_filter_choice = input("특정 클래스만 필터링하시겠습니까? (y/n, 기본값 n: Enter): ").strip().lower()
                if class_filter_choice == 'y':
                    try:
                        class_input = input("필터링할 클래스 ID를 쉼표로 구분해서 입력하세요 (예: 0,1,5): ").strip()
                        target_classes = [int(x.strip()) for x in class_input.split(',')]

                        if not target_classes:
                            print("경고: 클래스가 입력되지 않았습니다. 필터링하지 않습니다.")
                            target_classes = None
                        else:
                            print(f"필터링 모드 선택:")
                            print("  1. AND 모드 - 모든 클래스가 함께 있는 이미지만 선택")
                            print("  2. OR 모드 - 각 클래스별로 균등하게 분배")
                            mode_choice = input("모드를 선택하세요 (1/2, 기본값 2: Enter): ").strip()

                            if mode_choice == '1':
                                class_filter_mode = 'and'
                            else:
                                class_filter_mode = 'or'

                    except ValueError:
                        print("경고: 올바른 클래스 ID 형식이 아닙니다. 필터링하지 않습니다.")
                        target_classes = None

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"선택할 파일 개수: {num_files}개")
                print(f"배경 이미지만 추출: {'예' if background_only else '아니오'}")
                if target_classes:
                    print(f"클래스 필터링: {target_classes} (모드: {class_filter_mode})")

                try:
                    stats = create_limited_dataset(input_path, output_path, num_files, background_only=background_only, target_classes=target_classes, class_filter_mode=class_filter_mode)
                    
                    if stats:
                        print("\n제한된 데이터셋 생성 완료!")
                        print(f"요청한 파일 개수: {num_files}개")
                        print(f"선택된 파일 개수: {stats['selected_cnt']}개")
                        print(f"에러 발생 수: {stats['error_cnt']}개")
                        
                        print_class_statistics(stats['obj_annotation'], "클래스별 통계")
                
                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()        

            elif choice == '3':
                # 전체 데이터셋 리스트 생성 기능
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                # 파일 리스트 입력이면 전체 통합 모드만 가능
                is_file_list = os.path.isfile(input_path)

                if is_file_list:
                    process_mode = '1'
                else:
                    print(f"\n처리 방식을 선택하세요:")
                    print("  1. 전체 통합 모드  - 하위 폴더 전체를 하나의 파일로 생성")
                    print("  2. 폴더별 분리 모드 - 각 하위 폴더마다 결과 파일을 따로 저장")
                    process_mode = input("선택 (1/2, 기본값 1: Enter): ").strip() or '1'

                # 키워드 필터링 옵션 (공통)
                keyword_input = input("파일명 필터링 키워드를 입력하세요 (없으면 Enter): ").strip()
                keyword = keyword_input if keyword_input else None

                # 객체 크기 분석 옵션
                size_options = None
                if input("객체 크기 분석 포함? (y/n, 기본값 n: Enter): ").strip().lower() == 'y':
                    try:
                        area_bounds = parse_percent_bounds(
                            input("면적(√w×h) 구간 경계 % (기본 1,3,10,30: Enter): "), SIZE_AREA_BOUNDS)
                        height_bounds = parse_percent_bounds(
                            input("세로(높이) 구간 경계 % (기본 2,5,10,25: Enter): "), SIZE_HEIGHT_BOUNDS)
                    except ValueError as e:
                        print(f"오류: {e}")
                        continue
                    size_options = {'area_bounds': area_bounds, 'height_bounds': height_bounds}
                    if _PILImage is None:
                        print("경고: PIL이 없어 해상도를 읽을 수 없습니다. 비율 통계만 표시합니다.")

                if process_mode == '2':
                    # ── 폴더별 분리 모드 ──────────────────────────────────────
                    subfolders = [f for f in os.listdir(input_path)
                                  if os.path.isdir(os.path.join(input_path, f)) and not f.startswith('.')]
                    subfolders.sort()

                    if not subfolders:
                        print(f"오류: '{input_path}'에 하위 폴더가 없습니다.")
                        continue

                    print(f"\n발견된 하위 폴더 ({len(subfolders)}개):")
                    for i, folder in enumerate(subfolders, 1):
                        print(f"  {i}. {folder}")

                    # 출력 위치 선택
                    print(f"\n결과 저장 위치를 선택하세요:")
                    print("  1. 각 폴더 안에 저장  → 폴더명/output/complete_dataset.txt")
                    print("  2. 공통 폴더에 저장   → 공통폴더/폴더명_complete_dataset.txt")
                    output_mode = input("선택 (1/2, 기본값 1: Enter): ").strip() or '1'

                    common_output_path = None
                    if output_mode == '2':
                        common_output_path = input("공통 출력 폴더 경로를 입력하세요 (기본값: Enter): ").strip()
                        if not common_output_path:
                            common_output_path = os.path.join(input_path, 'output_all')
                        os.makedirs(common_output_path, exist_ok=True)
                        print(f"공통 출력 폴더: {common_output_path}")

                    # 각 폴더 처리
                    print(f"\n{'='*60}")
                    print(f"총 {len(subfolders)}개 폴더 처리 시작")
                    if keyword:
                        print(f"키워드 필터: '{keyword}'")
                    print(f"{'='*60}")

                    total_stats = {
                        'processed_folders': 0,
                        'total_files': 0,
                        'total_errors': 0,
                        'folder_results': []
                    }

                    for i, folder in enumerate(subfolders, 1):
                        folder_path = os.path.join(input_path, folder)

                        if output_mode == '2' and common_output_path:
                            folder_output_path = common_output_path
                        else:
                            folder_output_path = os.path.join(folder_path, 'output')

                        print(f"\n[{i}/{len(subfolders)}] 처리 중: {folder}")
                        print(f"  입력: {folder_path}")
                        print(f"  출력: {folder_output_path}")

                        try:
                            if output_mode == '2' and common_output_path:
                                stats = create_complete_dataset_list(
                                    folder_path, folder_output_path,
                                    keyword=keyword, output_prefix=folder,
                                    size_options=size_options)
                            else:
                                stats = create_complete_dataset_list(
                                    folder_path, folder_output_path,
                                    keyword=keyword, size_options=size_options)

                            if stats:
                                total_stats['processed_folders'] += 1
                                total_stats['total_files'] += stats['total_cnt']
                                total_stats['total_errors'] += stats['error_cnt']
                                total_stats['folder_results'].append({
                                    'folder': folder,
                                    'files': stats['total_cnt'],
                                    'errors': stats['error_cnt']
                                })
                                print(f"  완료: {stats['total_cnt']}개 파일 처리")

                        except Exception as e:
                            print(f"  오류 발생: {e}")
                            total_stats['folder_results'].append({
                                'folder': folder,
                                'files': 0,
                                'errors': -1,
                                'error_msg': str(e)
                            })

                    # 전체 결과 요약
                    print(f"\n{'='*60}")
                    print(f"전체 처리 완료! (폴더별 분리 모드)")
                    print(f"{'='*60}")
                    print(f"처리된 폴더: {total_stats['processed_folders']}/{len(subfolders)}개")
                    print(f"총 파일 수: {total_stats['total_files']}개")
                    print(f"총 에러 수: {total_stats['total_errors']}개")

                    print(f"\n폴더별 결과:")
                    for result in total_stats['folder_results']:
                        if result['errors'] == -1:
                            print(f"  {result['folder']}: 처리 실패 - {result.get('error_msg', 'Unknown error')}")
                        else:
                            print(f"  {result['folder']}: {result['files']}개 파일, {result['errors']}개 에러")

                else:
                    # ── 전체 통합 모드 ────────────────────────────────────────
                    output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                    if not output_path:
                        output_path = get_default_output_path(input_path)

                    print(f"\n처리 시작... (전체 통합 모드)")
                    print(f"입력 경로: {input_path}")
                    print(f"출력 경로: {output_path}")
                    if keyword:
                        print(f"키워드 필터: '{keyword}'")

                    try:
                        stats = create_complete_dataset_list(input_path, output_path, keyword=keyword,
                                                             size_options=size_options)

                        if stats:
                            print("\n전체 데이터셋 리스트 생성 완료!")
                            print(f"처리된 파일 개수: {stats['total_cnt']}개")
                            if stats.get('filtered_cnt'):
                                print(f"키워드 필터로 제외된 파일: {stats['filtered_cnt']}개")
                            print(f"에러 발생 수: {stats['error_cnt']}개")
                            print(f"생성된 라벨: {stats['created_labels']}개")
                            print(f"상세 리포트: {stats['report_path']}")

                    except Exception as e:
                        print(f"\n데이터 처리 중 오류 발생: {e}")
                        traceback.print_exc()
                  
            elif choice == '4':
                # 리스트 파일 검증 기능
                list_path = input("검증할 리스트 파일 경로를 입력하세요: ")
                
                if not os.path.isfile(list_path):
                    print(f"오류: 입력한 리스트 파일이 존재하지 않습니다: {list_path}")
                    continue
                
                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_dir = os.path.dirname(list_path)
                    list_name = os.path.basename(list_path).split('.')[0]
                    output_path = os.path.join(output_dir, f"{list_name}_validation")
                
                print(f"\n처리 시작...")
                print(f"리스트 파일: {list_path}")
                print(f"출력 경로: {output_path}")
                
                try:
                    stats = validate_dataset_from_list(list_path, output_path)
                    
                    if stats:
                        print("\n리스트 파일 검증 완료!")
                        print(f"전체 항목 수: {stats['total_lines']}")
                        
                        print(f"\n파일 상태 통계:")
                        print(f"- 정상 (jpg/txt 모두 있음): {stats['valid_pairs']}개 ({stats['valid_pairs']/stats['total_lines']*100:.1f}%)")
                        print(f"- jpg 파일만 있음: {stats['jpg_only']}개 ({stats['jpg_only']/stats['total_lines']*100:.1f}%)")
                        print(f"- txt 파일만 있음: {stats['txt_only']}개 ({stats['txt_only']/stats['total_lines']*100:.1f}%)")
                        print(f"- 모두 없음: {stats['both_missing']}개 ({stats['both_missing']/stats['total_lines']*100:.1f}%)")
                        print(f"- 비어있는 txt 파일: {stats['empty_txt_cnt']}개")
                        
                        print_class_statistics(stats['obj_annotation'], "어노테이션 통계")
                
                except Exception as e:
                    print(f"\n리스트 파일 검증 중 오류 발생: {e}")
                    traceback.print_exc()
                    
            elif choice == '5':
                # 배경 이미지 추출 기능
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue
                
                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = os.path.join(get_default_output_path(input_path), 'background')
                
                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                
                try:
                    stats = extract_background_images(input_path, output_path)
                    
                    if stats:
                        print("\n배경 이미지 추출 완료!")
                        print(f"처리된 파일 개수: {stats['total_cnt']}개")
                        print(f"배경 이미지 수: {stats['background_cnt']}개")
                        print(f"에러 발생 수: {stats['error_cnt']}개")
                
                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()
                    
            elif choice == '6':
                # 특정 클래스 포함 이미지 필터링 기능
                list_path = input("필터링할 이미지 리스트 파일 경로를 입력하세요: ")
                
                if not os.path.isfile(list_path):
                    print(f"오류: 입력한 리스트 파일이 존재하지 않습니다: {list_path}")
                    continue
                
                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_dir = os.path.dirname(list_path)
                    list_name = os.path.basename(list_path).split('.')[0]
                    output_path = os.path.join(output_dir, f"{list_name}_filtered")
                
                # 클래스 ID 입력 받기
                class_input = input("필터링할 클래스 ID를 입력하세요 (여러 개인 경우 쉼표로 구분): ")
                try:
                    target_classes = [int(c.strip()) for c in class_input.split(',')]
                    if not target_classes:
                        print("오류: 유효한 클래스 ID를 입력해야 합니다.")
                        continue
                except ValueError:
                    print("오류: 클래스 ID는 정수여야 합니다.")
                    continue
                
                print(f"\n처리 시작...")
                print(f"리스트 파일: {list_path}")
                print(f"출력 경로: {output_path}")
                print(f"대상 클래스: {target_classes}")
                
                try:
                    stats = filter_dataset_by_class(list_path, output_path, target_classes)
                    
                    if stats:
                        print("\n클래스 필터링 완료!")
                        print(f"전체 처리 항목: {stats['total_lines']}개")
                        print(f"필터링된 이미지: {stats['filtered_count']}개")
                        
                        print(f"\n클래스별 어노테이션 통계:")
                        for class_id in sorted(stats['class_counts'].keys()):
                            print(f"- 클래스 {class_id}: {stats['class_counts'][class_id]}개")
                
                except Exception as e:
                    print(f"\n데이터 필터링 중 오류 발생: {e}")
                    traceback.print_exc()
                    
            elif choice == '7':
                # 고급 데이터셋 처리 기능
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)
                
                # 학습/스킵 비율 입력
                try:
                    train_rate = float(input("학습 데이터 비율을 입력하세요 (기본값 0.8: Enter): ") or 0.8)
                    if not (0 < train_rate < 1):
                        print("오류: 학습 비율은 0과 1 사이여야 합니다")
                        continue

                    skip_rate = float(input("데이터 스킵 비율을 입력하세요 (기본값 0.0: Enter): ") or 0.0)
                    if not (0 <= skip_rate < 1):
                        print("오류: 스킵 비율은 0과 1 사이여야 합니다")
                        continue

                    seed = int(input("랜덤 시드를 입력하세요 (기본값 42: Enter): ") or 42)

                except ValueError:
                    print("오류: 올바른 숫자를 입력하세요")
                    continue
                
                # 필터링 옵션 설정
                print("\n=== 필터링 옵션 설정 ===")
                print("1. 클래스 필터링 (특정 클래스가 포함된 이미지만 선택)")
                print("2. 배경 이미지 제외 (어노테이션이 없는 이미지 제외)")
                print("3. 복합 필터링 (클래스 필터링 + 배경 제외)")
                print("4. 필터링 없음 (모든 이미지 처리)")
                
                filter_option = input("필터링 옵션을 선택하세요 (1-4): ")
                
                # 필터링 옵션 변수 초기화
                filter_by_class = False
                exclude_background = False
                combined_filter = False
                target_classes = []
                
                # 필터링 옵션에 따른 처리
                if filter_option == '1' or filter_option == '3':
                    filter_by_class = True
                    class_input = input("필터링할 클래스 ID를 입력하세요 (여러 개인 경우 쉼표로 구분): ")
                    try:
                        target_classes = [int(c.strip()) for c in class_input.split(',')]
                        if not target_classes:
                            print("오류: 유효한 클래스 ID를 입력해야 합니다.")
                            continue
                    except ValueError:
                        print("오류: 클래스 ID는 정수여야 합니다.")
                        continue
                
                if filter_option == '2':
                    exclude_background = True
                
                if filter_option == '3':
                    combined_filter = True
                    exclude_background = True
                
                # 설정 확인 출력
                valid_rate = 1.0 - train_rate
                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"학습 비율: {train_rate:.1%}")
                print(f"검증 비율: {valid_rate:.1%}")
                print(f"스킵 비율: {skip_rate:.1%}")
                print(f"랜덤 시드: {seed}")

                # 필터링 설정 출력
                if filter_by_class:
                    print(f"클래스 필터링: 활성화 (대상 클래스: {target_classes})")
                if exclude_background:
                    print("배경 이미지 제외: 활성화")
                if combined_filter:
                    print("복합 필터링: 활성화")

                # 확인 메시지
                confirm = input("\n위 설정으로 처리를 시작하시겠습니까? (y/n): ")
                if confirm.lower() != 'y':
                    print("처리가 취소되었습니다.")
                    continue

                # 데이터셋 처리 실행
                try:
                    stats = process_dataset_advanced(
                        input_path, output_path, train_rate, skip_rate,
                        filter_by_class, target_classes,
                        exclude_background, combined_filter, seed
                    )

                    print("\n고급 데이터셋 처리 완료!")
                    print(f"분할 방식: {stats['split_mode']}")
                    print(f"총 이미지 수: {stats['total_cnt']}")
                    print(f"필터링으로 선택된 이미지 수: {stats['filtered_cnt']}")
                    print(f"학습 이미지 수: {stats['train_img_cnt']}")
                    print(f"검증 이미지 수: {stats['valid_img_cnt']}")

                    print_class_statistics(stats['obj_annotation'], "전체 클래스별 통계")
                
                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()
                    
            elif choice == '8':
                # 경로 생성 테스트
                test_path_generation()

                # 사용자 입력 테스트
                user_path = input("\n테스트할 이미지 경로를 입력하세요 (Enter로 건너뛰기): ")
                if user_path.strip():
                    label_path = get_label_path_from_image(user_path)
                    print(f"입력: {user_path}")
                    print(f"결과: {label_path}")

            elif choice == '9':
                # 클래스별 리스트 파일 분리
                list_path = input("분리할 리스트 파일 경로를 입력하세요: ")

                if not os.path.isfile(list_path):
                    print(f"오류: 입력한 리스트 파일이 존재하지 않습니다: {list_path}")
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_dir = os.path.dirname(list_path)
                    list_name = os.path.basename(list_path).split('.')[0]
                    output_path = os.path.join(output_dir, f"{list_name}_class_separated")

                print(f"\n처리 시작...")
                print(f"리스트 파일: {list_path}")
                print(f"출력 경로: {output_path}")

                try:
                    stats = create_class_separated_lists(list_path, output_path)

                    if stats:
                        print("\n클래스별 리스트 분리 완료!")
                        print(f"전체 처리 항목: {stats['total_lines']}")
                        print(f"성공적으로 처리: {stats['processed']}")
                        print(f"라벨 없음: {stats['no_label_count']}")
                        print(f"배경 이미지: {stats['background_count']}")

                        print(f"\n생성된 클래스 리스트 파일:")
                        for class_id in sorted(stats['class_image_counts'].keys()):
                            print(f"  - class_{class_id}.txt: {stats['class_image_counts'][class_id]}개 이미지")

                        if stats['background_count'] > 0:
                            print(f"  - background.txt: {stats['background_count']}개 이미지")

                except Exception as e:
                    print(f"\n클래스 분리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '10':
                # 파일명 키워드 필터링 리스트 생성
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                keyword = input("필터링할 키워드를 입력하세요 (한글/특수문자 가능): ").strip()
                if not keyword:
                    print("오류: 키워드를 입력해야 합니다.")
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"필터 키워드: '{keyword}'")

                try:
                    stats = create_complete_dataset_list(input_path, output_path, keyword=keyword)

                    if stats:
                        print("\n키워드 필터링 리스트 생성 완료!")
                        print(f"필터링된 파일 수: {stats['filtered_cnt']}개")
                        print(f"선택된 파일 수: {stats['total_cnt']}개")
                        print(f"에러 발생 수: {stats['error_cnt']}개")
                        print(f"생성된 라벨: {stats['created_labels']}개")

                        print_class_statistics(stats['obj_annotation'], "클래스별 통계")

                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '11':
                # 특정 클래스 없는 파일 리스트 생성
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                try:
                    target_class = int(input("확인할 클래스 ID를 입력하세요 (0~88): "))
                    if not (0 <= target_class <= 88):
                        print("오류: 클래스 ID는 0~88 사이여야 합니다.")
                        continue
                except ValueError:
                    print("오류: 올바른 숫자를 입력하세요")
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"대상 클래스: {target_class}")

                try:
                    stats = find_images_without_class(input_path, output_path, target_class)

                    if stats:
                        print(f"\n클래스 {target_class} 검색 완료!")
                        print(f"전체 파일 수: {stats['total_cnt']}개")
                        print(f"클래스 없는 파일: {stats['missing_class_cnt']}개 ({stats['missing_class_cnt']/stats['total_cnt']*100:.1f}%)")
                        print(f"클래스 있는 파일: {stats['has_class_cnt']}개 ({stats['has_class_cnt']/stats['total_cnt']*100:.1f}%)")
                        print(f"라벨 파일 없음: {stats['no_label_cnt']}개")
                        print(f"배경 이미지 (빈 라벨): {stats['empty_label_cnt']}개")
                        print(f"에러 발생: {stats['error_cnt']}개")
                        print(f"\n생성된 파일:")
                        print(f"  - missing_class_{target_class}.txt: 클래스 없는 파일 목록")
                        print(f"  - has_class_{target_class}.txt: 클래스 있는 파일 목록")

                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '12':
                # 클래스 분포 균등화 데이터셋 생성
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)

                try:
                    num_files = int(input("생성할 파일 개수를 입력하세요 (예: 5000): "))
                    if num_files <= 0:
                        print("오류: 파일 개수는 1 이상이어야 합니다.")
                        continue
                except ValueError:
                    print("오류: 올바른 숫자를 입력하세요")
                    continue

                class_input = input("균등화할 클래스 ID를 입력하세요 (쉼표로 구분, 예: 0,1,2,3): ").strip()
                if not class_input:
                    print("오류: 클래스 ID를 입력해야 합니다.")
                    continue

                try:
                    target_classes = [int(c.strip()) for c in class_input.split(',')]
                    if not target_classes:
                        print("오류: 최소 1개 이상의 클래스를 입력해야 합니다.")
                        continue

                    # 클래스 ID 유효성 검사
                    for class_id in target_classes:
                        if not (0 <= class_id <= 88):
                            print(f"오류: 클래스 ID {class_id}는 유효하지 않습니다 (0~88 범위).")
                            continue
                except ValueError:
                    print("오류: 올바른 형식으로 클래스 ID를 입력하세요 (예: 0,1,2,3)")
                    continue

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"생성 파일 개수: {num_files}")
                print(f"대상 클래스: {target_classes}")

                try:
                    stats = create_balanced_class_dataset(input_path, output_path, num_files, target_classes)

                    if stats:
                        print("\n클래스 분포 균등화 데이터셋 생성 완료!")
                        print(f"총 선택된 파일: {stats['selected_cnt']}개")
                        print(f"목표 파일 수: {num_files}개")
                        print(f"처리된 클래스 수: {len(stats['class_stats'])}개")

                        print(f"\n선택된 데이터의 클래스별 분포:")
                        for class_id in sorted(stats['class_stats'].keys()):
                            count = stats['class_stats'][class_id]
                            percentage = count / stats['selected_cnt'] * 100 if stats['selected_cnt'] > 0 else 0
                            print(f"  클래스 {class_id}: {count}개 ({percentage:.1f}%)")

                        print(f"\n선택된 데이터의 DB별 분포:")
                        for db_name in sorted(stats['db_distribution'].keys()):
                            count = stats['db_distribution'][db_name]
                            percentage = count / stats['selected_cnt'] * 100 if stats['selected_cnt'] > 0 else 0
                            print(f"  {db_name}: {count}개 ({percentage:.1f}%)")

                        print(f"\n생성된 파일:")
                        print(f"  - balanced_dataset.txt: 선택된 이미지 경로 목록")
                        print(f"  - balanced_annotation.txt: 이미지별 어노테이션 수")
                        print(f"  - balanced_stats.txt: 상세 통계 정보")

                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '13':
                # 라벨 미존재 이미지 리스트 생성
                input_path = input("입력 데이터셋 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = os.path.join(get_default_output_path(input_path), 'missing_labels')

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"JPEGImages에 이미지는 있지만 labels에 txt 파일이 없는 데이터를 검색합니다.")

                try:
                    stats = find_missing_labels(input_path, output_path)

                    if stats:
                        print("\n라벨 미존재 이미지 검색 완료!")
                        print(f"전체 이미지 수: {stats['total_cnt']}개")
                        print(f"라벨 없는 이미지: {stats['missing_label_cnt']}개 ({stats['missing_label_cnt']/stats['total_cnt']*100:.1f}%)")
                        print(f"라벨 있는 이미지: {stats['has_label_cnt']}개 ({stats['has_label_cnt']/stats['total_cnt']*100:.1f}%)")
                        print(f"에러 발생: {stats['error_cnt']}개")

                        # 디렉토리별 통계 출력
                        missing_dirs = {k: v for k, v in stats['dir_stats'].items() if v['missing'] > 0}
                        if missing_dirs:
                            print(f"\n라벨 없는 이미지가 있는 디렉토리 ({len(missing_dirs)}개):")
                            for dir_name in sorted(missing_dirs.keys()):
                                dir_stat = missing_dirs[dir_name]
                                print(f"  {dir_name}: {dir_stat['missing']}/{dir_stat['total']}개 "
                                      f"({dir_stat['missing']/dir_stat['total']*100:.1f}%)")

                        print(f"\n생성된 파일:")
                        print(f"  - missing_labels.txt: 라벨 없는 이미지 경로 목록")
                        print(f"  - has_labels.txt: 라벨 있는 이미지 경로 목록")
                        print(f"  - missing_labels_detail.txt: 상세 정보 (이미지경로 | 예상라벨경로)")

                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '14':
                # DB 증강 복제 (오버샘플링)
                print("\n=== DB 증강 복제 ===")
                print("특정 클래스만 추출한 리스트처럼 수량이 부족한 DB를,")
                print("이미지/라벨을 파일명만 바꿔 복사해서 목표 수량까지 늘립니다.")
                print("특정 클래스가 포함된 이미지만 골라서 증강할 수도 있습니다.")
                print("  1. 증강 실행")
                print("  2. 증강 취소 (이전 작업으로 만든 파일 삭제)")
                sub_choice = input("선택 (1/2, 기본값 1: Enter): ").strip() or '1'

                if sub_choice == '2':
                    created_files_path = input("created_files.txt 경로를 입력하세요: ").strip()
                    if not created_files_path:
                        print("오류: 경로를 입력해야 합니다.")
                        continue
                    try:
                        rollback_duplication(created_files_path)
                    except Exception as e:
                        print(f"\n롤백 중 오류 발생: {e}")
                        traceback.print_exc()
                    continue

                input_path = input("입력 경로 또는 파일 리스트(.txt)를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue

                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)

                keyword_input = input("파일명 필터링 키워드를 입력하세요 (없으면 Enter): ").strip()
                keyword = keyword_input if keyword_input else None

                # 증강 대상 클래스 필터 (해당 클래스가 포함된 이미지만 복제)
                target_classes = None
                class_match_mode = 'any'

                print("\n증강할 클래스를 지정하면 그 클래스가 들어있는 이미지만 복제합니다.")
                print("(나머지 이미지는 원본 그대로 최종 리스트에 남습니다)")
                class_input = input("증강 대상 클래스 ID (예: 0,2,5 또는 0-3 / 전체 증강은 Enter): ").strip()

                if class_input:
                    target_classes, class_err = parse_class_id_list(class_input)
                    if class_err:
                        print(f"오류: {class_err}")
                        continue

                    if len(target_classes) > 1:
                        print("\n대상 이미지 판정 방식을 선택하세요.")
                        print("  1. OR  - 지정한 클래스 중 하나라도 있으면 증강 [권장]")
                        print("  2. AND - 지정한 클래스가 모두 있는 이미지만 증강")
                        match_choice = input("선택 (1/2, 기본값 1: Enter): ").strip() or '1'
                        class_match_mode = 'all' if match_choice == '2' else 'any'

                if target_classes:
                    print("\n목표 수량은 '증강 대상(해당 클래스 포함) 이미지' 기준으로 계산됩니다.")
                target_input = input("목표 수량을 입력하세요 (예: 300 / 3x / 3배): ").strip()
                if not target_input:
                    print("오류: 목표 수량을 입력해야 합니다.")
                    continue

                print("\n복사본을 어디에 만들까요?")
                print("  1. 새 출력 폴더에 생성 (원본 DB는 그대로 유지) [권장]")
                print("  2. 원본과 같은 폴더에 생성 (원본 DB 자체가 늘어남)")
                placement_choice = input("선택 (1/2, 기본값 1: Enter): ").strip() or '1'
                placement = 'inplace' if placement_choice == '2' else 'new'

                print("\n복제 방식을 선택하세요.")
                print("  1. 실제 파일 복사 (디스크 사용, 어떤 학습 코드에서도 안전) [권장]")
                print("  2. 하드링크 (같은 디스크에서 용량 거의 0, 실패 시 자동 복사)")
                print("  3. 심볼릭 링크 (용량 0, 리눅스 권장 / 윈도우는 권한 필요)")
                print("  4. 리스트 중복만 (파일 생성 없음, 리스트에 같은 경로를 여러 번 기록)")
                copy_choice = input("선택 (1-4, 기본값 1: Enter): ").strip() or '1'
                copy_mode = {'1': 'copy', '2': 'hardlink', '3': 'symlink', '4': 'list'}.get(copy_choice, 'copy')

                balance_choice = input("\n인스턴스가 적은 클래스를 우선 복제할까요? (y/n, 기본값 n: Enter): ").strip().lower()
                balance_classes = balance_choice == 'y'

                include_choice = input("최종 리스트에 원본도 포함할까요? (y/n, 기본값 y: Enter): ").strip().lower()
                include_original_in_list = include_choice != 'n'

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"목표 수량: {target_input}")
                if target_classes:
                    print(f"증강 대상 클래스: {target_classes} "
                          f"({'AND' if class_match_mode == 'all' else 'OR'})")
                else:
                    print("증강 대상 클래스: 전체 (필터 없음)")

                try:
                    stats = expand_dataset_by_duplication(
                        input_path, output_path, target_input,
                        placement=placement, copy_mode=copy_mode,
                        balance_classes=balance_classes,
                        include_original_in_list=include_original_in_list,
                        keyword=keyword,
                        target_classes=target_classes,
                        class_match_mode=class_match_mode)

                    if stats:
                        print("\nDB 증강 복제 완료!")
                        print(f"원본 수량: {stats['base_cnt']}개")
                        if stats.get('target_classes'):
                            print(f"증강 대상 클래스: {stats['target_classes']} "
                                  f"({'AND' if stats['class_match_mode'] == 'all' else 'OR'})")
                            print(f"증강 대상 수량: {stats['dup_base_cnt']}개 "
                                  f"(증강 제외 {stats['skipped_cnt']}개)")
                        print(f"목표 수량: {stats['target_cnt']}개")
                        print(f"생성한 복사본: {stats['created_cnt']}개 "
                              f"(라벨 {stats['created_label_cnt']}개, 빈 라벨 {stats['empty_label_cnt']}개)")
                        print(f"최종 리스트 수량: {stats['final_total']}개")
                        print(f"에러 발생: {stats['error_cnt']}개")

                        if stats['mode_counts']:
                            print(f"\n실제 사용된 복제 방식:")
                            for mode_name, cnt in stats['mode_counts'].items():
                                print(f"  {mode_name}: {cnt}개")

                        print(f"\n클래스별 인스턴스 수 (증강 전 → 증강 후):")
                        all_classes = sorted(set(stats['before_class_counts']) | set(stats['after_class_counts']))
                        for class_id in all_classes:
                            before = stats['before_class_counts'].get(class_id, 0)
                            after = stats['after_class_counts'].get(class_id, 0)
                            ratio = (after / before) if before else 0
                            print(f"  클래스 {class_id}: {before} → {after} ({ratio:.2f}배)")

                        print(f"\n생성된 파일:")
                        print(f"  - expanded_dataset.txt: 최종 학습용 리스트")
                        print(f"  - duplicated_only.txt: 복사본 경로만")
                        print(f"  - duplication_map.txt: 원본↔복사본 매핑 (검증용)")
                        print(f"  - created_files.txt: 생성 파일 전체 목록 (롤백용)")
                        print(f"  - expansion_stats.txt: 증강 전/후 클래스 통계")
                        print(f"\n주의: 복사본과 원본이 train/valid로 나뉘면 검증 점수가 부풀려집니다.")
                        print(f"      train/valid 분할을 먼저 하고, train 리스트만 증강하세요.")

                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '15':
                input_path = input("입력 데이터셋 경로 또는 이미지 목록(.txt): ").strip()
                if not input_path:
                    input_path = get_default_input_path()
                is_valid, err_msg = validate_input_source(input_path)
                if not is_valid:
                    print(err_msg)
                    continue
                output_path = input("출력 저장 경로 (Enter: 기본 output): ").strip()
                if not output_path:
                    output_path = get_default_output_path(input_path)
                try:
                    num_files = int(input("생성할 전체 이미지 수 (예: 30000): ").strip())
                    train_rate = float(input("TRAIN 비율 (기본값 0.8): ") or '0.8')
                    seed = int(input("랜덤 시드 (기본값 42): ") or '42')
                    if num_files <= 0 or not 0 < train_rate < 1:
                        raise ValueError
                except ValueError:
                    print("오류: 이미지 수는 1 이상, TRAIN 비율은 0과 1 사이여야 합니다.")
                    continue
                try:
                    stats = _annotation_balanced_limited_dataset(
                        input_path, output_path, num_files, train_rate, seed)
                    print("\n제한 수량 클래스 균형 리스트 생성 완료!")
                    print(f"선택: {stats['selected_cnt']} | TRAIN: {stats['train_img_cnt']} "
                          f"({stats['train_annotations']} annotations) | "
                          f"VALID: {stats['valid_img_cnt']} "
                          f"({stats['valid_annotations']} annotations)")
                    print(f"결과 경로: {stats['output_path']}")
                    print("클래스별 실제 비율은 limited_balanced_info.txt에서 확인할 수 있습니다.")
                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '16':
                print("\n=== 이미지/라벨 매칭 검사 ===")
                print("  1. 분석 + 불일치 파일 분리 이동")
                print("  2. 분석만 (이동 없음)")
                print("  3. 이전 이동 되돌리기 (pair_move_log.tsv)")
                sub_choice = input("선택 (기본값 1: Enter): ").strip() or '1'

                if sub_choice == '3':
                    log_path = input("pair_move_log.tsv 경로 또는 이동했던 폴더: ").strip().strip('"')
                    if log_path:
                        restore_moved_pairs(log_path)
                    continue
                if sub_choice not in ('1', '2'):
                    print("잘못된 선택입니다.")
                    continue

                input_path = input("이미지/라벨이 있는 폴더 경로: ").strip().strip('"')
                if not input_path or not os.path.isdir(input_path):
                    print(f"오류: 폴더가 존재하지 않습니다: {input_path}")
                    continue

                abs_input = os.path.abspath(input_path)
                default_move = os.path.join(os.path.dirname(abs_input),
                                            os.path.basename(abs_input) + '_unmatched')
                move_root = input(f"불일치 파일 이동(결과 저장) 경로 (기본값: {default_move}): ").strip().strip('"')
                if not move_root:
                    move_root = default_move

                try:
                    stats = separate_unmatched_pairs(input_path, move_root, do_move=(sub_choice == '1'))
                    if stats:
                        print(f"\n정상 DB 수량: {stats['matched_cnt']}쌍")
                        print(f"결과 파일: {stats['move_root']}")
                        print("  - pair_report.txt: 전체/폴더별 분석 결과")
                        print("  - matched_images.txt: 정상(매칭) 이미지 목록")
                        print("  - image_only.txt / label_only.txt: 불일치 목록")
                        if stats['moved_cnt']:
                            print("  - pair_move_log.tsv: 이동 기록 (메뉴 16-3으로 되돌리기 가능)")
                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '17':
                print("프로그램을 종료합니다.")
                return 0

            else:
                print("잘못된 선택입니다. 다시 선택해주세요.")

    except KeyboardInterrupt:
        print("\n프로그램이 사용자에 의해 중단되었습니다.")
        return 1
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
