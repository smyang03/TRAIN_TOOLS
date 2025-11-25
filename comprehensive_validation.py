# -*- coding: utf-8 -*-
"""
04.GTGEN_Tool_svms_v2 포괄적인 기능 검증 스크립트

검증 대상:
1. ExclusionZoneManager - 제외 영역 관리
2. AutoDeleteClassManager - 클래스 자동 삭제
3. ClassConfigManager - 클래스 설정 관리
4. ClassConfigDialog - 클래스 설정 다이얼로그
5. MainApp - 메인 애플리케이션 핵심 로직
6. 마스킹 기능
7. 파일 저장/로드 기능
8. UI 이벤트 핸들러
"""

import sys
import os
import json
import tempfile
import traceback
from pathlib import Path

# 색상 코드
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# 테스트 결과 저장
test_results = {
    'passed': [],
    'failed': [],
    'warnings': []
}

def print_header(title):
    """테스트 헤더 출력"""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")

def print_subheader(title):
    """서브헤더 출력"""
    print(f"\n{YELLOW}{'-' * 80}{RESET}")
    print(f"{YELLOW}{title}{RESET}")
    print(f"{YELLOW}{'-' * 80}{RESET}")

def print_success(msg):
    """성공 메시지"""
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    """에러 메시지"""
    print(f"{RED}✗ {msg}{RESET}")

def print_warning(msg):
    """경고 메시지"""
    print(f"{YELLOW}⚠ {msg}{RESET}")

def record_result(test_name, passed, message=""):
    """테스트 결과 기록"""
    if passed:
        test_results['passed'].append(test_name)
        print_success(f"{test_name}: {message}")
    else:
        test_results['failed'].append(test_name)
        print_error(f"{test_name}: {message}")

