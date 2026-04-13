"""
RTSP/HLS 주소 자동 스캔 및 수집
연결 가능한 CCTV 스트리밍 URL을 찾아내는 도구
"""

import cv2
import pandas as pd
from typing import List, Tuple, Dict
from dataclasses import dataclass, asdict
import time
from itertools import product


@dataclass
class WorkingStream:
    """작동하는 스트리밍 정보"""
    url: str
    resolution: str
    response_time: float
    server_ip: str
    port: str
    path: str
    stream_type: str


class RTSPScanner:
    """RTSP/HLS URL 스캐너"""
    
    def __init__(self):
        self.working_streams = []
        self.tested_count = 0
        self.success_count = 0
    
    def check_stream(self, url: str, timeout: int = 3) -> Tuple[bool, str, float]:
        """
        스트림 연결 확인
        
        Returns:
            (success, resolution, response_time)
        """
        start_time = time.time()
        
        try:
            cap = cv2.VideoCapture(url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            check_start = time.time()
            while time.time() - check_start < timeout:
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        height, width = frame.shape[:2]
                        response_time = time.time() - start_time
                        cap.release()
                        return True, f'{width}x{height}', response_time
                time.sleep(0.1)
            
            cap.release()
            return False, 'TIMEOUT', time.time() - start_time
            
        except Exception as e:
            return False, f'ERROR: {str(e)[:30]}', time.time() - start_time
    
    def scan_rtsp_pattern(self, base_ips: List[str], ports: List[str], 
                          paths: List[str], timeout: int = 3, 
                          max_test: int = None) -> List[WorkingStream]:
        """
        RTSP 패턴 스캔
        
        Args:
            base_ips: IP 주소 리스트 ['61.40.94.7', '211.34.191.215']
            ports: 포트 리스트 ['554', '1935', '8554']
            paths: 경로 패턴 리스트 ['/1/video1', '/live/1-75.stream']
            timeout: 연결 타임아웃
            max_test: 최대 테스트 개수 (None이면 전체)
        """
        
        print(f"\n{'='*70}")
        print(f"RTSP 패턴 스캔 시작")
        print(f"{'='*70}")
        print(f"IP 개수: {len(base_ips)}")
        print(f"포트 개수: {len(ports)}")
        print(f"경로 개수: {len(paths)}")
        print(f"총 조합: {len(base_ips) * len(ports) * len(paths)}개")
        print(f"{'='*70}\n")
        
        combinations = list(product(base_ips, ports, paths))
        
        if max_test:
            combinations = combinations[:max_test]
        
        for idx, (ip, port, path) in enumerate(combinations, 1):
            # RTSP URL 생성
            if ':' in ip:  # 이미 포트가 포함된 경우
                url = f'rtsp://{ip}{path}'
            else:
                url = f'rtsp://{ip}:{port}{path}'
            
            print(f"[{idx}/{len(combinations)}] Testing: {url[:60]}... ", end='', flush=True)
            
            self.tested_count += 1
            success, resolution, response_time = self.check_stream(url, timeout)
            
            if success:
                print(f"✅ {resolution} ({response_time:.2f}s)")
                self.success_count += 1
                
                working = WorkingStream(
                    url=url,
                    resolution=resolution,
                    response_time=round(response_time, 2),
                    server_ip=ip,
                    port=port,
                    path=path,
                    stream_type='RTSP'
                )
                self.working_streams.append(working)
            else:
                print(f"❌ {resolution}")
        
        return self.working_streams
    
    def scan_hls_pattern(self, base_urls: List[str], ids: List[str],
                        timeout: int = 3) -> List[WorkingStream]:
        """
        HLS 패턴 스캔
        
        Args:
            base_urls: 기본 URL ['https://strm1.spatic.go.kr/live/']
            ids: ID 리스트 ['1', '76', '100']
        """
        
        print(f"\n{'='*70}")
        print(f"HLS 패턴 스캔 시작")
        print(f"{'='*70}\n")
        
        for base_url in base_urls:
            for id_num in ids:
                # HLS URL 패턴들
                patterns = [
                    f'{base_url}{id_num}.stream/playlist.m3u8',
                    f'{base_url}{id_num}/playlist.m3u8',
                    f'{base_url}cctv{id_num}/hls.m3u8',
                ]
                
                for url in patterns:
                    print(f"[{self.tested_count + 1}] Testing: {url[:60]}... ", end='', flush=True)
                    
                    self.tested_count += 1
                    success, resolution, response_time = self.check_stream(url, timeout)
                    
                    if success:
                        print(f"✅ {resolution} ({response_time:.2f}s)")
                        self.success_count += 1
                        
                        working = WorkingStream(
                            url=url,
                            resolution=resolution,
                            response_time=round(response_time, 2),
                            server_ip=base_url.split('/')[2],
                            port='443',
                            path=url.replace(base_url, '/'),
                            stream_type='HLS'
                        )
                        self.working_streams.append(working)
                    else:
                        print(f"❌ {resolution}")
        
        return self.working_streams
    
    def generate_id_ranges(self, start: int, end: int, 
                          formats: List[str] = None) -> List[str]:
        """
        ID 범위 생성
        
        Args:
            start: 시작 번호
            end: 끝 번호
            formats: 포맷 리스트 ['{:d}', '{:02d}', '{:03d}']
        """
        if formats is None:
            formats = ['{:d}', '{:02d}', '{:03d}']
        
        ids = []
        for num in range(start, end + 1):
            for fmt in formats:
                ids.append(fmt.format(num))
        
        return list(set(ids))  # 중복 제거
    
    def save_to_excel(self, filename: str = 'working_streams.xlsx'):
        """연결된 스트림을 엑셀로 저장"""
        
        if not self.working_streams:
            print("\n❌ 저장할 작동하는 스트림이 없습니다.")
            return
        
        df = pd.DataFrame([asdict(stream) for stream in self.working_streams])
        
        # 응답 시간으로 정렬
        df = df.sort_values('response_time')
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Working_Streams', index=False)
            
            worksheet = writer.sheets['Working_Streams']
            
            # 열 너비 자동 조정
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 80)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        print(f"\n{'='*70}")
        print(f"✅ 결과가 '{filename}' 파일로 저장되었습니다.")
        print(f"{'='*70}")
        print(f"📊 스캔 통계:")
        print(f"   테스트: {self.tested_count}개")
        print(f"   성공: {self.success_count}개 ({self.success_count/self.tested_count*100:.1f}%)")
        print(f"   실패: {self.tested_count - self.success_count}개")
        print(f"{'='*70}")


