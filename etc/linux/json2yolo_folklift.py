#!/usr/bin/env python3
"""
JSON to YOLO 형식 변환기
사용법: python json_to_yolo.py <입력폴더> <출력폴더> [옵션]
"""

import json
import os
import sys
import argparse
from pathlib import Path
import glob
from typing import Dict, List, Tuple, Optional


def convert_xywh_to_yolo(coord: List[float], img_width: int, img_height: int, debug: bool = False) -> Tuple[float, float, float, float]:
    """
    [x, y, width, height] 형식을 YOLO 형식으로 변환 (x,y는 좌상단 좌표)
    
    Args:
        coord: [x, y, width, height] 좌표 리스트 (x,y는 좌상단)
        img_width: 이미지 너비
        img_height: 이미지 높이
        debug: 디버깅 출력 여부
    
    Returns:
        (norm_center_x, norm_center_y, norm_width, norm_height): YOLO 정규화된 좌표
    """
    
    if len(coord) < 4:
        raise ValueError(f"좌표가 4개 미만입니다: {coord}")
    
    x, y, width, height = coord[:4]
    
    if debug:
        print(f"원본 좌표: 좌상단({x}, {y}), 크기({width} x {height})")
        print(f"이미지 크기: {img_width} x {img_height}")
    
    # 유효성 검사
    if width <= 0 or height <= 0:
        raise ValueError(f"잘못된 박스 크기: width={width}, height={height}")
    
    # 중심점 계산
    center_x = x + width / 2
    center_y = y + height / 2
    
    # 박스 경계 계산 (확인용)
    left = x
    top = y
    right = x + width
    bottom = y + height
    
    if debug:
        print(f"중심점: ({center_x:.1f}, {center_y:.1f})")
        print(f"박스 경계: ({left:.1f}, {top:.1f}) → ({right:.1f}, {bottom:.1f})")
    
    # 박스가 이미지 경계를 벗어나는지 확인
    if left < 0 or top < 0 or right > img_width or bottom > img_height:
        if debug:
            print(f"⚠️ 경고: 박스가 이미지 경계를 벗어남")
            print(f"   이미지: 0~{img_width} x 0~{img_height}")
            print(f"   박스: ({left:.1f}, {top:.1f}) → ({right:.1f}, {bottom:.1f})")
    
    # YOLO 형식으로 정규화
    norm_center_x = center_x / img_width
    norm_center_y = center_y / img_height
    norm_width = width / img_width
    norm_height = height / img_height
    
    # 정규화 값 범위 검사
    if not (0 <= norm_center_x <= 1 and 0 <= norm_center_y <= 1 and 
            0 < norm_width <= 1 and 0 < norm_height <= 1):
        if debug:
            print(f"⚠️ 경고: 정규화 값이 범위를 벗어남")
            print(f"center_x: {norm_center_x:.6f}, center_y: {norm_center_y:.6f}")
            print(f"width: {norm_width:.6f}, height: {norm_height:.6f}")
    
    if debug:
        print(f"YOLO 정규화: center({norm_center_x:.6f}, {norm_center_y:.6f}), size({norm_width:.6f}, {norm_height:.6f})")
    
    return norm_center_x, norm_center_y, norm_width, norm_height


