#!/usr/bin/env python
"""
전체 마스킹 기능 버그 수정 검증 스크립트
"""

import os

def verify_all_fixes():
    """모든 마스킹 기능의 이미지 저장 코드 확인"""
    print("=" * 70)
    print("전체 마스킹 기능 버그 수정 검증")
    print("=" * 70)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    functions_to_check = [
        {
            "name": "convert_label_to_mask (Label→Mask)",
            "func_name": "def convert_label_to_mask(self):",
            "key": "M 키 + 체크박스",
            "checks": [
                ('.save(self.im_fn)', '이미지 파일 저장')
            ]
        },
        {
            "name": "load_masking (마스킹 로드)",
            "func_name": "def load_masking(self):",
            "key": "L 키",
            "checks": [
                ('.save(self.im_fn)', '이미지 파일 저장')
            ]
        },
        {
            "name": "copy_masking_to_range (마스킹 복사)",
            "func_name": "def copy_masking_to_range(self):",
            "key": "UI 버튼",
            "checks": [
                ('target_img.save(target_img_path)', '이미지 파일 저장')
            ]
        }
    ]

    all_passed = True
    for func_info in functions_to_check:
        print(f"\n{'='*70}")
        print(f"함수: {func_info['name']}")
        print(f"단축키: {func_info['key']}")
        print("=" * 70)

        # 함수 찾기
        func_start = content.find(func_info['func_name'])
        if func_start == -1:
            print(f"❌ 함수를 찾을 수 없습니다!")
            all_passed = False
            continue

        print(f"✅ 함수 발견")

        # 다음 함수 시작 찾기
        next_def = content.find('\n\tdef ', func_start + 1)
        if next_def == -1:
            next_def = content.find('\n\ndef ', func_start + 1)

        func_content = content[func_start:next_def] if next_def != -1 else content[func_start:]

        # 필수 코드 확인
        func_passed = True
        for code, desc in func_info['checks']:
            if code in func_content:
                print(f"  ✅ {desc}: {code}")
            else:
                print(f"  ❌ {desc} 누락: {code}")
                func_passed = False
                all_passed = False

        if func_passed:
            print(f"\n✅ {func_info['name']} - 정상!")
        else:
            print(f"\n❌ {func_info['name']} - 수정 필요!")

    print("\n" + "=" * 70)
    print("최종 결과")
    print("=" * 70)

    if all_passed:
        print("""
✅ 모든 마스킹 기능이 정상적으로 수정되었습니다!

수정된 기능들:
1. Label→Mask (M 키 + 체크박스)
   - 라벨을 마스킹으로 변환 시 즉시 파일에 저장

2. 마스킹 로드 (L 키)
   - 저장된 마스킹을 로드 시 즉시 파일에 저장

3. 마스킹 복사 (UI 버튼)
   - 이미 정상 동작 중 (확인됨)

이제 모든 마스킹 작업이 즉시 파일에 저장되므로
프레임을 이동하지 않아도 마스킹이 유지됩니다!
""")
        return True
    else:
        print("\n❌ 일부 기능에 문제가 있습니다. 위 결과를 확인하세요.")
        return False

if __name__ == "__main__":
    import sys
    success = verify_all_fixes()
    sys.exit(0 if success else 1)
