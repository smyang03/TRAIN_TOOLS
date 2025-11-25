"""
GTGEN Tool 마스킹 기능 분석 결과

테스트 날짜: 2025-11-25
"""

print("=" * 70)
print("마스킹 기능 전체 분석 결과")
print("=" * 70)

results = [
    {
        "name": "1. 일반 마스킹 저장 (get_masking)",
        "key": "S 키",
        "status": "✅ 정상",
        "details": [
            "메모리에만 저장하고 is_masking_dirty = True 설정",
            "프레임 이동 시 save_masking_if_dirty()가 자동 호출되어 파일에 저장됨",
            "의도된 설계: 프레임 이동 전까지 저장 지연"
        ]
    },
    {
        "name": "2. 마스킹 복사 (copy_masking_to_range)",
        "key": "UI 버튼",
        "status": "✅ 정상",
        "details": [
            "라인 2682: target_img.save(target_img_path) - 즉시 파일 저장",
            "각 대상 이미지마다 즉시 저장됨",
            "백업도 자동 생성됨"
        ]
    },
    {
        "name": "3. Label→Mask (convert_label_to_mask)",
        "key": "M 키 + 체크박스",
        "status": "✅ 수정됨",
        "details": [
            "이전: 메모리와 화면에만 적용, 파일 저장 안 됨 ❌",
            "수정: 라인 4774-4777에 이미지 저장 코드 추가 ✅",
            "이제 즉시 파일에 저장됨"
        ]
    },
    {
        "name": "4. 마스킹 로드 (load_masking)",
        "key": "L 키",
        "status": "❌ 버그 발견!",
        "details": [
            "메모리에만 적용, 화면에만 표시",
            "is_masking_dirty = True 설정하지만...",
            "프레임 이동하지 않으면 파일에 저장 안 됨!",
            "수정 필요: 즉시 파일 저장 코드 추가해야 함"
        ]
    }
]

for item in results:
    print(f"\n{item['name']}")
    print(f"단축키: {item['key']}")
    print(f"상태: {item['status']}")
    print("상세:")
    for detail in item['details']:
        print(f"  • {detail}")

print("\n" + "=" * 70)
print("결론")
print("=" * 70)
print("""
✅ 정상 동작:
  - 일반 마스킹 저장 (S 키): 프레임 이동 시 저장됨
  - 마스킹 복사: 즉시 저장됨

✅ 수정 완료:
  - Label→Mask: 이미지 저장 코드 추가됨

❌ 수정 필요:
  - 마스킹 로드 (L 키): 이미지 저장 코드 추가 필요!

    문제: L 키로 마스킹을 로드해도 현재 프레임에서 다른 프레임으로
          이동하지 않으면 파일에 저장되지 않음.

    해결: load_masking() 함수에 이미지 저장 코드 추가
""")
print("=" * 70)
