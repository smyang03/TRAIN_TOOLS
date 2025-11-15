import json
import os
from pathlib import Path
import glob

def convert_custom_json_to_yolo(json_file_path, output_dir="yolo_labels", class_mapping=None):
    """
    커스텀 JSON 구조를 YOLO 포맷으로 변환하는 함수
    
    Args:
        json_file_path (str): JSON 파일 경로
        output_dir (str): 출력 디렉토리 경로  
        class_mapping (dict): 클래스 이름을 숫자 ID로 매핑하는 딕셔너리
    """
    
    # JSON 파일 로드
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 이미지 정보 추출
    source_data = data.get('Source Data Info', {})
    raw_data = data.get('Raw Data Info', {})
    learning_data = data.get('Learning Data Info', {})
    
    # 이미지 파일명 생성
    source_data_id = source_data.get('source_data_id', 'unknown')
    file_extension = source_data.get('file_extension', 'jpg')
    image_filename = f"{source_data_id}.{file_extension}"
    
    # 이미지 해상도 (기본값 사용 또는 Raw Data에서 추출)
    resolution = raw_data.get('resolution', '1920, 1080')
    if isinstance(resolution, str):
        img_width, img_height = map(int, resolution.split(', '))
    else:
        img_width, img_height = 1920, 1080  # 기본값
    
    # 텍스트 파일명 생성
    txt_filename = Path(image_filename).stem + '.txt'
    txt_filepath = os.path.join(output_dir, txt_filename)
    
    # 어노테이션 처리
    yolo_lines = []
    annotations = learning_data.get('annotations', [])
    
    # 기본 클래스 매핑 (제공되지 않은 경우)
    if class_mapping is None:
        class_mapping = {
            'car-01': 0,
            'car-02': 1,
            'car-03': 2,
            'car-04': 3,
            'car-05': 4,
            'truck': 5,
            'bus': 6,
            'motorcycle': 7,
            'bicycle': 8,
            'person': 9
        }
    
    for ann in annotations:
        class_id_str = ann.get('class_id', 'car-01')
        coord = ann.get('coord', [])
        
        # 좌표 파싱 (문자열인 경우 처리)
        if isinstance(coord, str):
            # "[193.86, 145.56, 231.34, 287.24]" 형태 처리
            coord = coord.strip('[]').split(', ')
            coord = [float(x) for x in coord]
        
        if len(coord) >= 4:
            x, y, width, height = coord[:4]
            
            # YOLO 포맷으로 변환 (정규화된 중심점 좌표와 크기)
            center_x = (x + width / 2) / img_width
            center_y = (y + height / 2) / img_height
            norm_width = width / img_width
            norm_height = height / img_height
            
            # 클래스 ID 매핑
            class_id = class_mapping.get(class_id_str, 0)
            
            # YOLO 포맷: class_id center_x center_y width height
            yolo_line = f"{class_id} {center_x:.6f} {center_y:.6f} {norm_width:.6f} {norm_height:.6f}"
            yolo_lines.append(yolo_line)
    
    # 텍스트 파일로 저장
    with open(txt_filepath, 'w') as f:
        f.write('\n'.join(yolo_lines))
    
    return txt_filepath, len(yolo_lines)


def batch_convert_custom_json_to_yolo(json_folder_path, output_dir="yolo_labels", class_mapping=None):
    """
    폴더 내 모든 JSON 파일을 YOLO 포맷으로 일괄 변환
    
    Args:
        json_folder_path (str): JSON 파일들이 있는 폴더 경로
        output_dir (str): 출력 디렉토리 경로
        class_mapping (dict): 클래스 이름을 숫자 ID로 매핑하는 딕셔너리
    """
    
    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    
    # JSON 파일 목록 가져오기
    json_pattern = os.path.join(json_folder_path, "*.json")
    json_files = glob.glob(json_pattern)
    
    if not json_files:
        print(f"JSON 파일을 찾을 수 없습니다: {json_folder_path}")
        return
    
    print(f"총 {len(json_files)}개의 JSON 파일을 발견했습니다.")
    
    # 클래스 이름 수집 (자동 매핑 생성용)
    all_classes = set()
    if class_mapping is None:
        print("클래스 매핑을 자동으로 생성합니다...")
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                annotations = data.get('Learning Data Info', {}).get('annotations', [])
                for ann in annotations:
                    class_id = ann.get('class_id', '')
                    if class_id:
                        all_classes.add(class_id)
            except Exception as e:
                print(f"클래스 수집 중 오류 발생 ({json_file}): {e}")
        
        # 자동 클래스 매핑 생성
        class_mapping = {class_name: idx for idx, class_name in enumerate(sorted(all_classes))}
        print(f"발견된 클래스: {list(class_mapping.keys())}")
    
    # 각 JSON 파일 변환
    converted_count = 0
    total_annotations = 0
    
    for json_file in json_files:
        try:
            txt_filepath, ann_count = convert_custom_json_to_yolo(
                json_file, output_dir, class_mapping
            )
            print(f"변환 완료: {os.path.basename(json_file)} -> {os.path.basename(txt_filepath)} ({ann_count}개 어노테이션)")
            converted_count += 1
            total_annotations += ann_count
            
        except Exception as e:
            print(f"변환 실패 ({os.path.basename(json_file)}): {e}")
    
    print(f"\n=== 변환 완료 ===")
    print(f"성공: {converted_count}/{len(json_files)}개 파일")
    print(f"총 어노테이션: {total_annotations}개")
    print(f"출력 디렉토리: {output_dir}")
    
    # 클래스 정보 파일 생성
    classes_file = os.path.join(output_dir, 'classes.txt')
    with open(classes_file, 'w', encoding='utf-8') as f:
        for class_name in sorted(class_mapping.keys()):
            f.write(f"{class_name}\n")
    print(f"클래스 정보 파일 생성: {classes_file}")
    
    return class_mapping


# 사용 예시
if __name__ == "__main__":
    # JSON 파일들이 있는 폴더 경로
    json_folder_path = "path/to/your/json/files"  # 실제 폴더 경로로 변경
    output_directory = "yolo_labels"              # 출력 디렉토리
    
    # 커스텀 클래스 매핑 (선택사항)
    custom_class_mapping = {
        'car-01': 0,
        'car-02': 1,
        'car-03': 2,
        'car-04': 3,
        'car-05': 4,
        'truck': 5,
        'bus': 6,
        'motorcycle': 7,
        'bicycle': 8,
        'person': 9
    }
    
    # 폴더가 존재하는지 확인
    if os.path.exists(json_folder_path):
        # 일괄 변환 실행
        class_mapping = batch_convert_custom_json_to_yolo(
            json_folder_path, 
            output_directory, 
            custom_class_mapping  # None으로 설정하면 자동 매핑 생성
        )
        
        print("\n=== 최종 클래스 매핑 ===")
        for class_name, class_id in class_mapping.items():
            print(f"{class_id}: {class_name}")
    else:
        print(f"폴더를 찾을 수 없습니다: {json_folder_path}")
        print("폴더 경로를 확인하고 다시 시도해주세요.")