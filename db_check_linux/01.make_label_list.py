import traceback
import numpy as np
import os.path
import random
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

def print_class_statistics(obj_annotation, title):
    """클래스별 통계 출력"""
    print(f"\n{title}:")
    print(f"전체 어노테이션 수: {int(obj_annotation[0])}")
    for i in range(1, len(obj_annotation)):
        if obj_annotation[i] > 0:  # 0보다 큰 값만 출력
            print(f"클래스 {i-1}: {int(obj_annotation[i])}개")

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

def create_complete_dataset_list(input_path, output_path, keyword=None):
    """
    입력 경로의 모든 이미지 파일을 하나의 리스트로 생성하는 함수

    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 저장 경로
        keyword: 파일명 필터링 키워드 (None이면 모든 파일 포함, 한글/특수문자 지원)
    """
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"전체 데이터셋 리스트 생성 시작: {input_path}")
    if keyword:
        logger.info(f"파일명 필터 키워드: '{keyword}'")
    
    # 결과 파일 경로 설정
    complete_list_path = output_path / 'complete_dataset.txt'
    complete_annotation_path = output_path / 'complete_annotation.txt'
    error_log_path = output_path / 'errors.txt'
    
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
    }
    
    # 파일 리스트 초기화
    with open(complete_list_path, 'w', encoding='utf-8') as f:
        pass  # 파일 초기화
    
    # 에러 로그 파일 초기화
    with open(error_log_path, 'w', encoding='utf-8') as f:
        f.write("에러 로그\n")
        f.write("=" * 50 + "\n")
    
    # 전체 파일 수 계산
    total_files = count_jpg_files(input_path)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")
    
    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None
    
    # 입력 경로 순회
    logger.info(f"전체 {total_files}개 파일 처리 시작...")

    for root, _, files in os.walk(input_path):
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue

            # 키워드 필터링 (파일명에 키워드가 포함되어 있는지 확인)
            if keyword and keyword not in file:
                stats['filtered_cnt'] += 1
                continue

            stats['total_cnt'] += 1
            progress = (stats['total_cnt'] / total_files) * 100

            # 파일 경로 설정
            full_path = os.path.join(root, file)
            label_path = get_label_path_from_image(full_path)
            
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
                else:
                    stats['error_cnt'] += 1
                    continue
            
            # 어노테이션 처리
            current_annotation = np.zeros(90)
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if not lines:  # 빈 파일 처리
                        stats['empty_label_cnt'] += 1
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
                                if class_id < 0 or class_id >= 89:  # 클래스 ID 범위 검증
                                    logger.warning(f"잘못된 클래스 ID {label_path}:{line_num} - {class_id}")
                                    continue
                                    
                                current_annotation[0] += 1  # 전체 어노테이션 카운트
                                current_annotation[class_id + 1] += 1  # 클래스별 카운트
                            except (ValueError, IndexError) as e:
                                logger.warning(f"어노테이션 파싱 오류 {label_path}:{line_num} - {e}")
                                continue
                                
            except Exception as e:
                logger.error(f"라벨 파일 처리 오류 {label_path}: {e}")
                stats['error_cnt'] += 1
                with open(error_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"라벨 처리 오류 - {label_path}: {e}\n")
                continue
            
            # 결과 저장 - UTF-8로 인코딩
            with open(complete_list_path, 'a', encoding='utf-8') as f:
                f.write(f"{full_path}\n")
            
            stats['obj_annotation'] += current_annotation
            stats['total_annotations'] += current_annotation[0]
            
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
    
    # 경로 문제 요약 저장
    if stats['path_issues']:
        path_issues_path = output_path / 'path_issues_summary.txt'
        with open(path_issues_path, 'w', encoding='utf-8') as f:
            f.write(f"경로 문제 요약 (총 {len(stats['path_issues'])}개)\n")
            f.write("=" * 50 + "\n")
            for issue in stats['path_issues']:
                f.write(f"{issue}\n")
    
    logger.info("전체 데이터셋 리스트 생성 완료")
    logger.info(f"처리된 파일: {stats['total_cnt']}개")
    logger.info(f"생성된 라벨: {stats['created_labels']}개")
    logger.info(f"에러 발생: {stats['error_cnt']}개")

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

    # 전체 파일 수 계산
    total_files = count_jpg_files(input_path)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")

    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 입력 경로 순회
    logger.info(f"전체 {total_files}개 파일 처리 시작...")

    for root, _, files in os.walk(input_path):
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue

            stats['total_cnt'] += 1
            progress = (stats['total_cnt'] / total_files) * 100

            # 파일 경로 설정
            full_path = os.path.join(root, file)
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

