#!/usr/bin/env python3
"""
08.list_merge.py - 리스트 파일 병합 도구

여러 개의 텍스트 리스트 파일(.txt)을 하나로 병합하는 커맨드라인 도구입니다.

주요 기능:
- 여러 txt 파일을 하나로 병합
- 중복 라인 제거 옵션
- 셔플(무작위 순서) 옵션
- 파일 존재 여부 검증 옵션

사용 예시:
    # 기본 병합 (중복 제거)
    python 08.list_merge.py train1.txt train2.txt -o merged.txt

    # 중복 허용
    python 08.list_merge.py train1.txt train2.txt -o merged.txt --allow-duplicates

    # 셔플 적용
    python 08.list_merge.py train1.txt train2.txt -o merged.txt --shuffle

    # 파일 존재 여부 검증
    python 08.list_merge.py train1.txt train2.txt -o merged.txt --verify

    # 전체 옵션 조합
    python 08.list_merge.py train1.txt train2.txt train3.txt -o merged.txt --shuffle --verify
"""

import os
import sys
import argparse
import random
from collections import OrderedDict


def read_list_file(file_path):
    """
    리스트 파일을 읽어서 라인 목록을 반환합니다.

    Args:
        file_path: 읽을 파일 경로

    Returns:
        list: 파일의 각 라인 목록 (빈 라인 제외, 공백 제거)
    """
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:  # 빈 라인 제외
                    lines.append(line)
        print(f"[INFO] '{file_path}' 읽기 완료: {len(lines)}개 라인")
    except FileNotFoundError:
        print(f"[ERROR] 파일을 찾을 수 없습니다: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 파일 읽기 실패 ({file_path}): {e}")
        sys.exit(1)

    return lines


def verify_file_exists(file_list):
    """
    리스트의 각 경로가 실제로 존재하는지 확인합니다.

    Args:
        file_list: 확인할 파일 경로 목록

    Returns:
        tuple: (존재하는 파일 목록, 존재하지 않는 파일 목록)
    """
    existing = []
    missing = []

    total = len(file_list)
    for i, path in enumerate(file_list):
        if (i + 1) % 1000 == 0 or (i + 1) == total:
            print(f"\r[INFO] 파일 존재 여부 확인 중... {i + 1}/{total}", end='', flush=True)

        if os.path.exists(path):
            existing.append(path)
        else:
            missing.append(path)

    print()  # 줄바꿈
    return existing, missing


