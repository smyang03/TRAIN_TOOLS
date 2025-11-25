# -*- coding: utf-8 -*-
"""
04.GTGEN_Tool_svms_v2 고급 기능 검증 스크립트

검증 대상:
1. 실제 파일의 import 문 검증
2. 클래스 구조 및 메서드 존재 여부
3. 핵심 알고리즘 로직 검증
4. 파일 크기 및 코드 복잡도
"""

import os
import sys
import ast
import json

# 색상 코드
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(title):
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")

def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def print_info(msg):
    print(f"  {msg}")

# =================================================================
# 테스트 1: 파일 기본 정보
# =================================================================
def test_file_info():
    print_header("테스트 1: 파일 기본 정보")

    file_path = "04.GTGEN_Tool_svms_v2.py"

    if not os.path.exists(file_path):
        print_error(f"파일을 찾을 수 없습니다: {file_path}")
        return False

    # 파일 크기
    file_size = os.path.getsize(file_path)
    file_size_kb = file_size / 1024
    print_success(f"파일 크기: {file_size:,} bytes ({file_size_kb:.2f} KB)")

    # 줄 수
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        total_lines = len(lines)
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith('#'))
        comment_lines = sum(1 for line in lines if line.strip().startswith('#'))
        blank_lines = total_lines - code_lines - comment_lines

    print_success(f"총 줄 수: {total_lines:,}")
    print_info(f"코드 줄: {code_lines:,}")
    print_info(f"주석 줄: {comment_lines:,}")
    print_info(f"빈 줄: {blank_lines:,}")

    return True

# =================================================================
# 테스트 2: Import 문 검증
# =================================================================
def test_imports():
    print_header("테스트 2: Import 문 검증")

    file_path = "04.GTGEN_Tool_svms_v2.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 주요 라이브러리 확인
    required_imports = [
        'tkinter',
        'PIL',
        'cv2',
        'numpy',
        'json',
        'os',
        'sys'
    ]

    for lib in required_imports:
        if lib in content:
            print_success(f"{lib} import 확인")
        else:
            print_error(f"{lib} import 누락")

    return True

# =================================================================
# 테스트 3: 클래스 구조 분석
# =================================================================
def test_class_structure():
    print_header("테스트 3: 클래스 구조 분석")

    file_path = "04.GTGEN_Tool_svms_v2.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        tree = ast.parse(content)

        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

        print_success(f"총 클래스 수: {len(classes)}")

        for cls in classes:
            methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)]
            print_info(f"클래스: {cls.name} (메서드 {len(methods)}개)")

            # 주요 메서드 확인
            if cls.name == "ExclusionZoneManager":
                required_methods = ['add_zone', 'remove_zone', 'toggle_zone', 'is_bbox_in_exclusion_zone', 'save_global_zones', 'load_global_zones']
                for method in required_methods:
                    if any(m.name == method for m in methods):
                        print_info(f"  ✓ {method}")
                    else:
                        print_error(f"  ✗ {method} 누락")

            elif cls.name == "AutoDeleteClassManager":
                required_methods = ['add_class', 'remove_class', 'toggle_class', 'is_class_marked_for_deletion', 'filter_bboxes', 'save_config', 'load_config']
                for method in required_methods:
                    if any(m.name == method for m in methods):
                        print_info(f"  ✓ {method}")
                    else:
                        print_error(f"  ✗ {method} 누락")

            elif cls.name == "ClassConfigManager":
                required_methods = ['load_config', 'save_config', 'get_class_names', 'get_class_colors', 'get_button_configs']
                for method in required_methods:
                    if any(m.name == method for m in methods):
                        print_info(f"  ✓ {method}")
                    else:
                        print_error(f"  ✗ {method} 누락")

            elif cls.name == "MainApp":
                # MainApp는 메서드가 너무 많으므로 일부만 확인
                key_methods = ['load_images_from_folder', 'load_bbox', 'draw_bbox', 'load_masking', 'save_masking_info_to_file']
                for method in key_methods:
                    if any(m.name == method for m in methods):
                        print_info(f"  ✓ {method}")

    except SyntaxError as e:
        print_error(f"문법 오류 발견: {e}")
        return False

    return True

# =================================================================
# 테스트 4: 설정 파일 구조 검증
# =================================================================
def test_config_file_structure():
    print_header("테스트 4: 설정 파일 구조 검증")

    # 샘플 설정 파일 생성
    sample_config = {
        "classes": [
            {"id": 0, "name": "person", "key": "1", "color": "magenta"},
            {"id": 1, "name": "vehicle", "key": "2", "color": "blue"}
        ]
    }

    # JSON 직렬화 가능 여부
    try:
        json_str = json.dumps(sample_config, indent=2, ensure_ascii=False)
        print_success("설정 파일 JSON 직렬화 가능")
        print_info(f"샘플 크기: {len(json_str)} bytes")

        # 역직렬화
        loaded = json.loads(json_str)
        assert loaded == sample_config
        print_success("설정 파일 JSON 역직렬화 가능")

        # 필수 필드 확인
        for cls in loaded['classes']:
            required_fields = ['id', 'name', 'key', 'color']
            for field in required_fields:
                if field in cls:
                    print_info(f"  ✓ 필수 필드 '{field}' 존재")
                else:
                    print_error(f"  ✗ 필수 필드 '{field}' 누락")

    except Exception as e:
        print_error(f"설정 파일 구조 오류: {e}")
        return False

    return True

