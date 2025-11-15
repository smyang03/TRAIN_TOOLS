#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from pathlib import Path

def create_yolo_list(input_dir, output_file):
    """
    입력 폴더와 모든 하위 폴더에서 .jpg 파일을 찾아 절대 경로를 출력 파일에 저장합니다.
    
    Args:
        input_dir (str): 검색할 입력 폴더 경로
        output_file (str): 결과를 저장할 출력 파일 경로
    """
    # 입력 폴더 경로를 절대 경로로 변환
    input_path = Path(input_dir).resolve()
    
    # 입력 폴더가 존재하는지 확인
    if not input_path.is_dir():
        print(f"오류: 입력 폴더 '{input_dir}'가 존재하지 않습니다.")
        return False
    
    # .jpg 파일 찾기
    jpg_files = list(input_path.glob('**/*.jpg'))
    
    # 파일 경로 저장
    with open(output_file, 'w') as f:
        for jpg_file in jpg_files:
            f.write(f"{jpg_file.absolute()}\n")
    
    print(f"완료: {len(jpg_files)}개의 .jpg 파일 경로가 '{output_file}'에 저장되었습니다.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='YOLO 학습을 위한 이미지 경로 리스트 생성기')
    parser.add_argument('input_dir', help='검색할 입력 폴더 경로')
    parser.add_argument('output_file', help='결과를 저장할 출력 파일 경로')
    
    args = parser.parse_args()
    
    create_yolo_list(args.input_dir, args.output_file)