def convert_json_to_yolo(json_file_path: str, output_dir: str, class_mapping: Optional[Dict[str, int]] = None, debug: bool = False) -> Tuple[str, int]:
    """
    단일 JSON 파일을 YOLO 포맷으로 변환
    
    Args:
        json_file_path: JSON 파일 경로
        output_dir: 출력 디렉토리 경로  
        class_mapping: 클래스 이름을 숫자 ID로 매핑하는 딕셔너리
        debug: 디버깅 출력 여부
    
    Returns:
        (출력파일경로, 어노테이션개수): 변환 결과
    """
    
    try:
        # JSON 파일 로드
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if debug:
            print(f"\n=== 변환 중: {os.path.basename(json_file_path)} ===")
        
        # 이미지 정보 추출 (다양한 키 형태 지원)
        source_data = (data.get('Source data Info.') or 
                      data.get('Source Data Info.') or 
                      data.get('Source Data Info') or {})
        
        raw_data = (data.get('Raw data Info.') or 
                   data.get('Raw Data Info.') or 
                   data.get('Raw Data Info') or {})
        
        learning_data = (data.get('Learning data info.') or 
                        data.get('Learning Data info.') or 
                        data.get('Learning Data Info') or {})
        
        # 이미지 파일명 생성
        source_data_id = (source_data.get('source_data_ID') or 
                         source_data.get('source_data_id') or 'unknown')
        file_extension = source_data.get('file_extension', 'jpg')
        image_filename = f"{source_data_id}.{file_extension}"
        
        # 이미지 해상도 처리
        resolution = raw_data.get('resolution', [1920, 1080])
        if isinstance(resolution, list) and len(resolution) >= 2:
            img_width, img_height = resolution[0], resolution[1]
        elif isinstance(resolution, str):
            img_width, img_height = map(int, resolution.split(', '))
        else:
            img_width, img_height = 1920, 1080  # 기본값
        
        if debug:
            print(f"이미지: {image_filename}, 해상도: {img_width}x{img_height}")
        
        # 텍스트 파일명 생성
        txt_filename = Path(image_filename).stem + '.txt'
        txt_filepath = os.path.join(output_dir, txt_filename)
        
        # 어노테이션 처리
        yolo_lines = []
        annotations = (learning_data.get('annotation') or 
                      learning_data.get('annotations') or [])
        
        if debug:
            print(f"어노테이션 개수: {len(annotations)}")
        
        for i, ann in enumerate(annotations):
            class_id_str = ann.get('class_id', 'unknown')
            coord = ann.get('coord', [])
            
            # 좌표 파싱 (문자열인 경우 처리)
            if isinstance(coord, str):
                coord = coord.strip('[]').split(', ')
                coord = [float(x) for x in coord]
            
            if isinstance(coord, list):
                # 중첩 리스트 해제
                while len(coord) == 1 and isinstance(coord[0], list):
                    coord = coord[0]

                if len(coord) >= 4 and all(isinstance(c, (int, float)) for c in coord[:4]):
                    try:
                        # 올바른 좌표 변환 ([x, y, w, h] -> YOLO)
                        norm_cx, norm_cy, norm_w, norm_h = convert_xywh_to_yolo(
                            coord, img_width, img_height, debug=debug
                        )
                        
                        class_id = class_mapping.get(class_id_str, 0) if class_mapping else 0
                        yolo_line = f"{class_id} {norm_cx:.6f} {norm_cy:.6f} {norm_w:.6f} {norm_h:.6f}"
                        yolo_lines.append(yolo_line)
                        
                        if debug:
                            print(f"  {i+1}: {class_id_str} -> {yolo_line}")
                        
                    except Exception as e:
                        print(f"⚠️ 좌표 변환 오류 ({class_id_str}): {e}")
                else:
                    print(f"⚠️ 좌표 형식 오류 (coord={coord}) in {json_file_path}")
        
        # 출력 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        
        # 텍스트 파일로 저장
        with open(txt_filepath, 'w') as f:
            f.write('\n'.join(yolo_lines))
        
        return txt_filepath, len(yolo_lines)
        
    except Exception as e:
        print(f"❌ 파일 변환 실패 ({os.path.basename(json_file_path)}): {e}")
        return "", 0


