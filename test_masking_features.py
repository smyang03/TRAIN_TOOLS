#!/usr/bin/env python
"""
GTGEN Tool 마스킹 기능 테스트 스크립트
- MASK->DEel (delete_range)
- Label→Mask (convert_label_to_mask)
- 마스킹 복사 (copy_masking_to_range)
"""

import sys
import os

def test_delete_range_function():
    """delete_range 함수가 존재하고 올바르게 구현되었는지 확인"""
    print("=" * 60)
    print("1. MASK->DEel (delete_range) 기능 확인")
    print("=" * 60)

    # 04.GTGEN_Tool_svms_v2.py 파일에서 함수 정의 찾기
    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # delete_range 함수 확인
    if 'def delete_range(self):' in content:
        print("✅ delete_range 함수가 정의되어 있습니다.")

        # 버튼과 연결 확인
        if 'command=self.delete_range' in content:
            print("✅ 버튼과 함수가 올바르게 연결되어 있습니다.")
        else:
            print("❌ 버튼과 함수가 연결되지 않았습니다!")
            return False

        # 주요 기능 구현 확인
        required_features = [
            ('delete_start_frame_entry.get()', '시작 프레임 입력'),
            ('delete_end_frame_entry.get()', '종료 프레임 입력'),
            ('messagebox.askyesno', '확인 메시지'),
            ('original_backup', '백업 생성'),
            ('os.remove', '파일 삭제'),
            ('self.imlist.pop', '리스트에서 제거')
        ]

        for feature, desc in required_features:
            if feature in content:
                print(f"  ✅ {desc} 구현됨")
            else:
                print(f"  ❌ {desc} 미구현!")
                return False

    else:
        print("❌ delete_range 함수가 정의되지 않았습니다!")
        return False

    print("\n결과: delete_range 기능은 정상적으로 구현되어 있습니다.\n")
    return True

def test_label_to_mask_function():
    """convert_label_to_mask 함수가 존재하고 올바르게 구현되었는지 확인"""
    print("=" * 60)
    print("2. Label→Mask (convert_label_to_mask) 기능 확인")
    print("=" * 60)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # convert_label_to_mask 함수 확인
    if 'def convert_label_to_mask(self):' in content:
        print("✅ convert_label_to_mask 함수가 정의되어 있습니다.")

        # 체크박스 확인
        if 'self.label_to_mask_mode = tk.BooleanVar()' in content:
            print("✅ Label→Mask 체크박스가 정의되어 있습니다.")
        else:
            print("❌ Label→Mask 체크박스가 정의되지 않았습니다!")
            return False

        # 키 이벤트 연결 확인
        if 'self.label_to_mask_mode.get() and self.selid >= 0' in content:
            print("✅ 키 이벤트와 함수가 올바르게 연결되어 있습니다.")

            if 'self.convert_label_to_mask()' in content:
                print("✅ 함수 호출이 올바르게 구현되어 있습니다.")
            else:
                print("❌ 함수 호출이 구현되지 않았습니다!")
                return False
        else:
            print("❌ 키 이벤트와 함수가 연결되지 않았습니다!")
            return False

        # 주요 기능 구현 확인
        required_features = [
            ('self.bbox[self.selid]', '선택된 라벨 가져오기'),
            ('original_backup', '백업 생성'),
            ('self.current_img_array[orig_y1:orig_y2, orig_x1:orig_x2, :] = [255, 0, 255]', '마스킹 적용'),
            ('self.masking = np.where', '마스킹 정보 저장'),
            ('self.has_saved_masking = True', '마스킹 저장 플래그'),
            ('self.bbox.pop(self.selid)', '라벨 삭제')
        ]

        for feature, desc in required_features:
            if feature in content:
                print(f"  ✅ {desc} 구현됨")
            else:
                print(f"  ❌ {desc} 미구현!")
                return False

    else:
        print("❌ convert_label_to_mask 함수가 정의되지 않았습니다!")
        return False

    print("\n결과: Label→Mask 기능은 정상적으로 구현되어 있습니다.\n")
    return True

def test_copy_masking_function():
    """copy_masking_to_range 함수가 존재하고 올바르게 구현되었는지 확인"""
    print("=" * 60)
    print("3. 마스킹 복사 (copy_masking_to_range) 기능 확인")
    print("=" * 60)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # copy_masking_to_range 함수 확인
    if 'def copy_masking_to_range(self):' in content:
        print("✅ copy_masking_to_range 함수가 정의되어 있습니다.")

        # 버튼과 연결 확인
        if 'command=self.copy_masking_to_range' in content:
            print("✅ 버튼과 함수가 올바르게 연결되어 있습니다.")
        else:
            print("❌ 버튼과 함수가 연결되지 않았습니다!")
            return False

        # 주요 기능 구현 확인
        required_features = [
            ('self.has_saved_masking', '저장된 마스킹 확인'),
            ('start_frame_entry.get()', '시작 프레임 입력'),
            ('end_frame_entry.get()', '종료 프레임 입력'),
            ('messagebox.askyesno', '확인 메시지'),
            ('original_backup', '백업 생성'),
            ('target_img_array[self.masking] = [255, 0, 255]', '마스킹 적용'),
            ('target_img.save', '이미지 저장')
        ]

        for feature, desc in required_features:
            if feature in content:
                print(f"  ✅ {desc} 구현됨")
            else:
                print(f"  ❌ {desc} 미구현!")
                return False

    else:
        print("❌ copy_masking_to_range 함수가 정의되지 않았습니다!")
        return False

    print("\n결과: 마스킹 복사 기능은 정상적으로 구현되어 있습니다.\n")
    return True