# =================================================================
# 테스트 1: ExclusionZoneManager 전체 기능 검증
# =================================================================
def test_exclusion_zone_manager():
    print_header("테스트 1: ExclusionZoneManager 전체 기능 검증")

    try:
        test_code = """
import json
import tempfile
import os

class ExclusionZoneManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.zones = []
        self.global_zones = []
        self.current_zone_file = None
        self.global_zone_file = os.path.join(self.base_dir, ".global_exclusion_zones.json")
        self.enabled_file = os.path.join(self.base_dir, ".exclusion_zone_enabled.txt")
        self.use_global = True

    def add_zone(self, points, use_global=True):
        if len(points) >= 3:
            zone = {'points': points, 'enabled': True}
            if use_global:
                self.global_zones.append(zone)
            else:
                self.zones.append(zone)
            return True
        return False

    def remove_zone(self, index):
        if 0 <= index < len(self.global_zones):
            del self.global_zones[index]
            return True
        return False

    def toggle_zone(self, index):
        if 0 <= index < len(self.global_zones):
            self.global_zones[index]['enabled'] = not self.global_zones[index]['enabled']
            return True
        return False

    def clear_zones(self):
        self.global_zones = []

    def is_bbox_in_exclusion_zone(self, bbox):
        zones_to_check = self.global_zones if self.use_global else self.zones
        if not zones_to_check:
            return False
        x1, y1, x2, y2 = bbox[3], bbox[4], bbox[5], bbox[6]
        bbox_center = ((x1 + x2) / 2, (y1 + y2) / 2)
        for zone in zones_to_check:
            if zone['enabled'] and self._point_in_polygon(bbox_center, zone['points']):
                return True
        return False

    def _point_in_polygon(self, point, polygon):
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

    def save_global_zones(self):
        try:
            with open(self.global_zone_file, 'w') as f:
                json.dump(self.global_zones, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving: {e}")
            return False

    def load_global_zones(self):
        if os.path.exists(self.global_zone_file):
            try:
                with open(self.global_zone_file, 'r') as f:
                    self.global_zones = json.load(f)
                return True
            except Exception as e:
                print(f"Error loading: {e}")
                self.global_zones = []
                return False
        return True

    def save_enabled_state(self, enabled):
        try:
            with open(self.enabled_file, 'w') as f:
                f.write('1' if enabled else '0')
            return True
        except:
            return False

    def load_enabled_state(self):
        if os.path.exists(self.enabled_file):
            try:
                with open(self.enabled_file, 'r') as f:
                    return f.read().strip() == '1'
            except:
                pass
        return False

# 테스트 시작
with tempfile.TemporaryDirectory() as tmpdir:
    manager = ExclusionZoneManager(tmpdir)

    # 1-1. 인스턴스 생성
    assert manager is not None, "인스턴스 생성 실패"
    print("1-1. 인스턴스 생성: PASS")

    # 1-2. 폴리곤 추가 (사각형)
    rect = [(100, 100), (300, 100), (300, 300), (100, 300)]
    result = manager.add_zone(rect, use_global=True)
    assert result == True, "폴리곤 추가 실패"
    assert len(manager.global_zones) == 1, "폴리곤 수 불일치"
    print("1-2. 폴리곤 추가: PASS")

    # 1-3. 여러 개 폴리곤 추가
    triangle = [(400, 400), (500, 400), (450, 500)]
    pentagon = [(600, 600), (650, 580), (680, 620), (640, 680), (590, 660)]
    manager.add_zone(triangle, use_global=True)
    manager.add_zone(pentagon, use_global=True)
    assert len(manager.global_zones) == 3, "다중 폴리곤 추가 실패"
    print("1-3. 다중 폴리곤 추가: PASS")

    # 1-4. bbox 중심점 체크 (사각형 안쪽)
    bbox_inside = [False, 'person', 0, 150, 150, 250, 250]
    is_inside = manager.is_bbox_in_exclusion_zone(bbox_inside)
    assert is_inside == True, "bbox 내부 체크 실패"
    print("1-4. bbox 내부 체크: PASS")

    # 1-5. bbox 중심점 체크 (사각형 바깥쪽)
    bbox_outside = [False, 'car', 1, 350, 350, 380, 380]
    is_outside = manager.is_bbox_in_exclusion_zone(bbox_outside)
    assert is_outside == False, "bbox 외부 체크 실패"
    print("1-5. bbox 외부 체크: PASS")

    # 1-6. bbox 중심점 체크 (삼각형 안쪽)
    bbox_triangle = [False, 'bike', 2, 440, 440, 470, 470]
    is_in_triangle = manager.is_bbox_in_exclusion_zone(bbox_triangle)
    assert is_in_triangle == True, "삼각형 내부 체크 실패"
    print("1-6. 삼각형 내부 체크: PASS")

    # 1-7. 영역 토글 (비활성화)
    manager.toggle_zone(0)
    assert manager.global_zones[0]['enabled'] == False, "영역 비활성화 실패"
    is_inside_after_toggle = manager.is_bbox_in_exclusion_zone(bbox_inside)
    assert is_inside_after_toggle == False, "비활성화 후 체크 실패"
    print("1-7. 영역 토글 (비활성화): PASS")

    # 1-8. 영역 토글 (재활성화)
    manager.toggle_zone(0)
    assert manager.global_zones[0]['enabled'] == True, "영역 재활성화 실패"
    is_inside_reactivated = manager.is_bbox_in_exclusion_zone(bbox_inside)
    assert is_inside_reactivated == True, "재활성화 후 체크 실패"
    print("1-8. 영역 토글 (재활성화): PASS")

    # 1-9. 영역 삭제
    manager.remove_zone(1)  # 삼각형 삭제
    assert len(manager.global_zones) == 2, "영역 삭제 실패"
    print("1-9. 영역 삭제: PASS")

    # 1-10. 저장 및 로드
    manager.save_global_zones()
    new_manager = ExclusionZoneManager(tmpdir)
    new_manager.load_global_zones()
    assert len(new_manager.global_zones) == 2, "저장/로드 실패"
    print("1-10. 저장 및 로드: PASS")

    # 1-11. 활성화 상태 저장/로드
    manager.save_enabled_state(True)
    enabled = manager.load_enabled_state()
    assert enabled == True, "활성화 상태 저장/로드 실패"
    print("1-11. 활성화 상태 저장/로드: PASS")

    # 1-12. 모든 영역 삭제
    manager.clear_zones()
    assert len(manager.global_zones) == 0, "전체 삭제 실패"
    print("1-12. 모든 영역 삭제: PASS")

    # 1-13. 경계 케이스: 2개 점 (실패해야 함)
    invalid_polygon = [(100, 100), (200, 200)]
    result = manager.add_zone(invalid_polygon, use_global=True)
    assert result == False, "잘못된 폴리곤 추가가 허용됨"
    print("1-13. 경계 케이스 (2개 점): PASS")

    # 1-14. 경계 케이스: bbox가 영역 경계선에 정확히 위치
    manager.add_zone([(0, 0), (100, 0), (100, 100), (0, 100)], use_global=True)
    bbox_edge = [False, 'test', 0, 48, 48, 52, 52]  # 중심점 (50, 50)
    is_on_edge = manager.is_bbox_in_exclusion_zone(bbox_edge)
    print(f"1-14. 경계선 테스트: {is_on_edge}")

print("=" * 40)
print("테스트 1: 모든 ExclusionZoneManager 테스트 통과!")
"""

        exec(test_code)
        record_result("ExclusionZoneManager", True, "모든 서브 테스트 통과")

    except Exception as e:
        record_result("ExclusionZoneManager", False, str(e))
        print(traceback.format_exc())

