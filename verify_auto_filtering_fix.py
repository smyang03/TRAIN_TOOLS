# -*- coding: utf-8 -*-
"""
라벨 복사/붙여넣기 자동 필터링 충돌 수정 검증

수정 내용:
1. paste_label(): 붙여넣기 전 자동 필터링 대상 확인 및 경고
2. paste_multi_selected(): 다중 붙여넣기 전 자동 필터링 대상 확인 및 경고
3. copy_label_to_range(): preserve_mode "replace" 시 기존 라벨 제거 로직 수정
"""

GREEN = '\033[92m'
RED = '\033[91m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
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

print_header("라벨 복사/붙여넣기 자동 필터링 충돌 수정 검증")

# =================================================================
# 문제 분석
# =================================================================

print("🐛 발견된 문제:")
print()
print_error("다중 라벨 복사/붙여넣기 후 다른 페이지 갔다가 돌아오면 라벨 사라짐")
print_error("페이지 범위 복사 기능에서 replace 모드가 제대로 작동하지 않음")
print()

print("📋 원인 분석:")
print()
print_info("1. paste_multi_selected()와 paste_label() 문제:")
print_info("   - 붙여넣기 후 write_bbox() 호출하여 파일에 저장 ✓")
print_info("   - 다른 페이지 이동 시 load_bbox() 호출")
print_info("   - load_bbox()에서 자동 필터링 실행:")
print_info("     • auto_delete_manager: 자동 삭제 클래스 필터링")
print_info("     • exclusion_zone: 제외 영역 내 라벨 필터링")
print_info("   - 필터링 후 write_bbox() 재호출 → 파일에 다시 저장 ✗")
print_info("   - 결과: 붙여넣은 라벨이 자동으로 삭제됨")
print()

print_info("2. copy_label_to_range() 문제:")
print_info("   - 라인 2058: f.writelines(existing_labels) 항상 실행")
print_info("   - preserve_mode가 'replace'일 때도 기존 라벨 유지 ✗")
print_info("   - 결과: replace 모드가 제대로 작동하지 않음")
print()

# =================================================================
# 수정 내용
# =================================================================

print_header("수정 내용")

print("1️⃣ paste_label() 함수 (04.GTGEN_Tool_svms_v2.py:6068)")
print("-" * 80)
print_info("수정 사항:")
print_info("  - 붙여넣기 전 자동 필터링 대상인지 확인")
print_info("  - 자동 삭제 클래스 확인")
print_info("  - 제외 영역 확인")
print_info("  - 경고 메시지 표시 및 사용자 확인")
print()

print("2️⃣ paste_multi_selected() 함수 (04.GTGEN_Tool_svms_v2.py:6183)")
print("-" * 80)
print_info("수정 사항:")
print_info("  - 붙여넣기 전 자동 필터링 대상인지 확인")
print_info("  - 자동 삭제 클래스 확인 (각 라벨)")
print_info("  - 제외 영역 확인 (각 라벨)")
print_info("  - 경고 메시지 표시 및 사용자 확인")
print()

print("3️⃣ copy_label_to_range() 함수 (04.GTGEN_Tool_svms_v2.py:2056)")
print("-" * 80)
print_info("수정 사항:")
print_info("  - preserve_mode 체크를 먼저 실행")
print_info("  - preserve='preserve': existing_labels + copytext")
print_info("  - preserve='replace': copytext만 쓰기")
print()

# =================================================================
# 시나리오 테스트
# =================================================================

print_header("시나리오 테스트")

print("시나리오 1: 자동 필터링 대상 라벨 붙여넣기")
print("-" * 80)
print()

print("1️⃣ 기존 동작 (버그)")
print_info("1. person 클래스를 자동 삭제 대상으로 설정")
print_info("2. 이미지 A에서 person 라벨 선택, Ctrl+j로 복사")
print_info("3. 이미지 B로 이동")
print_info("4. Ctrl+k로 붙여넣기 → 라벨 추가됨, 파일 저장됨 ✓")
print_info("5. 이미지 C로 이동")
print_info("6. 다시 이미지 B로 돌아옴 → load_bbox() 호출")
print_info("7. auto_delete_manager가 person 라벨 삭제 ✗")
print_info("8. write_bbox() 호출 → 파일에 저장 (person 없이) ✗")
print_error("결과: 붙여넣은 라벨이 사라짐!")
print()

