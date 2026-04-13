"""
데이터 관리 모듈 - 데이터 로딩, 캐싱, 파일 I/O, 겹침 분석
"""
import os
import time
import gc
import threading
import queue
from collections import OrderedDict, defaultdict
from utils import (
    detect_file_encoding, convert_jpegimages_to_labels,
    read_label_file_lines, calculate_iou
)


class DataManager:
    """데이터 로딩, 캐싱, 라벨 데이터 관리를 담당하는 클래스"""

    def __init__(self, cache_limit=2000, page_size=350):
        self.cache_limit = cache_limit
        self.page_size = page_size

        # 데이터 저장소
        self.image_paths = []
        self.labels = []
        self.labelsdata = [[] for _ in range(100)]
        self.labelsdata_sets = [set() for _ in range(100)]

        # 캐시 시스템 (OrderedDict 기반 LRU)
        self.label_cache = OrderedDict()
        self.image_cache = OrderedDict()
        self.overlap_cache = {}
        self.file_encoding_cache = {}

        # 캐시 통계
        self.cache_hits = {'label': 0, 'image': 0}
        self.cache_misses = {'label': 0, 'image': 0}

        # 작업 상태 추적
        self.modified_labels = {
            'deleted': set(),
            'masking_changed': set(),
            'class_changed': set()
        }

        # 페이지네이션
        self.current_page = 0
        self.total_pages = 0

        # 상태 플래그
        self.data_loading = False

        self._setup_performance()

    def _setup_performance(self):
        """성능 최적화 설정"""
        try:
            import psutil
            total_mem_gb = psutil.virtual_memory().total / (1024 ** 3)
            if total_mem_gb < 4:
                self.page_size = 100
                self.cache_limit = 500
            elif total_mem_gb < 8:
                self.page_size = 200
                self.cache_limit = 1000
            elif total_mem_gb < 16:
                self.page_size = 350
                self.cache_limit = 2000
            else:
                self.page_size = 500
                self.cache_limit = 5000
        except ImportError:
            self.page_size = 200
            self.cache_limit = 1000
        gc.set_threshold(100, 5, 5)

    def reset(self, file_path):
        """새 파일 로딩 시 모든 데이터를 초기화합니다."""
        self.image_paths = []
        self.labels = []
        self.labelsdata = [[] for _ in range(100)]
        self.labelsdata_sets = [set() for _ in range(100)]
        self.current_page = 0
        self.total_pages = 0
        self.overlap_cache = {}
        self.modified_labels = {
            'deleted': set(),
            'masking_changed': set(),
            'class_changed': set()
        }
        gc.collect()

    def rebuild_class_lookup(self):
        """Rebuild fast class-to-label lookup sets from labelsdata."""
        self.labelsdata_sets = [set(paths) for paths in self.labelsdata]

    # ── 캐시 관리 ──

    def get_label_data(self, label_path):
        """라벨 파일 데이터를 캐시에서 가져오거나 파일에서 읽습니다."""
        if not os.path.isfile(label_path):
            return []

        if label_path in self.label_cache:
            try:
                mod_time = os.path.getmtime(label_path)
                cached_time = self.label_cache[label_path]['timestamp']
                if mod_time <= cached_time:
                    self.label_cache.move_to_end(label_path)
                    self.cache_hits['label'] += 1
                    return self.label_cache[label_path]['data']
            except OSError:
                pass

        self.cache_misses['label'] += 1
        lines = read_label_file_lines(label_path)

        # 캐시에 저장
        if len(self.label_cache) >= self.cache_limit:
            self.label_cache.popitem(last=False)
        try:
            self.label_cache[label_path] = {
                'data': lines,
                'timestamp': os.path.getmtime(label_path),
            }
        except OSError:
            pass
        return lines

    def invalidate_label_cache(self, label_path):
        """특정 라벨 파일의 모든 캐시를 무효화합니다."""
        if label_path in self.label_cache:
            del self.label_cache[label_path]

        # 겹침 캐시 무효화
        keys_to_remove = [k for k in self.overlap_cache if isinstance(k, tuple) and k[0] == label_path]
        for key in keys_to_remove:
            del self.overlap_cache[key]

        if label_path in self.file_encoding_cache:
            del self.file_encoding_cache[label_path]

    def invalidate_image_cache(self, img_path):
        """특정 이미지의 캐시를 무효화합니다."""
        keys_to_remove = [k for k in self.image_cache if isinstance(k, str) and img_path in k]
        for key in keys_to_remove:
            del self.image_cache[key]

    def get_cached_image(self, img_path, size=200):
        """캐시에서 이미지를 가져옵니다."""
        cache_key = f"{img_path}_{size}"
        if cache_key in self.image_cache:
            self.image_cache.move_to_end(cache_key)
            self.cache_hits['image'] += 1
            return self.image_cache[cache_key]
        self.cache_misses['image'] += 1
        return None

    def cache_image(self, img_path, image, size=200):
        """이미지를 캐시에 저장합니다."""
        cache_key = f"{img_path}_{size}"
        if len(self.image_cache) >= self.cache_limit:
            self.image_cache.popitem(last=False)
        self.image_cache[cache_key] = image

    def reset_overlap_cache(self):
        """겹침 캐시를 초기화합니다."""
        self.overlap_cache = {}

    def perform_memory_cleanup(self):
        """메모리 정리 작업 수행"""
        target_size = int(self.cache_limit * 0.7)
        while len(self.label_cache) > target_size:
            self.label_cache.popitem(last=False)
        while len(self.image_cache) > target_size:
            self.image_cache.popitem(last=False)
        gc.collect()

    # ── 데이터 로딩 ──

    def load_file_list(self, file_path):
        """
        텍스트 파일에서 이미지/라벨 경로 목록을 로드합니다.
        Returns:
            tuple: (image_paths, label_paths, total_lines)
        """
        file_encoding = detect_file_encoding(file_path)
        with open(file_path, encoding=file_encoding) as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        image_paths = []
        label_paths = []
        for line in lines:
            img_path = line
            label_path = convert_jpegimages_to_labels(line)
            image_paths.append(img_path)
            label_paths.append(label_path)

        return image_paths, label_paths, len(lines)

    def scan_classes(self, label_paths, progress_callback=None):
        """
        라벨 파일들에서 클래스 정보를 수집합니다.
        Args:
            label_paths: 라벨 파일 경로 목록
            progress_callback: (processed, total, valid, invalid) 콜백
        Returns:
            tuple: (labelsdata, sorted_classes, valid_files, invalid_files)
        """
        labelsdata_new = [[] for _ in range(100)]
        classes = set()
        valid_files = 0
        invalid_files = 0

        task_queue_local = queue.Queue()
        result_queue_local = queue.Queue()

        for lp in label_paths:
            task_queue_local.put(lp)

        def worker():
            while True:
                try:
                    lp = task_queue_local.get(timeout=1)
                except queue.Empty:
                    break
                file_classes = set()
                file_labels = defaultdict(list)
                file_valid = False

                if not os.path.isfile(lp):
                    result_queue_local.put((lp, file_classes, file_labels, file_valid))
                    task_queue_local.task_done()
                    continue
                try:
                    lines = read_label_file_lines(lp)
                    for line in lines:
                        parts = line.split()
                        if not parts:
                            continue
                        try:
                            ci = int(float(parts[0]))
                            if 0 <= ci < 100:
                                file_classes.add(parts[0])
                                file_labels[ci].append(lp)
                                file_valid = True
                        except (ValueError, IndexError):
                            continue
                except Exception:
                    pass
                result_queue_local.put((lp, file_classes, file_labels, file_valid))
                task_queue_local.task_done()

        num_threads = min(20, max(4, os.cpu_count() or 4))
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)

        processed = 0
        total = len(label_paths)

        while True:
            try:
                lp, file_classes, file_labels, file_valid = result_queue_local.get(timeout=0.1)
                result_queue_local.task_done()
                classes.update(file_classes)
                for ci, paths in file_labels.items():
                    labelsdata_new[ci].extend(paths)
                processed += 1
                if file_valid:
                    valid_files += 1
                else:
                    invalid_files += 1
                if progress_callback and processed % 50 == 0:
                    progress_callback(processed, total, valid_files, invalid_files)
            except queue.Empty:
                if task_queue_local.empty() and all(not t.is_alive() for t in threads):
                    # 남은 결과 처리
                    try:
                        while True:
                            lp, file_classes, file_labels, file_valid = result_queue_local.get_nowait()
                            result_queue_local.task_done()
                            classes.update(file_classes)
                            for ci, paths in file_labels.items():
                                labelsdata_new[ci].extend(paths)
                            processed += 1
                            if file_valid:
                                valid_files += 1
                            else:
                                invalid_files += 1
                    except queue.Empty:
                        pass
                    break

        if progress_callback:
            progress_callback(processed, total, valid_files, invalid_files)

        sorted_classes = sorted(list(classes), key=lambda x: int(float(x)))
        return labelsdata_new, sorted_classes, valid_files, invalid_files

    def refresh_label_data_cache(self, specific_paths=None):
        """라벨 데이터 캐시를 갱신합니다."""
        paths_to_process = specific_paths if specific_paths else self.labels

        if specific_paths:
            for class_idx, paths in enumerate(self.labelsdata):
                self.labelsdata[class_idx] = [p for p in paths if p not in specific_paths]
                self.labelsdata_sets[class_idx].difference_update(specific_paths)

        for label_path in paths_to_process:
            if not os.path.isfile(label_path):
                continue
            # 캐시 무효화 후 다시 읽기
            self.invalidate_label_cache(label_path)
            lines = self.get_label_data(label_path)
            for line in lines:
                parts = line.strip().split()
                if not parts:
                    continue
                try:
                    class_index = int(float(parts[0]))
                    if 0 <= class_index < len(self.labelsdata):
                        if label_path not in self.labelsdata_sets[class_index]:
                            self.labelsdata[class_index].append(label_path)
                            self.labelsdata_sets[class_index].add(label_path)
                except (ValueError, IndexError):
                    continue

    # ── 겹침 분석 ──

    def check_box_overlap(self, label_path, main_class_idx, target_class_idx, iou_threshold):
        """특정 클래스의 각 박스별로 겹침 정보를 분석합니다."""
        cache_key = (label_path, main_class_idx, target_class_idx, iou_threshold)
        if cache_key in self.overlap_cache:
            return self.overlap_cache[cache_key]

        if not os.path.isfile(label_path):
            return False, 0.0, [], []

        try:
            boxes_by_class = {}
            original_line_indices = {}

            lines = self.get_label_data(label_path)
            for line_idx, line in enumerate(lines):
                parts = line.strip().split()
                if not parts or len(parts) < 5:
                    continue
                try:
                    box_class = int(float(parts[0]))
                    x_center = float(parts[1])
                    y_center = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])

                    if not (0 <= x_center <= 1 and 0 <= y_center <= 1 and
                            0 <= width <= 1 and 0 <= height <= 1):
                        continue

                    x1 = x_center - width / 2
                    y1 = y_center - height / 2
                    x2 = x_center + width / 2
                    y2 = y_center + height / 2

                    if box_class not in boxes_by_class:
                        boxes_by_class[box_class] = []
                        original_line_indices[box_class] = []

                    boxes_by_class[box_class].append({
                        'coords': (x1, y1, x2, y2),
                        'class': box_class,
                        'center': (x_center, y_center),
                        'size': (width, height)
                    })
                    original_line_indices[box_class].append(line_idx)
                except (IndexError, ValueError):
                    continue

            if int(main_class_idx) not in boxes_by_class:
                result = (False, 0.0, [], [])
                self.overlap_cache[cache_key] = result
                return result

            all_boxes_overlap_info = []
            any_overlap = False
            max_overall_iou = 0.0

            for i, main_box in enumerate(boxes_by_class[int(main_class_idx)]):
                box_overlap_info = {
                    'box_index': i,
                    'original_line_index': original_line_indices[int(main_class_idx)][i],
                    'has_overlap': False,
                    'max_iou': 0.0,
                    'overlapping_boxes': []
                }

                if int(target_class_idx) in boxes_by_class:
                    for j, target_box in enumerate(boxes_by_class[int(target_class_idx)]):
                        if int(main_class_idx) == int(target_class_idx) and i == j:
                            continue
                        iou = calculate_iou(main_box['coords'], target_box['coords'])
                        if iou >= iou_threshold:
                            box_overlap_info['has_overlap'] = True
                            any_overlap = True
                            if iou > box_overlap_info['max_iou']:
                                box_overlap_info['max_iou'] = iou
                            box_overlap_info['overlapping_boxes'].append({
                                'target_box_index': j,
                                'original_line_index': original_line_indices[int(target_class_idx)][j],
                                'iou': iou
                            })

                if box_overlap_info['max_iou'] > max_overall_iou:
                    max_overall_iou = box_overlap_info['max_iou']
                all_boxes_overlap_info.append(box_overlap_info)

            detailed_overlap_info = []
            for box_info in all_boxes_overlap_info:
                if box_info['has_overlap']:
                    detailed_overlap_info.append({
                        'main_box_index': box_info['box_index'],
                        'max_iou': box_info['max_iou'],
                        'overlapping_boxes': box_info['overlapping_boxes']
                    })

            result = (any_overlap, max_overall_iou, detailed_overlap_info, all_boxes_overlap_info)
            self.overlap_cache[cache_key] = result
            return result

        except Exception as e:
            print(f"Error checking box overlap in {label_path}: {e}")
            return False, 0.0, [], []

    # ── 페이지네이션 ──

    def get_class_images(self, class_idx):
        """특정 클래스의 이미지(라벨) 목록을 반환합니다."""
        if 0 <= class_idx < len(self.labelsdata):
            class_paths = self.labelsdata_sets[class_idx]
            return [path for path in self.labels if path in class_paths]
        return []

    def get_page_data(self, class_images):
        """현재 페이지에 해당하는 이미지 슬라이스를 반환합니다."""
        total = len(class_images)
        self.total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        if self.current_page >= self.total_pages:
            self.current_page = max(0, self.total_pages - 1)
        start = self.current_page * self.page_size
        end = min(start + self.page_size, total)
        return class_images[start:end], start

    def get_memory_usage(self):
        """현재 프로세스의 메모리 사용량을 MB 단위로 반환"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0