def batch_convert_json_to_yolo(json_folder_path: str, output_dir: str, class_mapping: Optional[Dict[str, int]] = None, debug: bool = False) -> Dict[str, int]:
    """
    폴더 내 모든 JSON 파일을 YOLO 포맷으로 일괄 변환
    
    Args:
        json_folder_path: JSON 파일들이 있는 폴더 경로
        output_dir: 출력 디렉토리 경로
        class_mapping: 클래스 이름을 숫자 ID로 매핑하는 딕셔너리
        debug: 디버깅 출력 여부
    
    Returns:
        변환 통계 딕셔너리
    """
    
    if not os.path.exists(json_folder_path):
        print(f"❌ 입력 폴더를 찾을 수 없습니다: {json_folder_path}")
        return {}
    
    # JSON 파일 목록 가져오기
    json_pattern = os.path.join(json_folder_path, "*.json")
    json_files = glob.glob(json_pattern)
    
    if not json_files:
        print(f"❌ JSON 파일을 찾을 수 없습니다: {json_folder_path}")
        return {}
    
    print(f"📁 총 {len(json_files)}개의 JSON 파일을 발견했습니다.")
    
    # 클래스 이름 수집 (자동 매핑 생성용)
    if class_mapping is None:
        print("🔍 클래스 매핑을 자동으로 생성합니다...")
        all_classes = set()
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                learning_data = (data.get('Learning data info.') or 
                               data.get('Learning Data info.') or 
                               data.get('Learning Data Info') or {})
                
                annotations = (learning_data.get('annotation') or 
                             learning_data.get('annotations') or [])
                
                for ann in annotations:
                    class_id = ann.get('class_id', '')
                    if class_id:
                        all_classes.add(class_id)
            except Exception as e:
                if debug:
                    print(f"클래스 수집 중 오류 발생 ({json_file}): {e}")
        
        # 자동 클래스 매핑 생성
        class_mapping = {class_name: idx for idx, class_name in enumerate(sorted(all_classes))}
        print(f"📋 발견된 클래스 ({len(class_mapping)}개): {list(class_mapping.keys())}")
    
    # 각 JSON 파일 변환
    converted_count = 0
    total_annotations = 0
    failed_files = []
    
    print(f"\n🚀 변환 시작...")
    
    for i, json_file in enumerate(json_files):
        try:
            txt_filepath, ann_count = convert_json_to_yolo(
                json_file, output_dir, class_mapping, debug=debug
            )
            
            if ann_count > 0:
                if not debug and (i + 1) % 100 == 0:
                    print(f"   진행상황: {i + 1}/{len(json_files)} ({(i + 1)/len(json_files)*100:.1f}%)")
                elif debug or (i + 1) <= 10:
                    print(f"✅ 변환 완료: {os.path.basename(json_file)} -> {os.path.basename(txt_filepath)} ({ann_count}개 어노테이션)")
                
                converted_count += 1
                total_annotations += ann_count
            else:
                failed_files.append(os.path.basename(json_file))
            
        except Exception as e:
            failed_files.append(f"{os.path.basename(json_file)}: {e}")
            if debug:
                print(f"❌ 변환 실패 ({os.path.basename(json_file)}): {e}")
    
    # 결과 요약
    print(f"\n{'='*60}")
    print(f"🎉 변환 완료!")
    print(f"✅ 성공: {converted_count}/{len(json_files)}개 파일")
    print(f"📊 총 어노테이션: {total_annotations}개")
    print(f"📂 출력 디렉토리: {output_dir}")
    
    if failed_files:
        print(f"❌ 실패: {len(failed_files)}개")
        if len(failed_files) <= 10:
            for fail in failed_files:
                print(f"   {fail}")
        else:
            print(f"   처음 10개: {failed_files[:10]}")
    
    # 클래스 정보 파일 생성
    classes_file = os.path.join(output_dir, 'classes.txt')
    with open(classes_file, 'w', encoding='utf-8') as f:
        for class_name in sorted(class_mapping.keys()):
            f.write(f"{class_name}\n")
    print(f"📄 클래스 정보 파일 생성: {classes_file}")
    
    # 클래스 매핑 파일 생성
    mapping_file = os.path.join(output_dir, 'class_mapping.json')
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(class_mapping, f, indent=2, ensure_ascii=False)
    print(f"📄 클래스 매핑 파일 생성: {mapping_file}")
    
    return {
        'total_files': len(json_files),
        'converted_files': converted_count,
        'failed_files': len(failed_files),
        'total_annotations': total_annotations,
        'class_mapping': class_mapping
    }


