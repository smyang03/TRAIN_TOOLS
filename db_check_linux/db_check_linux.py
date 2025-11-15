#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import glob
import argparse
from collections import Counter, defaultdict

def create_directory(directory):
    """디렉토리가 없으면 생성하는 함수"""
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"디렉토리 생성: {directory}")

def get_base_filename(filepath):
    """파일 경로에서 기본 파일명만 추출 (확장자 제외)"""
    return os.path.splitext(os.path.basename(filepath))[0]

def check_annotation_content(label_path):
    """라벨 파일에 어노테이션 내용이 있는지 확인하고, 클래스 정보 반환"""
    classes = []
    try:
        with open(label_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:  # 빈 줄이 아닌 경우
                    parts = line.split()
                    if len(parts) >= 5:  # YOLO 포맷은 최소 5개 값이 필요 (class x y w h)
                        classes.append(int(parts[0]))
    except Exception as e:
        print(f"라벨 파일 읽기 오류 ({label_path}): {e}")
    
    return classes  # 빈 리스트면 어노테이션이 없는 것

def analyze_dataset(list_file, output_dir):
    """데이터셋 분석 및 결과 저장"""
    # 기본 파일명 추출 (확장자 제외)
    base_name = get_base_filename(list_file)
    
    # 카테고리별 리스트 파일 경로
    normal_list = os.path.join(output_dir, f"{base_name}_normal.txt")
    empty_label_list = os.path.join(output_dir, f"{base_name}_empty_label.txt")
    no_label_list = os.path.join(output_dir, f"{base_name}_no_label.txt")
    no_image_list = os.path.join(output_dir, f"{base_name}_no_image.txt")
    both_missing_list = os.path.join(output_dir, f"{base_name}_both_missing.txt")
    
    # 통계 집계용 변수
    total_count = 0
    normal_count = 0
    empty_label_count = 0
    no_label_count = 0
    no_image_count = 0
    both_missing_count = 0
    class_counter = Counter()
    
    # 카테고리별 파일 초기화
    open(normal_list, 'w').close()
    open(empty_label_list, 'w').close()
    open(no_label_list, 'w').close()
    open(no_image_list, 'w').close()
    open(both_missing_list, 'w').close()
    
    # 리스트 파일 읽기
    try:
        with open(list_file, 'r') as f:
            image_paths = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"입력 파일 읽기 오류: {e}")
        return None
    
    # 각 항목 분석
    for img_path in image_paths:
        total_count += 1
        
        # 이미지 경로에서 라벨 경로 추출
        label_path = img_path.replace('JPEGImages', 'labels').replace('.jpg', '.txt')
        
        # 파일 존재 여부 확인
        img_exists = os.path.isfile(img_path)
        label_exists = os.path.isfile(label_path)
        
        # 카테고리 분류
        if img_exists and label_exists:
            # 라벨 파일 내용 확인
            classes = check_annotation_content(label_path)
            if classes:
                # 정상: 이미지와 라벨 모두 있고 어노테이션도 있음
                normal_count += 1
                with open(normal_list, 'a') as f:
                    f.write(f"{img_path}\n")
                # 클래스별 카운트 업데이트
                for cls in classes:
                    class_counter[cls] += 1
            else:
                # 빈 라벨: 이미지와 라벨은 있지만 어노테이션이 없음
                empty_label_count += 1
                with open(empty_label_list, 'a') as f:
                    f.write(f"{img_path}\n")
        elif img_exists and not label_exists:
            # 라벨 없음: 이미지는 있지만 라벨이 없음
            no_label_count += 1
            with open(no_label_list, 'a') as f:
                f.write(f"{img_path}\n")
        elif not img_exists and label_exists:
            # 이미지 없음: 라벨은 있지만 이미지가 없음
            no_image_count += 1
            with open(no_image_list, 'a') as f:
                f.write(f"{img_path}\n")
        else:
            # 모두 없음: 이미지와 라벨 모두 없음
            both_missing_count += 1
            with open(both_missing_list, 'a') as f:
                f.write(f"{img_path}\n")
    
    # 요약 정보 생성
    summary = {
        'total': total_count,
        'normal': normal_count,
        'empty_label': empty_label_count,
        'no_label': no_label_count,
        'no_image': no_image_count,
        'both_missing': both_missing_count,
        'class_counts': dict(class_counter)
    }
    
    # 요약 파일 저장
    summary_file = os.path.join(output_dir, f"{base_name}_summary.txt")
    with open(summary_file, 'w') as f:
        f.write(f"입력 파일: {list_file}\n")
        f.write(f"분석 일시: {import_datetime().now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("======== 데이터셋 통계 정보 ========\n")
        f.write(f"전체 데이터베이스 항목 수: {total_count}\n\n")
        f.write("상태별 항목 수:\n")
        f.write(f"- 정상 (이미지와 라벨 모두 있고 어노테이션도 있음): {normal_count} ({normal_count/total_count*100:.2f}%)\n")
        f.write(f"- 빈 라벨 (이미지와 라벨은 있지만 어노테이션이 없음): {empty_label_count} ({empty_label_count/total_count*100:.2f}%)\n")
        f.write(f"- 라벨 없음 (이미지는 있지만 라벨이 없음): {no_label_count} ({no_label_count/total_count*100:.2f}%)\n")
        f.write(f"- 이미지 없음 (라벨은 있지만 이미지가 없음): {no_image_count} ({no_image_count/total_count*100:.2f}%)\n")
        f.write(f"- 모두 없음 (이미지와 라벨 모두 없음): {both_missing_count} ({both_missing_count/total_count*100:.2f}%)\n\n")
        f.write("클래스별 어노테이션 수량:\n")
        total_annotations = sum(class_counter.values())
        for cls, count in sorted(class_counter.items()):
            f.write(f"- 클래스 {cls}: {count} ({count/total_annotations*100:.2f}%)\n")
        f.write(f"\n총 어노테이션 수: {total_annotations}\n")
    
    print(f"\n분석 완료! 결과는 {output_dir} 디렉토리에 저장되었습니다.")
    return summary

def import_datetime():
    """datetime 모듈 임포트 함수"""
    import datetime
    return datetime

def main():
    parser = argparse.ArgumentParser(description='YOLO 데이터셋 분석기')
    parser.add_argument('-i', '--input', help='입력 리스트 파일 경로')
    parser.add_argument('-o', '--output', help='결과 저장 디렉토리')
    
    args = parser.parse_args()
    
    # 사용자 입력 받기
    input_file = args.input
    if not input_file:
        input_file = input("입력 리스트 파일 경로를 입력하세요: ")
    
    output_dir = args.output
    if not output_dir:
        output_dir = input("결과 저장 디렉토리를 입력하세요 (기본값: ./results): ") or "./results"
    
    # 입력 파일 존재 확인
    if not os.path.isfile(input_file):
        print(f"오류: 입력 파일 '{input_file}'이 존재하지 않습니다.")
        sys.exit(1)
    
    # 출력 디렉토리 생성
    create_directory(output_dir)
    
    # 데이터셋 분석
    summary = analyze_dataset(input_file, output_dir)
    
    if summary:
        # 요약 정보 출력
        print("\n======== 데이터셋 통계 요약 ========")
        print(f"전체 데이터베이스 항목 수: {summary['total']}")
        print("\n상태별 항목 수:")
        print(f"- 정상: {summary['normal']} ({summary['normal']/summary['total']*100:.2f}%)")
        print(f"- 빈 라벨: {summary['empty_label']} ({summary['empty_label']/summary['total']*100:.2f}%)")
        print(f"- 라벨 없음: {summary['no_label']} ({summary['no_label']/summary['total']*100:.2f}%)")
        print(f"- 이미지 없음: {summary['no_image']} ({summary['no_image']/summary['total']*100:.2f}%)")
        print(f"- 모두 없음: {summary['both_missing']} ({summary['both_missing']/summary['total']*100:.2f}%)")
        
        if summary['class_counts']:
            print("\n클래스별 어노테이션 수량:")
            total_annotations = sum(summary['class_counts'].values())
            for cls, count in sorted(summary['class_counts'].items()):
                print(f"- 클래스 {cls}: {count} ({count/total_annotations*100:.2f}%)")
            print(f"\n총 어노테이션 수: {total_annotations}")

if __name__ == "__main__":
    main()