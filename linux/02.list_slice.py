#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02.list_slice.py - 리스트 분할/작업자 분배 도구 (Linux CLI 버전)

Windows GUI 버전(02.data_slice.py)과 같은 규칙으로 동작하며, 결과 폴더 구조도 같다.

사용법:
  python3 02.list_slice.py split <리스트.txt> --parts 3          # N개로 균등 분할
  python3 02.list_slice.py split <리스트.txt> --lines 1000       # N줄 단위 분할
  python3 02.list_slice.py distribute a.txt b.txt --workers 3    # 작업자 분배
  python3 02.list_slice.py distribute a.txt --names 홍길동,김철수 --strategy auto --mode group

분배 전략(--strategy):
  none      전략 미사용, 전체를 균등 분할 (기본)
  prefix    파일명 앞 N글자(--prefix-len, 기본 10) 기준
  ip_date   Auto_IP-PORT_YYYYMMDDhhmmss_ 패턴의 IP_날짜 기준
  dir       경로의 마지막 폴더명 기준
  regex     --regex 패턴의 첫 번째 그룹 기준
  auto      파일명 샘플로 가장 잘 맞는 패턴 자동 선택
  worktype  [0]보강재(1) 형태의 작업 유형 기준

분배 방식(--mode):
  split     각 그룹을 작업자 수로 나눠 모두에게 고르게 (결과: split_paths/) (기본)
  group     그룹을 통째로 작업자에게 할당 (결과: assigned_paths/)