def create_default_class_mapping() -> Dict[str, int]:
    """기본 클래스 매핑 생성"""
    return {
        # 작업자 관련
        'WO-01': 0, 'WO-02': 1, 'WO-03': 2, 'WO-04': 3, 'WO-05': 4,
        'WO-06': 5, 'WO-07': 6, 'WO-08': 7,
        
        # 안전장비/상황 관련
        'SO-01': 8, 'SO-02': 9, 'SO-03': 10, 'SO-04': 11, 'SO-05': 12,
        'SO-06': 13, 'SO-07': 14, 'SO-08': 15, 'SO-09': 16, 'SO-10': 17,
        'SO-11': 18, 'SO-12': 19, 'SO-13': 20, 'SO-14': 21, 'SO-15': 22,
        'SO-16': 23, 'SO-17': 24, 'SO-18': 25, 'SO-19': 26, 'SO-20': 27,
        'SO-21': 28, 'SO-22': 29, 'SO-23': 30,
        
        # 기타
        'car-01': 31, 'car-02': 32, 'car-03': 33, 'car-04': 34, 'car-05': 35,
        'truck': 36, 'bus': 37, 'motorcycle': 38, 'bicycle': 39, 'person': 40
    }


def main():
    """메인 함수 - 명령행 인자 처리"""
    
    parser = argparse.ArgumentParser(
        description='JSON 어노테이션을 YOLO 형식으로 변환',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
사용 예시:
  python json_to_yolo.py /path/to/json/folder /path/to/output/folder
  python json_to_yolo.py ./labels_json ./yolo_labels --debug
  python json_to_yolo.py ./labels_json ./yolo_labels --mapping custom_mapping.json
        '''
    )
    
    parser.add_argument('input_folder', 
                       help='JSON 파일들이 있는 입력 폴더 경로')
    
    parser.add_argument('output_folder', 
                       help='YOLO 라벨 파일들을 저장할 출력 폴더 경로')
    
    parser.add_argument('--mapping', '-m',
                       help='커스텀 클래스 매핑 JSON 파일 경로')
    
    parser.add_argument('--debug', '-d', action='store_true',
                       help='디버깅 정보 출력')
    
    parser.add_argument('--default-mapping', action='store_true',
                       help='기본 클래스 매핑 사용 (자동 생성 비활성화)')
    
    args = parser.parse_args()
    
    # 입력 유효성 검사
    if not os.path.exists(args.input_folder):
        print(f"❌ 입력 폴더를 찾을 수 없습니다: {args.input_folder}")
        sys.exit(1)
    
    # 클래스 매핑 로드
    class_mapping = None
    
    if args.mapping:
        try:
            with open(args.mapping, 'r', encoding='utf-8') as f:
                class_mapping = json.load(f)
            print(f"📋 커스텀 클래스 매핑 로드: {args.mapping}")
        except Exception as e:
            print(f"❌ 클래스 매핑 파일 로드 실패: {e}")
            sys.exit(1)
    elif args.default_mapping:
        class_mapping = create_default_class_mapping()
        print("📋 기본 클래스 매핑 사용")
    
    # 변환 실행
    print(f"📁 입력 폴더: {args.input_folder}")
    print(f"📁 출력 폴더: {args.output_folder}")
    
    result = batch_convert_json_to_yolo(
        json_folder_path=args.input_folder,
        output_dir=args.output_folder,
        class_mapping=class_mapping,
        debug=args.debug
    )
    
    if result.get('converted_files', 0) > 0:
        print(f"\n🎉 변환 성공! {result['converted_files']}개 파일 처리 완료")
    else:
        print(f"\n❌ 변환 실패!")
        sys.exit(1)


if __name__ == "__main__":
    main()