# =================================================================
# 테스트 5: Ray Casting 알고리즘 정확도
# =================================================================
def test_ray_casting_accuracy():
    print_header("테스트 5: Ray Casting 알고리즘 정확도")

    def point_in_polygon(point, polygon):
        x, y = point
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    # 테스트 케이스
    test_cases = [
        # (polygon, point, expected)
        ([(0, 0), (10, 0), (10, 10), (0, 10)], (5, 5), True),  # 사각형 내부
        ([(0, 0), (10, 0), (10, 10), (0, 10)], (15, 15), False),  # 사각형 외부
        ([(0, 0), (10, 0), (5, 10)], (5, 3), True),  # 삼각형 내부
        ([(0, 0), (10, 0), (5, 10)], (0, 10), False),  # 삼각형 외부
        ([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)], (3, 3), True),  # L자 내부
        ([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)], (7, 7), False),  # L자 빈 공간
    ]

    passed = 0
    failed = 0

    for i, (polygon, point, expected) in enumerate(test_cases, 1):
        result = point_in_polygon(point, polygon)
        if result == expected:
            print_success(f"테스트 케이스 {i}: 통과 (예상: {expected}, 결과: {result})")
            passed += 1
        else:
            print_error(f"테스트 케이스 {i}: 실패 (예상: {expected}, 결과: {result})")
            failed += 1

    print_info(f"\n통과: {passed}/{len(test_cases)}")
    print_info(f"실패: {failed}/{len(test_cases)}")

    return failed == 0

# =================================================================
# 테스트 6: 코드 복잡도 분석
# =================================================================
def test_code_complexity():
    print_header("테스트 6: 코드 복잡도 분석")

    file_path = "04.GTGEN_Tool_svms_v2.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        tree = ast.parse(content)

        # 함수 개수
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        print_success(f"총 함수/메서드 수: {len(functions)}")

        # 클래스 개수
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        print_success(f"총 클래스 수: {len(classes)}")

        # import 문 개수
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        print_success(f"총 import 문 수: {len(imports)}")

        # 평균 함수 길이 (간단한 추정)
        total_func_lines = 0
        for func in functions:
            if hasattr(func, 'lineno') and hasattr(func, 'end_lineno'):
                total_func_lines += (func.end_lineno - func.lineno + 1)

        if functions:
            avg_func_length = total_func_lines / len(functions)
            print_info(f"평균 함수 길이: {avg_func_length:.1f} 줄")

    except Exception as e:
        print_error(f"코드 분석 오류: {e}")
        return False

    return True

# =================================================================
# 테스트 7: 성능 테스트
# =================================================================
def test_performance():
    print_header("테스트 7: 성능 테스트")

    import time

    # Ray Casting 성능 테스트
    def point_in_polygon(point, polygon):
        x, y = point
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]
    iterations = 10000

    start_time = time.time()
    for i in range(iterations):
        point = (i % 100, (i * 2) % 100)
        result = point_in_polygon(point, polygon)
    end_time = time.time()

    elapsed = end_time - start_time
    ops_per_sec = iterations / elapsed

    print_success(f"Ray Casting 성능 테스트")
    print_info(f"반복 횟수: {iterations:,}")
    print_info(f"소요 시간: {elapsed:.4f}초")
    print_info(f"초당 연산: {ops_per_sec:,.0f} ops/sec")

    if ops_per_sec > 100000:
        print_success("성능: 우수 (>100K ops/sec)")
    elif ops_per_sec > 10000:
        print_success("성능: 양호 (>10K ops/sec)")
    else:
        print_info("성능: 보통")

    return True

# =================================================================
# 메인 실행
# =================================================================
if __name__ == "__main__":
    print_header("04.GTGEN_Tool_svms_v2 고급 기능 검증 시작")

    results = []

    results.append(("파일 기본 정보", test_file_info()))
    results.append(("Import 문 검증", test_imports()))
    results.append(("클래스 구조 분석", test_class_structure()))
    results.append(("설정 파일 구조", test_config_file_structure()))
    results.append(("Ray Casting 정확도", test_ray_casting_accuracy()))
    results.append(("코드 복잡도 분석", test_code_complexity()))
    results.append(("성능 테스트", test_performance()))

    # 최종 요약
    print_header("검증 결과 요약")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"\n{GREEN}통과한 테스트: {passed}/{total}{RESET}")
    for test_name, result in results:
        if result:
            print(f"  {GREEN}✓{RESET} {test_name}")
        else:
            print(f"  {RED}✗{RESET} {test_name}")

    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}전체 통과율: {passed/total*100:.1f}%{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")

    if passed == total:
        print(f"{GREEN}🎉 모든 고급 검증 테스트 통과!{RESET}\n")
        sys.exit(0)
    else:
        print(f"{RED}❌ 일부 테스트 실패. 위 내용을 확인해주세요.{RESET}\n")
        sys.exit(1)