"""

import argparse
import os
import random
import re
import sys
from collections import defaultdict

try:
    import chardet
except ImportError:
    chardet = None


# ---------------------------------------------------------------------------
# 파일 읽기
# ---------------------------------------------------------------------------

def detect_encoding(file_path, encoding='auto'):
    """인코딩 감지. 신뢰도가 낮으면 cp949(한국어 리스트)로 본다."""
    if encoding != 'auto':
        return encoding
    if chardet is None:
        return 'utf-8'
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read(10000))
    if not result['encoding'] or result['confidence'] < 0.7:
        return 'cp949'
    return result['encoding']


def read_lines(file_path, encoding):
    """지정 인코딩으로 읽고, 실패하면 cp949 -> utf-8 -> 바이너리 순으로 재시도한다."""
    for enc in dict.fromkeys([encoding, 'cp949', 'utf-8']):
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.readlines(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    with open(file_path, 'rb') as f:
        return f.read().decode('utf-8', errors='replace').splitlines(True), 'utf-8'


def ensure_newline(lines):
    return [line if line.endswith('\n') else line + '\n' for line in lines]


# ---------------------------------------------------------------------------
# split: 한 파일을 N개 또는 N줄 단위로 분할
# ---------------------------------------------------------------------------

def cmd_split(args):
    file_path = args.file
    encoding = detect_encoding(file_path, args.encoding)
    lines, encoding = read_lines(file_path, encoding)
    lines = ensure_newline(lines)
    total = len(lines)
    if total == 0:
        print("파일이 비어있습니다.")
        return 1

    base_name, ext = os.path.splitext(os.path.basename(file_path))
    save_dir = args.output or os.path.join(os.path.dirname(os.path.abspath(file_path)), f"{base_name}_split")
    os.makedirs(save_dir, exist_ok=True)

    if args.parts:
        base, remainder = divmod(total, args.parts)
        sizes = [base + (1 if i < remainder else 0) for i in range(args.parts)]
        print(f"총 {total}줄을 {args.parts}개로 균등 분할합니다.")
    else:
        sizes = [min(args.lines, total - start) for start in range(0, total, args.lines)]
        print(f"총 {total}줄을 {args.lines}줄 단위로 분할합니다 ({len(sizes)}개).")

    start = 0
    for i, size in enumerate(sizes):
        end = start + size
        out = os.path.join(save_dir, f"{base_name}_part{i + 1}_{start + 1}-{end}{ext}")
        with open(out, 'w', encoding=encoding) as f:
            f.writelines(lines[start:end])
        print(f"- 파트 {i + 1}: {size}줄 ({start + 1}~{end}줄)")
        start = end

    print(f"\n저장 위치: {save_dir}")
    return 0


# ---------------------------------------------------------------------------
# distribute: 경로 그룹화 후 작업자 분배
# ---------------------------------------------------------------------------

AUTO_PATTERNS = [
    (r'\[(\d)\]([^(]+)\((\d+)\)', '작업유형'),
    (r'Auto_([\d\.]+)-\d+_(\d{8})', '아이피_날짜'),
    (r'Auto_([\d\.]+)-\d+_(\d{14})_(\d{14})', '아이피_시작종료시간'),
    (r'\[(\d)\]Auto', '접두어_인덱스'),
    (r'(\[\d\])[\w_-]+', '접두어'),
    (r'_(\d{14})_', '날짜시간'),
    (r'_(\d{8})_', '날짜만'),
    (r'\[(\d)\](\w+)\((\d+)\)_(\d{14})_(\d{14})_', '작업유형_시간'),
    (r'_(\d{14})_(\d{14})_', '시작종료시간'),
    (r'_(\d+)_(\d+)_(\d+)\.jpg$', '일련번호'),
    (r'_(\d+)_(\d+)_(\d+)_(\d+)$', '확장_일련번호'),
    (r'^([^_]+)', '첫_단어'),
]


def auto_group_key(match, pattern_name):
    groups = match.groups()
    if len(groups) == 1:
        return groups[0]
    if pattern_name in ('작업유형', '작업유형_시간'):
        return match.group(2).strip()
    if pattern_name == '아이피_날짜':
        return f"{match.group(1)}_{match.group(2)}"
    if pattern_name == '아이피_시작종료시간':
        return f"{match.group(1)}_{match.group(2)[:8]}"
    if pattern_name in ('일련번호', '확장_일련번호'):
        return f"{match.group(1)}_{match.group(2)}"
    if pattern_name == '시작종료시간':
        return f"날짜_{match.group(1)[:8]}"
    return '_'.join(groups)


def group_paths(all_paths, strategy, regex=None, prefix_len=10):
    groups = defaultdict(list)

    if strategy == 'none':
        groups['전체'] = list(all_paths)

    elif strategy == 'prefix':
        for path in all_paths:
            groups[os.path.basename(path)[:prefix_len]].append(path)

    elif strategy == 'ip_date':
        for path in all_paths:
            m = re.search(r'Auto_([\d\.]+)-\d+_(\d{14})_', os.path.basename(path))
            groups[f"{m.group(1)}_{m.group(2)[:8]}" if m else '기타'].append(path)

    elif strategy == 'dir':
        for path in all_paths:
            groups[os.path.basename(os.path.dirname(path.replace('\\', '/')))].append(path)

    elif strategy == 'regex':
        pattern = re.compile(regex)
        for path in all_paths:
            m = pattern.search(os.path.basename(path))
            groups[m.group(1) if m and m.groups() else '기타'].append(path)

    elif strategy == 'worktype':
        for path in all_paths:
            m = re.search(r'\[(\d)\]([^(]+)\((\d+)\)', os.path.basename(path))
            groups[m.group(2).strip() if m else '기타'].append(path)

    elif strategy == 'auto':
        sample = random.sample(all_paths, 50) if len(all_paths) > 50 else all_paths
        names = [os.path.basename(p) for p in sample]
        best_pattern, best_name, best_rate = None, '기본', 0
        for pattern, name in AUTO_PATTERNS:
            rate = sum(1 for n in names if re.search(pattern, n)) / len(names)
            print(f"  패턴 '{name}' 성공률: {rate:.1%}")
            if rate > best_rate:
                best_pattern, best_name, best_rate = pattern, name, rate
        print(f"가장 효과적인 패턴: '{best_name}' (성공률: {best_rate:.1%})")

        if best_pattern and best_rate > 0.3:
            for path in all_paths:
                m = re.search(best_pattern, os.path.basename(path))
                groups[auto_group_key(m, best_name) if m and m.groups() else '기타'].append(path)
        else:
            print("효과적인 패턴이 없어 파일명 길이로 그룹화합니다.")
            for path in all_paths:
                length = len(os.path.basename(path)) // 10 * 10
                groups[f"길이_{length}-{length + 9}"].append(path)

    if not groups:
        groups['전체'] = list(all_paths)
    return groups


def assign_split(path_groups, names):
    """각 그룹을 작업자 수로 균등 분할해 모든 작업자에게 나눠준다."""
    assignments = {name: [] for name in names}
    for group_name, paths in sorted(path_groups.items(), key=lambda x: len(x[1]), reverse=True):
        paths = list(paths)
        random.shuffle(paths)
        base, remainder = divmod(len(paths), len(names))
        start = 0
        for i, name in enumerate(names):
            end = start + base + (1 if i < remainder else 0)
            assignments[name].extend(paths[start:end])
            start = end
    return assignments


def assign_group(path_groups, names, rebalance):
    """그룹을 쪼개지 않고 작업자에게 통째로 할당한다."""
    assignments = {name: [] for name in names}
    sorted_groups = sorted(path_groups.items(), key=lambda x: len(x[1]), reverse=True)
    count = len(names)

    if len(sorted_groups) <= count:
        for i, (group_name, paths) in enumerate(sorted_groups):
            assignments[names[i]].extend(paths)
            print(f"- 그룹 '{group_name}' {len(paths)}개 -> {names[i]}")
    else:
        groups_per_worker, remainder = divmod(len(sorted_groups), count)
        worker_idx = assigned = 0
        for group_name, paths in sorted_groups:
            assignments[names[worker_idx]].extend(paths)
            print(f"- 그룹 '{group_name}' {len(paths)}개 -> {names[worker_idx]}")
            assigned += 1
            if assigned % (groups_per_worker + (1 if worker_idx < remainder else 0)) == 0:
                worker_idx = (worker_idx + 1) % count

    empty = [name for name, paths in assignments.items() if not paths]
    if empty:
        print(f"\n경고: {', '.join(empty)}에게 할당된 경로가 없습니다.")
        if rebalance:
            print("--rebalance: 모든 경로를 순환 방식으로 재분배합니다.")
            all_paths = [p for paths in assignments.values() for p in paths]
            random.shuffle(all_paths)
            assignments = {name: all_paths[i::count] for i, name in enumerate(names)}
    return assignments


def cmd_distribute(args):
    if args.names:
        names = [n.strip() for n in args.names.split(',') if n.strip()]
    else:
        names = [f"작업자{i}" for i in range(1, args.workers + 1)]
    if not names:
        print("작업자를 1명 이상 지정하세요 (--workers 또는 --names).")
        return 1
    if args.strategy == 'regex' and not args.regex:
        print("--strategy regex 에는 --regex 패턴이 필요합니다.")
        return 1
    if args.seed is not None:
        random.seed(args.seed)

    print("===== 1단계: 리스트에서 경로 수집 =====")
    all_paths, sources = [], {}
    for list_file in args.files:
        lines, _ = read_lines(list_file, detect_encoding(list_file, args.encoding))
        paths = [line.strip() for line in lines if line.strip()]
        for path in paths:
            sources[path] = list_file
        all_paths.extend(paths)
        print(f"{os.path.basename(list_file)}: {len(paths)}개")
    if not all_paths:
        print("유효한 경로가 없습니다.")
        return 1
    print(f"총 {len(all_paths)}개")

    print(f"\n===== 2단계: 그룹화 (전략: {args.strategy}) =====")
    path_groups = group_paths(all_paths, args.strategy, args.regex, args.prefix_len)
    for group_name, paths in sorted(path_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"- {group_name}: {len(paths)}개")

    print(f"\n===== 3단계: 작업자 {len(names)}명에게 분배 (방식: {args.mode}) =====")
    if args.mode == 'split':
        assignments = assign_split(path_groups, names)
        folder, suffix = 'split_paths', 'split'
    else:
        assignments = assign_group(path_groups, names, args.rebalance)
        folder, suffix = 'assigned_paths', 'assigned'

    print("\n===== 4단계: 작업자별 파일 생성 =====")
    output_dir = args.output or os.path.join(os.path.dirname(os.path.abspath(args.files[0])), folder)
    for name, paths in assignments.items():
        if not paths:
            print(f"{name}: 할당 없음")
            continue
        worker_dir = os.path.join(output_dir, name)
        os.makedirs(worker_dir, exist_ok=True)
        by_source = defaultdict(list)
        for path in paths:
            by_source[os.path.basename(sources.get(path, 'unknown'))].append(path)
        for source_name, source_paths in by_source.items():
            with open(os.path.join(worker_dir, f"{source_name}_{suffix}.txt"), 'w', encoding='utf-8') as f:
                f.writelines(f"{p}\n" for p in source_paths)
        print(f"{name}: {len(paths)}개")

    print(f"\n저장 위치: {output_dir}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="리스트 분할/작업자 분배 도구 (02.data_slice Linux CLI 버전)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    p_split = sub.add_parser('split', help='리스트 파일 하나를 N개 또는 N줄 단위로 분할')
    p_split.add_argument('file', help='분할할 리스트 파일')
    group = p_split.add_mutually_exclusive_group(required=True)
    group.add_argument('--parts', '-n', type=int, help='균등 분할 개수')
    group.add_argument('--lines', '-l', type=int, help='파일당 줄 수')
    p_split.add_argument('--output', '-o', help='저장 폴더 (기본: <파일명>_split)')
    p_split.add_argument('--encoding', '-e', default='auto',
                         choices=['auto', 'utf-8', 'cp949', 'euc-kr', 'utf-16'])
    p_split.set_defaults(func=cmd_split)

    p_dist = sub.add_parser('distribute', help='리스트 경로를 그룹화해 작업자에게 분배')
    p_dist.add_argument('files', nargs='+', help='입력 리스트 파일들')
    who = p_dist.add_mutually_exclusive_group(required=True)
    who.add_argument('--workers', '-w', type=int, help='작업자 수 (작업자1..N 자동 생성)')
    who.add_argument('--names', help='작업자 이름 (콤마 구분)')
    p_dist.add_argument('--strategy', '-s', default='none',
                        choices=['none', 'prefix', 'ip_date', 'dir', 'regex', 'auto', 'worktype'])
    p_dist.add_argument('--regex', help='strategy=regex 일 때 패턴 (첫 번째 그룹이 그룹 키)')
    p_dist.add_argument('--prefix-len', type=int, default=10, help='strategy=prefix 일 때 글자 수')
    p_dist.add_argument('--mode', '-m', default='split', choices=['split', 'group'])
    p_dist.add_argument('--rebalance', action='store_true',
                        help='mode=group 에서 빈 작업자가 생기면 전체를 순환 재분배')
    p_dist.add_argument('--seed', type=int, help='랜덤 시드 (같은 결과 재현)')
    p_dist.add_argument('--output', '-o', help='저장 폴더 (기본: 첫 입력 파일 옆 split_paths/assigned_paths)')
    p_dist.add_argument('--encoding', '-e', default='auto',
                        choices=['auto', 'utf-8', 'cp949', 'euc-kr', 'utf-16'])
    p_dist.set_defaults(func=cmd_distribute)
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == 'split' and (args.parts or args.lines or 0) < 1:
        print("--parts/--lines 는 1 이상이어야 합니다.")
        return 1
    if args.command == 'distribute' and args.workers is not None and args.workers < 1:
        print("--workers 는 1 이상이어야 합니다.")
        return 1
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