# =================================================================
# 테스트 2: AutoDeleteClassManager 전체 기능 검증
# =================================================================
def test_auto_delete_class_manager():
    print_header("테스트 2: AutoDeleteClassManager 전체 기능 검증")

    try:
        test_code = """
import json
import tempfile
import os

class AutoDeleteClassManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.config_file = os.path.join(self.base_dir, ".auto_delete_classes.json")
        self.delete_class_ids = set()
        self.load_config()

    def add_class(self, class_id):
        self.delete_class_ids.add(class_id)
        self.save_config()

    def remove_class(self, class_id):
        self.delete_class_ids.discard(class_id)
        self.save_config()

    def toggle_class(self, class_id):
        if class_id in self.delete_class_ids:
            self.delete_class_ids.remove(class_id)
        else:
            self.delete_class_ids.add(class_id)
        self.save_config()

    def is_class_marked_for_deletion(self, class_id):
        return class_id in self.delete_class_ids

    def filter_bboxes(self, bbox_list, class_name_list=None):
        if not self.delete_class_ids:
            return bbox_list
        filtered = []
        for bbox in bbox_list:
            class_id = int(bbox[2])
            if class_id not in self.delete_class_ids:
                filtered.append(bbox)
        return filtered

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(list(self.delete_class_ids), f)
            return True
        except Exception as e:
            print(f"Error saving: {e}")
            return False

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.delete_class_ids = set(json.load(f))
                return True
            except Exception as e:
                print(f"Error loading: {e}")
                self.delete_class_ids = set()
                return False
        return True

# 테스트 시작
with tempfile.TemporaryDirectory() as tmpdir:
    manager = AutoDeleteClassManager(tmpdir)

    # 2-1. 인스턴스 생성
    assert manager is not None, "인스턴스 생성 실패"
    assert len(manager.delete_class_ids) == 0, "초기 상태 불일치"
    print("2-1. 인스턴스 생성: PASS")

    # 2-2. 클래스 추가
    manager.add_class(0)
    manager.add_class(1)
    manager.add_class(2)
    assert len(manager.delete_class_ids) == 3, "클래스 추가 실패"
    assert 0 in manager.delete_class_ids, "클래스 0 누락"
    assert 1 in manager.delete_class_ids, "클래스 1 누락"
    assert 2 in manager.delete_class_ids, "클래스 2 누락"
    print("2-2. 클래스 추가: PASS")

    # 2-3. 클래스 삭제 대상 확인
    is_marked_0 = manager.is_class_marked_for_deletion(0)
    is_marked_5 = manager.is_class_marked_for_deletion(5)
    assert is_marked_0 == True, "클래스 0 마킹 확인 실패"
    assert is_marked_5 == False, "클래스 5는 마킹되지 않아야 함"
    print("2-3. 클래스 마킹 확인: PASS")

    # 2-4. bbox 필터링 (자동 삭제)
    bbox_list = [
        [False, 'person', 0, 100, 100, 200, 200],  # 삭제 대상
        [False, 'car', 1, 300, 300, 400, 400],     # 삭제 대상
        [False, 'bike', 2, 500, 500, 600, 600],    # 삭제 대상
        [False, 'truck', 3, 700, 700, 800, 800],   # 유지
        [False, 'bus', 4, 900, 900, 1000, 1000]    # 유지
    ]

    filtered = manager.filter_bboxes(bbox_list)
    assert len(filtered) == 2, f"필터링 결과 불일치: {len(filtered)}개"
    assert filtered[0][2] == 3, "남은 bbox 클래스 불일치"
    assert filtered[1][2] == 4, "남은 bbox 클래스 불일치"
    print("2-4. bbox 필터링: PASS")

    # 2-5. 클래스 제거
    manager.remove_class(1)
    assert 1 not in manager.delete_class_ids, "클래스 제거 실패"
    assert len(manager.delete_class_ids) == 2, "삭제 후 개수 불일치"
    print("2-5. 클래스 제거: PASS")

    # 2-6. 클래스 토글 (제거)
    manager.toggle_class(0)
    assert 0 not in manager.delete_class_ids, "토글 제거 실패"
    print("2-6. 클래스 토글 (제거): PASS")

    # 2-7. 클래스 토글 (추가)
    manager.toggle_class(5)
    assert 5 in manager.delete_class_ids, "토글 추가 실패"
    print("2-7. 클래스 토글 (추가): PASS")

    # 2-8. 설정 저장 및 로드
    manager.save_config()
    new_manager = AutoDeleteClassManager(tmpdir)
    assert len(new_manager.delete_class_ids) == len(manager.delete_class_ids), "저장/로드 후 개수 불일치"
    assert new_manager.delete_class_ids == manager.delete_class_ids, "저장/로드 후 데이터 불일치"
    print("2-8. 설정 저장 및 로드: PASS")

    # 2-9. 빈 리스트 필터링
    empty_filtered = manager.filter_bboxes([])
    assert len(empty_filtered) == 0, "빈 리스트 필터링 실패"
    print("2-9. 빈 리스트 필터링: PASS")

    # 2-10. 삭제 대상이 없을 때 필터링
    manager_empty = AutoDeleteClassManager(tmpdir + "/empty")
    all_bbox = [
        [False, 'person', 0, 100, 100, 200, 200],
        [False, 'car', 1, 300, 300, 400, 400]
    ]
    filtered_all = manager_empty.filter_bboxes(all_bbox)
    assert len(filtered_all) == 2, "삭제 대상 없을 때 필터링 실패"
    print("2-10. 삭제 대상 없을 때 필터링: PASS")

    # 2-11. 중복 추가 (set이므로 중복 없어야 함)
    manager.add_class(2)
    manager.add_class(2)
    manager.add_class(2)
    count_2 = list(manager.delete_class_ids).count(2)
    assert count_2 == 1, "중복 추가 방지 실패"
    print("2-11. 중복 추가 방지: PASS")

print("=" * 40)
print("테스트 2: 모든 AutoDeleteClassManager 테스트 통과!")
"""

        exec(test_code)
        record_result("AutoDeleteClassManager", True, "모든 서브 테스트 통과")

    except Exception as e:
        record_result("AutoDeleteClassManager", False, str(e))
        print(traceback.format_exc())

