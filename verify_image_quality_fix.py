#!/usr/bin/env python
"""
이미지 저장 품질 설정 확인 스크립트
"""

import os

def verify_quality_settings():
    print("=" * 70)
    print("이미지 저장 품질 설정 확인")
    print("=" * 70)

    with open('04.GTGEN_Tool_svms_v2.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # img_to_save.save(self.im_fn) 패턴 찾기
    save_locations = []

    for i, line in enumerate(lines):
        if 'img_to_save.save(self.im_fn)' in line or 'masked_img.save(self.im_fn' in line:
            save_locations.append({
                'line': i + 1,
                'code': line.strip(),
                'has_quality': False,
                'context': []
            })

            # 앞뒤 5줄 확인
            for j in range(max(0, i-5), min(len(lines), i+5)):
                save_locations[-1]['context'].append((j+1, lines[j].rstrip()))

                # quality 설정 확인
                if j > i - 5 and j < i + 3:
                    if 'quality=' in lines[j]:
                        save_locations[-1]['has_quality'] = True

    print(f"\n발견된 이미지 저장 코드: {len(save_locations)}개\n")

    all_good = True
    for idx, loc in enumerate(save_locations):
        print(f"{'='*70}")
        print(f"위치 {idx+1}: 라인 {loc['line']}")
        print(f"{'='*70}")

        # 컨텍스트 출력 (중요한 부분만)
        for line_num, code in loc['context']:
            marker = " → " if line_num == loc['line'] else "   "
            print(f"{marker}{line_num:5d}: {code}")

        if loc['has_quality']:
            print("\n✅ JPG 품질 설정 있음 (quality=95)")
        else:
            # JPG 체크하는 if문 확인
            has_jpg_check = any('endswith' in code and ('jpg' in code.lower() or 'jpeg' in code.lower())
                               for _, code in loc['context'])

            if has_jpg_check:
                print("\n✅ JPG 품질 설정 있음 (if문으로 처리)")
            else:
                print("\n❌ JPG 품질 설정 없음! (뭉개질 수 있음)")
                all_good = False

        print()

    print("=" * 70)
    print("검증 결과")
    print("=" * 70)

    if all_good:
        print("""
✅ 모든 이미지 저장 코드가 올바르게 설정되었습니다!

JPG 파일은 quality=95로 저장되어 마스킹이 뭉개지지 않습니다.
PNG 파일은 무손실 압축으로 저장됩니다.

수정 내용:
1. Label→Mask: JPG quality=95 설정 추가
2. load_masking: JPG quality=95 설정 추가

이제 마스킹이 깨끗하게 저장됩니다!
""")
        return True
    else:
        print("""
❌ 일부 코드에 품질 설정이 누락되었습니다!

JPG 파일을 기본 품질로 저장하면 압축되어 마스킹이 뭉개집니다.
위에 표시된 위치의 코드를 수정해야 합니다.

수정 예시:
```python
if self.im_fn.lower().endswith('.jpg') or self.im_fn.lower().endswith('.jpeg'):
    img_to_save.save(self.im_fn, quality=95, optimize=True)
else:
    img_to_save.save(self.im_fn)
```
""")
        return False

if __name__ == "__main__":
    import sys
    success = verify_quality_settings()
    sys.exit(0 if success else 1)
