#!/usr/bin/env python
"""
다중 선택 모드 버튼 위치 수정 검증
"""

import os

def verify_fix():
    print("=" * 70)
    print("다중 선택 모드 버튼 위치 수정 검증")
    print("=" * 70)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # multi_info_label과 multi_mode_btn 찾기
    multi_info_line = None
    multi_mode_line = None
    multi_info_frame = None
    multi_mode_frame = None

    for i, line in enumerate(lines):
        if 'self.multi_info_label = tk.Label(' in line:
            multi_info_line = i + 1
            # 다음 줄들에서 프레임 찾기
            for j in range(i, min(i+10, len(lines))):
                if 'self.label_copy_frame' in lines[j] or 'self.button_frame' in lines[j]:
                    if 'self.label_copy_frame' in lines[j]:
                        multi_info_frame = 'label_copy_frame'
                    else:
                        multi_info_frame = 'button_frame'
                    break

        if 'self.multi_mode_btn = tk.Button(' in line:
            multi_mode_line = i + 1
            # 다음 줄들에서 프레임 찾기
            for j in range(i, min(i+10, len(lines))):
                if 'self.label_copy_frame' in lines[j] or 'self.button_frame' in lines[j]:
                    if 'self.label_copy_frame' in lines[j]:
                        multi_mode_frame = 'label_copy_frame'
                    else:
                        multi_mode_frame = 'button_frame'
                    break

    print(f"\n✅ multi_info_label 발견 (라인 {multi_info_line})")
    print(f"   위치: {multi_info_frame}")

    print(f"\n✅ multi_mode_btn 발견 (라인 {multi_mode_line})")
    print(f"   위치: {multi_mode_frame}")

    print("\n" + "=" * 70)
    print("검증 결과")
    print("=" * 70)

    if multi_info_frame == multi_mode_frame == 'label_copy_frame':
        print("""
✅ 수정 완료!

둘 다 label_copy_frame에 있습니다.
이제 버튼이 올바른 위치에 표시됩니다.

위치: 상단의 라벨 복사 영역 (회색 박스 안)
- "선택된 라벨: 0개" 표시 옆에
- "다중선택모드: OFF" 버튼이 있습니다

사용 방법:
1. 프로그램 실행
2. 상단 라벨 복사 영역 확인 (마스킹 복사 오른쪽)
3. "선택된 라벨: 0개" 표시와 "다중선택모드: OFF" 버튼 확인
""")
        return True
    elif multi_mode_frame == 'button_frame':
        print("""
❌ 아직 수정되지 않았습니다!

문제:
- multi_info_label: {multi_info_frame}
- multi_mode_btn: {multi_mode_frame} ← 잘못된 위치!

해결:
라인 {multi_mode_line} 근처의 self.button_frame을
self.label_copy_frame으로 변경해야 합니다.
""")
        return False
    else:
        print(f"""
⚠️ 예상치 못한 상태

multi_info_label: {multi_info_frame}
multi_mode_btn: {multi_mode_frame}

수동 확인이 필요합니다.
""")
        return False

if __name__ == "__main__":
    import sys
    success = verify_fix()
    sys.exit(0 if success else 1)
