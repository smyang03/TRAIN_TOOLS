# -*- coding: utf-8 -*-
"""
클래스 설정 파일 생성 도구
기본 설정 파일을 빠르게 생성합니다.
"""
import json
import os

print("=" * 60)
print("GTGEN Tool 클래스 설정 파일 생성")
print("=" * 60)

# 기본 설정 (사람 검출 프로젝트)
default_config = {
    "classes": [
        {"id": 0, "name": "person", "key": "1", "color": "magenta"},
        {"id": 1, "name": "head", "key": "2", "color": "blue"},
        {"id": 2, "name": "helmet", "key": "3", "color": "yellow"},
        {"id": 3, "name": "vehicle", "key": "4", "color": "green"}
    ]
}

filename = "class_config.json"

# 이미 파일이 있으면 경고
if os.path.exists(filename):
    print(f"\n경고: {filename} 파일이 이미 존재합니다.")
    response = input("덮어쓰시겠습니까? (y/n): ")
    if response.lower() != 'y':
        print("취소되었습니다.")
        exit(0)

# 설정 파일 생성
try:
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, ensure_ascii=False, indent=2)

    print(f"\n✓ {filename} 파일이 생성되었습니다.")
    print("\n생성된 클래스:")
    for cls in default_config['classes']:
        print(f"  {cls['id']}: {cls['name']} (단축키: {cls['key']}, 색상: {cls['color']})")

    print("\n이제 04.GTGEN_Tool_svms_v2.py를 실행하세요.")
    print("설정 파일이 자동으로 로드됩니다.")

except Exception as e:
    print(f"\n✗ 오류 발생: {e}")
    exit(1)

print("=" * 60)