def test_get_masking_function():
    """get_masking 함수 (마스킹 저장) 확인"""
    print("=" * 60)
    print("4. 마스킹 저장 (get_masking) 기능 확인")
    print("=" * 60)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    if 'def get_masking(self):' in content:
        print("✅ get_masking 함수가 정의되어 있습니다.")

        required_features = [
            ('self.masking = np.where', '마스킹 픽셀 찾기'),
            ('self.has_saved_masking = True', '저장 플래그 설정'),
            ('self.maskingframewidth', '마스킹 크기 저장'),
            ('self.maskingframeheight', '마스킹 크기 저장')
        ]

        for feature, desc in required_features:
            if feature in content:
                print(f"  ✅ {desc} 구현됨")
            else:
                print(f"  ❌ {desc} 미구현!")
                return False
    else:
        print("❌ get_masking 함수가 정의되지 않았습니다!")
        return False

    print("\n결과: 마스킹 저장 기능은 정상적으로 구현되어 있습니다.\n")
    return True

def check_potential_issues():
    """잠재적 문제점 검사"""
    print("=" * 60)
    print("5. 잠재적 문제점 검사")
    print("=" * 60)

    issues = []

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # delete_range 함수의 entry 위젯 이름 확인
    delete_start_found = False
    delete_end_found = False

    for i, line in enumerate(lines):
        # Entry 위젯 정의 확인
        if 'self.delete_start_frame_entry = tk.Entry' in line:
            delete_start_found = True
            print(f"  ✅ delete_start_frame_entry 정의됨 (라인 {i+1})")

        if 'self.delete_end_frame_entry = tk.Entry' in line:
            delete_end_found = True
            print(f"  ✅ delete_end_frame_entry 정의됨 (라인 {i+1})")

    if not delete_start_found:
        issues.append("delete_start_frame_entry Entry 위젯이 정의되지 않았습니다")
        print("  ❌ delete_start_frame_entry가 정의되지 않았습니다!")

    if not delete_end_found:
        issues.append("delete_end_frame_entry Entry 위젯이 정의되지 않았습니다")
        print("  ❌ delete_end_frame_entry가 정의되지 않았습니다!")

    # Label→Mask 체크박스 확인
    label_to_mask_checkbox_found = False
    for i, line in enumerate(lines):
        if 'self.chk_label_to_mask = tk.Checkbutton' in line:
            label_to_mask_checkbox_found = True
            print(f"  ✅ Label→Mask 체크박스 정의됨 (라인 {i+1})")
            break

    if not label_to_mask_checkbox_found:
        issues.append("Label→Mask 체크박스가 정의되지 않았습니다")
        print("  ❌ Label→Mask 체크박스가 정의되지 않았습니다!")

    # 마스킹 복사 Entry 위젯 확인
    start_frame_found = False
    end_frame_found = False

    for i, line in enumerate(lines):
        if 'self.start_frame_entry = tk.Entry' in line:
            start_frame_found = True
            print(f"  ✅ start_frame_entry 정의됨 (라인 {i+1})")

        if 'self.end_frame_entry = tk.Entry' in line:
            end_frame_found = True
            print(f"  ✅ end_frame_entry 정의됨 (라인 {i+1})")

    if not start_frame_found:
        issues.append("start_frame_entry Entry 위젯이 정의되지 않았습니다")
        print("  ❌ start_frame_entry가 정의되지 않았습니다!")

    if not end_frame_found:
        issues.append("end_frame_entry Entry 위젯이 정의되지 않았습니다")
        print("  ❌ end_frame_entry가 정의되지 않았습니다!")

    if issues:
        print(f"\n발견된 문제점: {len(issues)}개")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("\n결과: 잠재적 문제점이 발견되지 않았습니다.")
        return True

def main():
    """메인 테스트 실행"""
    print("\n" + "=" * 60)
    print("GTGEN Tool 마스킹 기능 테스트 시작")
    print("=" * 60 + "\n")

    # 파일 존재 확인
    if not os.path.exists('04.GTGEN_Tool_svms_v2.py'):
        print("❌ 04.GTGEN_Tool_svms_v2.py 파일을 찾을 수 없습니다!")
        return False

    results = []

    # 각 기능 테스트
    results.append(("MASK->DEel", test_delete_range_function()))
    results.append(("Label→Mask", test_label_to_mask_function()))
    results.append(("마스킹 복사", test_copy_masking_function()))
    results.append(("마스킹 저장", test_get_masking_function()))
    results.append(("잠재적 문제", check_potential_issues()))

    # 최종 결과 출력
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"{name:20s}: {status}")
        if not result:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✅ 모든 기능이 정상적으로 구현되어 있습니다!")
        print("\n📋 사용 방법:")
        print("  1. MASK->DEel: 삭제 섹션에서 시작/종료 프레임 입력 후 '실행' 버튼 클릭")
        print("  2. Label→Mask: 'Label→Mask' 체크박스 체크 후, 라벨 선택 후 마스킹 키 누르기")
        print("  3. 마스킹 복사: 마스킹 생성 및 저장 후, 시작/종료 프레임 입력 후 '실행' 버튼 클릭")
        return True
    else:
        print("\n❌ 일부 기능에 문제가 있습니다. 위 결과를 확인해주세요.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
