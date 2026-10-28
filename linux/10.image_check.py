#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
10.image_check.py - 이미지 육안 검수 보조 도구 (Linux CLI 버전)

화면이 없는 서버에서 10.ImageCheck(GUI)의 작업 흐름을 대신한다.
  1) sheet : 리스트/폴더의 이미지를 번호가 붙은 썸네일 시트(jpg)로 만든다
  2) 시트를 내려받아 보고, 카테고리별 번호를 고른다
  3) apply : 고른 번호를 주간/야간/열화상 카테고리 파일에 저장한다
  4) stats : 진행 상황과 카테고리별 수량을 본다

카테고리 파일은 GUI와 같은 이름/형식이다:
  <리스트가 있는 폴더>/<리스트 파일명>_<카테고리>_<세션시각>.txt
한 이미지는 한 카테고리에만 들어가며, 다른 카테고리로 다시 지정하면 이전 파일에서 빠진다.

사용법:
  python3 10.image_check.py sheet list.txt                     # list.txt_imagecheck/ 에 시트 생성
  python3 10.image_check.py sheet /data/JPEGImages --boxes     # 폴더 입력, 라벨 박스 표시
  python3 10.image_check.py sheet list.txt --classes 0,3       # 0 또는 3번 클래스가 있는 이미지만
  python3 10.image_check.py apply list.txt_imagecheck --category 주간 --ids 1-40,45,47
  python3 10.image_check.py apply list.txt_imagecheck --category 야간 --ids-file night_ids.txt
  python3 10.image_check.py stats list.txt_imagecheck --csv stats.csv
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow가 필요합니다: pip install pillow")
    sys.exit(1)

CATEGORIES = ["주간", "야간", "열화상"]
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp')
BOX_COLORS = [(255, 0, 0), (0, 200, 0), (0, 120, 255), (255, 160, 0),
              (200, 0, 200), (0, 200, 200), (255, 255, 0), (128, 64, 255)]


# ---------------------------------------------------------------------------
# 입력 / 라벨
# ---------------------------------------------------------------------------

def convert_path(path):
    """GUI와 같은 경로 보정 (miss_detectionJPEGImages -> miss_detection/JPEGImages)."""
    path = path.replace('miss_detectionJPEGImages', 'miss_detection/JPEGImages')
    return path.replace('false_detectionJPEGImages', 'false_detection/JPEGImages')


def read_list(file_path):
    for encoding in ('utf-8', 'cp949', 'euc-kr'):
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return [convert_path(line.strip()) for line in f if line.strip()]
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 알 수 없습니다: {file_path}")


def collect_images(source):
    if os.path.isfile(source):
        return read_list(source)
    found = []
    for root, _, files in os.walk(source):
        for name in sorted(files):
            if name.lower().endswith(IMAGE_EXTS):
                found.append(convert_path(os.path.join(root, name)))
    return sorted(found)


def label_path_for(img_path):
    """GUI와 같은 규칙: JPEGImages -> labels, 없으면 이미지 옆 txt."""
    base = os.path.splitext(img_path)[0] + '.txt'
    if 'JPEGImages' in base:
        candidate = base.replace('JPEGImages', 'labels')
        if os.path.isfile(candidate):
            return candidate
    return base if os.path.isfile(base) else None


