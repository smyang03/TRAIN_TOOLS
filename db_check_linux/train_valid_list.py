import os
import argparse

def create_path_list(base_path, output_dir="path_lists"):
    """
    train과 valid 폴더의 JPEGImages 경로를 각각 txt 파일로 저장
    
    Args:
        base_path (str): train과 valid 폴더가 있는 기본 경로
        output_dir (str): 출력 txt 파일들이 저장될 폴더
    """
    
    # 출력 폴더 생성
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # train과 valid 폴더 처리
    for folder_name in ['train', 'valid']:
        folder_path = os.path.join(base_path, folder_name)
        jpeg_images_path = os.path.join(folder_path, 'JPEGImages')
        
        # JPEGImages 폴더가 존재하는지 확인
        if not os.path.exists(jpeg_images_path):
            print(f"Warning: {jpeg_images_path} 폴더가 존재하지 않습니다.")
            continue
        
        # JPEGImages 폴더 내의 모든 이미지 파일 찾기
        image_paths = []
        for file_name in os.listdir(jpeg_images_path):
            if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                full_path = os.path.join(jpeg_images_path, file_name)
                # 경로를 절대 경로로 변환
                absolute_path = os.path.abspath(full_path)
                image_paths.append(absolute_path)
        
        # 경로 정렬 (선택사항)
        image_paths.sort()
        
        # txt 파일로 저장
        output_file = os.path.join(output_dir, f"{folder_name}_images.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            for path in image_paths:
                f.write(path + '\n')
        
        print(f"{folder_name} 폴더: {len(image_paths)}개 이미지 경로를 {output_file}에 저장했습니다.")

# 사용 예시
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='JPEGImages 경로를 txt 파일로 추출')
    parser.add_argument('--base_path', '-b', required=True, 
                       help='train과 valid 폴더가 있는 기본 경로')
    parser.add_argument('--output_path', '-o', default='path_lists',
                       help='출력 txt 파일들이 저장될 폴더 (기본값: path_lists)')
    
    args = parser.parse_args()
    
    # 경로 리스트 생성
    create_path_list(args.base_path, args.output_path)
    
    print("작업 완료!")