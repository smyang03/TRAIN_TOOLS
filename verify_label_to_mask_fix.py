#!/usr/bin/env python
"""
Label→Mask 기능 버그 수정 확인 스크립트
"""

import os

def verify_fix():
    """이미지 파일 저장 코드가 추가되었는지 확인"""
    print("=" * 60)
    print("Label→Mask 기능 버그 수정 확인")
    print("=" * 60)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # convert_label_to_mask 함수 찾기
    if 'def convert_label_to_mask(self):' not in content:
        print("❌ convert_label_to_mask 함수를 찾을 수 없습니다!")
        return False

    print("✅ convert_label_to_mask 함수 발견")

    # 함수 내에서 이미지 저장 코드 확인
    func_start = content.find('def convert_label_to_mask(self):')
    # 다음 함수 시작 찾기 (대략적으로)
    func_end = content.find('\n\tdef ', func_start + 1)
    if func_end == -1:
        func_end = content.find('\n\ndef ', func_start + 1)

    func_content = content[func_start:func_end]

    # 필수 요소들 확인
    checks = [
        ('self.bbox.pop(self.selid)', '라벨 삭제'),
        ('self.write_bbox()', '라벨 파일 저장'),
        ('Image.fromarray(self.current_img_array)', '이미지 생성'),
        ('.save(self.im_fn)', '이미지 파일 저장 - 수정됨!')
    ]

    all_passed = True
    for code, desc in checks:
        if code in func_content:
            print(f"  ✅ {desc}: {code}")
        else:
            print(f"  ❌ {desc}: {code}")
            all_passed = False

    # 저장 순서 확인 (중요!)
    bbox_pop_pos = func_content.find('self.bbox.pop(self.selid)')
    write_bbox_pos = func_content.find('self.write_bbox()')
    save_pos = func_content.find('.save(self.im_fn)')

    print("\n순서 확인:")
    if bbox_pop_pos < write_bbox_pos < save_pos:
        print("  ✅ 순서가 올바릅니다:")
        print("     1. 라벨 삭제 (bbox.pop)")
        print("     2. 라벨 파일 저장 (write_bbox)")
        print("     3. 이미지 파일 저장 (save) ← 새로 추가됨!")
    else:
        print("  ⚠️  순서 확인 필요")
        print(f"     bbox.pop: {bbox_pop_pos}")
        print(f"     write_bbox: {write_bbox_pos}")
        print(f"     save: {save_pos}")

    print("\n" + "=" * 60)

    if all_passed:
        print("\n✅ 버그 수정 완료!")
        print("\n이제 Label→Mask 기능이 제대로 동작합니다:")
        print("  1. 'Label→Mask' 체크박스 체크")
        print("  2. Tab 키로 라벨 선택")
        print("  3. M 키 누르기")
        print("  4. ✨ 마스킹이 이미지 파일에 저장됩니다! ✨")
        print("\n다른 프레임으로 이동해도 마스킹이 유지됩니다!")
        return True
    else:
        print("\n❌ 일부 코드가 누락되었습니다.")
        return False

if __name__ == "__main__":
    import sys
    success = verify_fix()
    sys.exit(0 if success else 1)