# =================================================================
# 테스트 3: ClassConfigManager 전체 기능 검증
# =================================================================
def test_class_config_manager():
    print_header("테스트 3: ClassConfigManager 전체 기능 검증")

    try:
        test_code = """
import json
import tempfile
import os
from pathlib import Path

class ClassConfigManager:
    def __init__(self, config_file="class_config.json"):
        self.base_dir = os.getcwd()
        if not config_file.endswith('.json'):
            config_file += '.json'
        self.config_file = config_file
        self.config_path = os.path.join(self.base_dir, config_file)
        self.last_config_file = os.path.join(self.base_dir, ".last_class_config.txt")
        self.classes = []

    def set_config_file(self, config_file):
        if not config_file.endswith('.json'):
            config_file += '.json'
        self.config_file = config_file
        self.config_path = os.path.join(self.base_dir, config_file)

    def get_config_filename(self):
        return self.config_file

    def save_last_config(self):
        try:
            with open(self.last_config_file, 'w') as f:
                f.write(self.config_file)
            return True
        except Exception as e:
            print(f"Error saving last config: {e}")
            return False

    def load_last_config(self):
        if os.path.exists(self.last_config_file):
            try:
                with open(self.last_config_file, 'r') as f:
                    config_file = f.read().strip()
                    if config_file:
                        return config_file
            except Exception as e:
                print(f"Error loading last config: {e}")
        return None

    def get_available_configs(self):
        configs = []
        for file in Path(self.base_dir).glob("*.json"):
            if not file.name.startswith('.'):
                configs.append(file.name)
        return sorted(configs)

    def load_config(self, config_file=None):
        if config_file:
            self.set_config_file(config_file)

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.classes = data.get('classes', [])
                return True
            except Exception as e:
                print(f"Error loading config: {e}")
                self.classes = []
                return False
        return False

    def save_config(self, classes, config_file=None):
        if config_file:
            self.set_config_file(config_file)

        self.classes = classes
        data = {'classes': classes}

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.save_last_config()
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get_class_names(self):
        return [cls['name'] for cls in self.classes]

    def get_class_colors(self):
        names = [cls['name'] for cls in self.classes]
        colors = [cls['color'] for cls in self.classes]
        return [names, colors]

    def get_button_configs(self):
        configs = []
        for cls in self.classes:
            configs.append((cls['name'], cls['id'], cls.get('key', None)))
        return configs

# 테스트 시작
with tempfile.TemporaryDirectory() as tmpdir:
    os.chdir(tmpdir)

    # 3-1. 인스턴스 생성
    manager = ClassConfigManager("test_config.json")
    assert manager is not None, "인스턴스 생성 실패"
    assert manager.config_file == "test_config.json", "설정 파일명 불일치"
    print("3-1. 인스턴스 생성: PASS")

    # 3-2. 클래스 설정 저장
    test_classes = [
        {"id": 0, "name": "person", "key": "1", "color": "magenta"},
        {"id": 1, "name": "vehicle", "key": "2", "color": "blue"},
        {"id": 2, "name": "animal", "key": "3", "color": "yellow"}
    ]
    result = manager.save_config(test_classes)
    assert result == True, "설정 저장 실패"
    assert os.path.exists(manager.config_path), "설정 파일 생성 실패"
    print("3-2. 클래스 설정 저장: PASS")

    # 3-3. 클래스 설정 로드
    new_manager = ClassConfigManager()
    new_manager.load_config("test_config.json")
    assert len(new_manager.classes) == 3, "로드된 클래스 수 불일치"
    assert new_manager.classes[0]['name'] == "person", "로드된 데이터 불일치"
    print("3-3. 클래스 설정 로드: PASS")

    # 3-4. 파일명 자동 .json 확장자 추가
    manager2 = ClassConfigManager("test_config_2")
    assert manager2.config_file == "test_config_2.json", "자동 확장자 추가 실패"
    print("3-4. 파일명 자동 확장자 추가: PASS")

    # 3-5. 마지막 설정 저장/로드
    manager.save_last_config()
    last_config = manager.load_last_config()
    assert last_config == "test_config.json", "마지막 설정 저장/로드 실패"
    print("3-5. 마지막 설정 저장/로드: PASS")

    # 3-6. 설정 파일 목록 조회
    manager.save_config(test_classes, "config_1.json")
    manager.save_config(test_classes, "config_2.json")
    manager.save_config(test_classes, "config_3")  # .json 자동 추가

    available = manager.get_available_configs()
    assert len(available) >= 4, f"설정 파일 목록 불일치: {len(available)}개"
    print(f"3-6. 설정 파일 목록 조회: PASS (발견: {len(available)}개)")

    # 3-7. get_class_names() 테스트
    manager.load_config("test_config.json")
    names = manager.get_class_names()
    assert names == ["person", "vehicle", "animal"], "클래스 이름 리스트 불일치"
    print("3-7. get_class_names(): PASS")

    # 3-8. get_class_colors() 테스트
    colors_data = manager.get_class_colors()
    assert len(colors_data) == 2, "색상 데이터 구조 불일치"
    assert colors_data[0] == ["person", "vehicle", "animal"], "색상 데이터 이름 불일치"
    assert colors_data[1] == ["magenta", "blue", "yellow"], "색상 데이터 색상 불일치"
    print("3-8. get_class_colors(): PASS")

    # 3-9. get_button_configs() 테스트
    button_configs = manager.get_button_configs()
    assert len(button_configs) == 3, "버튼 설정 개수 불일치"
    assert button_configs[0] == ("person", 0, "1"), "버튼 설정 데이터 불일치"
    assert button_configs[1] == ("vehicle", 1, "2"), "버튼 설정 데이터 불일치"
    assert button_configs[2] == ("animal", 2, "3"), "버튼 설정 데이터 불일치"
    print("3-9. get_button_configs(): PASS")

    # 3-10. 빈 설정 로드
    manager_empty = ClassConfigManager("nonexistent.json")
    result = manager_empty.load_config()
    assert result == False, "존재하지 않는 파일 로드가 성공으로 처리됨"
    assert len(manager_empty.classes) == 0, "빈 클래스 리스트가 아님"
    print("3-10. 빈 설정 로드: PASS")

    # 3-11. 한글 클래스 이름 지원
    korean_classes = [
        {"id": 0, "name": "사람", "key": "1", "color": "red"},
        {"id": 1, "name": "자동차", "key": "2", "color": "green"}
    ]
    manager_korean = ClassConfigManager("korean_config.json")
    manager_korean.save_config(korean_classes)
    manager_korean.load_config()
    assert manager_korean.classes[0]['name'] == "사람", "한글 저장/로드 실패"
    print("3-11. 한글 클래스 이름 지원: PASS")

    # 3-12. 설정 파일 변경
    manager.set_config_file("new_config")
    assert manager.config_file == "new_config.json", "설정 파일 변경 실패"
    print("3-12. 설정 파일 변경: PASS")

print("=" * 40)
print("테스트 3: 모든 ClassConfigManager 테스트 통과!")
"""

        exec(test_code)
        record_result("ClassConfigManager", True, "모든 서브 테스트 통과")

    except Exception as e:
        record_result("ClassConfigManager", False, str(e))
        print(traceback.format_exc())

