import os
import shutil
import argparse
import time
from pathlib import Path

def find_paired_files(jpeg_folder, json_folder):
    """JPEGImages와 label_json 폴더에서 같은 이름의 파일 쌍 찾기"""
    print("파일 쌍 검색 시작...")
    start_time = time.time()
    
    jpeg_path = Path(jpeg_folder)
    json_path = Path(json_folder)
    
    if not jpeg_path.exists():
        print(f"에러: JPEGImages 폴더가 없습니다: {jpeg_folder}")
        return []
    
    if not json_path.exists():
        print(f"에러: label_json 폴더가 없습니다: {json_folder}")
        return []
    
    print(f"JPEGImages 폴더: {jpeg_folder}")
    print(f"label_json 폴더: {json_folder}")
    
    # JPEG 파일들 수집
    print("JPEG 파일 검색 중...")
    jpeg_files = {}
    jpeg_count = 0
    for jpeg_file in jpeg_path.rglob("*.jpg"):
        base_name = jpeg_file.stem  # 확장자 제거한 파일명
        jpeg_files[base_name] = str(jpeg_file)
        jpeg_count += 1
        if jpeg_count % 1000 == 0:
            print(f"  {jpeg_count}개 JPEG 파일 발견...")
    
    print(f"총 JPEG 파일: {jpeg_count}개")
    
    # JSON 파일들 수집
    print("JSON 파일 검색 중...")
    json_files = {}
    json_count = 0
    for json_file in json_path.rglob("*.json"):
        base_name = json_file.stem  # 확장자 제거한 파일명
        json_files[base_name] = str(json_file)
        json_count += 1
        if json_count % 1000 == 0:
            print(f"  {json_count}개 JSON 파일 발견...")
    
    print(f"총 JSON 파일: {json_count}개")
    
    # 같은 이름을 가진 파일 쌍 찾기
    print("파일 쌍 매칭 중...")
    paired_files = []
    
    for base_name in jpeg_files:
        if base_name in json_files:
            paired_files.append({
                'name': base_name,
                'jpeg': jpeg_files[base_name],
                'json': json_files[base_name]
            })
    
    search_time = time.time() - start_time
    print(f"파일 쌍 검색 완료: {search_time:.1f}초")
    print(f"매칭된 파일 쌍: {len(paired_files)}개")
    print("=" * 50)
    
    return paired_files

def select_diverse_samples(paired_files, target_count, sampling_method='uniform'):
    """다양한 분포로 파일 샘플 선택"""
    if len(paired_files) <= target_count:
        print(f"전체 파일 개수({len(paired_files)})가 목표 개수({target_count})보다 적음")
        return paired_files
    
    print(f"샘플링 방법: {sampling_method}")
    print(f"전체 {len(paired_files)}개 중 {target_count}개 선택")
    
    # 파일명 기준으로 정렬 (일관된 순서)
    paired_files.sort(key=lambda x: x['name'])
    
    if sampling_method == 'uniform':
        # 균일한 간격으로 선택
        step = len(paired_files) / target_count
        selected = []
        for i in range(target_count):
            index = int(i * step)
            if index < len(paired_files):
                selected.append(paired_files[index])
        return selected
    
    elif sampling_method == 'distributed':
        # 전체를 구간으로 나누어 각 구간에서 선택
        section_size = len(paired_files) // target_count
        remainder = len(paired_files) % target_count
        
        selected = []
        start_idx = 0
        
        for i in range(target_count):
            # 나머지를 앞쪽 구간들에 분배
            current_section_size = section_size + (1 if i < remainder else 0)
            end_idx = start_idx + current_section_size
            
            if end_idx > start_idx:
                # 각 구간의 중간 지점에서 선택
                mid_idx = start_idx + current_section_size // 2
                if mid_idx < len(paired_files):
                    selected.append(paired_files[mid_idx])
            
            start_idx = end_idx
        
        return selected
    
    else:  # random
        import random
        random.seed(42)  # 재현 가능한 랜덤
        return random.sample(paired_files, target_count)

