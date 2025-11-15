#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
간단한 자동 마스킹 도구
특정 클래스의 바운딩 박스를 자동으로 마스킹하는 프로그램
"""

import os
import sys
from PIL import Image
import numpy as np
from pathlib import Path

# YOLO 클래스 정의
class_name = [
    "person", "slip", "head", "helmet", "gasmask", "Drum", "sitting",
    "bicycle", "car", "motorbike", "aeroplane",
    "bus", "train", "truck", "boat", "trafficlight",
    "firehydrant", "stop sign", "parking meter", "bench", "bird",
    "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "van", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut",
    "cake", "chair", "sofa", "pottedplant", "bed",
    "diningtable", "toilet", "tvmonitor", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book"
]

def get_class_index(class_numbers_input):
    """클래스 번호들을 검증하고 반환"""
    indices = []
    for num_str in class_numbers_input:
        try:
            num = int(num_str.strip())
            if 0 <= num < len(class_name):
                indices.append(num)
                print(f"선택된 클래스: {num} - {class_name[num]}")
            else:
                print(f"경고: '{num}' 번호가 유효하지 않습니다. (0-{len(class_name)-1} 범위)")
        except ValueError:
            print(f"경고: '{num_str}'는 유효한 숫자가 아닙니다.")
    return indices

def load_yolo_labels(label_path):
    """YOLO 형식 라벨 파일 로드"""
    if not os.path.exists(label_path):
        return []
    
    labels = []
    with open(label_path, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split()
                if len(parts) >= 5:
                    class_id = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                    labels.append([class_id, cx, cy, w, h])
    return labels

def convert_yolo_to_bbox(yolo_coords, img_width, img_height):
    """YOLO 좌표를 절대 좌표로 변환"""
    cx, cy, w, h = yolo_coords
    
    # 절대 좌표 계산
    x1 = int((cx - w/2) * img_width)
    y1 = int((cy - h/2) * img_height)
    x2 = int((cx + w/2) * img_width)
    y2 = int((cy + h/2) * img_height)
    
    # 이미지 경계 내로 제한
    x1 = max(0, min(x1, img_width-1))
    y1 = max(0, min(y1, img_height-1))
    x2 = max(0, min(x2, img_width-1))
    y2 = max(0, min(y2, img_height-1))
    
    return x1, y1, x2, y2

def apply_masking(image_path, label_path, target_classes, output_path, mask_color=[255, 0, 255]):
    """이미지에 마스킹 적용"""
    try:
        # 이미지 로드
        img = Image.open(image_path)
        img_array = np.array(img)
        img_height, img_width = img_array.shape[:2]
        
        # 라벨 로드
        labels = load_yolo_labels(label_path)
        
        masked_count = 0
        
        # 각 라벨에 대해 처리
        for label in labels:
            class_id = label[0]
            
            # 타겟 클래스인 경우 마스킹 적용
            if class_id in target_classes:
                x1, y1, x2, y2 = convert_yolo_to_bbox(label[1:5], img_width, img_height)
                
                # 마스킹 적용
                img_array[y1:y2, x1:x2] = mask_color
                masked_count += 1
        
        # 마스킹된 이미지 저장
        if masked_count > 0:
            masked_img = Image.fromarray(img_array)
            masked_img.save(output_path)
            return True, masked_count
        else:
            # 마스킹할 객체가 없으면 원본 복사
            img.save(output_path)
            return False, 0
            
    except Exception as e:
        print(f"오류 발생 - {image_path}: {e}")
        return False, 0

def process_images(image_folder, label_folder, output_folder, target_classes):
    """이미지들을 일괄 처리"""
    
    # 출력 폴더 생성
    os.makedirs(output_folder, exist_ok=True)
    
    # 이미지 파일들 찾기 (중복 제거를 위해 set 사용)
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
    image_files = set()
    
    for ext in image_extensions:
        # 소문자와 대문자 확장자 모두 검색하되 중복 제거
        image_files.update(Path(image_folder).glob(f'*{ext}'))
        image_files.update(Path(image_folder).glob(f'*{ext.upper()}'))
    
    # set을 list로 변환
    image_files = list(image_files)
    
    if not image_files:
        print(f"이미지 폴더에서 이미지 파일을 찾을 수 없습니다: {image_folder}")
        return
    
    print(f"총 {len(image_files)}개의 이미지를 처리합니다...")
    
    processed_count = 0
    masked_count = 0
    
    for img_path in image_files:
        # 해당하는 라벨 파일 경로
        label_path = Path(label_folder) / f"{img_path.stem}.txt"
        
        # 출력 파일 경로
        output_path = Path(output_folder) / img_path.name
        
        # 마스킹 적용
        success, masks_applied = apply_masking(
            str(img_path), 
            str(label_path), 
            target_classes, 
            str(output_path)
        )
        
        if success:
            masked_count += 1
            print(f"✓ {img_path.name} - {masks_applied}개 객체 마스킹됨")
        else:
            print(f"- {img_path.name} - 마스킹할 객체 없음")
        
        processed_count += 1
    
    print(f"\n처리 완료!")
    print(f"총 처리된 이미지: {processed_count}개")
    print(f"마스킹 적용된 이미지: {masked_count}개")
    print(f"결과 저장 위치: {output_folder}")

def show_available_classes():
    """사용 가능한 클래스 목록 표시"""
    print("사용 가능한 클래스 목록:")
    for i, cls in enumerate(class_name):
        print(f"{i:2d}: {cls}")

def main():
    print("=" * 50)
    print("간단한 자동 마스킹 도구")
    print("=" * 50)
    
    # 사용 가능한 클래스 표시
    show_available_classes()
    print()
    
    # 사용자 입력 받기
    try:
        # 이미지 폴더 입력
        image_folder = input("이미지 폴더 경로를 입력하세요: ").strip()
        if not os.path.exists(image_folder):
            print("이미지 폴더가 존재하지 않습니다.")
            return
        
        # 라벨 폴더 입력
        label_folder = input("라벨 폴더 경로를 입력하세요: ").strip()
        if not os.path.exists(label_folder):
            print("라벨 폴더가 존재하지 않습니다.")
            return
        
        # 출력 폴더 입력
        output_folder = input("출력 폴더 경로를 입력하세요: ").strip()
        
        # 마스킹할 클래스 입력
        print("\n마스킹할 클래스 번호를 입력하세요 (쉼표로 구분):")
        print("예시: 0, 8, 21 (person, car, dog)")
        class_input = input("클래스 번호: ").strip()
        
        if not class_input:
            print("클래스 번호가 입력되지 않았습니다.")
            return
        
        # 클래스 번호를 리스트로 변환
        target_class_numbers = [num.strip() for num in class_input.split(',')]
        target_classes = get_class_index(target_class_numbers)
        
        if not target_classes:
            print("유효한 클래스가 없습니다.")
            return
        
        print(f"\n선택된 클래스: {[class_name[i] for i in target_classes]}")
        
        # 처리 시작 확인
        confirm = input("\n처리를 시작하시겠습니까? (y/n): ").strip().lower()
        if confirm != 'y':
            print("처리가 취소되었습니다.")
            return
        
        # 이미지 처리 실행
        process_images(image_folder, label_folder, output_folder, target_classes)
        
    except KeyboardInterrupt:
        print("\n\n처리가 중단되었습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()