def merge_lists(input_files, output_file, allow_duplicates=False, shuffle=False, verify=False):
    """
    여러 리스트 파일을 하나로 병합합니다.

    Args:
        input_files: 입력 파일 목록
        output_file: 출력 파일 경로
        allow_duplicates: True이면 중복 허용, False이면 중복 제거
        shuffle: True이면 결과를 셔플
        verify: True이면 파일 존재 여부 확인

    Returns:
        dict: 처리 통계 정보
    """
    stats = {
        'input_files': len(input_files),
        'total_lines': 0,
        'unique_lines': 0,
        'duplicate_lines': 0,
        'missing_files': 0,
        'output_lines': 0
    }

    # 모든 입력 파일에서 라인 수집
    all_lines = []
    for input_file in input_files:
        lines = read_list_file(input_file)
        all_lines.extend(lines)

    stats['total_lines'] = len(all_lines)

    # 중복 처리
    if allow_duplicates:
        merged_lines = all_lines
        stats['unique_lines'] = len(set(all_lines))
        stats['duplicate_lines'] = len(all_lines) - stats['unique_lines']
    else:
        # OrderedDict를 사용하여 순서 유지하면서 중복 제거
        seen = OrderedDict()
        for line in all_lines:
            if line not in seen:
                seen[line] = True
        merged_lines = list(seen.keys())
        stats['unique_lines'] = len(merged_lines)
        stats['duplicate_lines'] = stats['total_lines'] - stats['unique_lines']
        print(f"[INFO] 중복 제거: {stats['total_lines']}개 -> {stats['unique_lines']}개 ({stats['duplicate_lines']}개 중복 제거)")

    # 파일 존재 여부 확인
    if verify:
        print("[INFO] 파일 존재 여부 확인 중...")
        existing, missing = verify_file_exists(merged_lines)
        stats['missing_files'] = len(missing)

        if missing:
            print(f"[WARNING] {len(missing)}개 파일이 존재하지 않습니다:")
            # 최대 10개까지만 출력
            for path in missing[:10]:
                print(f"  - {path}")
            if len(missing) > 10:
                print(f"  ... 외 {len(missing) - 10}개")

            # 누락된 파일 목록 저장
            missing_file = output_file.replace('.txt', '_missing.txt')
            with open(missing_file, 'w', encoding='utf-8') as f:
                for path in missing:
                    f.write(path + '\n')
            print(f"[INFO] 누락된 파일 목록 저장: {missing_file}")

            # 존재하는 파일만 유지
            merged_lines = existing
            print(f"[INFO] 존재하는 파일만 유지: {len(merged_lines)}개")

    # 셔플
    if shuffle:
        print("[INFO] 셔플 적용 중...")
        random.shuffle(merged_lines)

    stats['output_lines'] = len(merged_lines)

    # 출력 디렉토리 생성
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[INFO] 출력 디렉토리 생성: {output_dir}")

    # 결과 저장
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in merged_lines:
            f.write(line + '\n')

    print(f"[INFO] 병합 결과 저장: {output_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='리스트 파일 병합 도구 - 여러 txt 파일을 하나로 병합합니다.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 기본 병합 (중복 제거)
  python 08.list_merge.py train1.txt train2.txt -o merged.txt

  # 중복 허용
  python 08.list_merge.py train1.txt train2.txt -o merged.txt --allow-duplicates

  # 셔플 적용
  python 08.list_merge.py train1.txt train2.txt -o merged.txt --shuffle

  # 파일 존재 여부 검증
  python 08.list_merge.py train1.txt train2.txt -o merged.txt --verify

  # 전체 옵션 조합
  python 08.list_merge.py train1.txt train2.txt train3.txt -o merged.txt --shuffle --verify
        """
    )

    parser.add_argument(
        'input_files',
        nargs='+',
        help='병합할 리스트 파일들 (2개 이상)'
    )

    parser.add_argument(
        '-o', '--output',
        required=True,
        help='출력 파일 경로'
    )

    parser.add_argument(
        '--allow-duplicates',
        action='store_true',
        help='중복 라인 허용 (기본값: 중복 제거)'
    )

    parser.add_argument(
        '--shuffle',
        action='store_true',
        help='결과를 무작위 순서로 섞기'
    )

    parser.add_argument(
        '--verify',
        action='store_true',
        help='리스트의 각 파일이 실제로 존재하는지 확인'
    )

    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='셔플에 사용할 랜덤 시드 (재현성을 위해)'
    )

    args = parser.parse_args()

    # 입력 파일 수 검증
    if len(args.input_files) < 1:
        parser.error("최소 1개 이상의 입력 파일이 필요합니다.")

    # 입력 파일 존재 여부 확인
    for input_file in args.input_files:
        if not os.path.isfile(input_file):
            print(f"[ERROR] 입력 파일을 찾을 수 없습니다: {input_file}")
            sys.exit(1)

    # 랜덤 시드 설정
    if args.seed is not None:
        random.seed(args.seed)
        print(f"[INFO] 랜덤 시드 설정: {args.seed}")

    print("=" * 60)
    print("리스트 파일 병합 도구")
    print("=" * 60)
    print(f"입력 파일: {len(args.input_files)}개")
    for i, f in enumerate(args.input_files, 1):
        print(f"  {i}. {f}")
    print(f"출력 파일: {args.output}")
    print(f"중복 제거: {'아니오' if args.allow_duplicates else '예'}")
    print(f"셔플: {'예' if args.shuffle else '아니오'}")
    print(f"파일 검증: {'예' if args.verify else '아니오'}")
    print("=" * 60)

    # 병합 실행
    stats = merge_lists(
        input_files=args.input_files,
        output_file=args.output,
        allow_duplicates=args.allow_duplicates,
        shuffle=args.shuffle,
        verify=args.verify
    )

    # 결과 출력
    print("\n" + "=" * 60)
    print("처리 완료!")
    print("=" * 60)
    print(f"입력 파일 수: {stats['input_files']}개")
    print(f"총 라인 수: {stats['total_lines']}개")
    print(f"고유 라인 수: {stats['unique_lines']}개")
    print(f"중복 라인 수: {stats['duplicate_lines']}개")
    if args.verify:
        print(f"누락된 파일 수: {stats['missing_files']}개")
    print(f"출력 라인 수: {stats['output_lines']}개")
    print(f"출력 파일: {args.output}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