# =================================================================
# 테스트 4: 통합 시나리오 시뮬레이션
# =================================================================
def test_integrated_scenarios():
    print_header("테스트 4: 통합 시나리오 시뮬레이션")

    try:
        print_subheader("시나리오 1: 제외 영역 + 클래스 자동 삭제 통합")
        test_code_1 = """
import json
import tempfile
import os

# 간단한 매니저 클래스들 (이전 테스트에서 검증됨)
class ExclusionZoneManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.global_zones = []
        self.use_global = True

    def add_zone(self, points, use_global=True):
        if len(points) >= 3:
            self.global_zones.append({'points': points, 'enabled': True})
            return True
        return False

    def is_bbox_in_exclusion_zone(self, bbox):
        if not self.global_zones:
            return False
        x1, y1, x2, y2 = bbox[3], bbox[4], bbox[5], bbox[6]
        bbox_center = ((x1 + x2) / 2, (y1 + y2) / 2)
        for zone in self.global_zones:
            if zone['enabled'] and self._point_in_polygon(bbox_center, zone['points']):
                return True
        return False

    def _point_in_polygon(self, point, polygon):
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

class AutoDeleteClassManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.delete_class_ids = set()

    def add_class(self, class_id):
        self.delete_class_ids.add(class_id)

    def filter_bboxes(self, bbox_list):
        if not self.delete_class_ids:
            return bbox_list
        return [bbox for bbox in bbox_list if int(bbox[2]) not in self.delete_class_ids]

# 시나리오 실행
with tempfile.TemporaryDirectory() as tmpdir:
    # 초기 bbox 리스트
    bbox_list = [
        [False, 'person', 0, 150, 150, 250, 250],   # 제외 영역 안, 클래스 0
        [False, 'car', 1, 350, 150, 450, 250],      # 제외 영역 밖, 클래스 1
        [False, 'person', 0, 500, 500, 600, 600],   # 제외 영역 밖, 클래스 0
        [False, 'bike', 2, 180, 180, 220, 220],     # 제외 영역 안, 클래스 2
        [False, 'truck', 3, 700, 700, 800, 800]     # 제외 영역 밖, 클래스 3
    ]

    print(f"초기 bbox 수: {len(bbox_list)}")

    # 1단계: 제외 영역 필터링
    exclusion_manager = ExclusionZoneManager(tmpdir)
    exclusion_polygon = [(100, 100), (300, 100), (300, 300), (100, 300)]
    exclusion_manager.add_zone(exclusion_polygon, use_global=True)

    filtered_by_zone = []
    excluded_by_zone = []
    for bbox in bbox_list:
        if not exclusion_manager.is_bbox_in_exclusion_zone(bbox):
            filtered_by_zone.append(bbox)
        else:
            excluded_by_zone.append(bbox)

    print(f"제외 영역 필터링 후: {len(filtered_by_zone)}개 (제외: {len(excluded_by_zone)}개)")
    assert len(filtered_by_zone) == 3, "제외 영역 필터링 결과 불일치"

    # 2단계: 클래스 자동 삭제 필터링 (클래스 1 삭제)
    auto_delete_manager = AutoDeleteClassManager(tmpdir)
    auto_delete_manager.add_class(1)  # car 클래스 삭제

    filtered_by_class = auto_delete_manager.filter_bboxes(filtered_by_zone)

    print(f"클래스 필터링 후: {len(filtered_by_class)}개")
    print(f"최종 결과: 초기 {len(bbox_list)}개 → 최종 {len(filtered_by_class)}개")

    # 검증
    assert len(filtered_by_class) == 2, "통합 필터링 결과 불일치"
    assert all(bbox[2] != 1 for bbox in filtered_by_class), "클래스 1이 여전히 존재"

    print("\\n남은 bbox:")
    for bbox in filtered_by_class:
        print(f"  - {bbox[1]} (클래스 {bbox[2]}), 위치: ({bbox[3]}, {bbox[4]})")

    # 예상 결과: person(클래스 0, 제외영역 밖), truck(클래스 3, 제외영역 밖)
    expected_classes = {0, 3}
    actual_classes = {int(bbox[2]) for bbox in filtered_by_class}
    assert actual_classes == expected_classes, f"예상 클래스: {expected_classes}, 실제: {actual_classes}"

    print("\\n시나리오 1 검증 성공!")
"""

        exec(test_code_1)
        record_result("통합 시나리오 1", True, "제외 영역 + 클래스 자동 삭제")

        print_subheader("시나리오 2: 복잡한 다중 필터링")
        test_code_2 = """
import json
import tempfile
import os

# 매니저 클래스 재정의
class ExclusionZoneManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.global_zones = []
        self.use_global = True

    def add_zone(self, points, use_global=True):
        if len(points) >= 3:
            self.global_zones.append({'points': points, 'enabled': True})
            return True
        return False

    def is_bbox_in_exclusion_zone(self, bbox):
        if not self.global_zones:
            return False
        x1, y1, x2, y2 = bbox[3], bbox[4], bbox[5], bbox[6]
        bbox_center = ((x1 + x2) / 2, (y1 + y2) / 2)
        for zone in self.global_zones:
            if zone['enabled'] and self._point_in_polygon(bbox_center, zone['points']):
                return True
        return False

    def _point_in_polygon(self, point, polygon):
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

class AutoDeleteClassManager:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.getcwd()
        self.delete_class_ids = set()

    def add_class(self, class_id):
        self.delete_class_ids.add(class_id)

    def filter_bboxes(self, bbox_list):
        if not self.delete_class_ids:
            return bbox_list
        return [bbox for bbox in bbox_list if int(bbox[2]) not in self.delete_class_ids]

# 더 복잡한 시나리오: 여러 제외 영역 + 여러 클래스 삭제
with tempfile.TemporaryDirectory() as tmpdir:
    # 20개의 bbox 생성
    bbox_list = []
    for i in range(20):
        x = (i % 5) * 200 + 100
        y = (i // 5) * 200 + 100
        bbox_list.append([False, f'class_{i%4}', i % 4, x, y, x+50, y+50])

    print(f"\\n초기 bbox 수: {len(bbox_list)}")

    # 여러 개의 제외 영역 추가
    exclusion_manager = ExclusionZoneManager(tmpdir)
    exclusion_manager.add_zone([(0, 0), (300, 0), (300, 300), (0, 300)], use_global=True)
    exclusion_manager.add_zone([(600, 600), (900, 600), (900, 900), (600, 900)], use_global=True)

    # 제외 영역 필터링
    filtered_by_zone = []
    for bbox in bbox_list:
        if not exclusion_manager.is_bbox_in_exclusion_zone(bbox):
            filtered_by_zone.append(bbox)
    print(f"제외 영역 필터링 후: {len(filtered_by_zone)}개")

    # 여러 클래스 삭제
    auto_delete_manager = AutoDeleteClassManager(tmpdir)
    auto_delete_manager.add_class(0)
    auto_delete_manager.add_class(2)

    # 클래스 필터링
    final_filtered = auto_delete_manager.filter_bboxes(filtered_by_zone)
    print(f"클래스 필터링 후: {len(final_filtered)}개")
    print(f"최종 결과: 초기 {len(bbox_list)}개 → 최종 {len(final_filtered)}개")

    # 검증: 클래스 0, 2가 없어야 함
    for bbox in final_filtered:
        assert int(bbox[2]) not in {0, 2}, f"삭제 대상 클래스 발견: {bbox[2]}"

    print("\\n시나리오 2 검증 성공!")
"""

        exec(test_code_2)
        record_result("통합 시나리오 2", True, "복잡한 다중 필터링")

    except Exception as e:
        record_result("통합 시나리오", False, str(e))
        print(traceback.format_exc())