def read_boxes(label_path):
    boxes = []
    if not label_path:
        return boxes
    try:
        with open(label_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 5:
                    boxes.append((int(float(parts[0])), *map(float, parts[1:5])))
    except (OSError, ValueError):
        pass
    return boxes


# ---------------------------------------------------------------------------
# 작업 폴더 상태
# ---------------------------------------------------------------------------

def load_state(work_dir):
    state_path = os.path.join(work_dir, 'state.json')
    if not os.path.isfile(state_path):
        print(f"작업 폴더가 아닙니다 (state.json 없음): {work_dir}")
        print("먼저 sheet 명령으로 시트를 만드세요.")
        sys.exit(1)
    with open(state_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_state(work_dir, state):
    with open(os.path.join(work_dir, 'state.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def category_file(state, category):
    return os.path.join(state['rootpath'], f"{state['filename']}_{category}_{state['session']}.txt")


# ---------------------------------------------------------------------------
# sheet
# ---------------------------------------------------------------------------

def load_font(size):
    for name in ('DejaVuSans.ttf', 'NanumGothic.ttf', 'malgun.ttf', 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_thumb(img_path, size, draw_boxes, font):
    tile = Image.new('RGB', (size, size + 18), (40, 40, 40))
    draw = ImageDraw.Draw(tile)
    try:
        with Image.open(img_path) as img:
            img = img.convert('RGB')
            w, h = img.size
            boxes = read_boxes(label_path_for(img_path)) if draw_boxes else []
            img.thumbnail((size, size))
            tw, th = img.size
            ox, oy = (size - tw) // 2, (size - th) // 2
            tile.paste(img, (ox, oy))
            for cls, cx, cy, bw, bh in boxes:
                x1, y1 = ox + (cx - bw / 2) * tw, oy + (cy - bh / 2) * th
                x2, y2 = ox + (cx + bw / 2) * tw, oy + (cy + bh / 2) * th
                draw.rectangle([x1, y1, x2, y2], outline=BOX_COLORS[cls % len(BOX_COLORS)], width=2)
            caption = f"{w}x{h}"
    except (OSError, ValueError):
        draw.text((10, size // 2), "OPEN FAIL", fill=(255, 80, 80), font=font)
        caption = "missing"
    name = os.path.basename(img_path)
    draw.text((3, size + 2), f"{caption} {name}"[:48], fill=(200, 200, 200), font=font)
    return tile


def cmd_sheet(args):
    images = collect_images(args.source)
    if not images:
        print("이미지가 없습니다.")
        return 1

    if args.classes:
        wanted = {int(c) for c in args.classes.split(',') if c.strip()}
        images = [p for p in images if wanted & {b[0] for b in read_boxes(label_path_for(p))}]
        print(f"클래스 {sorted(wanted)} 포함 이미지: {len(images)}개")
        if not images:
            return 1

    source = os.path.abspath(args.source.rstrip('/\\'))
    rootpath = os.path.dirname(source) if os.path.isfile(source) else source
    filename = os.path.basename(source)
    work_dir = args.output or os.path.join(rootpath, f"{filename}_imagecheck")
    sheet_dir = os.path.join(work_dir, 'sheets')
    os.makedirs(sheet_dir, exist_ok=True)

    per_sheet = args.cols * args.rows
    cell_w, cell_h = args.thumb, args.thumb + 18
    font = load_font(12)
    num_font = load_font(22)
    total_sheets = (len(images) + per_sheet - 1) // per_sheet

    with open(os.path.join(work_dir, 'index.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['no', 'sheet', 'image'])
        for s in range(total_sheets):
            chunk = images[s * per_sheet:(s + 1) * per_sheet]
            sheet = Image.new('RGB', (args.cols * cell_w, args.rows * cell_h), (20, 20, 20))
            draw = ImageDraw.Draw(sheet)
            for i, img_path in enumerate(chunk):
                no = s * per_sheet + i + 1
                x, y = (i % args.cols) * cell_w, (i // args.cols) * cell_h
                sheet.paste(make_thumb(img_path, args.thumb, args.boxes, font), (x, y))
                draw.rectangle([x, y, x + 52, y + 28], fill=(0, 0, 0))
                draw.text((x + 4, y + 2), str(no), fill=(255, 255, 0), font=num_font)
                draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline=(90, 90, 90))
                writer.writerow([no, s + 1, img_path])
            sheet_name = f"sheet_{s + 1:04d}.jpg"
            sheet.save(os.path.join(sheet_dir, sheet_name), quality=85)
            print(f"[{s + 1}/{total_sheets}] {sheet_name}  ({s * per_sheet + 1}~{s * per_sheet + len(chunk)})")

    save_state(work_dir, {
        'source': source,
        'rootpath': rootpath,
        'filename': filename,
        'session': datetime.now().strftime("%Y%m%d_%H%M%S"),
        'images': images,
        'processed': {},
    })
    print(f"\n이미지 {len(images)}개, 시트 {total_sheets}장")
    print(f"작업 폴더: {work_dir}")
    print(f"다음: python3 {os.path.basename(__file__)} apply {work_dir} --category 주간 --ids 1-10")
    return 0


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def parse_ids(text, maximum):
    ids = set()
    for token in text.replace('\n', ',').replace(' ', ',').split(','):
        token = token.strip()
        if not token:
            continue
        if '-' in token:
            start, end = token.split('-', 1)
            ids.update(range(int(start), int(end) + 1))
        else:
            ids.add(int(token))
    bad = sorted(i for i in ids if i < 1 or i > maximum)
    if bad:
        raise ValueError(f"범위(1~{maximum}) 밖 번호: {bad[:10]}")
    return sorted(ids)


def cmd_apply(args):
    state = load_state(args.work_dir)
    images = state['images']
    text = args.ids
    if args.ids_file:
        with open(args.ids_file, 'r', encoding='utf-8') as f:
            text = f.read()
    try:
        ids = parse_ids(text or '', len(images))
    except ValueError as e:
        print(f"번호 오류: {e}")
        return 1
    if not ids:
        print("지정한 번호가 없습니다.")
        return 1

    contents = {}
    for cat in CATEGORIES:
        path = category_file(state, cat)
        contents[cat] = set()
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                contents[cat] = {line.strip() for line in f if line.strip()}

    processed = state['processed']
    changed_from = {}
    added = 0
    for no in ids:
        img_path = images[no - 1]
        prev = processed.get(img_path)
        if prev == args.category:
            continue
        if prev and img_path in contents.get(prev, set()):
            contents[prev].discard(img_path)
            changed_from[prev] = changed_from.get(prev, 0) + 1
        contents[args.category].add(img_path)
        processed[img_path] = args.category
        added += 1

    for cat, paths in contents.items():
        path = category_file(state, cat)
        if paths:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(f"{p}\n" for p in sorted(paths))
        elif os.path.exists(path):
            os.remove(path)

    save_state(args.work_dir, state)
    print(f"{args.category}: {added}개 저장 (지정 {len(ids)}개, 이미 같은 카테고리 {len(ids) - added}개)")
    for prev, count in changed_from.items():
        print(f"  {prev}에서 {count}개 이동")
    print(f"파일: {category_file(state, args.category)}")
    return 0


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def cmd_stats(args):
    state = load_state(args.work_dir)
    total = len(state['images'])
    processed = state['processed']
    done = len(processed)
    counts = {cat: sum(1 for c in processed.values() if c == cat) for cat in CATEGORIES}
    pct = lambda n: (n / total * 100) if total else 0

    print(f"총 이미지 수: {total}")
    print(f"처리된 이미지 수: {done} ({pct(done):.1f}%)")
    for cat in CATEGORIES:
        print(f"  {cat}: {counts[cat]} ({pct(counts[cat]):.1f}%)")

    if args.unprocessed:
        index = {p: i + 1 for i, p in enumerate(state['images'])}
        todo = [index[p] for p in state['images'] if p not in processed]
        print(f"\n미처리 번호 ({len(todo)}개): {compress_ids(todo)}")

    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["통계 항목", "값"])
            writer.writerow(["총 이미지 수", total])
            writer.writerow(["처리된 이미지 수", done])
            writer.writerow(["진행률", f"{pct(done):.2f}%"])
            for cat in CATEGORIES:
                writer.writerow([f"{cat} 이미지 수", counts[cat]])
        print(f"\nCSV 저장: {args.csv}")
    return 0


def compress_ids(ids):
    """[1,2,3,7,8] -> '1-3,7-8'"""
    ranges, start, prev = [], None, None
    for i in ids:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = i
    if start is not None:
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ','.join(ranges)


def build_parser():
    parser = argparse.ArgumentParser(
        description="이미지 육안 검수 보조 도구 (10.ImageCheck Linux CLI 버전)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    p_sheet = sub.add_parser('sheet', help='번호 붙은 썸네일 시트 생성')
    p_sheet.add_argument('source', help='이미지 리스트(.txt) 또는 이미지 폴더')
    p_sheet.add_argument('--output', '-o', help='작업 폴더 (기본: <입력>_imagecheck)')
    p_sheet.add_argument('--cols', type=int, default=6, help='시트 가로 칸 수 (기본 6)')
    p_sheet.add_argument('--rows', type=int, default=5, help='시트 세로 칸 수 (기본 5)')
    p_sheet.add_argument('--thumb', type=int, default=256, help='썸네일 크기 px (기본 256)')
    p_sheet.add_argument('--boxes', action='store_true', help='YOLO 라벨 박스 표시')
    p_sheet.add_argument('--classes', help='이 클래스가 하나라도 있는 이미지만 (콤마 구분)')
    p_sheet.set_defaults(func=cmd_sheet)

    p_apply = sub.add_parser('apply', help='번호를 카테고리 파일에 저장')
    p_apply.add_argument('work_dir', help='sheet 로 만든 작업 폴더')
    p_apply.add_argument('--category', '-c', required=True, choices=CATEGORIES)
    ids = p_apply.add_mutually_exclusive_group(required=True)
    ids.add_argument('--ids', help='번호 (예: 1-40,45,47)')
    ids.add_argument('--ids-file', help='번호가 적힌 텍스트 파일 (콤마/공백/줄바꿈 구분)')
    p_apply.set_defaults(func=cmd_apply)

    p_stats = sub.add_parser('stats', help='진행 상황과 카테고리별 수량')
    p_stats.add_argument('work_dir', help='sheet 로 만든 작업 폴더')
    p_stats.add_argument('--csv', help='통계를 CSV로 저장')
    p_stats.add_argument('--unprocessed', action='store_true', help='미처리 번호 목록 출력')
    p_stats.set_defaults(func=cmd_stats)
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == 'sheet' and min(args.cols, args.rows, args.thumb) < 1:
        print("--cols/--rows/--thumb 는 1 이상이어야 합니다.")
        return 1
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