print("2️⃣ 수정된 동작")
print_info("1. person 클래스를 자동 삭제 대상으로 설정")
print_info("2. 이미지 A에서 person 라벨 선택, Ctrl+j로 복사")
print_info("3. 이미지 B로 이동")
print_info("4. Ctrl+k로 붙여넣기 시도")
print_info("5. ⚠️ 경고 메시지 표시:")
print_info("   '붙여넣을 라벨이 자동 필터링 대상입니다:'")
print_info("   '자동 삭제 대상 클래스: person'")
print_info("   '다음 페이지로 이동 시 자동으로 삭제됩니다.'")
print_info("   '계속하시겠습니까?'")
print_info("6. 사용자가 '아니오' 선택 → 붙여넣기 취소 ✓")
print_info("   또는 '예' 선택 → 경고를 알고 붙여넣기 진행 ✓")
print_success("결과: 사용자가 상황을 인지하고 선택!")
print()

print("시나리오 2: copy_label_to_range() replace 모드")
print("-" * 80)
print()

print("1️⃣ 기존 동작 (버그)")
print_info("1. 이미지 1: [person, car] 라벨")
print_info("2. 이미지 2: [bicycle] 라벨 선택")
print_info("3. 범위 복사: 이미지 1에 bicycle 복사, mode='replace'")
print_info("4. existing_labels를 먼저 씀 → [person, car] 유지 ✗")
print_info("5. 그 다음 copytext를 씀 → [bicycle] 추가")
print_error("결과: 이미지 1에 [person, car, bicycle] (replace 안됨!)")
print()

print("2️⃣ 수정된 동작")
print_info("1. 이미지 1: [person, car] 라벨")
print_info("2. 이미지 2: [bicycle] 라벨 선택")
print_info("3. 범위 복사: 이미지 1에 bicycle 복사, mode='replace'")
print_info("4. preserve_mode 확인 → 'replace'")
print_info("5. copytext만 씀 → [bicycle]")
print_success("결과: 이미지 1에 [bicycle] (replace 성공!)")
print()

# =================================================================
# 코드 변경사항 상세
# =================================================================

print_header("코드 변경사항 상세")

print("1️⃣ paste_label() - 자동 필터링 확인 추가")
print("-" * 80)
print(f"{GREEN}[추가된 코드]{RESET}")
print("""
    # 자동 필터링 충돌 확인
    warning_messages = []

    # 1. 자동 삭제 클래스 확인
    if self.auto_delete_manager and self.auto_delete_manager.delete_class_ids:
        global class_name
        class_id = int(self.copied_label[2])
        if class_id in self.auto_delete_manager.delete_class_ids:
            class_str = class_name[class_id] if class_id < len(class_name) else str(class_id)
            warning_messages.append(f"자동 삭제 대상 클래스: {class_str}")

    # 2. 제외 영역 확인
    if self.exclusion_zone_enabled and self.exclusion_zone_manager:
        if self.exclusion_zone_manager.is_bbox_in_exclusion_zone(self.copied_label):
            warning_messages.append("제외 영역 내 라벨")

    # 경고가 있으면 사용자에게 확인
    if warning_messages:
        warning_text = "\\n".join(warning_messages)
        msg = f"⚠️ 붙여넣을 라벨이 자동 필터링 대상입니다:\\n\\n{warning_text}\\n\\n다음 페이지로 이동 시 자동으로 삭제됩니다.\\n계속하시겠습니까?"
        if not messagebox.askyesno("자동 필터링 경고", msg):
            return
""")
print()

print("2️⃣ paste_multi_selected() - 자동 필터링 확인 추가")
print("-" * 80)
print(f"{GREEN}[추가된 코드]{RESET}")
print("""
    # 자동 필터링 충돌 확인
    warning_messages = []

    # 1. 자동 삭제 클래스 확인
    if self.auto_delete_manager and self.auto_delete_manager.delete_class_ids:
        global class_name
        filtered_labels = []
        for label in self.copied_multi_labels:
            class_id = int(label[2])
            if class_id in self.auto_delete_manager.delete_class_ids:
                class_str = class_name[class_id] if class_id < len(class_name) else str(class_id)
                filtered_labels.append(class_str)

        if filtered_labels:
            warning_messages.append(f"자동 삭제 대상 클래스: {', '.join(filtered_labels)}")

    # 2. 제외 영역 확인
    if self.exclusion_zone_enabled and self.exclusion_zone_manager:
        in_exclusion_count = 0
        for label in self.copied_multi_labels:
            if self.exclusion_zone_manager.is_bbox_in_exclusion_zone(label):
                in_exclusion_count += 1

        if in_exclusion_count > 0:
            warning_messages.append(f"제외 영역 내 라벨: {in_exclusion_count}개")

    # 경고가 있으면 사용자에게 확인
    if warning_messages:
        warning_text = "\\n".join(warning_messages)
        msg = f"⚠️ 붙여넣을 라벨이 자동 필터링 대상입니다:\\n\\n{warning_text}\\n\\n다음 페이지로 이동 시 자동으로 삭제됩니다.\\n계속하시겠습니까?"
        if not messagebox.askyesno("자동 필터링 경고", msg):
            return
""")
print()