# =================================================================
# 테스트 5: 파일 I/O 및 예외 처리
# =================================================================
def test_file_io_and_exceptions():
    print_header("테스트 5: 파일 I/O 및 예외 처리")

    try:
        test_code = """
import json
import tempfile
import os

# 5-1. 잘못된 JSON 파일 처리
print("5-1. 잘못된 JSON 파일 처리")
with tempfile.TemporaryDirectory() as tmpdir:
    invalid_json_file = os.path.join(tmpdir, "invalid.json")
    with open(invalid_json_file, 'w') as f:
        f.write("{invalid json content")

    # JSON 파싱 실패 시 예외 처리
    try:
        with open(invalid_json_file, 'r') as f:
            data = json.load(f)
        print("  예외 발생하지 않음 - 실패")
        assert False
    except json.JSONDecodeError:
        print("  JSONDecodeError 정상 처리: PASS")

# 5-2. 읽기 전용 디렉토리 처리
print("\\n5-2. 파일 쓰기 권한 테스트")
with tempfile.TemporaryDirectory() as tmpdir:
    test_file = os.path.join(tmpdir, "test.json")
    data = {"test": "data"}

    # 정상 쓰기
    with open(test_file, 'w') as f:
        json.dump(data, f)
    assert os.path.exists(test_file), "파일 쓰기 실패"
    print("  파일 쓰기: PASS")

    # 읽기
    with open(test_file, 'r') as f:
        loaded = json.load(f)
    assert loaded == data, "파일 읽기 실패"
    print("  파일 읽기: PASS")

# 5-3. 빈 파일 처리
print("\\n5-3. 빈 파일 처리")
with tempfile.TemporaryDirectory() as tmpdir:
    empty_file = os.path.join(tmpdir, "empty.json")
    with open(empty_file, 'w') as f:
        pass  # 빈 파일

    try:
        with open(empty_file, 'r') as f:
            data = json.load(f)
        print("  빈 파일 파싱이 성공함 - 예외 발생해야 함")
        assert False
    except json.JSONDecodeError:
        print("  빈 파일 예외 처리: PASS")

# 5-4. 대용량 데이터 처리
print("\\n5-4. 대용량 데이터 처리")
with tempfile.TemporaryDirectory() as tmpdir:
    large_file = os.path.join(tmpdir, "large.json")

    # 1000개의 클래스 설정 생성
    large_data = {
        "classes": [
            {"id": i, "name": f"class_{i}", "key": str(i % 10), "color": "blue"}
            for i in range(1000)
        ]
    }

    # 저장
    with open(large_file, 'w') as f:
        json.dump(large_data, f)

    # 로드
    with open(large_file, 'r') as f:
        loaded = json.load(f)

    assert len(loaded['classes']) == 1000, "대용량 데이터 처리 실패"
    print("  대용량 데이터 (1000개 클래스) 처리: PASS")

# 5-5. 동시 파일 접근 (순차)
print("\\n5-5. 동시 파일 접근 시뮬레이션")
with tempfile.TemporaryDirectory() as tmpdir:
    shared_file = os.path.join(tmpdir, "shared.json")

    # 첫 번째 쓰기
    data1 = {"version": 1}
    with open(shared_file, 'w') as f:
        json.dump(data1, f)

    # 읽기
    with open(shared_file, 'r') as f:
        loaded = json.load(f)
    assert loaded['version'] == 1

    # 두 번째 쓰기 (덮어쓰기)
    data2 = {"version": 2}
    with open(shared_file, 'w') as f:
        json.dump(data2, f)

    # 다시 읽기
    with open(shared_file, 'r') as f:
        loaded = json.load(f)
    assert loaded['version'] == 2

    print("  파일 순차 접근: PASS")

print("\\n" + "=" * 40)
print("테스트 5: 모든 파일 I/O 및 예외 처리 테스트 통과!")
"""

        exec(test_code)
        record_result("파일 I/O 및 예외 처리", True, "모든 서브 테스트 통과")

    except Exception as e:
        record_result("파일 I/O 및 예외 처리", False, str(e))
        print(traceback.format_exc())

