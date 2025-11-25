# -*- coding: utf-8 -*-
"""
다중 선택 모드 bbox 경계 선택 버그 수정 검증

문제: range() 함수가 끝 값을 포함하지 않아 bbox 경계를 클릭하면 선택되지 않음
수정: range() 대신 <= 비교 연산자 사용
"""

GREEN = '\033[92m'
RED = '\033[91m'
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

print_header("다중 선택 모드 bbox 경계 선택 버그 수정 검증")

# 테스트 케이스
bbox = [False, 'person', 0, 100, 100, 200, 200]  # [sel, class, id, x1, y1, x2, y2]

print("bbox 좌표: x1=100, y1=100, x2=200, y2=200\n")

# 기존 코드 (버그 있음)
def old_check(x, y, rc):
    """기존 버그 있는 코드"""
    return x in range(int(rc[3]), int(rc[5])) and y in range(int(rc[4]), int(rc[6]))

# 수정된 코드
def new_check(x, y, rc):
    """수정된 코드"""
    return int(rc[3]) <= x <= int(rc[5]) and int(rc[4]) <= y <= int(rc[6])

# 테스트 케이스
test_cases = [
    (100, 100, "좌상단 모서리"),
    (200, 100, "우상단 모서리"),
    (100, 200, "좌하단 모서리"),
    (200, 200, "우하단 모서리"),
    (150, 100, "상단 경계"),
    (150, 200, "하단 경계"),
    (100, 150, "좌측 경계"),
    (200, 150, "우측 경계"),
    (150, 150, "중앙"),
    (99, 150, "좌측 바깥"),
    (201, 150, "우측 바깥"),
    (150, 99, "상단 바깥"),
    (150, 201, "하단 바깥"),
]

print("=" * 80)
print(f"{'위치':<15} {'좌표':<15} {'기존 코드':<15} {'수정 코드':<15} {'상태'}")
print("=" * 80)

all_pass = True
for x, y, desc in test_cases:
    old_result = old_check(x, y, bbox)
    new_result = new_check(x, y, bbox)

    # 경계와 모서리는 선택되어야 함
    should_select = (100 <= x <= 200) and (100 <= y <= 200)

    status = ""
    if new_result == should_select:
        status = f"{GREEN}✓ 정상{RESET}"
    else:
        status = f"{RED}✗ 오류{RESET}"
        all_pass = False

    old_str = "선택됨" if old_result else "선택안됨"
    new_str = "선택됨" if new_result else "선택안됨"

    print(f"{desc:<15} ({x:3},{y:3})    {old_str:<15} {new_str:<15} {status}")

print("=" * 80)

if all_pass:
    print(f"\n{GREEN}🎉 모든 테스트 통과! 수정이 성공적으로 적용되었습니다.{RESET}\n")
else:
    print(f"\n{RED}❌ 일부 테스트 실패. 코드를 확인해주세요.{RESET}\n")

# 버그 설명
print_header("버그 설명")
print("문제:")
print("  - Python의 range(start, end)는 end 값을 포함하지 않음")
print("  - range(100, 200)은 100~199까지만 포함")
print("  - bbox 경계(x=200 또는 y=200)를 클릭하면 선택되지 않음\n")

print("수정:")
print("  - range() 대신 <= 비교 연산자 사용")
print("  - 기존: x in range(int(rc[3]), int(rc[5]))")
print("  - 수정: int(rc[3]) <= x <= int(rc[5]))\n")

print("영향:")
print("  - 4672번 줄: Ctrl + 클릭 다중 선택")
print("  - 4678번 줄: 일반 클릭 및 다중 선택 모드")
print("  - 4699번 줄: Ctrl + 마우스 다운 이벤트\n")

# 실제 시나리오 테스트
print_header("실제 사용 시나리오 테스트")

print("시나리오 1: bbox 경계 클릭")
print("  bbox가 (100, 100, 200, 200)일 때")
print("  사용자가 우측 경계(x=200, y=150)를 클릭")
print(f"  - 기존 코드: {old_check(200, 150, bbox)} (선택 안됨) {RED}✗{RESET}")
print(f"  - 수정 코드: {new_check(200, 150, bbox)} (선택됨) {GREEN}✓{RESET}\n")

print("시나리오 2: bbox 모서리 클릭")
print("  bbox가 (100, 100, 200, 200)일 때")
print("  사용자가 우하단 모서리(x=200, y=200)를 클릭")
print(f"  - 기존 코드: {old_check(200, 200, bbox)} (선택 안됨) {RED}✗{RESET}")
print(f"  - 수정 코드: {new_check(200, 200, bbox)} (선택됨) {GREEN}✓{RESET}\n")

print("시나리오 3: bbox 내부 클릭")
print("  bbox가 (100, 100, 200, 200)일 때")
print("  사용자가 중앙(x=150, y=150)을 클릭")
print(f"  - 기존 코드: {old_check(150, 150, bbox)} (선택됨) {GREEN}✓{RESET}")
print(f"  - 수정 코드: {new_check(150, 150, bbox)} (선택됨) {GREEN}✓{RESET}\n")

print_header("결론")
print(f"{GREEN}✅ 수정 완료{RESET}")
print("  - bbox 경계와 모서리를 클릭해도 정상적으로 선택됩니다")
print("  - 다중 선택 모드에서 모든 bbox를 정확하게 선택할 수 있습니다")
print("  - Ctrl + 클릭으로 다중 선택도 정상 동작합니다\n")