def main():
    """사용 예시"""
    scanner = RTSPScanner()
    
    # === 1. RTSP 패턴 스캔 예시 ===
    
    # UTIC/공공기관 IP 주소들
    rtsp_ips = [
        '61.40.94.7',           # 인천
        '61.108.209.254',       # 과천/양주/의정부
        '218.148.33.151',       # 의왕
        '211.175.58.104',       # 경기광주
        '211.34.191.215',       # 이미지에서 본 IP
    ]
    
    # 일반적인 RTSP 포트
    rtsp_ports = [
        '554',      # 기본 RTSP
        '8554',     # 대체 RTSP
        '1935',     # RTMP/RTSP
    ]
    
    # 경로 패턴 생성 (1~100번까지 테스트)
    rtsp_paths = []
    
    # 인천 패턴: /ID/videoXX
    for i in range(1, 101):
        for ch in ['01', '51', '1']:
            rtsp_paths.append(f'/{i}/video{ch}')
    
    # 과천/양주 패턴: /CCTVID/video1
    for i in range(1, 101):
        rtsp_paths.append(f'/L06{i:03d}/video1')
        rtsp_paths.append(f'/L13{i:03d}/video1')
    
    # 의왕 패턴: /ID
    for i in range(1, 201):
        rtsp_paths.append(f'/{i}')
    
    # 경기광주 패턴: /PORT/video3
    for port in ['8554', '554', '1935']:
        rtsp_paths.append(f'/{port}/video3')
    
    # 커스텀 패턴: /live/X-XX.stream
    for i in range(1, 11):
        for j in range(1, 101):
            rtsp_paths.append(f'/live/{i}-{j}.stream')
    
    print(f"생성된 경로 패턴: {len(rtsp_paths)}개")
    
    # RTSP 스캔 실행 (최대 100개만 테스트 - 전체는 시간이 오래 걸림)
    scanner.scan_rtsp_pattern(
        base_ips=rtsp_ips,
        ports=rtsp_ports,
        paths=rtsp_paths[:50],  # 처음 50개만 테스트
        timeout=3,
        max_test=100  # 최대 100개 조합만 테스트
    )
    
    # === 2. HLS 패턴 스캔 예시 ===
    
    hls_base_urls = [
        'https://strm1.spatic.go.kr/live/',
        'https://lw.hrfco.go.kr/live/',
        'https://hi.hrfco.go.kr/live/',
    ]
    
    # ID 범위 생성 (1~100)
    hls_ids = scanner.generate_id_ranges(1, 100)
    
    scanner.scan_hls_pattern(
        base_urls=hls_base_urls,
        ids=hls_ids[:20]  # 처음 20개만 테스트
    )
    
    # === 3. 결과 저장 ===
    scanner.save_to_excel('working_cctv_streams.xlsx')
    
    # === 4. 연결된 스트림 출력 ===
    if scanner.working_streams:
        print(f"\n{'='*70}")
        print("연결된 스트림 목록:")
        print(f"{'='*70}")
        for idx, stream in enumerate(scanner.working_streams, 1):
            print(f"{idx}. {stream.url}")
            print(f"   해상도: {stream.resolution}, 응답시간: {stream.response_time}s")


if __name__ == '__main__':
    main()