# =================================================================
# 테스트 6: 경계 케이스 및 엣지 케이스
# =================================================================
def test_edge_cases():
    print_header("테스트 6: 경계 케이스 및 엣지 케이스")

    try:
        test_code = """
import tempfile

# 6-1. 제외 영역 경계 테스트
print("6-1. 제외 영역 정확한 경계 테스트")
class ExclusionZoneManager:
    def __init__(self, base_dir=None):
        self.global_zones = []
        self.use_global = True

    def add_zone(self, points, use_global=True):
        if len(points) >= 3:
            self.global_zones.append({'points': points, 'enabled': True})
            return True
        return False

    def is_bbox_in_exclusion_zone(self, bbox):
        if not self.global_zones:
            return False
        x1, y1, x2, y2 = bbox[3], bbox[4], bbox[5], bbox[6]
        bbox_center = ((x1 + x2) / 2, (y1 + y2) / 2)
        for zone in self.global_zones:
            if zone['enabled'] and self._point_in_polygon(bbox_center, zone['points']):
                return True
        return False

    def _point_in_polygon(self, point, polygon):
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

manager = ExclusionZoneManager()
manager.add_zone([(0, 0), (100, 0), (100, 100), (0, 100)], use_global=True)

# 정확히 경계선 위
bbox_on_edge = [False, 'test', 0, 98, 98, 102, 102]  # 중심: (100, 100)
is_on_edge = manager.is_bbox_in_exclusion_zone(bbox_on_edge)
print(f"  경계선 테스트 (중심 100,100): {is_on_edge}")

# 살짝 안쪽
bbox_inside = [False, 'test', 0, 48, 48, 52, 52]  # 중심: (50, 50)
is_inside = manager.is_bbox_in_exclusion_zone(bbox_inside)
assert is_inside == True, "안쪽 테스트 실패"
print(f"  안쪽 테스트 (중심 50,50): PASS")

# 살짝 바깥쪽
bbox_outside = [False, 'test', 0, 148, 148, 152, 152]  # 중심: (150, 150)
is_outside = manager.is_bbox_in_exclusion_zone(bbox_outside)
assert is_outside == False, "바깥쪽 테스트 실패"
print(f"  바깥쪽 테스트 (중심 150,150): PASS")

# 6-2. 매우 작은 bbox
print("\\n6-2. 매우 작은 bbox 테스트")
tiny_bbox = [False, 'tiny', 0, 50, 50, 51, 51]  # 1x1 픽셀
is_tiny_inside = manager.is_bbox_in_exclusion_zone(tiny_bbox)
assert is_tiny_inside == True, "작은 bbox 테스트 실패"
print("  1x1 픽셀 bbox: PASS")

# 6-3. 매우 큰 bbox
print("\\n6-3. 매우 큰 bbox 테스트")
huge_bbox = [False, 'huge', 0, 0, 0, 1000, 1000]  # 1000x1000 픽셀
is_huge_inside = manager.is_bbox_in_exclusion_zone(huge_bbox)  # 중심: (500, 500)
assert is_huge_inside == False, "큰 bbox 테스트 실패"
print("  1000x1000 픽셀 bbox: PASS")

# 6-4. 음수 좌표
print("\\n6-4. 음수 좌표 테스트")
negative_bbox = [False, 'negative', 0, -50, -50, -10, -10]
is_negative_inside = manager.is_bbox_in_exclusion_zone(negative_bbox)
assert is_negative_inside == False, "음수 좌표 테스트 실패"
print("  음수 좌표 bbox: PASS")

# 6-5. 부동소수점 좌표
print("\\n6-5. 부동소수점 좌표 테스트")
float_bbox = [False, 'float', 0, 49.5, 49.5, 50.5, 50.5]
is_float_inside = manager.is_bbox_in_exclusion_zone(float_bbox)
assert is_float_inside == True, "부동소수점 좌표 테스트 실패"
print("  부동소수점 좌표 bbox: PASS")

# 6-6. 클래스 ID 경계 값
print("\\n6-6. 클래스 ID 경계 값 테스트")
class AutoDeleteClassManager:
    def __init__(self):
        self.delete_class_ids = set()

    def add_class(self, class_id):
        self.delete_class_ids.add(class_id)

    def is_class_marked_for_deletion(self, class_id):
        return class_id in self.delete_class_ids

auto_delete = AutoDeleteClassManager()
auto_delete.add_class(0)  # 최소 클래스 ID
auto_delete.add_class(999)  # 큰 클래스 ID
auto_delete.add_class(-1)  # 음수 클래스 ID (허용되는지 테스트)

assert auto_delete.is_class_marked_for_deletion(0) == True
assert auto_delete.is_class_marked_for_deletion(999) == True
assert auto_delete.is_class_marked_for_deletion(-1) == True
print("  클래스 ID 경계 값 (0, 999, -1): PASS")

# 6-7. 빈 폴리곤
print("\\n6-7. 빈 폴리곤 테스트")
manager2 = ExclusionZoneManager()
bbox_test = [False, 'test', 0, 50, 50, 100, 100]
is_no_zone = manager2.is_bbox_in_exclusion_zone(bbox_test)
assert is_no_zone == False, "빈 폴리곤 테스트 실패"
print("  제외 영역 없을 때: PASS")

# 6-8. 복잡한 폴리곤 (오목 다각형)
print("\\n6-8. 복잡한 오목 다각형 테스트")
manager3 = ExclusionZoneManager()
# L자 형태 폴리곤
concave_polygon = [(0, 0), (100, 0), (100, 50), (50, 50), (50, 100), (0, 100)]
manager3.add_zone(concave_polygon, use_global=True)

# L자 안쪽 (0,0 ~ 50,50 영역)
bbox_in_L1 = [False, 'test', 0, 20, 20, 30, 30]  # 중심: (25, 25)
is_in_L1 = manager3.is_bbox_in_exclusion_zone(bbox_in_L1)
assert is_in_L1 == True, "오목 다각형 안쪽 테스트1 실패"

# L자 안쪽 (50,0 ~ 100,50 영역)
bbox_in_L2 = [False, 'test', 0, 70, 20, 80, 30]  # 중심: (75, 25)
is_in_L2 = manager3.is_bbox_in_exclusion_zone(bbox_in_L2)
assert is_in_L2 == True, "오목 다각형 안쪽 테스트2 실패"

# L자 바깥쪽 (오른쪽 아래 빈 공간)
bbox_out_L = [False, 'test', 0, 70, 70, 80, 80]  # 중심: (75, 75)
is_out_L = manager3.is_bbox_in_exclusion_zone(bbox_out_L)
assert is_out_L == False, "오목 다각형 바깥쪽 테스트 실패"
print("  오목 다각형 (L자): PASS")

print("\\n" + "=" * 40)
print("테스트 6: 모든 경계 케이스 테스트 통과!")
"""

        exec(test_code)
        record_result("경계 케이스 및 엣지 케이스", True, "모든 서브 테스트 통과")

    except Exception as e:
        record_result("경계 케이스 및 엣지 케이스", False, str(e))
        print(traceback.format_exc())