def copy_paired_files(selected_files, output_folder):
    """선택된 파일 쌍들을 목표 폴더로 복사"""
    print(f"파일 복사 시작... (총 {len(selected_files)}쌍)")
    copy_start = time.time()
    
    # 출력 폴더 생성
    jpeg_output = os.path.join(output_folder, 'JPEGImages')
    json_output = os.path.join(output_folder, 'label_json')
    
    os.makedirs(jpeg_output, exist_ok=True)
    os.makedirs(json_output, exist_ok=True)
    
    print(f"JPEG 출력 폴더: {jpeg_output}")
    print(f"JSON 출력 폴더: {json_output}")
    
    success_count = 0
    
    for i, file_pair in enumerate(selected_files, 1):
        try:
            # JPEG 파일 복사
            jpeg_filename = os.path.basename(file_pair['jpeg'])
            jpeg_dest = os.path.join(jpeg_output, jpeg_filename)
            shutil.copy2(file_pair['jpeg'], jpeg_dest)
            
            # JSON 파일 복사
            json_filename = os.path.basename(file_pair['json'])
            json_dest = os.path.join(json_output, json_filename)
            shutil.copy2(file_pair['json'], json_dest)
            
            success_count += 1
            
            # 진행률 표시
            if i % 100 == 0 or i == len(selected_files):
                elapsed = time.time() - copy_start
                progress = i / len(selected_files) * 100
                if i > 0:
                    estimated_total = elapsed * len(selected_files) / i
                    remaining = estimated_total - elapsed
                    print(f"  진행률: {i}/{len(selected_files)} ({progress:.1f}%) "
                          f"- 경과: {elapsed:.1f}초, 예상 잔여: {remaining:.1f}초")
        
        except Exception as e:
            print(f"  에러: {file_pair['name']} 복사 실패 - {e}")
            continue
    
    copy_time = time.time() - copy_start
    print(f"복사 완료: {copy_time:.1f}초")
    print(f"성공: {success_count}쌍 ({success_count * 2}개 파일)")
    
    return success_count

def main():
    start_time = time.time()
    
    # 명령줄 인자 파싱
    parser = argparse.ArgumentParser(description='JPEGImages와 label_json 폴더에서 같은 이름의 파일 쌍을 복사합니다.')
    parser.add_argument('--input', required=True, help='입력 루트 폴더 (JPEGImages, label_json 포함)')
    parser.add_argument('--output', required=True, help='출력 폴더')
    parser.add_argument('--count', type=int, required=True, help='복사할 파일 쌍 개수')
    parser.add_argument('--sampling', choices=['uniform', 'distributed', 'random'], 
                        default='distributed', help='샘플링 방법')
    
    args = parser.parse_args()
    
    # 입력 폴더 설정
    jpeg_folder = os.path.join(args.input, 'JPEGImages')
    json_folder = os.path.join(args.input, 'label_json')
    
    # 설정 출력
    print("=" * 60)
    print(f"시작 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"입력 폴더: {args.input}")
    print(f"JPEGImages: {jpeg_folder}")
    print(f"label_json: {json_folder}")
    print(f"출력 폴더: {args.output}")
    print(f"목표 개수: {args.count}쌍")
    print(f"샘플링 방법: {args.sampling}")
    print("=" * 60)
    
    # 1. 파일 쌍 찾기
    paired_files = find_paired_files(jpeg_folder, json_folder)
    
    if not paired_files:
        print("매칭되는 파일 쌍이 없습니다.")
        return
    
    # 2. 샘플 선택
    print("샘플 선택 중...")
    selected_files = select_diverse_samples(paired_files, args.count, args.sampling)
    print(f"선택된 파일 쌍: {len(selected_files)}개")
    print("=" * 50)
    
    # 3. 파일 복사
    success_count = copy_paired_files(selected_files, args.output)
    
    # 4. 결과 출력
    total_time = time.time() - start_time
    print("=" * 60)
    print("작업 완료!")
    print(f"복사된 파일 쌍: {success_count}개")
    print(f"총 파일 개수: {success_count * 2}개 (JPEG + JSON)")
    print(f"총 실행 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
    print("=" * 60)

if __name__ == "__main__":
    main()