def create_limited_dataset(input_path, output_path, num_files, keyword=None, background_only=False):
    """
    전체 데이터셋에서 지정된 개수의 파일을 파일명 패턴 분포에 맞게 선택하여 리스트 생성

    Args:
        input_path: 입력 데이터셋 경로
        output_path: 출력 저장 경로
        num_files: 선택할 파일 개수
        keyword: 파일명 필터링 키워드 (None이면 모든 파일 포함, 한글/특수문자 지원)
        background_only: True일 경우 배경 이미지(어노테이션 없음)만 추출
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
    
    # 전체 파일 리스트 수집
    all_files = []
    print(f"입력 경로에서 이미지 파일 찾는 중...")

    for root, _, files in os.walk(input_path):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg')):
                # 키워드 필터링 (파일명에 키워드가 포함되어 있는지 확인)
                if keyword and keyword not in file:
                    stats['filtered_cnt'] += 1
                    continue
                full_path = os.path.join(root, file)
                all_files.append(full_path)

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
    클래스 분포를 균등하게 맞춰서 제한된 데이터셋 생성

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
    }

    # 1단계: 전체 이미지 수집
    print(f"입력 경로에서 이미지 파일 찾는 중...")
    all_files = []
    for root, _, files in os.walk(input_path):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg')):
                full_path = os.path.join(root, file)
                all_files.append(full_path)

    total_available = len(all_files)
    logger.info(f"총 {total_available}개의 이미지 파일 발견")

    if total_available == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None

    # 2단계: 각 이미지가 포함하는 클래스 분석
    print(f"\n각 이미지의 클래스 정보 분석 중...")
    class_to_images = defaultdict(list)  # {class_id: [image_paths]}
    image_class_count = defaultdict(int)  # 각 클래스를 포함하는 이미지 개수

    for i, image_path in enumerate(all_files):
        if (i + 1) % 100 == 0:
            print(f"\r진행률: {(i+1)/total_available*100:.1f}% ({i+1}/{total_available})", end='')

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

                # 각 클래스별로 이미지 기록
                for class_id in image_classes:
                    if class_id in target_classes:
                        class_to_images[class_id].append(image_path)
                        image_class_count[class_id] += 1

        except Exception as e:
            logger.warning(f"라벨 파일 읽기 실패: {label_path} - {e}")
            continue

    print(f"\r클래스 분석 완료: 100.0%                    ")

    # 클래스별 분포 출력
    print(f"\n클래스별 이미지 분포:")
    for class_id in sorted(target_classes):
        count = image_class_count.get(class_id, 0)
        stats['class_distribution'][class_id] = count
        print(f"  클래스 {class_id}: {count}개 이미지")

    if not class_to_images:
        logger.error("균등화 대상 클래스를 포함하는 이미지가 없습니다.")
        return None

    # 3단계: 클래스 균등 샘플링
    print(f"\n클래스 균등 샘플링 시작...")
    selected_images = set()
    target_per_class = num_files // len(target_classes)

    # 라운드 로빈 방식으로 각 클래스에서 순차적으로 선택
    class_indices = {class_id: 0 for class_id in target_classes}

    # 각 클래스에서 랜덤하게 섞기
    for class_id in target_classes:
        random.shuffle(class_to_images[class_id])

    # 목표 개수에 도달할 때까지 반복
    round_num = 0
    while len(selected_images) < num_files:
        added_this_round = 0

        for class_id in target_classes:
            if len(selected_images) >= num_files:
                break

            # 이 클래스에서 아직 선택할 이미지가 있는지 확인
            if class_indices[class_id] < len(class_to_images[class_id]):
                image_path = class_to_images[class_id][class_indices[class_id]]

                # 중복 체크 후 추가
                if image_path not in selected_images:
                    selected_images.add(image_path)
                    added_this_round += 1

                class_indices[class_id] += 1

        round_num += 1

        # 더 이상 추가할 이미지가 없으면 종료
        if added_this_round == 0:
            logger.warning(f"목표 개수({num_files})에 도달하지 못했습니다. 선택된 개수: {len(selected_images)}")
            break

    selected_files = list(selected_images)
    logger.info(f"{len(selected_files)}개 이미지 선택 완료")

    # 4단계: 선택된 이미지의 클래스별 통계
    selected_class_count = defaultdict(int)
    for image_path in selected_files:
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
        except:
            pass

    print(f"\n선택된 이미지의 클래스별 분포:")
    for class_id in sorted(target_classes):
        count = selected_class_count.get(class_id, 0)
        stats['class_stats'][class_id] = count
        percentage = count / len(selected_files) * 100 if selected_files else 0
        print(f"  클래스 {class_id}: {count}개 ({percentage:.1f}%)")

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

    logger.info("클래스 분포 균등화 데이터셋 생성 완료")
    return stats

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
    
    # 전체 파일 수 계산
    total_files = count_jpg_files(input_path)
    logger.info(f"입력 경로에서 총 {total_files}개의 이미지 파일 발견")
    
    if total_files == 0:
        logger.error("입력 경로에 이미지 파일이 없습니다.")
        return None
    
    # 입력 경로 순회
    for root, _, files in os.walk(input_path):
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue
                
            stats['total_cnt'] += 1
            progress = (stats['total_cnt'] / total_files) * 100
            
            # 파일 경로 설정
            full_path = os.path.join(root, file)
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

def process_dataset(input_path, output_path, train_rate=0.8, skip_rate=0):
    """데이터셋을 처리하고 train/validation 세트로 분할하는 함수"""
    valid_rate = 1.0 - train_rate
    
    # 출력 디렉토리 생성
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"데이터셋 처리 시작: {input_path}")
    
    # 전체 파일 수 계산
    total_files = count_jpg_files(input_path)
    logger.info(f"전체 처리할 파일 수: {total_files}")
    
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
        'created_labels': 0       
    }

    # train/valid 파일 초기화
    with open(train_path, 'w', encoding='utf-8') as f:
        pass
    with open(val_path, 'w', encoding='utf-8') as f:
        pass
    with open(error_path, 'w', encoding='utf-8') as f:
        f.write("에러 로그\n")

    # 입력 경로 순회
    for root, _, files in os.walk(input_path):
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue

            stats['total_cnt'] += 1
            progress = (stats['total_cnt'] / total_files) * 100
            
            # 스킵 처리
            if random.random() < skip_rate:
                stats['skip_cnt'] += 1
                continue

            # 파일 경로 설정
            full_path = os.path.join(root, file)
            label_path = get_label_path_from_image(full_path)

            # train/valid 분할 결정
            is_train = random.random() < train_rate

            # 라벨 파일 존재 확인 및 처리
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

            # 어노테이션 처리
            current_annotation = np.zeros(90)
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if not lines:  # 빈 파일 처리
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
                                    current_annotation[0] += 1  # 전체 어노테이션 카운트
                                    current_annotation[class_id + 1] += 1  # 클래스별 카운트
                            except (ValueError, IndexError):
                                continue
                                
            except Exception as e:
                logger.error(f"어노테이션 처리 오류 {label_path}: {e}")
                stats['error_cnt'] += 1
                with open(error_path, 'a', encoding='utf-8') as f:
                    f.write(f"{label_path}: {e}\n")
                continue

            # 결과 저장 - UTF-8 인코딩 추가
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

            # 진행률 표시
            if stats['total_cnt'] % 1000 == 0:
                logger.info(f"진행률: {progress:.1f}%")
                
            print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
                  f"학습: {stats['train_img_cnt']}(어노테이션: {stats['train_annotations']}) | "
                  f"검증: {stats['valid_img_cnt']}(어노테이션: {stats['valid_annotations']}) | "
                  f"전체 어노테이션: {stats['total_annotations']}", end='')

    print("\n")  # 진행률 표시 줄바꿈

    # 최종 통계 저장
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
                        exclude_background=False, combined_filter=False):
    """데이터셋을 처리하고 train/validation 세트로 분할하는 고급 함수"""
    
    valid_rate = 1.0 - train_rate
    
    # 출력 디렉토리 생성
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logger = setup_logging(output_path)
    logger.info(f"고급 데이터셋 처리 시작: {input_path}")
    
    # 전체 파일 수 계산
    total_files = count_jpg_files(input_path)
    logger.info(f"전체 처리 대상 파일 수: {total_files}")
    
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
        'target_class_annotations': 0  
    }

    # 출력 파일 초기화
    with open(train_path, 'w', encoding='utf-8') as f:
        pass
    with open(val_path, 'w', encoding='utf-8') as f:
        pass
    with open(filtered_path, 'w', encoding='utf-8') as f:
        pass
    with open(excluded_path, 'w', encoding='utf-8') as f:
        pass

    # 입력 경로 순회
    for root, _, files in os.walk(input_path):
        for file in files:
            if not file.lower().endswith(('.jpg', '.jpeg')):
                continue

            stats['total_cnt'] += 1
            progress = (stats['total_cnt'] / total_files) * 100
            
            # 스킵 처리
            if random.random() < skip_rate:
                stats['skip_cnt'] += 1
                continue

            # 파일 경로 설정
            full_path = os.path.join(root, file)
            label_path = get_label_path_from_image(full_path)

            # 라벨 파일 존재 확인 및 처리
            no_label = False
            empty_label = False
            
            if not os.path.isfile(label_path):
                if create_empty_label(label_path, logger):
                    stats['created_labels'] += 1
                    no_label = True
                else:
                    stats['error_cnt'] += 1
                    continue

            # 어노테이션 처리 및 필터링 조건 검사
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
                                    
                                    # 대상 클래스 포함 여부 확인
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
            
            # 1. 클래스 필터링
            if filter_by_class and not combined_filter:
                include_file = contains_target_class
                if contains_target_class:
                    stats['class_filtered'] += 1
            
            # 2. 배경 이미지 제외
            if exclude_background and not combined_filter:
                if empty_label or current_annotation[0] == 0:
                    include_file = False
                    stats['background_excluded'] += 1
            
            # 3. 복합 필터링 (클래스 필터링 + 배경 제외)
            if combined_filter:
                include_file = contains_target_class and not (empty_label or current_annotation[0] == 0)
                if contains_target_class:
                    stats['class_filtered'] += 1
                if empty_label or current_annotation[0] == 0:
                    stats['background_excluded'] += 1
            
            # 필터링 결과에 따라 처리
            if include_file:
                stats['filtered_cnt'] += 1
                stats['processed_cnt'] += 1
                
                # 필터링된 전체 목록에 추가
                with open(filtered_path, 'a', encoding='utf-8') as f:
                    f.write(f"{full_path}\n")
                
                # train/valid 분할 결정
                is_train = random.random() < train_rate
                
                # 라벨 상태 통계 업데이트
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
                
                # 결과 저장
                if is_train:
                    with open(train_path, 'a', encoding='utf-8') as f:
                        f.write(f"{full_path}\n")
                else:
                    with open(val_path, 'a', encoding='utf-8') as f:
                        f.write(f"{full_path}\n")
                
                # 어노테이션 통계 업데이트
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
            else:
                # 제외된 파일 목록에 추가
                stats['excluded_cnt'] += 1
                with open(excluded_path, 'a', encoding='utf-8') as f:
                    f.write(f"{full_path}\n")
            
            # 진행 상황 출력
            print(f"\r진행률: {progress:.1f}% ({stats['total_cnt']}/{total_files}) | "
                  f"처리: {stats['processed_cnt']} | "
                  f"필터링: {stats['filtered_cnt']} | "
                  f"제외: {stats['excluded_cnt']} | "
                  f"학습: {stats['train_img_cnt']} | "
                  f"검증: {stats['valid_img_cnt']}", end='')

    print("\n")  # 진행률 표시 줄바꿈

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
            print("13. 종료")

            choice = input("\n작업을 선택하세요 (1-13): ")
            
            if choice == '1':
                # 데이터셋 처리 기능
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()
                
                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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

                try:
                    stats = process_dataset(input_path, output_path, train_rate, skip_rate)
                    
                    # 결과 출력
                    print("\n처리 완료!")
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()
                
                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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

                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                print(f"선택할 파일 개수: {num_files}개")
                print(f"배경 이미지만 추출: {'예' if background_only else '아니오'}")

                try:
                    stats = create_limited_dataset(input_path, output_path, num_files, background_only=background_only)
                    
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()
                
                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
                    continue
                
                output_path = input("출력 저장 경로를 입력하세요 (기본 경로: Enter): ")
                if not output_path:
                    output_path = get_default_output_path(input_path)
                
                print(f"\n처리 시작...")
                print(f"입력 경로: {input_path}")
                print(f"출력 경로: {output_path}")
                
                try:
                    stats = create_complete_dataset_list(input_path, output_path)
                    
                    if stats:
                        print("\n전체 데이터셋 리스트 생성 완료!")
                        print(f"처리된 파일 개수: {stats['total_cnt']}개")
                        print(f"에러 발생 수: {stats['error_cnt']}개")
                        print(f"생성된 라벨: {stats['created_labels']}개")
                        
                        print_class_statistics(stats['obj_annotation'], "클래스별 통계")
                
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()
                
                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()
                
                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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
                        exclude_background, combined_filter
                    )
                    
                    print("\n고급 데이터셋 처리 완료!")
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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
                input_path = input("입력 데이터셋 경로를 입력하세요 (기본 경로: Enter): ")
                if not input_path:
                    input_path = get_default_input_path()

                if not os.path.exists(input_path):
                    print(f"오류: 입력한 경로가 존재하지 않습니다: {input_path}")
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
                        print(f"총 선택된 파일: {stats['total_selected']}개")
                        print(f"목표 파일 수: {num_files}개")
                        print(f"처리된 클래스 수: {len(stats['class_distribution'])}개")

                        print(f"\n클래스별 분포:")
                        for class_id in sorted(stats['class_distribution'].keys()):
                            count = stats['class_distribution'][class_id]
                            print(f"  클래스 {class_id}: {count}개 이미지")

                        print(f"\n생성된 파일:")
                        print(f"  - balanced_dataset.txt: 선택된 이미지 경로 목록")
                        print(f"  - balanced_annotation.txt: 이미지별 어노테이션 수")
                        print(f"  - balanced_stats.txt: 상세 통계 정보")

                except Exception as e:
                    print(f"\n데이터 처리 중 오류 발생: {e}")
                    traceback.print_exc()

            elif choice == '13':
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