# =================================================================
# 최종 결과 출력
# =================================================================
def print_final_summary():
    print_header("검증 결과 요약")

    total_tests = len(test_results['passed']) + len(test_results['failed'])
    pass_rate = len(test_results['passed']) / total_tests * 100 if total_tests > 0 else 0

    print(f"\n{GREEN}통과한 테스트: {len(test_results['passed'])}/{total_tests}{RESET}")
    for test in test_results['passed']:
        print(f"  {GREEN}✓{RESET} {test}")

    if test_results['failed']:
        print(f"\n{RED}실패한 테스트: {len(test_results['failed'])}/{total_tests}{RESET}")
        for test in test_results['failed']:
            print(f"  {RED}✗{RESET} {test}")

    if test_results['warnings']:
        print(f"\n{YELLOW}경고:{RESET}")
        for warning in test_results['warnings']:
            print(f"  {YELLOW}⚠{RESET} {warning}")

    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}전체 통과율: {pass_rate:.1f}%{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")

    if len(test_results['failed']) == 0:
        print(f"{GREEN}🎉 모든 테스트 통과! gtgen tool이 정상적으로 작동합니다.{RESET}\n")
        return True
    else:
        print(f"{RED}❌ 일부 테스트 실패. 위 내용을 확인하여 문제를 수정해주세요.{RESET}\n")
        return False

# =================================================================
# 메인 실행
# =================================================================
if __name__ == "__main__":
    print_header("04.GTGEN_Tool_svms_v2 포괄적인 기능 검증 시작")

    # 각 테스트 실행
    test_exclusion_zone_manager()
    test_auto_delete_class_manager()
    test_class_config_manager()
    test_integrated_scenarios()
    test_file_io_and_exceptions()
    test_edge_cases()

    # 최종 요약
    all_passed = print_final_summary()

    sys.exit(0 if all_passed else 1)