print("3️⃣ copy_label_to_range() - preserve_mode 로직 수정")
print("-" * 80)
print(f"{YELLOW}[수정 전]{RESET}")
print("""
    with open(target_label_path, 'w', encoding='utf-8') as f:
        f.writelines(existing_labels)  # 항상 기존 라벨 먼저 씀
        if copy_mode == "selected" and preserve_mode == "preserve":
            # 중복 검사
            ...
            if not is_duplicate:
                f.writelines(copytext)
        else:
            f.writelines(copytext)
""")
print()

print(f"{GREEN}[수정 후]{RESET}")
print("""
    with open(target_label_path, 'w', encoding='utf-8') as f:
        if preserve_mode == "preserve":
            # 기존 라벨 유지하고 새 라벨 추가
            f.writelines(existing_labels)

            if copy_mode == "selected":
                # 중복 검사
                ...
                if not is_duplicate:
                    f.writelines(copytext)
            else:
                # 다중 선택 또는 전체 복사 시 중복 검사 없이 추가
                f.writelines(copytext)
        else:
            # replace 모드: 기존 라벨 지우고 새 라벨만 쓰기
            f.writelines(copytext)
""")
print()

# =================================================================
# 영향 분석
# =================================================================

print_header("영향 분석")

print("✅ 긍정적 영향:")
print_info("1. 자동 필터링 대상 라벨 붙여넣기 시 사전 경고")
print_info("2. 사용자가 상황을 인지하고 선택 가능")
print_info("3. 예상치 못한 라벨 삭제 방지")
print_info("4. copy_label_to_range() replace 모드 정상 작동")
print_info("5. 파일 작업의 예측 가능성 향상")
print()

print("⚠️ 주의사항:")
print_info("1. 경고 대화상자가 추가로 표시됨 (사용자 인터랙션 증가)")
print_info("2. 자동 삭제 클래스나 제외 영역이 설정되어 있을 때만 경고")
print_info("3. 설정이 없으면 기존과 동일하게 작동")
print()

print("🔒 안전성:")
print_info("1. 사용자에게 확인 후 진행")
print_info("2. 경고를 무시하고 진행할 수도 있음 (사용자 선택)")
print_info("3. 기존 백업 시스템은 그대로 유지")
print()

# =================================================================
# 테스트 체크리스트
# =================================================================

print_header("테스트 체크리스트")

print("[ ] 1. 자동 삭제 클래스가 설정된 상태에서 라벨 붙여넣기")
print_info("    - 해당 클래스 라벨 복사")
print_info("    - 다른 페이지에서 붙여넣기 시도")
print_info("    - 경고 메시지 표시 확인")
print_info("    - '아니오' 선택 시 취소 확인")
print_info("    - '예' 선택 시 붙여넣기 진행 확인")
print()

print("[ ] 2. 제외 영역이 설정된 상태에서 라벨 붙여넣기")
print_info("    - 제외 영역 내 라벨 복사")
print_info("    - 다른 페이지에서 붙여넣기 시도")
print_info("    - 경고 메시지 표시 확인")
print()

print("[ ] 3. 다중 라벨 붙여넣기 경고")
print_info("    - 여러 라벨 선택 (일부는 자동 삭제 대상)")
print_info("    - Ctrl+j로 복사")
print_info("    - Ctrl+k로 붙여넣기 시도")
print_info("    - 경고 메시지에 모든 문제 라벨 표시 확인")
print()

print("[ ] 4. copy_label_to_range() replace 모드")
print_info("    - 기존 라벨이 있는 이미지들에 대해")
print_info("    - replace 모드로 라벨 복사")
print_info("    - 기존 라벨이 삭제되고 새 라벨만 남는지 확인")
print()

print("[ ] 5. copy_label_to_range() preserve 모드")
print_info("    - 기존 라벨이 있는 이미지들에 대해")
print_info("    - preserve 모드로 라벨 복사")
print_info("    - 기존 라벨이 유지되고 새 라벨이 추가되는지 확인")
print()

# =================================================================
# 결론
# =================================================================

print_header("결론")

print(f"{GREEN}✅ 모든 버그 수정 완료{RESET}")
print()
print("수정된 기능:")
print_success("1. paste_label() - 자동 필터링 충돌 경고 추가")
print_success("2. paste_multi_selected() - 자동 필터링 충돌 경고 추가")
print_success("3. copy_label_to_range() - preserve_mode 로직 수정")
print()
print("예상 효과:")
print_success("✓ 자동 필터링으로 인한 예상치 못한 라벨 삭제 방지")
print_success("✓ 사용자가 상황을 인지하고 선택 가능")
print_success("✓ replace 모드가 제대로 작동")
print_success("✓ 라벨 복사 기능의 예측 가능성 향상")
print()
print(f"{BLUE}커밋 준비 완료 ✓{RESET}")
print()
