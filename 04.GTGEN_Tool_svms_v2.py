#!/usr/bin/env python
from ast import dump
import os
import re
import sys
# PyInstaller RecursionError 방지 - 빌드 프로세스에서 recursion limit 증가
sys.setrecursionlimit(100000)

from xml.dom.minidom import Element
from xml.etree import ElementTree
import six
import numpy.core.multiarray
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import ttk
from functools import partial 
import cv2
import natsort
import configparser
import time
import atexit
import copy
import shutil
import numpy as np
import pyautogui
from numpy import array
from collections import Counter
import json

#BASE_DIR = "C:/S1/TrainData/"
BASE_DIR = os.getcwd() + "\\"
_dir_goodbye = ""

IMAGE_FILE_EXTENSIONS = ('.jpg', '.jpeg', '.png')
LIST_FILE_ENCODINGS = ['utf-8', 'cp949', 'euc-kr', 'latin-1', 'shift-jis']

def image_to_label_path(image_path):
	"""이미지 경로에 대응하는 YOLO 라벨(txt) 경로. 화면 저장/범위 복사/삭제가 모두 같은 규칙을 쓴다."""
	label_path = str(image_path).replace('JPEGImages', 'labels')
	label_path = label_path.replace('images', 'annotations')
	root, _ = os.path.splitext(label_path)
	return root + '.txt'

def is_image_file(path):
	return os.path.splitext(str(path))[1].lower() in IMAGE_FILE_EXTENSIONS

def image_sort_key(path):
	normalized = os.path.normpath(str(path)).replace('\\', '/')
	return os.path.normcase(normalized)

def sort_image_paths(paths):
	return natsort.natsorted(paths, key=image_sort_key)

def to_list_file_path(path):
	return str(path).replace('//192.168.79.253/', '/s_mnt/253/').rstrip('\r\n') + '\n'

def normalize_list_image_path(line):
	path = str(line).strip().lstrip('\ufeff')
	if len(path) >= 2 and path[0] == path[-1] and path[0] in ('"', "'"):
		path = path[1:-1]
	return path.replace('/s_mnt/253/','//192.168.79.253/')

def safe_path_exists(path):
	try:
		return os.path.exists(path)
	except (OSError, ValueError) as e:
		print(f"[ListLoad] path check failed: {path} ({e})")
		return False

def read_image_list_file(list_path):
	attempts = []
	for encoding in LIST_FILE_ENCODINGS:
		valid_images = []
		missing_images = []
		try:
			with open(list_path, "rt", encoding=encoding) as file:
				for line_number, raw_line in enumerate(file, start=1):
					image_path = normalize_list_image_path(raw_line)
					if not image_path:
						continue
					if safe_path_exists(image_path):
						valid_images.append(image_path)
					else:
						missing_images.append((line_number, image_path))
		except UnicodeDecodeError as e:
			print(f"[ListLoad] encoding failed: {encoding} ({e})")
			continue
		except Exception as e:
			print(f"[ListLoad] read failed with {encoding}: {e}")
			attempts.append((encoding, valid_images, missing_images, e))
			continue

		attempts.append((encoding, valid_images, missing_images, None))
		if valid_images:
			return valid_images, missing_images, encoding

	if attempts:
		encoding, valid_images, missing_images, error = max(attempts, key=lambda item: len(item[1]))
		if error is None:
			return valid_images, missing_images, encoding
		raise error

	raise RuntimeError("No supported encoding could read the list file.")

def print_missing_list_items(missing_images, limit=50):
	for line_number, image_path in missing_images[:limit]:
		print(f"no file ({line_number}) : {image_path}")
	if len(missing_images) > limit:
		print(f"[ListLoad] {len(missing_images) - limit} more missing files omitted from log")

def point_in_polygon(point, polygon):
	x, y = point
	inside = False
	if len(polygon) < 3:
		return False
	p1x, p1y = polygon[-1]
	for p2x, p2y in polygon:
		if (p1y > y) != (p2y > y):
			x_intersection = (p2x - p1x) * (y - p1y) / (p2y - p1y) + p1x
			if x < x_intersection:
				inside = not inside
		p1x, p1y = p2x, p2y
	return inside

def label_line_center(line):
	values = line.strip().split()
	if len(values) < 5:
		raise ValueError("label line must contain class, center, width, and height")
	return float(values[1]), float(values[2])

def merge_copy_region_label_lines(existing_lines, copied_lines, regions):
	"""Replace target labels whose centers are inside active normalized copy regions."""
	if not regions:
		return list(copied_lines)
	result = []
	for line in existing_lines:
		try:
			center = label_line_center(line)
			if any(point_in_polygon(center, region) for region in regions):
				continue
		except (ValueError, TypeError):
			result.append(line)
			continue
		result.append(line)
	filtered_copied = []
	for line in copied_lines:
		try:
			if any(point_in_polygon(label_line_center(line), region) for region in regions):
				filtered_copied.append(line)
		except (ValueError, TypeError):
			continue
	return filtered_copied + result

class CopyRegionManager:
	def __init__(self, config_file='.copy_zones.json'):
		self.config_file = config_file
		self.zones = []
		self.load()

	def load(self):
		if not os.path.exists(self.config_file):
			return
		try:
			with open(self.config_file, 'r', encoding='utf-8') as f:
				loaded = json.load(f)
			self.zones = [z for z in loaded if isinstance(z, dict) and len(z.get('points', [])) >= 3]
			for zone in self.zones:
				zone['enabled'] = bool(zone.get('enabled', True))
		except Exception as e:
			print(f"[CopyZone] load failed: {e}")
			self.zones = []

	def save(self):
		try:
			with open(self.config_file, 'w', encoding='utf-8') as f:
				json.dump(self.zones, f, indent=2)
			return True
		except Exception as e:
			print(f"[CopyZone] save failed: {e}")
			return False

	def active_regions(self):
		return [z['points'] for z in self.zones if z.get('enabled', True)]

	def zone_at(self, point):
		for index in range(len(self.zones) - 1, -1, -1):
			zone = self.zones[index]
			if point_in_polygon(point, zone.get('points', [])):
				return index
		return None

	def toggle_at(self, point):
		index = self.zone_at(point)
		if index is None:
			return None
		self.zones[index]['enabled'] = not self.zones[index].get('enabled', True)
		self.save()
		return index

# 폴리곤 제외 영역 관리 클래스
class ExclusionZoneManager:
	"""폴리곤 제외 영역을 관리하는 클래스"""

	def __init__(self, base_dir=None):
		self.base_dir = base_dir or os.getcwd()
		self.zones = []  # 현재 이미지의 제외 영역
		self.global_zones = []  # 모든 이미지에 적용되는 전역 제외 영역
		self.current_zone_file = None
		self.global_zone_file = os.path.join(self.base_dir, ".global_exclusion_zones.json")
		self.enabled_file = os.path.join(self.base_dir, ".exclusion_zone_enabled.txt")
		self.use_global = True  # 전역 영역 사용 여부
		self.load_global_zones()

	def add_zone(self, points, use_global=True, class_ids=None, zone_type='polygon'):
		"""새로운 제외 영역 추가 (points는 [(x,y), ...] 형태)
		Args:
			points: 폴리곤 점들
			use_global: 전역 영역에 추가할지 여부
			class_ids: 적용할 클래스 ID 리스트 (None 또는 빈 리스트면 모든 클래스에 적용)
		"""
		zone_type = zone_type if zone_type in ('polygon', 'point') else 'polygon'
		required_points = 1 if zone_type == 'point' else 3
		if len(points) >= required_points:
			zone = {
				'points': points,
				'zone_type': zone_type,
				'enabled': True,
				'class_ids': class_ids if class_ids else []  # 빈 리스트면 모든 클래스에 적용
			}
			if use_global:
				self.global_zones.append(zone)
			else:
				self.zones.append(zone)
			return True
		return False

	def remove_zone(self, index):
		"""제외 영역 삭제 (전역 영역에서)"""
		if 0 <= index < len(self.global_zones):
			del self.global_zones[index]
			return True
		return False

	def toggle_zone(self, index):
		"""제외 영역 활성화/비활성화 토글 (전역 영역에서)"""
		if 0 <= index < len(self.global_zones):
			self.global_zones[index]['enabled'] = not self.global_zones[index]['enabled']
			return True
		return False

	def update_zone_classes(self, index, class_ids):
		"""제외 영역의 적용 클래스 업데이트
		Args:
			index: 영역 인덱스
			class_ids: 적용할 클래스 ID 리스트 (빈 리스트면 모든 클래스에 적용)
		"""
		if 0 <= index < len(self.global_zones):
			self.global_zones[index]['class_ids'] = class_ids if class_ids else []
			return True
		return False

	def clear_zones(self):
		"""모든 제외 영역 삭제"""
		self.global_zones = []

	def is_bbox_in_exclusion_zone(self, bbox, class_name_list=None, zoom_ratio=1.0):
		"""bbox가 제외 영역과 겹치는지 확인 (면적 기반 + 클래스 필터)
		Args:
			bbox: [sel, clsname, info, x1, y1, x2, y2] 형태 (화면 좌표)
			class_name_list: 클래스 이름 리스트 (전역 class_name)
			zoom_ratio: 현재 줌 비율 (bbox를 원본 좌표로 변환하기 위해 필요)
		Returns:
			bool: 조금이라도 겹치면 True
		"""
		zones_to_check = self.global_zones if self.use_global else self.zones
		if not zones_to_check:
			# 제외 영역이 없으면 False 반환 (디버그 로그 제거)
			return False

		# bbox의 클래스 ID 가져오기
		bbox_class_id = bbox[2]  # info 필드가 class_id
		# bbox를 원본 좌표로 변환 (화면 좌표 / zoom_ratio)
		x1, y1, x2, y2 = bbox[3] / zoom_ratio, bbox[4] / zoom_ratio, bbox[5] / zoom_ratio, bbox[6] / zoom_ratio

		for i, zone in enumerate(zones_to_check):
			# 하위 호환성: class_ids 키가 없으면 빈 리스트로 간주
			zone_class_ids = zone.get('class_ids', [])

			if zone['enabled']:
				# 클래스 필터 체크: class_ids가 비어있으면 모든 클래스에 적용
				if zone_class_ids and bbox_class_id not in zone_class_ids:
					continue

				overlap = self._bbox_matches_zone(x1, y1, x2, y2, zone)
				if overlap:
					return True
		return False

	def _normalize_zone(self, zone):
		"""Add default fields for zones saved by older versions."""
		if not isinstance(zone, dict):
			return None
		points = zone.get('points') or []
		if not points:
			return None
		if 'zone_type' not in zone:
			zone['zone_type'] = 'point' if len(points) == 1 else 'polygon'
		if zone['zone_type'] not in ('polygon', 'point'):
			zone['zone_type'] = 'polygon'
		zone['enabled'] = zone.get('enabled', True)
		zone['class_ids'] = zone.get('class_ids', [])
		return zone

	def _bbox_matches_zone(self, x1, y1, x2, y2, zone):
		points = zone.get('points') or []
		if not points:
			return False
		zone_type = zone.get('zone_type', 'point' if len(points) == 1 else 'polygon')
		if zone_type == 'point':
			return self._point_in_bbox(points[0], x1, y1, x2, y2)
		if len(points) < 3:
			return False
		return self._bbox_polygon_overlap(x1, y1, x2, y2, points)

	def _point_in_bbox(self, point, x1, y1, x2, y2):
		px, py = point
		min_x, max_x = min(x1, x2), max(x1, x2)
		min_y, max_y = min(y1, y2), max(y1, y2)
		return min_x <= px <= max_x and min_y <= py <= max_y

	def _bbox_polygon_overlap(self, x1, y1, x2, y2, polygon):
		"""bbox와 폴리곤이 겹치는지 확인 (면적 기반)
		Args:
			x1, y1, x2, y2: bbox 좌표
			polygon: 폴리곤 점들 [(x, y), ...]
		Returns:
			bool: 조금이라도 겹치면 True
		"""
		# bbox 좌표 정규화 (x1 < x2, y1 < y2 보장)
		min_x, max_x = min(x1, x2), max(x1, x2)
		min_y, max_y = min(y1, y2), max(y1, y2)

		# 1. bbox의 네 모서리 중 하나라도 폴리곤 안에 있는지 확인
		bbox_corners = [
			(min_x, min_y),  # 왼쪽 위
			(max_x, min_y),  # 오른쪽 위
			(min_x, max_y),  # 왼쪽 아래
			(max_x, max_y)   # 오른쪽 아래
		]

		for corner in bbox_corners:
			if self._point_in_polygon(corner, polygon):
				return True  # bbox 모서리가 폴리곤 안에 있음

		# 2. 폴리곤의 점 중 하나라도 bbox 안에 있는지 확인
		for point in polygon:
			px, py = point
			if min_x <= px <= max_x and min_y <= py <= max_y:
				return True  # 폴리곤 점이 bbox 안에 있음

		# 3. bbox의 변과 폴리곤의 변이 교차하는지 확인
		bbox_edges = [
			((min_x, min_y), (max_x, min_y)),  # 위쪽 변
			((max_x, min_y), (max_x, max_y)),  # 오른쪽 변
			((max_x, max_y), (min_x, max_y)),  # 아래쪽 변
			((min_x, max_y), (min_x, min_y))   # 왼쪽 변
		]

		n = len(polygon)
		for i in range(n):
			polygon_edge = (polygon[i], polygon[(i + 1) % n])
			for bbox_edge in bbox_edges:
				if self._segments_intersect(bbox_edge[0], bbox_edge[1], polygon_edge[0], polygon_edge[1]):
					return True  # 변들이 교차함

		return False  # 겹치지 않음

	def _segments_intersect(self, p1, p2, p3, p4):
		"""두 선분이 교차하는지 확인
		Args:
			p1, p2: 첫 번째 선분의 시작/끝점
			p3, p4: 두 번째 선분의 시작/끝점
		Returns:
			bool: 교차하면 True
		"""
		def ccw(A, B, C):
			return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

		return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

	def _point_in_polygon(self, point, polygon):
		"""점이 폴리곤 안에 있는지 확인 (Ray casting algorithm)"""
		x, y = point
		n = len(polygon)
		inside = False

		p1x, p1y = polygon[0]
		for i in range(1, n + 1):
			p2x, p2y = polygon[i % n]
			if y > min(p1y, p2y):
				if y <= max(p1y, p2y):
					if x <= max(p1x, p2x):
						if p1y != p2y:
							xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
						if p1x == p2x or x <= xinters:
							inside = not inside
			p1x, p1y = p2x, p2y

		return inside

	def save_global_zones(self):
		"""전역 제외 영역을 파일로 저장"""
		try:
			with open(self.global_zone_file, 'w') as f:
				json.dump(self.global_zones, f, indent=2)
			print(f"[ExclusionZone] 전역 제외 영역 저장: {len(self.global_zones)}개")
		except Exception as e:
			print(f"[ERROR] Failed to save global exclusion zones: {e}")

	def load_global_zones(self):
		"""전역 제외 영역을 파일에서 로드"""
		if os.path.exists(self.global_zone_file):
			try:
				with open(self.global_zone_file, 'r') as f:
					loaded_zones = json.load(f)
					if not isinstance(loaded_zones, list):
						loaded_zones = []
					self.global_zones = [
						zone for zone in (self._normalize_zone(zone) for zone in loaded_zones)
						if zone is not None
					]
				print(f"[ExclusionZone] 전역 제외 영역 로드: {len(self.global_zones)}개")
			except Exception as e:
				print(f"[ERROR] Failed to load global exclusion zones: {e}")
				self.global_zones = []

	def save_enabled_state(self, enabled):
		"""제외 영역 기능 활성화 상태 저장"""
		try:
			with open(self.enabled_file, 'w') as f:
				f.write('1' if enabled else '0')
		except Exception as e:
			print(f"[ERROR] Failed to save enabled state: {e}")

	def load_enabled_state(self):
		"""제외 영역 기능 활성화 상태 로드"""
		if os.path.exists(self.enabled_file):
			try:
				with open(self.enabled_file, 'r') as f:
					return f.read().strip() == '1'
			except Exception as e:
				print(f"[ERROR] Failed to load enabled state: {e}")
		return False

	def save_zones(self, image_path):
		"""현재 이미지의 제외 영역을 파일로 저장 (사용 안 함 - 전역만 사용)"""
		# 전역 영역 저장
		self.save_global_zones()

	def load_zones(self, image_path):
		"""현재 이미지의 제외 영역을 파일에서 로드 (사용 안 함 - 전역만 사용)"""
		# 전역 영역은 이미 __init__에서 로드됨
		pass

# 클래스 변경 영역 관리 클래스
class ClassChangeZoneManager:
	"""폴리곤 영역 내 bbox의 클래스를 변경하는 기능을 관리하는 클래스"""

	def __init__(self, base_dir=None):
		self.base_dir = base_dir or os.getcwd()
		self.zones = []  # 클래스 변경 영역 리스트
		self.global_zone_file = os.path.join(self.base_dir, ".class_change_zones.json")
		self.load_zones()

	def add_zone(self, points, mode, target_class_id, source_class_id=None, zone_type='polygon'):
		"""새로운 클래스 변경 영역 추가
		Args:
			points: 폴리곤 점들 [(x, y), ...]
			mode: 변경 모드 ("all" 또는 "filter")
			target_class_id: 변경할 목표 클래스 ID
			source_class_id: 필터 모드일 때 대상 클래스 ID (mode="filter"일 때만 사용)
		"""
		zone_type = zone_type if zone_type in ('polygon', 'point') else 'polygon'
		required_points = 1 if zone_type == 'point' else 3
		if len(points) >= required_points:
			zone = {
				'points': points,
				'zone_type': zone_type,
				'enabled': True,
				'mode': mode,  # "all" or "filter"
				'target_class_id': target_class_id,
				'source_class_id': source_class_id  # mode="filter"일 때만 사용
			}
			self.zones.append(zone)
			return True
		return False

	def remove_zone(self, index):
		"""클래스 변경 영역 삭제"""
		if 0 <= index < len(self.zones):
			del self.zones[index]
			return True
		return False

	def toggle_zone(self, index):
		"""클래스 변경 영역 활성화/비활성화 토글"""
		if 0 <= index < len(self.zones):
			self.zones[index]['enabled'] = not self.zones[index]['enabled']
			return True
		return False

	def clear_zones(self):
		"""모든 클래스 변경 영역 삭제"""
		self.zones = []

	def apply_class_changes(self, bbox_list, class_name_list, zoom_ratio=1.0):
		"""bbox 리스트에 클래스 변경 영역 적용
		Args:
			bbox_list: bbox 리스트 (화면 좌표)
			class_name_list: 클래스 이름 리스트
			zoom_ratio: 현재 줌 비율
		Returns:
			tuple: (변경된 bbox 리스트, 변경 개수)
		"""
		if not self.zones:
			return bbox_list, 0

		changed_count = 0
		new_bbox_list = []

		for bbox in bbox_list:
			# bbox: [sel, clsname, info, x1, y1, x2, y2]
			bbox_class_id = bbox[2]
			x1, y1, x2, y2 = bbox[3] / zoom_ratio, bbox[4] / zoom_ratio, bbox[5] / zoom_ratio, bbox[6] / zoom_ratio

			changed = False
			for zone in self.zones:
				if not zone['enabled']:
					continue

				# 폴리곤 내부에 있는지 확인
				if self._bbox_matches_zone(x1, y1, x2, y2, zone):
					# 모드에 따라 클래스 변경
					if zone['mode'] == 'all':
						# 모든 클래스를 target_class_id로 변경
						new_class_id = zone['target_class_id']
						if 0 <= new_class_id < len(class_name_list):
							new_class_name = class_name_list[new_class_id]
							# bbox 복사 후 클래스 정보 변경
							new_bbox = list(bbox)
							new_bbox[1] = new_class_name
							new_bbox[2] = new_class_id
							new_bbox_list.append(new_bbox)
							changed = True
							changed_count += 1
							break
					elif zone['mode'] == 'filter':
						# source_class_id와 일치하는 경우만 target_class_id로 변경
						if bbox_class_id == zone['source_class_id']:
							new_class_id = zone['target_class_id']
							if 0 <= new_class_id < len(class_name_list):
								new_class_name = class_name_list[new_class_id]
								new_bbox = list(bbox)
								new_bbox[1] = new_class_name
								new_bbox[2] = new_class_id
								new_bbox_list.append(new_bbox)
								changed = True
								changed_count += 1
								break

			# 변경되지 않았으면 원본 bbox 추가
			if not changed:
				new_bbox_list.append(bbox)

		return new_bbox_list, changed_count

	def _normalize_zone(self, zone):
		"""Add default fields for zones saved by older versions."""
		if not isinstance(zone, dict):
			return None
		points = zone.get('points') or []
		if not points:
			return None
		if 'zone_type' not in zone:
			zone['zone_type'] = 'point' if len(points) == 1 else 'polygon'
		if zone['zone_type'] not in ('polygon', 'point'):
			zone['zone_type'] = 'polygon'
		zone['enabled'] = zone.get('enabled', True)
		zone['mode'] = zone.get('mode', 'all')
		return zone

	def _bbox_matches_zone(self, x1, y1, x2, y2, zone):
		points = zone.get('points') or []
		if not points:
			return False
		zone_type = zone.get('zone_type', 'point' if len(points) == 1 else 'polygon')
		if zone_type == 'point':
			return self._point_in_bbox(points[0], x1, y1, x2, y2)
		if len(points) < 3:
			return False
		return self._bbox_in_polygon(x1, y1, x2, y2, points)

	def _point_in_bbox(self, point, x1, y1, x2, y2):
		px, py = point
		min_x, max_x = min(x1, x2), max(x1, x2)
		min_y, max_y = min(y1, y2), max(y1, y2)
		return min_x <= px <= max_x and min_y <= py <= max_y

	def _bbox_in_polygon(self, x1, y1, x2, y2, polygon):
		"""bbox가 폴리곤 내부에 있는지 확인 (중심점 기준)
		Args:
			x1, y1, x2, y2: bbox 좌표
			polygon: 폴리곤 점들 [(x, y), ...]
		Returns:
			bool: bbox 중심점이 폴리곤 안에 있으면 True
		"""
		# bbox 중심점 계산
		cx = (x1 + x2) / 2
		cy = (y1 + y2) / 2

		return self._point_in_polygon((cx, cy), polygon)

	def _point_in_polygon(self, point, polygon):
		"""점이 폴리곤 안에 있는지 확인 (Ray casting algorithm)"""
		x, y = point
		n = len(polygon)
		inside = False

		p1x, p1y = polygon[0]
		for i in range(1, n + 1):
			p2x, p2y = polygon[i % n]
			if y > min(p1y, p2y):
				if y <= max(p1y, p2y):
					if x <= max(p1x, p2x):
						if p1y != p2y:
							xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
						if p1x == p2x or x <= xinters:
							inside = not inside
			p1x, p1y = p2x, p2y

		return inside

	def save_zones(self):
		"""클래스 변경 영역을 파일로 저장"""
		try:
			with open(self.global_zone_file, 'w') as f:
				json.dump(self.zones, f, indent=2)
			print(f"[ClassChangeZone] 클래스 변경 영역 저장: {len(self.zones)}개")
		except Exception as e:
			print(f"[ERROR] Failed to save class change zones: {e}")

	def load_zones(self):
		"""클래스 변경 영역을 파일에서 로드"""
		if os.path.exists(self.global_zone_file):
			try:
				with open(self.global_zone_file, 'r') as f:
					loaded_zones = json.load(f)
					if not isinstance(loaded_zones, list):
						loaded_zones = []
					self.zones = [
						zone for zone in (self._normalize_zone(zone) for zone in loaded_zones)
						if zone is not None
					]
				print(f"[ClassChangeZone] 클래스 변경 영역 로드: {len(self.zones)}개")
			except Exception as e:
				print(f"[ERROR] Failed to load class change zones: {e}")
				self.zones = []

# 클래스 자동 삭제 관리 클래스
class AutoDeleteClassManager:
	"""특정 클래스를 자동으로 삭제하는 기능을 관리하는 클래스"""

	def __init__(self, base_dir=None):
		self.base_dir = base_dir or os.getcwd()
		self.config_file = os.path.join(self.base_dir, ".auto_delete_classes.json")
		# 새로운 구조: {class_id: mode} - 각 클래스별로 삭제 모드 저장
		self.delete_class_config = {}  # {class_id: "auto" or "shortcut"}
		self.load_config()

	def add_class(self, class_id, mode="auto"):
		"""자동 삭제 대상에 클래스 추가
		Args:
			class_id: 클래스 ID
			mode: 삭제 모드 ("auto" 또는 "shortcut")
		"""
		self.delete_class_config[class_id] = mode
		self.save_config()

	def remove_class(self, class_id):
		"""자동 삭제 대상에서 클래스 제거"""
		if class_id in self.delete_class_config:
			del self.delete_class_config[class_id]
		self.save_config()

	def set_class_mode(self, class_id, mode):
		"""클래스의 삭제 모드 설정
		Args:
			class_id: 클래스 ID
			mode: 삭제 모드 ("auto" 또는 "shortcut")
		"""
		if class_id in self.delete_class_config:
			self.delete_class_config[class_id] = mode

	def get_class_mode(self, class_id):
		"""클래스의 삭제 모드 반환
		Args:
			class_id: 클래스 ID
		Returns:
			mode: "auto", "shortcut" 또는 None (설정 안됨)
		"""
		return self.delete_class_config.get(class_id, None)

	def is_class_marked_for_deletion(self, class_id):
		"""해당 클래스가 자동 삭제 대상인지 확인"""
		return class_id in self.delete_class_config

	def filter_bboxes(self, bbox_list, class_name_list, mode_filter=None):
		"""bbox 리스트에서 자동 삭제 대상 클래스 제거
		Args:
			bbox_list: bbox 리스트 ([sel, clsname, info, x1, y1, x2, y2] 형태)
			class_name_list: 클래스 이름 리스트 (전역 class_name)
			mode_filter: 특정 모드만 필터링 ("auto", "shortcut", None=모두)
		Returns:
			filtered_list: 필터링된 bbox 리스트
		"""
		if not self.delete_class_config:
			return bbox_list

		# bbox[1]에서 클래스 이름을 가져와서 class_id로 변환
		filtered = []
		for bbox in bbox_list:
			class_name_str = bbox[1]  # 클래스 이름 (문자열)
			try:
				# 클래스 이름을 인덱스(class_id)로 변환
				class_id = class_name_list.index(class_name_str)

				# 삭제 대상인지 확인
				if class_id in self.delete_class_config:
					class_mode = self.delete_class_config[class_id]
					# mode_filter가 지정되면 해당 모드만 삭제
					if mode_filter is None or class_mode == mode_filter:
						# 삭제 대상 - 필터링됨 (추가하지 않음)
						continue

				# 삭제 대상이 아니면 유지
				filtered.append(bbox)
			except ValueError:
				# 클래스 이름을 찾을 수 없으면 유지
				print(f"[WARNING] Unknown class name: {class_name_str}, keeping bbox")
				filtered.append(bbox)

		return filtered

	def save_config(self):
		"""설정을 파일로 저장"""
		try:
			# 새 형식: class_id를 문자열 키로 저장 (JSON 호환)
			config_data = {
				"version": 3,
				"delete_class_config": {str(k): v for k, v in self.delete_class_config.items()}
			}
			with open(self.config_file, 'w') as f:
				json.dump(config_data, f, indent=2)
		except Exception as e:
			print(f"[ERROR] Failed to save auto delete config: {e}")

	def load_config(self):
		"""설정을 파일에서 로드 (이전 버전 호환)"""
		if os.path.exists(self.config_file):
			try:
				with open(self.config_file, 'r') as f:
					config_data = json.load(f)

					# Version 1: 리스트만 있는 경우 [0, 1, 2]
					if isinstance(config_data, list):
						self.delete_class_config = {class_id: "auto" for class_id in config_data}
						print(f"[AutoDelete] V1 형식 로드: 모두 auto 모드로 변환")

					# Version 2: delete_class_ids + delete_mode
					elif "delete_class_ids" in config_data:
						class_ids = config_data.get("delete_class_ids", [])
						mode = config_data.get("delete_mode", "auto")
						self.delete_class_config = {class_id: mode for class_id in class_ids}
						print(f"[AutoDelete] V2 형식 로드: 모두 {mode} 모드로 변환")

					# Version 3: delete_class_config (새 형식)
					elif "delete_class_config" in config_data:
						# 문자열 키를 정수로 변환
						raw_config = config_data.get("delete_class_config", {})
						self.delete_class_config = {int(k): v for k, v in raw_config.items()}
						print(f"[AutoDelete] V3 형식 로드: 클래스별 개별 설정")

					else:
						self.delete_class_config = {}
						print(f"[AutoDelete] 빈 설정 파일")

			except Exception as e:
				print(f"[ERROR] Failed to load auto delete config: {e}")
				self.delete_class_config = {}
		else:
			print(f"[AutoDelete] 설정 파일 없음 - 새로 시작")

# 클래스 설정 관리 클래스
class ClassConfigManager:
	def __init__(self, config_file="class_config.json"):
		# 현재 작업 디렉토리를 기준으로 설정 파일 저장/로드
		self.base_dir = os.getcwd()
		self.config_file = os.path.join(self.base_dir, config_file)
		self.last_config_file = os.path.join(self.base_dir, ".last_class_config.txt")
		self.classes = []
		self.enable_backup = True  # 백업 기본값
		self.default_colors = [
			'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'cyan', 'magenta',
			'lime', 'pink', 'teal', 'lavender', 'brown', 'beige', 'maroon', 'mint',
			'olive', 'coral', 'navy', 'grey', 'white', 'salmon', 'gold', 'turquoise',
			'violet', 'indigo', 'tan', 'khaki', 'plum', 'orchid', 'sienna', 'crimson'
		]
		print(f"[DEBUG] ClassConfigManager 초기화 - base_dir: {self.base_dir}")

	def set_config_file(self, config_file):
		"""설정 파일 경로 변경"""
		if not config_file.endswith('.json'):
			config_file += '.json'
		self.config_file = os.path.join(self.base_dir, config_file)

	def get_config_filename(self):
		"""현재 설정 파일명 반환 (경로 제외)"""
		return os.path.basename(self.config_file)

	def save_last_config(self):
		"""마지막으로 사용한 설정 파일 저장"""
		try:
			with open(self.last_config_file, 'w') as f:
				f.write(self.get_config_filename())
		except:
			pass

	def load_last_config(self):
		"""마지막으로 사용한 설정 파일명 로드"""
		try:
			if os.path.exists(self.last_config_file):
				with open(self.last_config_file, 'r') as f:
					return f.read().strip()
		except:
			pass
		return None

	def get_available_configs(self):
		"""사용 가능한 설정 파일 목록 반환"""
		try:
			# base_dir에서 찾기
			search_dir = self.base_dir
			print(f"[DEBUG] 설정 파일 검색 경로: {search_dir}")

			if not os.path.exists(search_dir):
				print(f"[DEBUG] 경로가 존재하지 않음: {search_dir}")
				return []

			all_files = os.listdir(search_dir)
			print(f"[DEBUG] 전체 파일 개수: {len(all_files)}")

			# 모든 .json 파일 출력 (디버깅)
			json_files = [f for f in all_files if f.endswith('.json')]
			print(f"[DEBUG] JSON 파일 목록: {json_files}")

			# class_config로 시작하는 파일들만 필터링 (대소문자 무시)
			config_files = [f for f in json_files if f.lower().startswith('class_config') or f.lower().startswith('classconfig')]
			print(f"[DEBUG] 찾은 설정 파일: {config_files}")

			# 만약 없으면 class와 config가 포함된 모든 JSON 파일 반환
			if not config_files:
				config_files = [f for f in json_files if 'class' in f.lower() and 'config' in f.lower()]
				print(f"[DEBUG] 유연한 검색 결과: {config_files}")

			# 그래도 없으면 모든 .json 파일 반환
			if not config_files:
				print(f"[DEBUG] 설정 파일 없음. 모든 JSON 파일 표시")
				config_files = json_files

			return sorted(config_files)
		except Exception as e:
			print(f"[DEBUG] get_available_configs 오류: {e}")
			import traceback
			traceback.print_exc()
			return []

	def config_exists(self):
		return os.path.exists(self.config_file)

	def load_config(self, config_file=None):
		"""설정 파일 로드"""
		if config_file:
			self.set_config_file(config_file)

		if not self.config_exists():
			return False

		try:
			with open(self.config_file, 'r', encoding='utf-8') as f:
				data = json.load(f)
				self.classes = data.get('classes', [])
				# 백업 옵션 로드 (기본값: True)
				backup_value = data.get('enable_backup', True)
				if isinstance(backup_value, str):
					self.enable_backup = backup_value.strip().lower() not in ('false', '0', 'no', 'off', '')
				else:
					self.enable_backup = bool(backup_value)
			self.save_last_config()
			return True
		except Exception as e:
			print(f"설정 파일 로드 실패: {e}")
			return False

	def save_config(self, classes, config_file=None, enable_backup=True):
		"""설정 파일 저장"""
		if config_file:
			self.set_config_file(config_file)

		self.classes = classes
		self.enable_backup = enable_backup
		try:
			with open(self.config_file, 'w', encoding='utf-8') as f:
				json.dump({
					'classes': self.classes,
					'enable_backup': self.enable_backup
				}, f, ensure_ascii=False, indent=2)
			self.save_last_config()
			return True
		except Exception as e:
			print(f"설정 파일 저장 실패: {e}")
			return False

	def get_class_names(self):
		"""클래스 이름 리스트 반환"""
		# 클래스를 id 순으로 정렬
		sorted_classes = sorted(self.classes, key=lambda x: x['id'])
		return [c['name'] for c in sorted_classes]

	def get_class_colors(self):
		"""클래스 색상 정보 반환 (기존 class_color 형식)"""
		sorted_classes = sorted(self.classes, key=lambda x: x['id'])
		names = [c['name'] for c in sorted_classes]
		colors = [c['color'] for c in sorted_classes]
		return [names, colors]

	def get_class_name(self, class_id):
		"""특정 클래스 ID의 이름 반환"""
		for c in self.classes:
			if c['id'] == class_id:
				return c['name']
		return f"Unknown({class_id})"  # 찾지 못한 경우

	def get_button_configs(self):
		"""버튼 생성에 필요한 정보 반환 [(name, id, key), ...] - key가 설정된 클래스만"""
		return [
			(c['name'], c['id'], normalize_shortcut_key(c.get('key')))
			for c in self.classes
			if normalize_shortcut_key(c.get('key'))
		]

# 클래스 필터 관리 클래스
class ClassFilterManager:
	def __init__(self):
		self.visible_classes = set()  # 표시할 클래스 ID 집합 (비어있으면 전체 표시)
		self.filter_enabled = False  # 필터 활성화 여부

	def set_visible_classes(self, class_ids):
		"""표시할 클래스 ID 목록 설정"""
		self.visible_classes = set(class_ids) if class_ids else set()
		self.filter_enabled = len(self.visible_classes) > 0
		print(f"[FILTER DEBUG] set_visible_classes() called")
		print(f"[FILTER DEBUG] Filter enabled: {self.filter_enabled}")
		print(f"[FILTER DEBUG] Visible classes: {sorted(self.visible_classes)}")

	def is_class_visible(self, class_id):
		"""특정 클래스가 표시 대상인지 확인"""
		if not self.filter_enabled:
			return True  # 필터 비활성화 시 모두 표시
		result = class_id in self.visible_classes
		# 디버깅: 필터링된 클래스만 로그 출력
		if not result:
			print(f"[FILTER DEBUG] Class {class_id} is HIDDEN by filter")
		return result

	def clear_filter(self):
		"""필터 초기화 (전체 표시)"""
		self.visible_classes.clear()
		self.filter_enabled = False
		print(f"[FILTER DEBUG] clear_filter() called - Filter disabled, all classes visible")

	def get_visible_classes(self):
		"""현재 표시 중인 클래스 ID 목록 반환"""
		return list(self.visible_classes)

	def is_filter_active(self):
		"""필터가 활성화되어 있는지 확인"""
		return self.filter_enabled

def normalize_shortcut_key(key):
	"""Return a Tk bind sequence for supported shortcut text."""
	if key is None:
		return None
	key = str(key).strip()
	if not key:
		return None
	if len(key) == 1:
		return key

	if key.startswith('<') and key.endswith('>'):
		return key

	compact = key.replace(' ', '')
	lower_key = compact.lower()

	named_keys = {
		'enter': '<Return>',
		'return': '<Return>',
		'tab': '<Tab>',
		'esc': '<Escape>',
		'escape': '<Escape>',
		'space': '<space>',
		'delete': '<Delete>',
		'del': '<Delete>',
		'backspace': '<BackSpace>',
		'up': '<Up>',
		'down': '<Down>',
		'left': '<Left>',
		'right': '<Right>',
		'plus': '+',
		'minus': '-',
	}
	if lower_key in named_keys:
		return named_keys[lower_key]

	if lower_key.startswith('f') and lower_key[1:].isdigit():
		return f"<F{lower_key[1:]}>"

	if '+' in compact:
		parts = [part for part in compact.split('+') if part]
		if len(parts) < 2:
			return None
		modifier_map = {
			'ctrl': 'Control',
			'control': 'Control',
			'shift': 'Shift',
			'alt': 'Alt',
			'option': 'Alt',
		}
		modifiers = []
		for part in parts[:-1]:
			modifier = modifier_map.get(part.lower())
			if not modifier:
				return None
			if modifier not in modifiers:
				modifiers.append(modifier)

		key_part = parts[-1]
		key_part_lower = key_part.lower()
		if key_part_lower in named_keys:
			key_part = named_keys[key_part_lower].strip('<>')
		elif key_part_lower.startswith('f') and key_part_lower[1:].isdigit():
			key_part = f"F{key_part_lower[1:]}"
		elif len(key_part) != 1:
			return None

		return '<' + '-'.join(modifiers + [key_part]) + '>'

	return None

def is_simple_shortcut_key(key):
	return bool(key and len(str(key)) == 1)

# 클래스 설정 다이얼로그
class ClassConfigDialog:
	def __init__(self, parent, config_manager=None):
		print(f"[DEBUG] ClassConfigDialog.__init__ 호출")
		print(f"[DEBUG] 받은 config_manager: {config_manager}")
		if config_manager:
			print(f"[DEBUG] config_manager.base_dir: {config_manager.base_dir}")

		self.result = None
		self.config_filename = None
		self.config_manager = config_manager
		self.dialog = tk.Toplevel(parent)
		self.dialog.title("클래스 설정")
		self.dialog.geometry("650x600")
		self.dialog.transient(parent)
		self.dialog.grab_set()

		# 기본 색상 리스트
		self.default_colors = [
			'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'cyan', 'magenta',
			'lime', 'pink', 'teal', 'lavender', 'brown', 'beige', 'maroon', 'mint',
			'olive', 'coral', 'navy', 'grey', 'white', 'salmon', 'gold', 'turquoise',
			'violet', 'indigo', 'tan', 'khaki', 'plum', 'orchid', 'sienna', 'crimson'
		]

		# 클래스 엔트리 리스트
		self.class_entries = []

		# 상단 설명
		info_label = tk.Label(self.dialog, text="클래스 설정 (최대 80개까지 설정 가능)", font=("Arial", 12, "bold"))
		info_label.pack(pady=10)

		# 파일명 입력 프레임
		filename_frame = tk.Frame(self.dialog)
		filename_frame.pack(fill=tk.X, padx=20, pady=5)

		tk.Label(filename_frame, text="설정 파일명:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
		self.filename_entry = tk.Entry(filename_frame, width=30)
		self.filename_entry.pack(side=tk.LEFT, padx=5)
		self.filename_entry.insert(0, "class_config")

		tk.Label(filename_frame, text=".json", font=("Arial", 10)).pack(side=tk.LEFT)

		# 기존 설정 로드 버튼
		if config_manager:
			load_btn = tk.Button(filename_frame, text="기존 설정 로드", command=self.load_existing_config, bd=1)
			load_btn.pack(side=tk.LEFT, padx=10)

		# 백업 옵션 프레임
		backup_frame = tk.Frame(self.dialog)
		backup_frame.pack(fill=tk.X, padx=20, pady=5)

		self.enable_backup_var = tk.BooleanVar()
		self.enable_backup_var.set(config_manager.enable_backup if config_manager else True)
		self.backup_checkbox = tk.Checkbutton(
			backup_frame,
			text="오리지널 백업 활성화 (original_backup 폴더에 백업)",
			variable=self.enable_backup_var,
			font=("Arial", 10)
		)
		self.backup_checkbox.pack(side=tk.LEFT, padx=5)

		# 스크롤 가능한 프레임
		canvas = tk.Canvas(self.dialog)
		scrollbar = tk.Scrollbar(self.dialog, orient="vertical", command=canvas.yview)
		scrollable_frame = tk.Frame(canvas)

		scrollable_frame.bind(
			"<Configure>",
			lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
		)

		canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
		canvas.configure(yscrollcommand=scrollbar.set)

		# 마우스 휠 스크롤 바인딩
		def on_mousewheel(event):
			canvas.yview_scroll(int(-1*(event.delta/120)), "units")
		canvas.bind_all("<MouseWheel>", on_mousewheel)

		# 헤더
		header_frame = tk.Frame(scrollable_frame)
		header_frame.pack(fill=tk.X, padx=10, pady=5)
		tk.Label(header_frame, text="번호", width=5).pack(side=tk.LEFT)
		tk.Label(header_frame, text="클래스 이름", width=20).pack(side=tk.LEFT, padx=5)
		tk.Label(header_frame, text="단축키", width=10).pack(side=tk.LEFT, padx=5)
		tk.Label(header_frame, text="색상", width=10).pack(side=tk.LEFT, padx=5)

		# 80개의 클래스 입력 필드 생성
		for i in range(80):
			self.add_class_entry(scrollable_frame, i)

		canvas.pack(side="left", fill="both", expand=True, padx=10)
		scrollbar.pack(side="right", fill="y")

		# 하단 버튼
		button_frame = tk.Frame(self.dialog)
		button_frame.pack(side=tk.BOTTOM, pady=10)

		tk.Button(button_frame, text="저장", command=self.save, width=10).pack(side=tk.LEFT, padx=5)
		tk.Button(button_frame, text="취소", command=self.cancel, width=10).pack(side=tk.LEFT, padx=5)

		# 다이얼로그 중앙에 배치
		self.dialog.update_idletasks()
		x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
		y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
		self.dialog.geometry(f"+{x}+{y}")

	def add_class_entry(self, parent, index):
		frame = tk.Frame(parent)
		frame.pack(fill=tk.X, padx=10, pady=2)

		# 번호 레이블
		tk.Label(frame, text=str(index), width=5).pack(side=tk.LEFT)

		# 클래스 이름 입력
		name_entry = tk.Entry(frame, width=20)
		name_entry.pack(side=tk.LEFT, padx=5)

		# 단축키 입력
		key_entry = tk.Entry(frame, width=10)
		key_entry.pack(side=tk.LEFT, padx=5)
		if index < 9:
			key_entry.insert(0, str(index + 1))

		# 색상 선택
		color_var = tk.StringVar(value=self.default_colors[index % len(self.default_colors)])

		# 색상 표시 레이블 (색상 샘플)
		color_display = tk.Label(frame, text="  ", width=3, relief=tk.RAISED, bd=1)
		color_display.pack(side=tk.LEFT, padx=2)

		# 초기 색상 설정
		try:
			color_display.config(bg=color_var.get())
		except:
			color_display.config(bg='white')

		# 색상 메뉴
		color_menu = tk.OptionMenu(frame, color_var, *self.default_colors,
									command=lambda c, disp=color_display: self.update_color_display(disp, c))
		color_menu.config(width=8)
		color_menu.pack(side=tk.LEFT, padx=5)

		self.class_entries.append({
			'name': name_entry,
			'key': key_entry,
			'color': color_var,
			'color_display': color_display
		})

	def update_color_display(self, color_display, color_name):
		"""색상 표시 레이블 업데이트"""
		try:
			color_display.config(bg=color_name)
		except:
			color_display.config(bg='white')

	def load_existing_config(self):
		"""기존 설정 파일 로드"""
		print(f"[DEBUG] load_existing_config 호출")
		print(f"[DEBUG] self.config_manager: {self.config_manager}")

		if not self.config_manager:
			print(f"[DEBUG] config_manager가 None입니다!")
			return

		print(f"[DEBUG] config_manager.base_dir: {self.config_manager.base_dir}")
		available_configs = self.config_manager.get_available_configs()
		print(f"[DEBUG] load_existing_config에서 받은 available_configs: {available_configs}")

		if not available_configs:
			messagebox.showinfo("정보", "기존 설정 파일이 없습니다.")
			return

		# 설정 파일 선택 다이얼로그
		select_dialog = tk.Toplevel(self.dialog)
		select_dialog.title("설정 파일 선택")
		select_dialog.geometry("400x300")
		select_dialog.transient(self.dialog)
		select_dialog.grab_set()

		tk.Label(select_dialog, text="로드할 설정 파일을 선택하세요:", font=("Arial", 10, "bold")).pack(pady=10)

		# 리스트박스
		listbox_frame = tk.Frame(select_dialog)
		listbox_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

		scrollbar = tk.Scrollbar(listbox_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

		listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set)
		listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		scrollbar.config(command=listbox.yview)

		for config_file in available_configs:
			listbox.insert(tk.END, config_file)

		selected_file = [None]

		def on_select():
			selection = listbox.curselection()
			if selection:
				selected_file[0] = listbox.get(selection[0])
				select_dialog.destroy()

		def on_cancel():
			select_dialog.destroy()

		btn_frame = tk.Frame(select_dialog)
		btn_frame.pack(pady=10)
		tk.Button(btn_frame, text="로드", command=on_select, width=10).pack(side=tk.LEFT, padx=5)
		tk.Button(btn_frame, text="취소", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)

		select_dialog.wait_window()

		if selected_file[0]:
			# 선택한 파일 로드
			temp_manager = ClassConfigManager()
			if temp_manager.load_config(selected_file[0]):
				# 파일명 업데이트
				filename = selected_file[0].replace('.json', '')
				self.filename_entry.delete(0, tk.END)
				self.filename_entry.insert(0, filename)

				# 클래스 정보로 필드 채우기
				for i, entry in enumerate(self.class_entries):
					entry['name'].delete(0, tk.END)
					entry['key'].delete(0, tk.END)

					if i < len(temp_manager.classes):
						cls = temp_manager.classes[i]
						entry['name'].insert(0, cls['name'])
						if cls.get('key'):
							entry['key'].insert(0, cls['key'])
						entry['color'].set(cls['color'])
						# 색상 표시 업데이트
						try:
							entry['color_display'].config(bg=cls['color'])
						except:
							pass
			else:
				messagebox.showerror("오류", f"설정 파일 로드 실패: {selected_file[0]}")

	def save(self):
		classes = []
		used_keys = set()

		# 파일명 검증
		filename = self.filename_entry.get().strip()
		if not filename:
			messagebox.showwarning("경고", "설정 파일명을 입력하세요.")
			return

		# .json 확장자 제거 (자동으로 추가됨)
		if filename.endswith('.json'):
			filename = filename[:-5]

		for i, entry in enumerate(self.class_entries):
			name = entry['name'].get().strip()
			key = entry['key'].get().strip()
			color = entry['color'].get()

			# 빈 이름은 건너뛰기
			if not name:
				continue

			# 단축키 중복 체크
			normalized_key = normalize_shortcut_key(key)
			if key and not normalized_key:
				messagebox.showwarning(
					"경고",
					f"지원하지 않는 단축키 형식입니다: {key}\n"
					"예: 1, a, <F1>, Ctrl+J, Shift+A, Space"
				)
				return
			if normalized_key and normalized_key in used_keys:
				messagebox.showwarning("경고", f"단축키 '{normalized_key}'가 중복됩니다.")
				return

			if normalized_key:
				used_keys.add(normalized_key)

			classes.append({
				'id': i,
				'name': name,
				'key': normalized_key if normalized_key else None,
				'color': color
			})

		if not classes:
			messagebox.showwarning("경고", "최소 1개 이상의 클래스를 설정해야 합니다.")
			return

		self.result = classes
		self.config_filename = filename + '.json'
		# 백업 설정 저장
		self.enable_backup_result = self.enable_backup_var.get() if hasattr(self, 'enable_backup_var') else True
		print(f"[ClassConfig] 백업 설정 저장: {self.enable_backup_result}")
		self.dialog.destroy()

	def cancel(self):
		self.result = None
		self.config_filename = None
		self.enable_backup_result = True
		self.dialog.destroy()

	def show(self):
		self.dialog.wait_window()
		enable_backup = self.enable_backup_result if hasattr(self, 'enable_backup_result') else True
		return (self.result, self.config_filename, enable_backup)

# 기본 클래스 이름 (클래스 설정 파일을 사용하지 않을 경우의 기본값)
class_name = [ 'person', 'Slip', 'head', 'Helmet', 'GasMask', 'Drum', 'car', 'bus', 'truck', 'forklift', 'motorcycle','chair','backpack','bird','animal','etc']

anchor_name = ['nw','n','ne','e','se','s','sw','w']
class_color = [
	['person' ,'slip','head'  ,'helmet','car' ,'truck','bus',"forklift","animal"],
	['magenta','blue','yellow','cyan'  ,'green'   ,'orange'   ,'white','green','yellow']
]
anchor_color = { 'magenta':'yellow', 'yellow':'red', 'blue':'yellow', 'cyan':'red' , 'white':'black','green':'yellow'}
judge_criteria = ['TP', 'FP']
judge_string = [['NA', 'black'], ['TP','blue'], ['FP','red']]
keysetting = ['0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','25','26','27','28','29','30','31','32','33','34','35','36','37','38','39','40']

def get_list_jpg(_dir):
	if not os.path.exists(_dir): os.makedirs(_dir)
	return sort_image_paths([os.path.join(_dir, f) for f in os.listdir(_dir) if is_image_file(f)])

def win_long_path(path):
	"""Windows 경로 길이(260자) 제한을 넘는 백업 경로도 쓸 수 있도록 확장 경로 접두사를 붙인다 (다른 OS는 그대로)."""
	if os.name != 'nt' or not path:
		return path
	path = os.path.abspath(path)
	if path.startswith('\\\\?\\'):
		return path
	if path.startswith('\\\\'):
		return '\\\\?\\UNC\\' + path[2:]
	return '\\\\?\\' + path

class FileSafetyManager:
	def __init__(self, base_dir):
		self.base_dir = base_dir

	def get_backup_path(self, source_path, category):
		source_abs = os.path.abspath(source_path)
		base_abs = os.path.abspath(self.base_dir)
		try:
			rel_path = os.path.relpath(source_abs, base_abs)
			if rel_path == '..' or rel_path.startswith('..' + os.sep) or os.path.isabs(rel_path):
				raise ValueError
		except ValueError:
			drive, tail = os.path.splitdrive(source_abs)
			drive_name = re.sub(r'[\\/:]+', '_', drive).strip('_') or 'root'
			rel_path = os.path.join('_external', drive_name, tail.lstrip('\\/'))
		backup_path = os.path.join(self.base_dir, 'original_backup', category, rel_path)
		if os.path.normcase(os.path.abspath(backup_path)) == os.path.normcase(source_abs):
			raise ValueError(f"backup path equals source: {source_abs}")
		backup_path = win_long_path(backup_path)
		os.makedirs(os.path.dirname(backup_path), exist_ok=True)
		return backup_path

	def backup_file(self, source_path, category):
		if not source_path or not os.path.exists(source_path):
			return True
		backup_path = self.get_backup_path(source_path, category)
		if os.path.exists(backup_path):
			return True
		try:
			shutil.copy2(source_path, backup_path)
			return os.path.exists(backup_path)
		except Exception as e:
			print(f"[Backup] Failed to backup {source_path}: {e}")
			return False

	def backup_pair(self, image_path, label_path=None):
		if not self.backup_file(image_path, 'JPEGImages'):
			return False
		if label_path and not self.backup_file(label_path, 'labels'):
			return False
		return True

	def write_backup_text_if_missing(self, source_path, category, lines):
		backup_path = self.get_backup_path(source_path, category)
		if os.path.exists(backup_path):
			return True
		try:
			with open(backup_path, 'w', encoding='utf-8') as f:
				f.writelines(lines)
			return os.path.exists(backup_path)
		except Exception as e:
			print(f"[Backup] Failed to write backup text {source_path}: {e}")
			return False

	def replace_files_transaction(self, replacements):
		originals = {}
		replaced = []
		try:
			for target_path in replacements:
				if os.path.exists(target_path):
					with open(target_path, 'rb') as f:
						originals[target_path] = f.read()
				else:
					originals[target_path] = None

			for target_path, temp_path in replacements.items():
				os.replace(temp_path, target_path)
				replaced.append(target_path)
			return True
		except Exception as e:
			print(f"[Transaction] Replace failed: {e}")
			for target_path in reversed(replaced):
				try:
					original = originals.get(target_path)
					if original is None:
						if os.path.exists(target_path):
							os.remove(target_path)
					else:
						with open(target_path, 'wb') as f:
							f.write(original)
				except Exception as rollback_error:
					print(f"[Transaction] Rollback failed for {target_path}: {rollback_error}")
			for temp_path in replacements.values():
				try:
					if os.path.exists(temp_path):
						os.remove(temp_path)
				except Exception:
					pass
			return False

	def write_text_files_transaction(self, file_text_map, backup_category='labels', enable_backup=True):
		replacements = {}
		try:
			for target_path, text in file_text_map.items():
				if enable_backup and not self.backup_file(target_path, backup_category):
					print(f"[Transaction] Backup failed: {target_path}")
					return False
				target_dir = os.path.dirname(target_path)
				if target_dir and not os.path.exists(target_dir):
					os.makedirs(target_dir)
				temp_path = target_path + '.tmp_gtgen'
				with open(temp_path, 'w', encoding='utf-8') as f:
					f.write(text)
				replacements[target_path] = temp_path
			return self.replace_files_transaction(replacements)
		except Exception as e:
			print(f"[Transaction] Prepare failed: {e}")
			for temp_path in replacements.values():
				try:
					if os.path.exists(temp_path):
						os.remove(temp_path)
				except Exception:
					pass
			return False

class MaskLabelManager:
	def read_label_lines(self, label_path):
		if not os.path.exists(label_path):
			return []
		try:
			with open(label_path, 'r', encoding='utf-8') as f:
				return f.readlines()
		except UnicodeDecodeError:
			with open(label_path, 'r', encoding='cp949') as f:
				return f.readlines()

	def bbox_overlaps_mask_pixels(self, x1, y1, x2, y2, mask, frame_width, frame_height):
		if mask is None or len(mask) < 2 or len(mask[0]) == 0:
			return False

		min_x = int(max(0, min(x1, x2)))
		max_x = int(min(frame_width, max(x1, x2)))
		min_y = int(max(0, min(y1, y2)))
		max_y = int(min(frame_height, max(y1, y2)))

		if max_x <= min_x or max_y <= min_y:
			return False

		mask_y, mask_x = mask
		overlap = (
			(mask_x >= min_x) & (mask_x < max_x) &
			(mask_y >= min_y) & (mask_y < max_y)
		)
		return bool(np.any(overlap))

	def filter_label_lines_by_mask(self, label_path, image_width, image_height, mask):
		labels_to_keep = []
		lines = self.read_label_lines(label_path)
		deleted_label_count = 0

		for line in lines:
			values = line.strip().split()
			if len(values) < 5:
				labels_to_keep.append(line)
				continue
			try:
				_, cx, cy, w, h = map(float, values[:5])
			except ValueError:
				labels_to_keep.append(line)
				continue

			abs_x1 = int((cx - w / 2) * image_width)
			abs_y1 = int((cy - h / 2) * image_height)
			abs_x2 = int((cx + w / 2) * image_width)
			abs_y2 = int((cy + h / 2) * image_height)

			if self.bbox_overlaps_mask_pixels(abs_x1, abs_y1, abs_x2, abs_y2, mask, image_width, image_height):
				deleted_label_count += 1
			else:
				labels_to_keep.append(line)

		return labels_to_keep, len(lines), deleted_label_count

class IouTrackManager:
	def get_label_path_for_image(self, image_path):
		return image_to_label_path(image_path)

	def calc_iou(self, box_a, box_b):
		ax1, ay1, ax2, ay2 = box_a
		bx1, by1, bx2, by2 = box_b
		ax1, ax2 = min(ax1, ax2), max(ax1, ax2)
		ay1, ay2 = min(ay1, ay2), max(ay1, ay2)
		bx1, bx2 = min(bx1, bx2), max(bx1, bx2)
		by1, by2 = min(by1, by2), max(by1, by2)

		inter_x1 = max(ax1, bx1)
		inter_y1 = max(ay1, by1)
		inter_x2 = min(ax2, bx2)
		inter_y2 = min(ay2, by2)
		inter_w = max(0.0, inter_x2 - inter_x1)
		inter_h = max(0.0, inter_y2 - inter_y1)
		inter_area = inter_w * inter_h
		if inter_area <= 0:
			return 0.0

		area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
		area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
		union = area_a + area_b - inter_area
		if union <= 0:
			return 0.0
		return inter_area / union

	def load_label_records(self, image_path):
		label_path = self.get_label_path_for_image(image_path)
		records = []
		try:
			with Image.open(image_path) as img:
				width, height = img.size
		except Exception as e:
			print(f"[IOUTrack] Failed to read image size: {image_path}, {e}")
			return records, label_path

		if not os.path.exists(label_path):
			return records, label_path

		try:
			with open(label_path, 'r', encoding='utf-8') as f:
				lines = f.readlines()
		except UnicodeDecodeError:
			with open(label_path, 'r', encoding='cp949') as f:
				lines = f.readlines()
		except Exception as e:
			print(f"[IOUTrack] Failed to read labels: {label_path}, {e}")
			return records, label_path

		for line_index, line in enumerate(lines):
			parts = line.strip().split()
			if len(parts) < 5:
				continue
			try:
				class_id = int(float(parts[0]))
				cx, cy, w, h = [float(v) for v in parts[1:5]]
			except ValueError:
				continue

			x1 = (cx - w / 2.0) * width
			y1 = (cy - h / 2.0) * height
			x2 = (cx + w / 2.0) * width
			y2 = (cy + h / 2.0) * height
			records.append({
				'line_index': line_index,
				'class_id': class_id,
				'line': line if line.endswith('\n') else line + '\n',
				'box': [x1, y1, x2, y2],
			})

		return records, label_path

	def track(self, imlist, gt_fn, start_idx, end_idx, selected_box, selected_class_id,
			selected_label_line, selected_bbox_index, iou_threshold, same_class_only, max_missing=2):
		prev_box = selected_box
		missing_count = 0
		result = {
			'start_idx': start_idx,
			'end_idx': end_idx,
			'threshold': iou_threshold,
			'same_class_only': same_class_only,
			'class_id': selected_class_id,
			'matches': [{
				'frame_idx': start_idx,
				'image_path': imlist[start_idx],
				'label_path': gt_fn,
				'bbox_index': selected_bbox_index,
				'line_index': selected_bbox_index,
				'line': selected_label_line,
				'iou': 1.0,
				'box': prev_box,
			}],
			'missing': [],
			'stopped': False,
		}

		for frame_idx in range(start_idx + 1, end_idx + 1):
			image_path = imlist[frame_idx]
			records, label_path = self.load_label_records(image_path)
			candidates = [
				record for record in records
				if (not same_class_only or record['class_id'] == selected_class_id)
			]

			best_record = None
			best_iou = 0.0
			for record in candidates:
				iou = self.calc_iou(prev_box, record['box'])
				if iou > best_iou:
					best_iou = iou
					best_record = record

			if best_record is not None and best_iou >= iou_threshold:
				result['matches'].append({
					'frame_idx': frame_idx,
					'image_path': image_path,
					'label_path': label_path,
					'bbox_index': best_record['line_index'],
					'line_index': best_record['line_index'],
					'line': best_record['line'],
					'iou': best_iou,
					'box': best_record['box'],
				})
				prev_box = best_record['box']
				missing_count = 0
			else:
				result['missing'].append({
					'frame_idx': frame_idx,
					'image_path': image_path,
					'label_path': label_path,
					'best_iou': best_iou,
				})
				missing_count += 1
				if missing_count > max_missing:
					result['stopped'] = True
					break

		return result

	def build_keep_only_label_text(self, label_path, matched_line, matched_line_index,
			tracked_class_id, preserve_other_classes):
		matched_line = matched_line if matched_line.endswith('\n') else matched_line + '\n'
		if not preserve_other_classes:
			return matched_line

		try:
			with open(label_path, 'r', encoding='utf-8') as f:
				lines = f.readlines()
		except UnicodeDecodeError:
			with open(label_path, 'r', encoding='cp949') as f:
				lines = f.readlines()
		except FileNotFoundError:
			return matched_line
		except Exception as e:
			print(f"[IOUTrack] Failed to preserve labels from {label_path}: {e}")
			return matched_line

		output_lines = []
		matched_added = False
		for line_index, line in enumerate(lines):
			if line_index == matched_line_index:
				output_lines.append(matched_line)
				matched_added = True
				continue

			parts = line.strip().split()
			if len(parts) < 5:
				output_lines.append(line)
				continue
			try:
				class_id = int(float(parts[0]))
			except ValueError:
				output_lines.append(line)
				continue

			if class_id != tracked_class_id:
				output_lines.append(line)

		if not matched_added:
			output_lines.append(matched_line)
		return ''.join(output_lines)

class MainApp:
	maskingframewidth=0
	maskingframeheight=0
	is_masking_dirty = False  # 저장 필요 플래그
	original_img_array = None  # 원본 이미지 배열 (백업용)
	current_img_array = None   # 현재 작업중인 이미지 배열
	ci = 0
	pi = -1
	multi_selected = set()  # 다중 선택된 라벨 인덱스들
	multi_select_mode = False  # 다중 선택 모드 활성화 여부
	im_fn = None
	gt_fn = None
	imlist = []
	imsize = [-1, -1]
	master = None
	canvas = None
	bbox = []
	area = []
	bbox_resize_anchor = None
	bbox_add = False
	bbox_move_start_crop = None
	bbox_crop = False
	bbox_move = False
	bbox_masking = False
	mouse_masking = False
	s_region = False
	l_region = False
	bbox_move_start_pt = None
	selid = -1
	zoom_ratio = 1
	cross_line = False
	pre_rc = None
	_dir = None	
	CLASSIFY_TPFP=True
	masking = None
	viewclass = True
	crop_resize_anchor = None   # crop canvas 드래그 앵커 방향 ('nw','n','ne',...,'move')
	crop_transform = None       # crop canvas 좌표 변환 파라미터
	crop_was_dragged = False    # 드래그 발생 여부 (click vs drag 구분)
	crop_drag_last = None       # 이전 드래그 마우스 좌표 (move 계산용)
	crop_drag_active = False    # 드래그 중 update_crop_preview 재진입 방지 플래그
	onlyselect = False
	onlybox = True
	has_saved_masking = False	

	polygon_masking = False
	polygon_points = []
	temp_polygon_line = None
	is_polygon_closed = False
	show_polygon_points = True

	# 제외 영역 기능 변수
	exclusion_zone_mode = False  # 제외 영역 그리기 모드
	exclusion_zone_points = []  # 현재 그리고 있는 제외 영역의 점들
	exclusion_zone_draw_type = 'polygon'
	exclusion_zone_enabled = False  # 제외 영역 기능 활성화 여부

	def __init__(self, _dir):
		global _dir_goodbye
		self.file_safety_manager = FileSafetyManager(BASE_DIR)
		self.mask_label_manager = MaskLabelManager()
		self.iou_track_manager = IouTrackManager()
		self.loaded_list_file_path = None
		atexit.register(self.goodbye)

		# 클래스 설정 관리자 초기화
		self.class_config_manager = ClassConfigManager()

		# 클래스 필터 관리자 초기화
		self.class_filter_manager = ClassFilterManager()

		# 제외 영역 관리자 초기화
		self.exclusion_zone_manager = ExclusionZoneManager()
		# 제외 영역 활성화 상태 로드
		self.exclusion_zone_enabled = self.exclusion_zone_manager.load_enabled_state()
		print(f"[ExclusionZone] 기능 활성화 상태: {self.exclusion_zone_enabled}")

		# 클래스 변경 영역 관리자 초기화
		self.class_change_zone_manager = ClassChangeZoneManager()
		self.copy_region_manager = CopyRegionManager()
		self.copy_region_mode = False
		self.copy_region_points = []
		self.copy_region_source_lines = None
		self.class_change_zone_mode = False  # 클래스 변경 영역 그리기 모드
		self.class_change_zone_points = []  # 현재 그리고 있는 클래스 변경 영역의 점들
		self.class_change_zone_draw_type = 'polygon'
		self.class_change_zone_config = None  # 클래스 변경 영역 설정
		print(f"[ClassChangeZone] 클래스 변경 영역: {len(self.class_change_zone_manager.zones)}개")

		# 클래스 자동 삭제 관리자 초기화
		self.auto_delete_manager = AutoDeleteClassManager()
		if self.auto_delete_manager.delete_class_config:
			auto_classes = [f"ID{k}(auto)" for k, v in self.auto_delete_manager.delete_class_config.items() if v == "auto"]
			shortcut_classes = [f"ID{k}(g)" for k, v in self.auto_delete_manager.delete_class_config.items() if v == "shortcut"]
			all_config = auto_classes + shortcut_classes
			print(f"[AutoDelete] 자동 삭제 설정: {', '.join(all_config) if all_config else '없음'}")
		else:
			print(f"[AutoDelete] 자동 삭제 설정: 없음")

		# Pending changes 시스템 초기화 (캐시 업데이트 최적화)
		self.pending_operation_count = 0  # 현재 페이지에서 수행된 작업 수
		self.pending_deleted_labels = []  # 삭제된 라벨 정보 (빨간색 동그라미)
		self.pending_masked_labels = []   # 마스킹으로 변환된 라벨 정보 (노란색 동그라미)
		print("[CacheOptimization] Pending changes 시스템 초기화 완료")

		# 자동 복사 기능 초기화
		self.auto_copy_labels_enabled = False  # 라벨 자동 복사 활성화 여부
		self.auto_copy_masking_enabled = False  # 마스킹 자동 복사 활성화 여부
		self.prev_page_labels = None  # 이전 페이지의 라벨 정보
		self.prev_page_masking = None  # 이전 페이지의 마스킹 정보
		self.prev_page_polygon_points = None  # 이전 페이지의 폴리곤 포인트
		self.prev_page_masking_width = None  # 이전 페이지의 마스킹 너비
		self.prev_page_masking_height = None  # 이전 페이지의 마스킹 높이
		print("[AutoCopy] 자동 복사 기능 초기화 완료")

		# 연속 삭제 기능 초기화
		self.delete_count = 1  # 기본값: 1장 삭제
		print("[DeleteMode] 연속 삭제 기능 초기화 완료 - 기본값: 1장")

		# 메인 윈도우 초기 생성 (설정 다이얼로그를 띄우기 위해)
		self.master = tk.Tk()
		self.master.withdraw()  # 일시적으로 숨김

		# 클래스 설정 로드 또는 생성
		global class_name, class_color

		# 마지막으로 사용한 설정 파일 확인
		last_config = self.class_config_manager.load_last_config()
		config_loaded = False

		print(f"마지막 설정 파일: {last_config}")

		if last_config:
			# 파일 경로 설정 후 존재 여부 확인
			self.class_config_manager.set_config_file(last_config)
			if self.class_config_manager.config_exists():
				# 마지막 설정 파일이 존재하면 로드
				print(f"설정 파일 로드 중: {last_config}")
				config_loaded = self.class_config_manager.load_config(last_config)
				if config_loaded:
					print("✓ 설정 파일 로드 성공")
				else:
					print("✗ 설정 파일 로드 실패")
			else:
				print(f"설정 파일을 찾을 수 없음: {last_config}")

		if not config_loaded:
			print("설정 파일이 없습니다. 설정 다이얼로그를 표시합니다.")

			# 다이얼로그를 띄우기 위해 부모 윈도우를 잠깐 표시
			self.master.deiconify()
			self.master.update()

			# 설정 파일이 없으면 설정 다이얼로그 표시
			available_configs = self.class_config_manager.get_available_configs()

			# 다이얼로그 생성
			dialog = ClassConfigDialog(self.master, self.class_config_manager)
			dialog.dialog.focus_force()

			if available_configs:
				print(f"기존 설정 파일 발견: {available_configs}")
				# 기존 설정 파일이 있으면 선택 옵션 제공
				self.master.attributes('-topmost', True)  # 최상위 표시
				msg = "기존 설정 파일을 찾았습니다.\n\n새 설정을 만들려면 '예'를,\n기존 설정을 로드하려면 '아니오'를 선택하세요."
				create_new = messagebox.askyesno("클래스 설정", msg)
				self.master.attributes('-topmost', False)  # 최상위 해제

				if not create_new:
					# 기존 설정 로드 시도
					print("기존 설정 로드를 시도합니다...")
					dialog.load_existing_config()

					# 로드 후 config_loaded 확인
					if len(self.class_config_manager.classes) > 0:
						config_loaded = True
						print("✓ 기존 설정 로드 완료")
						# 로드 성공 시 다이얼로그 닫기
						dialog.dialog.destroy()
					else:
						print("로드된 설정이 없습니다. 새 설정을 입력하세요.")

			# config_loaded가 여전히 False면 다이얼로그에서 새 설정 입력받기
			if not config_loaded:
				print("새 설정을 입력하세요...")
				classes, config_filename, enable_backup = dialog.show()

				if classes is None:
					# 사용자가 취소한 경우 프로그램 종료
					print("클래스 설정이 취소되었습니다. 프로그램을 종료합니다.")
					self.master.destroy()
					sys.exit(0)

				# 설정 저장
				self.class_config_manager.save_config(classes, config_filename, enable_backup)
				print(f"클래스 설정이 저장되었습니다: {self.class_config_manager.config_file}")
				print(f"백업 설정: {'활성화' if enable_backup else '비활성화'}")

				# 저장한 설정 로드
				self.class_config_manager.load_config(config_filename)
				config_loaded = True

			# 다이얼로그 완료 후 부모 윈도우 다시 숨김
			self.master.withdraw()

		class_name = self.class_config_manager.get_class_names()
		class_color = self.class_config_manager.get_class_colors()

		# 클래스 이름 출력
		print("\n=== 로드된 클래스 설정 ===")
		print(f"설정 파일: {self.class_config_manager.get_config_filename()}")
		for i in range(len(class_name)):
			print(f"{i} == {class_name[i]}")
		print("========================\n")

		self.master.deiconify()  # 윈도우 다시 표시

		self.copied_label = None

		# 설정 파일 로드
		cfg = configparser.ConfigParser()
		cfg_path = os.path.join(BASE_DIR, 'config.ini')
		try:
			cfg.read(cfg_path, encoding='utf-8')
		except UnicodeDecodeError:
			cfg.read(cfg_path, encoding='cp949')
		default_config = {
			'Setting': {'NATPFP': 'False', 'SkipFrame': keysetting[0]},
			'BasicKeySetting': {
				'SkipLkey': keysetting[1], 'SkipRkey': keysetting[2],
				'Lkey': keysetting[3], 'Rkey': keysetting[4],
				'FirstPage': keysetting[5], 'LastPage': keysetting[6],
				'Reload': keysetting[7], 'Delete': keysetting[8],
				'Add': keysetting[9], 'Remove': keysetting[10],
				'ResizeDown': keysetting[11], 'ResizeUp': keysetting[12],
				'CopyKey': keysetting[13], 'ZoomIn': keysetting[14],
				'ZoomOut': keysetting[15], 'CrossLine': keysetting[16],
				'Help': keysetting[17], 'Crop': keysetting[28],
				'Masking': keysetting[29], 'Mmasking': keysetting[30],
				'MaskingSave': keysetting[31], 'LoadMasking': keysetting[32],
				'ReLoadBackup': keysetting[33], 'CopyLabeling': keysetting[36],
			},
			'SpecialKeySetting': {
				'NextRect': keysetting[18], 'PreRect': keysetting[19],
				'ReduceUp': keysetting[20], 'ReduceDown': keysetting[21],
				'ReduceRight': keysetting[22], 'ReduceLeft': keysetting[23],
				'IncreaseUp': keysetting[24], 'IncreaseDown': keysetting[25],
				'IncreaseRight': keysetting[26], 'IncreaseLeft': keysetting[27],
				'ViewClass': keysetting[34], 'OnlySelect': keysetting[35],
				'OnlyBox': keysetting[37],
			},
		}
		for section, values in default_config.items():
			if not cfg.has_section(section):
				cfg.add_section(section)
			for option, value in values.items():
				if not cfg.has_option(section, option):
					cfg.set(section, option, value)
		if not os.path.exists(cfg_path):
			with open(cfg_path, 'w', encoding='utf-8') as f:
				cfg.write(f)
			print(f"[Config] Default config.ini created: {cfg_path}")
		
		# TP/FP 분류 설정
		if(cfg.getboolean('Setting', 'NATPFP', fallback=False)):
			self.CLASSIFY_TPFP=True
		else:
			self.CLASSIFY_TPFP=False
		
		# 키 설정 로드
		keysetting[0]=cfg.get('Setting', 'SkipFrame', fallback=keysetting[0])
		keysetting[1]=cfg.get('BasicKeySetting', 'SkipLkey', fallback=keysetting[1])
		keysetting[2]=cfg.get('BasicKeySetting', 'SkipRkey', fallback=keysetting[2])
		keysetting[3]=cfg.get('BasicKeySetting', 'Lkey', fallback=keysetting[3])
		keysetting[4]=cfg.get('BasicKeySetting', 'Rkey', fallback=keysetting[4])
		keysetting[5]=cfg.get('BasicKeySetting', 'FirstPage', fallback=keysetting[5])
		keysetting[6]=cfg.get('BasicKeySetting', 'LastPage', fallback=keysetting[6])
		keysetting[7]=cfg.get('BasicKeySetting', 'Reload', fallback=keysetting[7])
		keysetting[8]=cfg.get('BasicKeySetting', 'Delete', fallback=keysetting[8])
		keysetting[9]=cfg.get('BasicKeySetting', 'Add', fallback=keysetting[9])
		keysetting[10]=cfg.get('BasicKeySetting', 'Remove', fallback=keysetting[10])
		keysetting[11]=cfg.get('BasicKeySetting', 'ResizeDown', fallback=keysetting[11])
		keysetting[12]=cfg.get('BasicKeySetting', 'ResizeUp', fallback=keysetting[12])
		keysetting[13]=cfg.get('BasicKeySetting', 'CopyKey', fallback=keysetting[13])
		keysetting[14]=cfg.get('BasicKeySetting', 'ZoomIn', fallback=keysetting[14])
		keysetting[15]=cfg.get('BasicKeySetting', 'ZoomOut', fallback=keysetting[15])
		keysetting[16]=cfg.get('BasicKeySetting', 'CrossLine', fallback=keysetting[16])
		keysetting[17]=cfg.get('BasicKeySetting', 'Help', fallback=keysetting[17])
		keysetting[18]=cfg.get('SpecialKeySetting', 'NextRect', fallback=keysetting[18])
		keysetting[19]=cfg.get('SpecialKeySetting', 'PreRect', fallback=keysetting[19])
		keysetting[20]=cfg.get('SpecialKeySetting', 'ReduceUp', fallback=keysetting[20])
		keysetting[21]=cfg.get('SpecialKeySetting', 'ReduceDown', fallback=keysetting[21])
		keysetting[22]=cfg.get('SpecialKeySetting', 'ReduceRight', fallback=keysetting[22])
		keysetting[23]=cfg.get('SpecialKeySetting', 'ReduceLeft', fallback=keysetting[23])
		keysetting[24]=cfg.get('SpecialKeySetting', 'IncreaseUp', fallback=keysetting[24])
		keysetting[25]=cfg.get('SpecialKeySetting', 'IncreaseDown', fallback=keysetting[25])
		keysetting[26]=cfg.get('SpecialKeySetting', 'IncreaseRight', fallback=keysetting[26])
		keysetting[27]=cfg.get('SpecialKeySetting', 'IncreaseLeft', fallback=keysetting[27])
		keysetting[28]=cfg.get('BasicKeySetting', 'Crop', fallback=keysetting[28])
		keysetting[29]=cfg.get('BasicKeySetting', 'Masking', fallback=keysetting[29])
		keysetting[30]=cfg.get('BasicKeySetting', 'Mmasking', fallback=keysetting[30])
		keysetting[31]=cfg.get('BasicKeySetting', 'MaskingSave', fallback=keysetting[31])
		keysetting[32]=cfg.get('BasicKeySetting', 'LoadMasking', fallback=keysetting[32])
		keysetting[33]=cfg.get('BasicKeySetting', 'ReLoadBackup', fallback=keysetting[33])
		keysetting[34]=cfg.get('SpecialKeySetting', 'ViewClass', fallback=keysetting[34])
		keysetting[35]=cfg.get('SpecialKeySetting', 'OnlySelect', fallback=keysetting[35])
		keysetting[36]=cfg.get('BasicKeySetting', 'CopyLabeling', fallback=keysetting[36])
		keysetting[37]=cfg.get('SpecialKeySetting', 'OnlyBox', fallback=keysetting[37])
		# keysetting[38]=cfg['BasicKeySetting']['ResetLabeling']  # 제거됨 - 위험한 기능

		# 버튼별 클래스 ID를 저장할 딕셔너리
		self.button_class_map = {}
		# zoom_ratio 명시적 초기화
		self.zoom_ratio = 1.0

		
		# == UI 레이아웃 구성 시작 ==
		
		# 1. 상단 슬라이더 프레임
		self.scroll_frame = tk.Frame(self.master, bd=0)
		self.scroll_frame.pack(side=tk.TOP, fill="x", padx=0, pady=0)
		
		# 슬라이더 정보 레이블
		self.slider_info = tk.Label(self.scroll_frame, text="0/0", width=8)
		self.slider_info.pack(side=tk.LEFT, padx=0)
		
		# 이미지 위치 슬라이더
		self.img_slider = tk.Scale(
			self.scroll_frame, 
			from_=1, 
			to=100,
			orient=tk.HORIZONTAL,
			label=None,
			showvalue=0,
			length=600,
			command=self.on_slider_change
		)
		self.img_slider.pack(side=tk.LEFT, fill="x", expand=True, padx=0)
		
		# 2. 버튼 프레임 - 스크롤 아래에 배치
		self.button_frame = tk.Frame(self.master, bd=0)
		self.button_frame.pack(side=tk.TOP, fill="x", padx=0, pady=1)
		
		# 버튼들 배치 - 버튼 프레임에 직접 추가
		self.frameLabel = tk.Label(self.button_frame, text="Frame:", bd=0)
		self.frameLabel.pack(side=tk.LEFT, padx=0)
		
		self.btnBack = tk.Button(self.button_frame, text="Back", command=self.back_frame, bd=1)
		self.btnBack.pack(side=tk.LEFT, padx=0)
		
		self.btnNext = tk.Button(self.button_frame, text="Next", command=self.next_frame, bd=1)
		self.btnNext.pack(side=tk.LEFT, padx=0)
		
		self.objectLabel = tk.Label(self.button_frame, text="Object:", bd=0)
		self.objectLabel.pack(side=tk.LEFT, padx=0)
		
		self.btnAdd = tk.Button(self.button_frame, text="Add", command=self.add_bbox_rc, bd=1)
		self.btnAdd.pack(side=tk.LEFT, padx=0)
		
		self.btnRemove = tk.Button(self.button_frame, text="Remove", command=self.remove_bbox_rc, bd=1)
		self.btnRemove.pack(side=tk.LEFT, padx=0)
		
		self.classLabel = tk.Label(self.button_frame, text="Class:", bd=0)
		self.classLabel.pack(side=tk.LEFT, padx=0)

		self.key_button_map = {}
		# 클래스 버튼 동적 생성
		self.class_buttons = []
		try:
			button_configs = self.class_config_manager.get_button_configs()
			print(f"[DEBUG] 버튼 생성 시작. button_configs 개수: {len(button_configs)}")
			for i, (name, class_id, key) in enumerate(button_configs):
				print(f"[DEBUG] 버튼 {i}: name={name}, class_id={class_id}, key={key}")
				btn = self.create_class_button(name, class_id, key)
				self.class_buttons.append(btn)
			print(f"[DEBUG] 버튼 생성 완료. 총 {len(self.class_buttons)}개")
		except Exception as e:
			print(f"[ERROR] 버튼 생성 중 오류: {e}")
			import traceback
			traceback.print_exc()

		# Load 관련 버튼들
		self.loadLabel = tk.Label(self.button_frame, text="Load:", bd=0)
		self.loadLabel.pack(side=tk.LEFT, padx=0)
		
		self.btnLoadFolder = tk.Button(self.button_frame, text="Open Folder", command=self.load_new_folder, bd=1)
		self.btnLoadFolder.pack(side=tk.LEFT, padx=0)
		
		self.btnLoadList = tk.Button(self.button_frame, text="Open List", command=self.load_new_list, bd=1)
		self.btnLoadList.pack(side=tk.LEFT, padx=0)

		self.sort_list_on_load_var = tk.BooleanVar()
		self.sort_list_on_load_var.set(True)
		self.chk_sort_list_on_load = tk.Checkbutton(
			self.button_frame,
			text="Sort List Fixed",
			variable=self.sort_list_on_load_var,
			state=tk.DISABLED
		)
		self.chk_sort_list_on_load.pack(side=tk.LEFT, padx=5)
		
		self.btnHelp = tk.Button(self.button_frame, text="Help", command=self.print_help, bd=1)
		self.btnHelp.pack(side=tk.RIGHT, padx=0)

		# 제외 영역 관련 버튼
		self.btnExclusionZone = tk.Button(self.button_frame, text="제외영역", command=self.manage_exclusion_zones, bd=1)
		self.btnExclusionZone.pack(side=tk.RIGHT, padx=2)

		# 클래스 변경 영역 버튼
		self.btnClassChangeZone = tk.Button(self.button_frame, text="클래스변경", command=self.manage_class_change_zones, bd=1)
		self.btnClassChangeZone.pack(side=tk.RIGHT, padx=2)

		# 클래스 자동 삭제 버튼
		self.btnAutoDelete = tk.Button(self.button_frame, text="자동삭제", command=self.manage_auto_delete_classes, bd=1)
		self.btnAutoDelete.pack(side=tk.RIGHT, padx=2)

		self.btnConfigClass = tk.Button(self.button_frame, text="클래스 설정", command=self.change_class_config, bd=1)
		self.btnConfigClass.pack(side=tk.RIGHT, padx=2)

		# 클래스 필터 버튼
		self.btnClassFilter = tk.Button(self.button_frame, text="클래스 필터", command=self.manage_class_filter, bd=1)
		self.btnClassFilter.pack(side=tk.RIGHT, padx=2)

		# 현재 설정 파일명 표시
		config_filename = self.class_config_manager.get_config_filename()
		self.configFileLabel = tk.Label(self.button_frame, text=f"[{config_filename}]", fg="blue", bd=0)
		self.configFileLabel.pack(side=tk.RIGHT, padx=5)

		self.show_size_info = tk.BooleanVar()
		self.show_size_info.set(False)  # 기본값은 표시하지 않음
		self.chk_show_size = tk.Checkbutton(
			self.button_frame, 
			text="Show Size", 
			variable=self.show_size_info,
			command=self.toggle_size_display
		)
		self.chk_show_size.pack(side=tk.LEFT, padx=5) # 체크박스 추가

		# 라벨 마스킹 모드 체크박스 추가
		self.label_to_mask_mode = tk.BooleanVar()
		self.label_to_mask_mode.set(False)  # 기본값은 비활성화
		self.chk_label_to_mask = tk.Checkbutton(
			self.button_frame, 
			text="Label→Mask", 
			variable=self.label_to_mask_mode
		)
		self.chk_label_to_mask.pack(side=tk.LEFT, padx=5) # 체크박스 추가

		# 마스킹 시 겹치는 라벨 삭제 옵션 추가
		self.remove_overlapping_labels = tk.BooleanVar()
		self.remove_overlapping_labels.set(False)  # 기본값은 비활성화
		self.chk_remove_labels = tk.Checkbutton(
			self.button_frame, 
			text="Mask→Del Labels", 
			variable=self.remove_overlapping_labels
		)
		self.chk_remove_labels.pack(side=tk.LEFT, padx=5) # 체크박스 추가

		self.show_polygon_points_var = tk.BooleanVar()
		self.show_polygon_points_var.set(True)  # 기본값은 점 표시
		self.chk_show_polygon_points = tk.Checkbutton(
			self.button_frame, 
			text="Show Poly Pts", 
			variable=self.show_polygon_points_var,
			command=self.toggle_polygon_points_display
		)
		self.chk_show_polygon_points.pack(side=tk.LEFT, padx=5)

		# 라벨 리스트 체크박스 추가
		self.show_label_list = tk.BooleanVar()
		self.chk_show_label_list = tk.Checkbutton(
			self.button_frame, 
			text="Show Label List", 
			variable=self.show_label_list,
			command=self.toggle_label_list_view
		)
		self.chk_show_label_list.pack(side=tk.LEFT, padx=5)

		# 클래스 이름 표시 체크박스
		self.show_class_name_var = tk.BooleanVar()
		self.show_class_name_var.set(True)  # viewclass 기본값 True
		self.chk_show_class_name = tk.Checkbutton(
			self.button_frame,
			text="Show Class",
			variable=self.show_class_name_var,
			command=self.toggle_class_name_display
		)
		self.chk_show_class_name.pack(side=tk.LEFT, padx=5)

		# 박스만 표시 체크박스
		self.show_only_box_var = tk.BooleanVar()
		self.show_only_box_var.set(True)  # onlybox 기본값 True
		self.chk_show_only_box = tk.Checkbutton(
			self.button_frame,
			text="Only Box",
			variable=self.show_only_box_var,
			command=self.toggle_only_box_display
		)
		self.chk_show_only_box.pack(side=tk.LEFT, padx=5)

		self.btnMultiClassSelect = tk.Button(
		self.button_frame,
		text="다중 클래스",
		command=self.implement_multi_class_selection,
		bd=1)
		self.btnMultiClassSelect.pack(side=tk.LEFT, padx=5)  # 다른 버튼들 옆에 배치

		self.chk_show_polygon_points.pack(side=tk.LEFT, padx=5)
		self.copy_functions_frame = tk.Frame(self.master, bd=1, relief=tk.RAISED)
		self.copy_functions_frame.pack(side=tk.TOP, fill="x", padx=5, pady=5)

		# ========== 1줄: 복사 기능 (마스킹 + 라벨) ==========
		self.copy_row_frame = tk.Frame(self.copy_functions_frame)
		self.copy_row_frame.pack(side=tk.TOP, padx=5, fill="x", expand=True, pady=2)

		# 마스킹 복사 섹션
		self.mask_copy_label = tk.Label(self.copy_row_frame, text="[마스킹]", bd=0, fg="blue")
		self.mask_copy_label.pack(side=tk.LEFT, padx=2)

		self.start_frame_label = tk.Label(self.copy_row_frame, text="시작:", bd=0)
		self.start_frame_label.pack(side=tk.LEFT, padx=1)

		self.start_frame_entry = tk.Entry(self.copy_row_frame, width=5)
		self.start_frame_entry.pack(side=tk.LEFT, padx=1)

		self.end_frame_label = tk.Label(self.copy_row_frame, text="종료:", bd=0)
		self.end_frame_label.pack(side=tk.LEFT, padx=1)

		self.end_frame_entry = tk.Entry(self.copy_row_frame, width=5)
		self.end_frame_entry.pack(side=tk.LEFT, padx=1)

		self.copy_masking_btn = tk.Button(self.copy_row_frame, text="실행", command=self.copy_masking_to_range, bd=1)
		self.copy_masking_btn.pack(side=tk.LEFT, padx=2)

		self.masking_dry_run_btn = tk.Button(self.copy_row_frame, text="Dry-run", command=self.preview_masking_delete_to_range, bd=1)
		self.masking_dry_run_btn.pack(side=tk.LEFT, padx=2)

		# 마스킹 자동복사 체크박스
		self.auto_copy_masking_var = tk.BooleanVar()
		self.auto_copy_masking_var.set(False)
		self.auto_copy_masking_chk = tk.Checkbutton(
			self.copy_row_frame,
			text="자동",
			variable=self.auto_copy_masking_var,
			command=self.toggle_auto_copy_masking
		)
		self.auto_copy_masking_chk.pack(side=tk.LEFT, padx=2)

		# 구분선
		tk.Label(self.copy_row_frame, text="|", fg="gray").pack(side=tk.LEFT, padx=5)

		# 라벨 복사 섹션
		tk.Label(self.copy_row_frame, text="[라벨]", bd=0, fg="blue").pack(side=tk.LEFT, padx=2)

		# 라벨 복사 UI를 담을 별도 프레임 생성 (update_label_copy_ui에서 파괴하지 않도록)
		self.label_copy_frame = tk.Frame(self.copy_row_frame)
		self.label_copy_frame.pack(side=tk.LEFT, fill="x", expand=True)
		self.update_label_copy_ui()

		# ========== 2줄: 기타 작업 (d키 삭제 + 범위삭제 + 이동) ==========
		self.actions_row_frame = tk.Frame(self.copy_functions_frame)
		self.actions_row_frame.pack(side=tk.TOP, padx=5, fill="x", expand=True, pady=2)

		# d키 삭제 섹션
		self.delete_mode_label = tk.Label(self.actions_row_frame, text="[d키삭제]", bd=0, fg="blue")
		self.delete_mode_label.pack(side=tk.LEFT, padx=2)

		self.delete_count_var = tk.IntVar()
		self.delete_count_var.set(1)

		self.rb_delete_1 = tk.Radiobutton(self.actions_row_frame, text="1장", variable=self.delete_count_var, value=1)
		self.rb_delete_1.pack(side=tk.LEFT, padx=1)

		self.rb_delete_5 = tk.Radiobutton(self.actions_row_frame, text="5장", variable=self.delete_count_var, value=5)
		self.rb_delete_5.pack(side=tk.LEFT, padx=1)

		self.rb_delete_10 = tk.Radiobutton(self.actions_row_frame, text="10장", variable=self.delete_count_var, value=10)
		self.rb_delete_10.pack(side=tk.LEFT, padx=1)

		self.rb_delete_custom = tk.Radiobutton(self.actions_row_frame, text="직접:", variable=self.delete_count_var, value=0)
		self.rb_delete_custom.pack(side=tk.LEFT, padx=1)

		self.delete_custom_entry = tk.Entry(self.actions_row_frame, width=5)
		self.delete_custom_entry.pack(side=tk.LEFT, padx=1)
		self.delete_custom_entry.insert(0, "1")

		# 구분선
		tk.Label(self.actions_row_frame, text="|", fg="gray").pack(side=tk.LEFT, padx=5)

		# 범위삭제 섹션
		self.delete_range_label = tk.Label(self.actions_row_frame, text="[범위삭제]", bd=0, fg="blue")
		self.delete_range_label.pack(side=tk.LEFT, padx=2)

		self.delete_start_frame_label = tk.Label(self.actions_row_frame, text="시작:", bd=0)
		self.delete_start_frame_label.pack(side=tk.LEFT, padx=1)

		self.delete_start_frame_entry = tk.Entry(self.actions_row_frame, width=5)
		self.delete_start_frame_entry.pack(side=tk.LEFT, padx=1)

		self.delete_end_frame_label = tk.Label(self.actions_row_frame, text="종료:", bd=0)
		self.delete_end_frame_label.pack(side=tk.LEFT, padx=1)

		self.delete_end_frame_entry = tk.Entry(self.actions_row_frame, width=5)
		self.delete_end_frame_entry.pack(side=tk.LEFT, padx=1)

		self.delete_range_btn = tk.Button(self.actions_row_frame, text="실행", command=self.delete_range, bd=1)
		self.delete_range_btn.pack(side=tk.LEFT, padx=2)

		# 구분선
		tk.Label(self.actions_row_frame, text="|", fg="gray").pack(side=tk.LEFT, padx=5)

		# 이동 섹션
		self.page_move_label = tk.Label(self.actions_row_frame, text="[이동]", bd=0, fg="blue")
		self.page_move_label.pack(side=tk.LEFT, padx=2)

		self.page_entry = tk.Entry(self.actions_row_frame, width=5)
		self.page_entry.pack(side=tk.LEFT, padx=1)

		self.page_move_btn = tk.Button(self.actions_row_frame, text="Go", command=self.move_to_page, bd=1)
		self.page_move_btn.pack(side=tk.LEFT, padx=2)

		# ========== 3줄: 시계열 IOU 추적 ==========
		self.track_row_frame = tk.Frame(self.copy_functions_frame)
		self.track_row_frame.pack(side=tk.TOP, padx=5, fill="x", expand=True, pady=2)

		self.track_label = tk.Label(self.track_row_frame, text="[IOU추적]", bd=0, fg="blue")
		self.track_label.pack(side=tk.LEFT, padx=2)

		self.track_range_label = tk.Label(self.track_row_frame, text="범위:", bd=0)
		self.track_range_label.pack(side=tk.LEFT, padx=1)

		self.track_range_entry = tk.Entry(self.track_row_frame, width=5)
		self.track_range_entry.pack(side=tk.LEFT, padx=1)
		self.track_range_entry.insert(0, "30")

		self.track_iou_label = tk.Label(self.track_row_frame, text="IOU:", bd=0)
		self.track_iou_label.pack(side=tk.LEFT, padx=1)

		self.track_iou_entry = tk.Entry(self.track_row_frame, width=5)
		self.track_iou_entry.pack(side=tk.LEFT, padx=1)
		self.track_iou_entry.insert(0, "0.20")

		self.track_same_class_var = tk.BooleanVar()
		self.track_same_class_var.set(True)
		self.track_same_class_chk = tk.Checkbutton(
			self.track_row_frame,
			text="동일클래스",
			variable=self.track_same_class_var
		)
		self.track_same_class_chk.pack(side=tk.LEFT, padx=2)

		self.track_preview_btn = tk.Button(self.track_row_frame, text="Preview", command=self.preview_iou_track, bd=1)
		self.track_preview_btn.pack(side=tk.LEFT, padx=2)

		self.track_keep_btn = tk.Button(self.track_row_frame, text="Keep Only", command=self.apply_iou_track_keep_only, bd=1)
		self.track_keep_btn.pack(side=tk.LEFT, padx=2)

		self.setup_label_list_ui()

		# 3. 캔버스 프레임 (스크롤바 포함)
		self.canvas_frame = tk.Frame(self.master)
		self.canvas_frame.pack(fill="both", expand=True)
		
		# 수직 스크롤바
		self.v_scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical")
		self.v_scrollbar.pack(side="right", fill="y")
		
		# 수평 스크롤바
		self.h_scrollbar = tk.Scrollbar(self.canvas_frame, orient="horizontal")
		self.h_scrollbar.pack(side="bottom", fill="x")
		
		# 캔버스 생성 및 스크롤바 연결
		self.canvas = tk.Canvas(
			self.canvas_frame, 
			width=100, 
			height=100,
			xscrollcommand=self.h_scrollbar.set,
			yscrollcommand=self.v_scrollbar.set
		)
		self.canvas.pack(side="left", fill="both", expand=True)
		
		# 스크롤바와 캔버스 연결
		self.v_scrollbar.config(command=self.canvas.yview)
		self.h_scrollbar.config(command=self.canvas.xview)
		
		# == UI 레이아웃 구성 종료 ==
		
		# 시작 시 자동으로 열기 창을 띄우지 않는다. Open Folder / Open List 버튼으로 데이터를 연다.
		_dir = None
		self.imlist = []

		self._dir = _dir
		_dir_goodbye = _dir
		self.setup_input_validation()
		self.setup_input_focus_handling()
		self.improve_key_bindings()

			# 초기에 캔버스에 포커스 설정
		self.canvas.focus_set()
		self.apply_modern_theme()

    # == UI 레이아웃 구성 시작 ==
		self.process()
		self.master.mainloop()        
		return
	def reset_data(self):
		self.ci = 0
		self.pi = -1
		self.im_fn = None
		self.gt_fn = None
		self.imlist = []
		self.bbox = []
		self.selid = -1
		self.canvas.delete("all")

	def load_images_from_folder(self, folder_path):
		"""폴더에서 이미지 파일들을 자동으로 로드"""
		try:
			# JPEGImages 폴더 확인
			jpeg_folder = os.path.join(folder_path, 'JPEGImages')
			if os.path.exists(jpeg_folder):
				search_path = jpeg_folder
			else:
				search_path = folder_path

			# 이미지 파일 찾기
			image_files = []

			for root, dirs, files in os.walk(search_path):
				for file in files:
					if is_image_file(file):
						full_path = os.path.join(root, file)
						image_files.append(full_path)

			# 자연스러운 정렬
			image_files = sort_image_paths(image_files)

			if len(image_files) == 0:
				print(f"[WARNING] 폴더에서 이미지 파일을 찾을 수 없습니다: {folder_path}")
				messagebox.showwarning("경고", "선택한 폴더에서 이미지 파일을 찾을 수 없습니다.")
				return

			# 이미지 리스트 설정
			self.imlist = image_files
			self.loaded_list_file_path = None
			self.folder_loaded = True
			print(f"[INFO] {len(image_files)}개의 이미지 파일을 로드했습니다.")

			# 첫 번째 이미지 로드
			if len(self.imlist) > 0:
				self.ci = 0
				self.draw_image()

		except Exception as e:
			print(f"[ERROR] 폴더에서 이미지 로드 중 오류: {e}")
			messagebox.showerror("오류", f"이미지 로드 중 오류가 발생했습니다:\n{e}")
		
	def get_directory(self):
		a = tk.Tk()
		a.withdraw()
		a.update()

		# 파일 또는 폴더 선택 다이얼로그
		# 먼저 파일 선택 시도
		_dir = tk.filedialog.askopenfile()

		# 파일을 선택하지 않은 경우 폴더 선택 제안
		if _dir is None:
			print("[INFO] 파일이 선택되지 않았습니다. 폴더를 선택하시겠습니까?")
			folder_path = tk.filedialog.askdirectory(title="이미지 폴더 선택")

			if folder_path:
				# 폴더가 선택된 경우 자동으로 이미지 리스트 생성
				print(f"[INFO] 폴더 선택됨: {folder_path}")
				self.load_images_from_folder(folder_path)
				a.destroy()
				return folder_path
			else:
				print("[DEBUG] 파일과 폴더 선택이 모두 취소되었습니다.")
				a.destroy()
				raise Exception("파일 선택이 취소되었습니다.")

		dirname = _dir.buffer.name
		fname, ext = os.path.splitext(_dir.buffer.name)
		framenum = 0
		if ext == '.txt':
			# 파일 내용을 자동 감지하여 처리 방식 결정
			# 첫 줄을 읽어서 이미지 경로인지 확인
			inputtype = "0"  # 기본값: 이미지 리스트 로드

			try:
				with open(dirname, 'r', encoding='utf-8') as f:
					first_line = f.readline().strip()
					# 첫 줄이 이미지 파일 경로가 아니면 XML 생성 모드로 추정
					# (하지만 기본적으로 이미지 리스트 로드 모드 사용)
					if first_line and not (first_line.endswith(('.jpg', '.png', '.jpeg', '.JPG', '.PNG'))):
						# 이미지 경로가 아닌 경우에도 일단 이미지 리스트로 시도
						pass
			except:
				pass

			# XML 생성은 별도 기능으로 분리 (사용자가 거의 사용하지 않음)
			# 필요시 메뉴나 명령줄 인자로 처리 가능
			if inputtype=="1":
				pathstr = os.path.split(dirname)
				dirstr = os.path.split(pathstr[0])
				savedir = os.path.split(dirstr[0])
				labellist = [pathstr[0] + '/' + f for f in natsort.natsorted(os.listdir(pathstr[0])) if f.find('.txt') >= 0]
				imgname = labellist[0].replace('labels','JPEGImages')
				imgname = imgname.replace('.txt','.jpg')
				if os.path.exists(imgname) is False: imgname = imgname.replace('.jpg','.png')
				image = cv2.imread(imgname, cv2.IMREAD_ANYCOLOR)
				height, width, channel = image.shape
				imgfilecnt=0
				savename = savedir[0]+'/'+dirstr[1]+'_ObjGT.xml'
				file=Element("File", ResolutionX=str(width), ResolutionY=str(height))
				while True:
					print(imgfilecnt)
					if imgfilecnt>len(labellist)-1:
						break
					fnametmp, exttmp = os.path.splitext(labellist[imgfilecnt])					
					framef = open(labellist[imgfilecnt])
					path = os.path.splitext(labellist[imgfilecnt])
					dir = os.path.split(path[0])
					framenum = dir[1].split('_')
					frame=Element("Frame", Frame_Num=str(int(framenum[len(framenum)-1])))
					objnumf = open(labellist[imgfilecnt])
					objnum=0
					for j in objnumf.readlines():
						objnum=objnum+1
					objnumf.close()
					numofobj=Element("NumofObj")
					numofobj.text=str(objnum)
					imgfilecnt=imgfilecnt+1
					firstappend = True
					errorfile = False
					for l in framef.readlines():
						try:
							gt = [float(c) for c in l.replace('\r','').replace('\n','').split(' ')]
						except:
							errorfile = True
							print("ERROR FILE : " + labellist[imgfilecnt-1])
							framef.close()
							os.remove(labellist[imgfilecnt-1])
							imagefile = labellist[imgfilecnt-1].replace('labels','JPEGImages')
							imagefile = imagefile.replace('.txt','.jpg')
							if os.path.exists(imagefile) is False: imagefile = imagefile.replace('.jpg','.png')
							if os.path.exists(imagefile) is True:
								os.remove(imagefile)
							break
						if firstappend is True:							
							file.append(frame)					
							frame.append(numofobj)
							firstappend = False
						object=Element("Object", Object_ID="1")
						frame.append(object)

						name = class_name[gt[0]]
						obj_type=Element("Obj_Type", Sub_type="No", Main_Type=name)
						# if gt[0]==0.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Person")
						# elif gt[0]==2.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Car")
						# elif gt[0]==5.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Bus")
						# elif gt[0]==7.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Truck")
						# elif gt[0]==56.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Chair")
						# elif gt[0]==8.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Boat")
						# elif gt[0]==6.0:		    
						# 	obj_type=Element("Obj_Type", Sub_type="No", Main_Type="Train")
						object.append(obj_type)	
						region=Element("Region", Height=str(int(gt[4]*height)), Width=str(int(gt[3]*width)), Top=str(int((gt[2]*height)-(gt[4]/2*height))), Left=str(int((gt[1]*width)-(gt[3]/2*width))))
						object.append(region)
						movingshape=Element("MovingShape")
						movingshape.text="No"
						object.append(movingshape)					
					if errorfile is False:
						framef.close()
				dump(file)
				print(savename)
				ElementTree(file).write(savename)
				time.sleep(2)				
				_dir = dirname.replace(".txt",".evaluation")
			if inputtype=="0":
				try:
					self.imlist, nofile, encoding = read_image_list_file(dirname)
				except Exception as e:
					print(f"[ListLoad] failed to read list file: {e}")
					a.destroy()
					return None
				self.imlist = sort_image_paths(self.imlist)
				print_missing_list_items(nofile)
				print(f"[ListLoad] loaded={len(self.imlist)}, missing={len(nofile)}, encoding={encoding}")
				if not self.imlist:
					print("[ListLoad] no valid images found in the list file.")
					a.destroy()
					return None
				encodings = []
				success = True

				for encoding in encodings:
					try:
						with open(dirname, "rt", encoding=encoding) as file:
							nofile = []
							self.imlist = []  # 리스트 초기화
							
							while True:
								line = file.readline()
								if not line:
									break
								line = line.strip().replace('/s_mnt/253/','//192.168.79.253/')
								print(f"{str(len(self.imlist))} : {line}")
								if os.path.exists(line):					
									self.imlist.append(line)
								else: 
									nofile.append(line)
							
							# 파일에 없는 경로 출력
							for nofilename in nofile:
								print(f"no file : {nofilename}")
							
							# 존재하는 파일만 다시 저장
							with open(dirname, "wt", encoding=encoding) as f:
								self.imlist = sort_image_paths(self.imlist)
								for existfilename in self.imlist:
									f.write(to_list_file_path(existfilename))
							
							success = True
							print(f"파일을 성공적으로 로드했습니다. 사용된 인코딩: {encoding}")
							break  # 성공적인 인코딩을 찾았으므로 루프 종료
						
					except UnicodeDecodeError:
						# 인코딩 오류 발생 시 다음 인코딩 시도
						print(f"인코딩 {encoding}으로 읽기 실패, 다음 인코딩 시도 중...")
						continue
					except Exception as e:
						# 기타 예외 발생 시 로그 출력 후 다음 인코딩 시도
						print(f"인코딩 {encoding}으로 읽는 중 오류 발생: {e}")
						continue
				
				if not success:
					print("지원되는 인코딩으로 파일을 읽을 수 없습니다.")
					a.destroy()
					return None
				self.CLASSIFY_TPFP=False
				self.loaded_list_file_path = dirname
				_dir = dirname
		elif not is_image_file(dirname):
			# 비디오 파일 처리 (기본 모드만 지원)
			capture = cv2.VideoCapture(dirname)
			pathstr = os.path.splitext(dirname)
			pathstr = os.path.split(pathstr[0])
			dirname = pathstr[0] + '/JPEGImages/' + pathstr[1]
			if not(os.path.isdir(pathstr[0] + '/JPEGImages/' + pathstr[1])):
				os.makedirs(os.path.join(pathstr[0] + '/JPEGImages/' + pathstr[1]))
				if not(os.path.isdir(pathstr[0] + '/labels/' + pathstr[1])):
					os.makedirs(os.path.join(pathstr[0] + '/labels/' + pathstr[1]))
				resizeflag = False
				if capture.get(cv2.CAP_PROP_FRAME_WIDTH) >= 1920:resizeflag = True
				elif capture.get(cv2.CAP_PROP_FRAME_HEIGHT) >= 1080:resizeflag = True

				# 프레임 스킵 자동 설정 (기본값: 1, 즉 모든 프레임 처리)
				# 사용자에게 입력 요청 없이 자동으로 진행
				frameskip = "1"  # 기본값: 모든 프레임 처리
				print(f"[INFO] 프레임 스킵: {frameskip} (자동 설정)")
				while True:
					ret, frame = capture.read()
					if ret == False:
						break
					framenum = framenum + 1
					firsttxt = False
					if (framenum % int(frameskip)) == 0:
						framestr = '%07d' % (framenum)
						imagename = pathstr[0] + '/JPEGImages/' + pathstr[1] + '/' + pathstr[1] + '_' + framestr + '.jpg'
						print(imagename)
						if resizeflag == True:frame = cv2.resize(frame,(1280,720))
						cv2.imwrite(imagename,frame)
						if (firsttxt == False):
							firsttxtfile = imagename.replace('JPEGImages','labels')
							firsttxtfile = firsttxtfile.replace('.jpg','.txt')
							firsttxtfile = firsttxtfile.replace('.png','.txt')
							f = open(firsttxtfile, 'w')
							f.close()
							firsttxt = True
				capture.release()
			else:
				print("Folder Exists.\n")
				time.sleep(3)
				sys.exit(0)
			_dir = pathstr[0]+'/JPEGImages/'+pathstr[1]
		else:
			_dir = os.path.dirname(fname)
		a.destroy()
		if _dir == None: sys.exit(0)
		return _dir

	def __del__(self):
		self.write_bbox()
		return
	
	def process(self):
		self.draw_image()
		self.draw_bbox()
		self.bind_event_handlers()
		self.canvas.pack()
		self.canvas.focus_set()
		return

	def get_current_criteria(self):
		c = 0 # 0 none, 1 TP, 2 FP
		a_path = os.path.abspath(self.im_fn).split('\\' if os.name == 'nt' else '/')
		c = judge_criteria.index(a_path[-2]) + 1 if a_path[-2] in judge_criteria else 0
		return c

	def draw_criteria(self):
		c = self.get_current_criteria()
		self.canvas.create_rectangle([10,10,40,25], fill=judge_string[c][1], outline='', tags='img')
		self.canvas.create_text([23,17], font='Arial\ Black 8', fill='white', text=judge_string[c][0], tags='img')
		return
	def get_last_open_dir(self):
		"""최근에 연 폴더/리스트 위치 (파일 대화상자 시작 위치)"""
		try:
			with open(os.path.join(BASE_DIR, '.last_open_path.txt'), 'r', encoding='utf-8') as f:
				path = f.read().strip()
			if os.path.isdir(path):
				return path
			if os.path.isdir(os.path.dirname(path)):
				return os.path.dirname(path)
		except OSError:
			pass
		return None

	def save_last_open_path(self, path):
		try:
			with open(os.path.join(BASE_DIR, '.last_open_path.txt'), 'w', encoding='utf-8') as f:
				f.write(str(path))
		except OSError as e:
			print(f"[Open] 최근 경로 저장 실패: {e}")

	def save_before_switching_data(self):
		"""다른 폴더/리스트를 열기 전에 현재 작업(라벨, 마스킹)을 저장"""
		if self.imlist and self.gt_fn:
			self.save_masking_if_dirty()
			self.write_bbox()

	def load_new_folder(self):
		try:
			new_dir = filedialog.askdirectory(parent=self.master, title="이미지 폴더 선택", initialdir=self.get_last_open_dir())
			if new_dir:  # 폴더가 선택된 경우
				jpeg_dir = os.path.join(new_dir, 'JPEGImages')
				search_dir = jpeg_dir if os.path.isdir(jpeg_dir) else new_dir
				images = []
				for root, dirs, files in os.walk(search_dir):
					images.extend(os.path.join(root, f) for f in files if is_image_file(f))
				if not images:
					messagebox.showwarning("폴더 열기", f"선택한 폴더(하위 폴더 포함)에서 이미지를 찾지 못했습니다.\n{new_dir}")
					return
				self.save_before_switching_data()
				self.reset_data()
				self.imlist = sort_image_paths(images)
				if self.CLASSIFY_TPFP:
					# TP/FP 판정용 라벨 폴더 생성 (JPEGImages 구조일 때만, 이미지 폴더 안에 만들지 않도록)
					if 'JPEGImages' in search_dir:
						labels_dir = search_dir.replace('JPEGImages','labels')
						os.makedirs(labels_dir + '/TP', exist_ok=True)
						os.makedirs(labels_dir + '/FP', exist_ok=True)
				else:
					# 각 이미지에 대한 라벨 파일 확인/생성
					for f in self.imlist:
						label = image_to_label_path(f)
						label = label.replace('/','\\')
						if os.path.exists(label) is False:
							pathstr = os.path.split(label)
							if os.path.isdir(pathstr[0]) is False:
								os.makedirs(os.path.join(pathstr[0]))
							flabel = open(label, "wt")
							flabel.close()
				self.loaded_list_file_path = None
				self.img_slider.config(to=len(self.imlist))
				self.img_slider.set(self.ci + 1)
				self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
				self._dir = new_dir
				self.save_last_open_path(new_dir)
				print(f"[Open] 폴더 {new_dir}: 이미지 {len(self.imlist)}개")
				self.draw_image()
				self.draw_bbox()
		except Exception as e:
			print(f"Error loading folder: {e}")
			messagebox.showerror("Error", f"Failed to load folder: {e}")
	def check_bbox_mask_overlap(self, mask_area, bbox):
		"""마스킹 영역과 바운딩 박스가 겹치는지 확인 (면적 기반)

		Args:
			mask_area: 마스킹 영역 [x1, y1, x2, y2] (뷰 좌표)
			bbox: 바운딩 박스 [sel, clsname, info, x1, y1, x2, y2]

		Returns:
			bool: 조금이라도 면적이 겹치면 True
		"""
		# 바운딩 박스 좌표 정규화
		bbox_x1, bbox_y1, bbox_x2, bbox_y2 = bbox[3:]
		bbox_min_x = min(bbox_x1, bbox_x2)
		bbox_max_x = max(bbox_x1, bbox_x2)
		bbox_min_y = min(bbox_y1, bbox_y2)
		bbox_max_y = max(bbox_y1, bbox_y2)

		# 마스킹 영역 좌표 정규화 (x1 < x2, y1 < y2 보장)
		mask_min_x = min(mask_area[0], mask_area[2])
		mask_min_y = min(mask_area[1], mask_area[3])
		mask_max_x = max(mask_area[0], mask_area[2])
		mask_max_y = max(mask_area[1], mask_area[3])

		# 면적 기반 겹침 체크: 두 사각형이 조금이라도 겹치는지
		# 겹치지 않는 조건: 한 쪽이 다른 쪽의 완전히 밖에 있음
		if bbox_max_x <= mask_min_x or bbox_min_x >= mask_max_x:
			return False  # x축에서 겹치지 않음
		if bbox_max_y <= mask_min_y or bbox_min_y >= mask_max_y:
			return False  # y축에서 겹치지 않음

		# 두 축 모두에서 겹침 -> 면적 겹침 있음
		return True

	def check_original_bbox_mask_pixel_overlap(self, x1, y1, x2, y2, mask=None):
		"""원본 이미지 좌표 bbox가 실제 마스킹 픽셀과 겹치는지 확인."""
		mask = mask if mask is not None else getattr(self, 'masking', None)
		frame_width = getattr(self, 'maskingframewidth', getattr(self, 'original_width', 0))
		frame_height = getattr(self, 'maskingframeheight', getattr(self, 'original_height', 0))
		return self.mask_label_manager.bbox_overlaps_mask_pixels(x1, y1, x2, y2, mask, frame_width, frame_height)

	def check_bbox_mask_pixel_overlap(self, bbox, mask=None):
		"""뷰 좌표 bbox가 실제 마스킹 픽셀과 겹치는지 확인."""
		x1, y1 = self.convert_view_to_original(bbox[3], bbox[4])
		x2, y2 = self.convert_view_to_original(bbox[5], bbox[6])
		return self.check_original_bbox_mask_pixel_overlap(x1, y1, x2, y2, mask)

	def read_label_lines_for_masking(self, label_path):
		return self.mask_label_manager.read_label_lines(label_path)

	def filter_label_lines_by_current_mask(self, label_path, image_width, image_height):
		return self.mask_label_manager.filter_label_lines_by_mask(label_path, image_width, image_height, self.masking)

	def load_new_list(self):
		"""새로운 이미지 리스트 파일 로드"""
		try:
			file_path = filedialog.askopenfilename(parent=self.master, title="이미지 리스트 파일(.txt) 선택",
				initialdir=self.get_last_open_dir(), filetypes=[("이미지 리스트", "*.txt"), ("모든 파일", "*.*")])
			if file_path:  # 파일이 선택된 경우
				try:
					images, nofile, encoding = read_image_list_file(file_path)
				except Exception as e:
					print(f"[ListLoad] failed to read list file: {e}")
					messagebox.showerror("리스트 열기 실패", f"리스트 파일을 읽지 못했습니다.\n{file_path}\n\n{e}")
					return
				if not images:
					sample = "\n".join(f"{p[0]}번째 줄: {p[1]}" if isinstance(p, tuple) else str(p) for p in list(nofile)[:3])
					messagebox.showwarning(
						"리스트 열기",
						f"리스트에 있는 이미지를 하나도 찾지 못했습니다.\n{file_path}\n\n"
						f"없는 경로 {len(nofile)}개 (네트워크 드라이브 연결/경로를 확인하세요)\n{sample}")
					return
				self.save_before_switching_data()
				self.reset_data()
				self.imlist = sort_image_paths(images)
				print_missing_list_items(nofile)
				print(f"[ListLoad] loaded={len(self.imlist)}, missing={len(nofile)}, encoding={encoding}")
				encodings = []
				success = True
		
				for encoding in encodings:
					try:
						with open(file_path, "rt", encoding=encoding) as file:
							self.imlist = []
							nofile = []
							for line in file:
								line = line.strip()
								line = line.replace('/s_mnt/253/','//192.168.79.253/')
								if os.path.exists(line):
									self.imlist.append(line)
								else:
									nofile.append(line)
									print(f"Warning: File not found - {line}")

						self.imlist = sort_image_paths(self.imlist)
						with open(file_path, "wt", encoding=encoding) as file:
							for image_path in self.imlist:
								file.write(to_list_file_path(image_path))
						
						success = True
						print(f"파일을 성공적으로 로드했습니다. 사용된 인코딩: {encoding}")
						break  # 성공적인 인코딩을 찾았으므로 루프 종료
						
					except UnicodeDecodeError:
						# 인코딩 오류 발생 시 다음 인코딩 시도
						continue
					except Exception as e:
						# 기타 예외 발생 시 로그 출력
						print(f"인코딩 {encoding}으로 읽는 중 오류 발생: {e}")
						continue
				
				if not success:
					messagebox.showerror("오류", "지원되는 인코딩으로 파일을 읽을 수 없습니다.")
					return

				self.loaded_list_file_path = file_path
				self.img_slider.config(to=len(self.imlist))
				self.img_slider.set(self.ci + 1)
				self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
				self._dir = file_path
				self.save_last_open_path(file_path)
				if nofile:
					self.show_temporary_status(f"리스트 {len(self.imlist)}개 로드, 없는 경로 {len(nofile)}개 제외", duration=4000, bg_color='#D97706')
				self.draw_image()
				self.draw_bbox()
		except Exception as e:
			print(f"Error loading list: {e}")
			messagebox.showerror("Error", f"Failed to load list: {e}")
	def delete_range(self):
		"""지정된 범위의 이미지와 라벨 파일을 삭제합니다"""
		# 시작 및 종료 프레임 번호 가져오기
		try:
			start_frame = int(self.delete_start_frame_entry.get())
			end_frame = int(self.delete_end_frame_entry.get())
		except ValueError:
			messagebox.showerror("오류", "시작 및 종료 프레임 번호는 숫자여야 합니다.")
			return
		
		# 프레임 범위 검증
		if start_frame < 1 or end_frame > len(self.imlist) or start_frame > end_frame:
			messagebox.showerror("오류", f"프레임 범위는 1에서 {len(self.imlist)} 사이여야 합니다.")
			return
		
		# 현재 보고 있는 이미지 인덱스 저장
		current_idx = self.ci
		
		# 확인 메시지
		if not messagebox.askyesno("확인", f"{start_frame}에서 {end_frame}까지 총 {end_frame-start_frame+1}개의 이미지를 삭제하시겠습니까?\n이 작업은 취소할 수 없습니다."):
			return
		
		# 진행 상황 창 생성
		progress_window = tk.Toplevel(self.master)
		progress_window.title("파일 삭제 중...")
		progress_window.geometry("300x100")
		progress_window.transient(self.master)
		
		progress_label = tk.Label(progress_window, text="파일을 삭제 중입니다...", pady=10)
		progress_label.pack()
		
		progress_bar = ttk.Progressbar(progress_window, orient="horizontal",
										length=250, mode="determinate")
		progress_bar.pack(pady=10)
		
		# 프로그레스 바 설정
		total_frames = end_frame - start_frame + 1
		progress_bar["maximum"] = total_frames
		progress_bar["value"] = 0
		
		# 첫 번째 이미지에 적용
		self.master.update()
		
		# 삭제할 이미지 목록 생성 (역순으로 삭제하여 인덱스 문제 방지)
		to_delete_indices = list(range(start_frame - 1, end_frame))
		to_delete_indices.reverse()  # 역순으로 정렬
		
		# 삭제 진행
		deleted_count = 0
		for idx, i in enumerate(to_delete_indices):
			# 프로그레스 바 업데이트
			progress_bar["value"] = idx + 1
			progress_label.config(text=f"처리 중: {idx+1}/{total_frames} ({int(progress_bar['value']/total_frames*100)}%)")
			self.master.update()
			
			try:
				# 현재 파일 경로
				img_path = self.imlist[i]
				label_path = image_to_label_path(img_path)
				if not self.backup_original_pair(img_path, label_path):
					print(f"[DeleteRange] Backup failed. Skipped delete: {img_path}")
					continue
				
				# 파일 삭제
				if os.path.exists(img_path):
					os.remove(img_path)
				
				if os.path.exists(label_path):
					os.remove(label_path)
				
				# 이미지 리스트에서 삭제
				self.imlist.pop(i)
				deleted_count += 1
				# 실제로 삭제된 경우에만 현재 인덱스 조정 (백업 실패로 건너뛴 프레임은 위치에 영향 없음)
				if i <= current_idx:
					current_idx -= 1

			except Exception as e:
				print(f"이미지 {i+1} 삭제 중 오류 발생: {e}")
		
		# 진행 창 닫기
		progress_window.destroy()
		
		# 현재 인덱스 조정
		if current_idx < 0:
			current_idx = 0
		if current_idx >= len(self.imlist):
			current_idx = len(self.imlist) - 1
		
		self.ci = current_idx
		
		# 슬라이더 최대값 조정
		if len(self.imlist) > 0:
			self.img_slider.config(to=len(self.imlist))
			self.img_slider.set(self.ci + 1)
			self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
		
		# 완료 메시지
		messagebox.showinfo("완료", f"파일 삭제가 완료되었습니다. {deleted_count}개의 파일이 삭제되었습니다.")
		
		# 현재 이미지 다시 로드
		self.pi = -1
		self.draw_image()
	def update_label_copy_ui(self):
		"""라벨 복사 UI 업데이트 및 확장"""

		# 기존 label_copy_frame 내용을 지우기
		for widget in self.label_copy_frame.winfo_children():
			widget.destroy()

		# 복사 모드 선택을 위한 라디오 버튼
		self.copy_mode = tk.StringVar(value="all")  # 기본값: 모든 라벨 복사

		# 모든 라벨 모드 라디오 버튼
		self.rb_all = tk.Radiobutton(
			self.label_copy_frame,
			text="전체",
			variable=self.copy_mode,
			value="all",
			command=self.toggle_copy_mode
		)
		self.rb_all.pack(side=tk.LEFT, padx=1)

		# 선택 라벨 모드 라디오 버튼
		self.rb_selected = tk.Radiobutton(
			self.label_copy_frame,
			text="선택",
			variable=self.copy_mode,
			value="selected",
			command=self.toggle_copy_mode
		)
		self.rb_selected.pack(side=tk.LEFT, padx=1)

		# 다중 선택 라벨 모드 라디오 버튼
		self.rb_multi = tk.Radiobutton(
			self.label_copy_frame,
			text="다중",
			variable=self.copy_mode,
			value="selected_multi",
			command=self.toggle_copy_mode
		)
		self.rb_multi.pack(side=tk.LEFT, padx=1)

		# 대상 이미지의 기존 라벨 처리 옵션
		self.preserve_mode = tk.StringVar(value="preserve")  # 기본값: 기존 라벨 유지

		self.rb_preserve = tk.Radiobutton(
			self.label_copy_frame,
			text="유지",
			variable=self.preserve_mode,
			value="preserve"
		)
		self.rb_preserve.pack(side=tk.LEFT, padx=1)

		self.rb_replace = tk.Radiobutton(
			self.label_copy_frame,
			text="삭제",
			variable=self.preserve_mode,
			value="replace"
		)
		self.rb_replace.pack(side=tk.LEFT, padx=1)

		# 시작/종료 프레임 입력 UI
		self.label_start_frame_label = tk.Label(self.label_copy_frame, text="시작:", bd=0)
		self.label_start_frame_label.pack(side=tk.LEFT, padx=1)

		self.label_start_frame_entry = tk.Entry(self.label_copy_frame, width=5)
		self.label_start_frame_entry.pack(side=tk.LEFT, padx=1)

		self.label_end_frame_label = tk.Label(self.label_copy_frame, text="종료:", bd=0)
		self.label_end_frame_label.pack(side=tk.LEFT, padx=1)

		self.label_end_frame_entry = tk.Entry(self.label_copy_frame, width=5)
		self.label_end_frame_entry.pack(side=tk.LEFT, padx=1)

		# 실행 버튼
		self.copy_label_btn = tk.Button(
			self.label_copy_frame,
			text="실행",
			command=self.copy_label_to_range,
			bd=1
		)
		self.copy_label_btn.pack(side=tk.LEFT, padx=2)

		# 라벨 자동 복사 체크박스
		self.auto_copy_labels_var = tk.BooleanVar()
		self.auto_copy_labels_var.set(False)
		self.auto_copy_labels_chk = tk.Checkbutton(
			self.label_copy_frame,
			text="자동",
			variable=self.auto_copy_labels_var,
			command=self.toggle_auto_copy_labels
		)
		self.auto_copy_labels_chk.pack(side=tk.LEFT, padx=2)

		# 다중 선택 정보 표시 라벨 (간결하게)
		self.multi_info_label = tk.Label(
			self.label_copy_frame,
			text="",
			font=("Arial", 7),
			fg="green"
		)
		self.multi_info_label.pack(side=tk.LEFT, padx=2)

		# 다중 선택 모드 토글 버튼 (간결하게)
		self.multi_mode_btn = tk.Button(
			self.label_copy_frame,
			text="다중모드",
			command=self.toggle_multi_select_mode,
			bd=1,
			bg="lightgray",
			width=8
		)
		self.multi_mode_btn.pack(side=tk.LEFT, padx=2)

		# 초기 상태 설정
		self.toggle_copy_mode()

	# 2. 라디오 버튼 토글 기능 추가
	def toggle_copy_mode(self):
		"""복사 모드 변경 시 처리"""
		mode = self.copy_mode.get()
		
		# 선택 모드인데 선택된 라벨이 없으면 경고
		if mode == "selected" and self.selid < 0:
			messagebox.showwarning("경고", "선택된 라벨이 없습니다. 라벨을 먼저 선택해주세요.")
			self.copy_mode.set("all")
		
		# 다중 선택 모드인데 선택된 라벨이 없으면 경고
		elif mode == "selected_multi" and not self.multi_selected:
			messagebox.showwarning("경고", "다중 선택된 라벨이 없습니다. 라벨을 먼저 선택해주세요.")
			self.copy_mode.set("all")
		# 3. 선택적 복사 기능이 포함된 새 라벨 복사 함수
		# 라벨 복사 기능 버그 수정 - "선택 + 유지" 모드에서 기존 라벨이 삭제되는 문제 해결

# 라벨 복사 기능 문제 완전 수정 - 단계별 디버깅 추가

	# 간소화된 라벨 복사 기능

	def copy_label_to_range(self):
		"""현재 레이블을 지정된 범위의 이미지들에 복사 (다중 선택 지원)"""
		copy_mode = self.copy_mode.get()
		preserve_mode = self.preserve_mode.get()

		# 모드별 체크
		if copy_mode == "all" and len(self.bbox) == 0:
			messagebox.showwarning("경고", "복사할 라벨이 없습니다.")
			return
		elif copy_mode == "selected" and self.selid < 0:
			messagebox.showwarning("경고", "선택된 라벨이 없습니다.")
			return
		elif copy_mode == "selected_multi" and not self.multi_selected:
			messagebox.showwarning("경고", "다중 선택된 라벨이 없습니다.")
			return

		# 시작 및 종료 프레임 번호 가져오기
		try:
			start_frame = int(self.label_start_frame_entry.get())
			end_frame = int(self.label_end_frame_entry.get())
		except ValueError:
			messagebox.showerror("오류", "시작 및 종료 프레임 번호는 숫자여야 합니다.")
			return

		# 프레임 범위 검증
		if start_frame < 1 or end_frame > len(self.imlist) or start_frame > end_frame:
			messagebox.showerror("오류", f"프레임 범위는 1에서 {len(self.imlist)} 사이여야 합니다.")
			return

		# 현재 보고 있는 이미지 인덱스 저장
		current_idx = self.ci

		# 모드별 작업 확인 메시지 (수정됨)
		if copy_mode == "all":
			confirm_msg = f"{start_frame}에서 {end_frame}까지의 이미지에 모든 라벨을 복사하시겠습니까?"
		elif copy_mode == "selected":
			selected_bbox = self.bbox[self.selid]
			if preserve_mode == "preserve":
				confirm_msg = f"{start_frame}에서 {end_frame}까지의 이미지에 선택한 '{selected_bbox[1]}' 라벨을 추가하고 기존 라벨을 유지하시겠습니까?"
			else:  # replace
				confirm_msg = f"{start_frame}에서 {end_frame}까지의 이미지에 선택한 '{selected_bbox[1]}' 라벨만 복사하고 기존 라벨을 삭제하시겠습니까?"
		else:  # selected_multi
			count = len(self.multi_selected)
			if preserve_mode == "preserve":
				confirm_msg = f"{start_frame}에서 {end_frame}까지의 이미지에 선택한 {count}개 라벨을 추가하고 기존 라벨을 유지하시겠습니까?"
			else:  # replace
				confirm_msg = f"{start_frame}에서 {end_frame}까지의 이미지에 선택한 {count}개 라벨만 복사하고 기존 라벨을 삭제하시겠습니까?"

		# 확인 메시지
		if not messagebox.askyesno("확인", confirm_msg):
			return

		# 현재 라벨 저장
		self.write_bbox()

		# 복사할 라벨 정보 준비 (절대 좌표로 저장)
		source_bboxes = []  # 절대 좌표 bbox 리스트
		use_file_content = False  # 파일 내용을 직접 사용할지 여부

		if copy_mode == "all":
			# 모든 라벨 복사 - 파일 내용 직접 사용
			with open(self.gt_fn, 'rt') as f:
				copytext = f.readlines()

			if not copytext:
				messagebox.showwarning("경고", "복사할 라벨 내용이 없습니다.")
				return
			use_file_content = True
		elif copy_mode == "selected":
			# 선택된 라벨만 복사 - 절대 좌표 저장
			source_bboxes = [self.bbox[self.selid]]
		else:  # selected_multi
			# 다중 선택된 라벨들 복사 - 절대 좌표 저장
			for idx in sorted(self.multi_selected):
				if idx < len(self.bbox):
					source_bboxes.append(self.bbox[idx])
		
		# 진행 상황 창 생성
		progress_window = tk.Toplevel(self.master)
		progress_window.title("라벨 복사 중...")
		progress_window.geometry("300x100")
		progress_window.transient(self.master)
		
		progress_label = tk.Label(progress_window, text="라벨을 복사 중입니다...", pady=10)
		progress_label.pack()
		
		progress_bar = ttk.Progressbar(progress_window, orient="horizontal",
										length=250, mode="determinate")
		progress_bar.pack(pady=10)
		
		# 프로그레스 바 설정
		total_frames = end_frame - start_frame + 1
		progress_bar["maximum"] = total_frames
		progress_bar["value"] = 0
		
		# 첫 번째 이미지에 적용
		self.master.update()
		
		# 지정된 범위의 이미지에 라벨 적용
		success_count = 0
		for i in range(start_frame - 1, end_frame):
			# 프로그레스 바 업데이트
			progress_bar["value"] = i - (start_frame - 1) + 1
			progress_label.config(text=f"처리 중: {i+1}/{end_frame} ({int(progress_bar['value']/total_frames*100)}%)")
			self.master.update()

			# 현재 이미지 건너뛰기
			if i == current_idx:
				continue

			try:
				# 대상 파일 경로 계산
				target_img_path = self.imlist[i]
				target_label_path = image_to_label_path(target_img_path)

				# 타겟 이미지의 해상도 읽기 (선택/다중 선택 모드일 때만)
				if not use_file_content:
					try:
						target_img = Image.open(target_img_path)
						target_size = target_img.size  # (width, height)
						target_img.close()

						# 타겟 이미지 해상도로 bbox 변환
						copytext = []
						for bbox in source_bboxes:
							# bbox: [sel, clsname, info, x1, y1, x2, y2] 형태 (절대 좌표)
							# 현재 이미지 크기에서 타겟 이미지 크기로 스케일 조정
							scale_x = target_size[0] / self.imsize[0]
							scale_y = target_size[1] / self.imsize[1]

							# 절대 좌표 스케일링
							x1 = bbox[3] * scale_x
							y1 = bbox[4] * scale_y
							x2 = bbox[5] * scale_x
							y2 = bbox[6] * scale_y

							# YOLO 상대 좌표로 변환
							cx = 0.5 * (x1 + x2) / target_size[0]
							cy = 0.5 * (y1 + y2) / target_size[1]
							w = abs(x2 - x1) / target_size[0]
							h = abs(y2 - y1) / target_size[1]

							class_idx = bbox[2]  # class_id
							rel_coords = [class_idx, cx, cy, w, h]
							copytext.append(' '.join(str(e) for e in rel_coords) + '\n')

					except Exception as e:
						print(f"타겟 이미지 해상도 읽기 오류: {e}")
						continue

				# 디렉토리 확인/생성은 별도 try 블록
				try:
					target_dir = os.path.dirname(target_label_path)
					if not os.path.exists(target_dir):
						os.makedirs(target_dir)
				except Exception as e:
					print(f"디렉토리 생성 오류: {e}")
					continue

				# 기존 라벨 읽기는 별도 try 블록
				existing_labels = []
				try:
					if os.path.exists(target_label_path):
						with open(target_label_path, 'r', encoding='utf-8') as f:
							existing_labels = f.readlines()
				except Exception as e:
					print(f"라벨 읽기 오류: {e}")
					# 읽기 실패 시 결정: 계속 진행 또는 건너뛰기

				output_lines = []
				copy_regions = self.copy_region_manager.active_regions()
				if copy_regions:
					output_lines = merge_copy_region_label_lines(existing_labels, copytext, copy_regions)
				elif preserve_mode == "preserve":
					output_lines.extend(existing_labels)
					if copy_mode == "selected":
						is_duplicate = any(existing_label.strip() == copytext[0].strip() for existing_label in existing_labels)
						if not is_duplicate:
							output_lines.extend(copytext)
					else:
						output_lines.extend(copytext)
				else:
					output_lines.extend(copytext)

				if not self.write_text_files_transaction({target_label_path: ''.join(output_lines)}, backup_category='labels'):
					print(f"[LabelCopy] Transaction failed. Skipped frame: {target_label_path}")
					continue

				success_count += 1
					
			except Exception as e:
				print(f"이미지 {i+1} 라벨 처리 중 오류 발생: {e}")
		
		# 진행 창 닫기
		progress_window.destroy()
		
		# 완료 메시지
		if copy_mode == "all":
			messagebox.showinfo("완료", f"모든 라벨 복사가 완료되었습니다. {success_count}개의 이미지에 성공적으로 적용되었습니다.")
		elif preserve_mode == "preserve":
			messagebox.showinfo("완료", f"선택 라벨 추가가 완료되었습니다. {success_count}개의 이미지에 성공적으로 적용되었습니다.")
		else:  # replace
			messagebox.showinfo("완료", f"선택 라벨 복사가 완료되었습니다. {success_count}개의 이미지에 성공적으로 적용되었습니다.")

		# 현재 이미지 다시 표시
		self.draw_image()

	def start_copy_region_drawing(self):
		self.copy_region_mode = True
		self.copy_region_points = []
		messagebox.showinfo("Copy region", "Left-click points to draw a copy region. Right-click to save it.")

	def finish_copy_region_drawing(self):
		if len(self.copy_region_points) < 3:
			self.copy_region_mode = False
			self.copy_region_points = []
			return
		self.copy_region_manager.zones.append({
			'points': list(self.copy_region_points),
			'enabled': True,
		})
		self.copy_region_manager.save()
		self.copy_region_mode = False
		self.copy_region_points = []
		self.draw_bbox()

	def show_copy_region_context_menu(self, event, normalized_point):
		menu = tk.Menu(self.master, tearoff=0)
		original_point = (
			normalized_point[0] * self.imsize[0] / max(self.zoom_ratio, 0.0001),
			normalized_point[1] * self.imsize[1] / max(self.zoom_ratio, 0.0001),
		)
		exclusion_index = next((i for i, zone in enumerate(self.exclusion_zone_manager.global_zones)
			if point_in_polygon(original_point, zone.get('points', []))), None)
		class_change_index = next((i for i, zone in enumerate(self.class_change_zone_manager.zones)
			if point_in_polygon(original_point, zone.get('points', []))), None)
		if exclusion_index is not None:
			zone = self.exclusion_zone_manager.global_zones[exclusion_index]
			menu.add_command(
				label="Enable exclusion zone" if not zone.get('enabled', True) else "Disable exclusion zone",
				command=lambda: self.toggle_exclusion_zone_from_canvas(exclusion_index),
			)
		if class_change_index is not None:
			zone = self.class_change_zone_manager.zones[class_change_index]
			menu.add_command(
				label="Enable class change zone" if not zone.get('enabled', True) else "Disable class change zone",
				command=lambda: self.toggle_class_change_zone_from_canvas(class_change_index),
			)
		if exclusion_index is not None or class_change_index is not None:
			menu.add_separator()
		menu.add_command(label="Draw exclusion zone", command=lambda: self.start_exclusion_zone_drawing('polygon'))
		zone_index = self.copy_region_manager.zone_at(normalized_point)
		if zone_index is not None:
			zone = self.copy_region_manager.zones[zone_index]
			label = "복사영역 끄기" if zone.get('enabled', True) else "복사영역 켜기"
			menu.add_command(label=label, command=lambda: self.toggle_copy_region(zone_index))
			menu.add_command(label="복사영역 삭제", command=lambda: self.delete_copy_region(zone_index))
			menu.add_separator()
			menu.add_command(label="Draw new copy region", command=self.start_copy_region_drawing)
		else:
			menu.add_command(label="Draw copy region here", command=self.start_copy_region_drawing)
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()

	def toggle_exclusion_zone_from_canvas(self, index):
		self.exclusion_zone_manager.toggle_zone(index)
		if self.exclusion_zone_manager.global_zones[index].get('enabled', True):
			self.exclusion_zone_enabled = True
			self.exclusion_zone_manager.save_enabled_state(True)
		self.exclusion_zone_manager.save_global_zones()
		self.draw_bbox()

	def toggle_class_change_zone_from_canvas(self, index):
		self.class_change_zone_manager.toggle_zone(index)
		self.class_change_zone_manager.save_zones()
		self.draw_bbox()

	def toggle_copy_region(self, index):
		if 0 <= index < len(self.copy_region_manager.zones):
			zone = self.copy_region_manager.zones[index]
			zone['enabled'] = not zone.get('enabled', True)
			self.copy_region_manager.save()
			self.draw_bbox()

	def delete_copy_region(self, index):
		if 0 <= index < len(self.copy_region_manager.zones):
			self.copy_region_manager.zones.pop(index)
			self.copy_region_manager.save()
			self.draw_bbox()

	def show_temporary_status(self, message, duration=2000, bg_color=None):
		"""화면 하단에 일시 상태 메시지 표시"""
		if bg_color is None:
			bg_color = getattr(self, 'theme_colors', {}).get('success_bg', '#059669')

		# 기존 상태 레이블 제거
		if hasattr(self, 'status_label') and self.status_label:
			try:
				self.status_label.destroy()
			except:
				pass

		# 새 상태 레이블 생성
		self.status_label = tk.Label(
			self.master,
			text=message,
			bg=bg_color,
			fg='white',
			font=('Arial', 10, 'bold'),
			padx=10,
			pady=5
		)
		self.status_label.pack(side='bottom', fill='x')

		# 자동으로 사라지게
		self.master.after(duration, lambda: self.hide_status_label())

	def hide_status_label(self):
		"""상태 레이블 숨기기"""
		if hasattr(self, 'status_label') and self.status_label:
			try:
				self.status_label.destroy()
				self.status_label = None
			except:
				pass

	def show_empty_hint(self):
		"""이미지가 없을 때 캔버스에 안내 문구 표시"""
		self.canvas.delete("all")
		self.canvas.update_idletasks()
		w = max(self.canvas.winfo_width(), 400)
		h = max(self.canvas.winfo_height(), 300)
		self.canvas.create_text(w // 2, h // 2, text="Open Folder 또는 Open List 버튼으로 작업할 데이터를 여세요",
			font=("맑은 고딕", 14), fill="gray40", tags="empty_hint")

	def draw_image(self):
		if not self.imlist:
			self.show_empty_hint()
			return
		if self.ci == self.pi: return
		self.canvas.delete("all")
		try:
			previous_page_index = self.pi
			self.page_move_delta = 0 if previous_page_index < 0 else self.ci - previous_page_index
			self.pi = self.ci

			# 페이지 전환 시 pending 작업 카운터 및 작업 내역 초기화
			self.pending_operation_count = 0
			self.pending_deleted_labels = []
			self.pending_masked_labels = []

			# 페이지 전환 시 onlyselect 모드 해제 (클래스 필터가 작동하도록)
			self.onlyselect = False

			print(f"[CacheOptimization] 페이지 전환 - pending 카운터 및 작업 내역 초기화")

			if len(self.imlist) > 0:
				self.img_slider.config(to=len(self.imlist))
				self.img_slider.set(self.ci + 1)  # 1-인덱스로 표시
				self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
			
			self.im_fn = self.imlist[self.ci]
			self.gt_fn = image_to_label_path(self.im_fn)
			self.canvas.delete("img")
			fname, ext = os.path.splitext(self.im_fn)
			if ext=='.db':
				return
			if ext!='':
				try:
					im = Image.open(self.im_fn)
				except (IOError, OSError, FileNotFoundError) as e:
					messagebox.showerror("Image Load Error", f"Failed to open image: {self.im_fn}\nError: {e}")
					print(f"ERROR: Failed to open image {self.im_fn}: {e}")
					return
				
			# === 새로운 마스킹 메모리 관리 코드 추가 ===
			# 새 이미지 로드 시 배열 초기화
			self.original_img_array = array(im.copy())  # 원본 백업
			self.current_img_array = array(im.copy())   # 작업용 복사본
			self.is_masking_dirty = False  # 새 이미지이므로 더티 플래그 초기화

			# 마스킹 자동 로드 제거 - s/l 키로만 복사/붙여넣기 가능
			self.imsize = im.size
			self.imsize = [(int)(i * self.zoom_ratio) for i in im.size]
			self.original_width = im.width
			self.original_height = im.height

			# 원본 이미지만 표시 (마스킹 자동 표시하지 않음)
			im = im.resize(self.imsize, Image.LANCZOS)

			if os.path.exists(self.gt_fn):
				filesize = os.path.getsize(self.gt_fn)
			else :
				filesize=0

			self.canvas.config(width=min(self.imsize[0], 1200), height=min(self.imsize[1], 800))
			self.canvas.config(scrollregion=(0, 0, self.imsize[0], self.imsize[1]))
			self.canvas.image = ImageTk.PhotoImage(im)
			self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
			self.master.title('[%d/%d] %s' % (self.ci+1, len(self.imlist), self.im_fn))
			if self.CLASSIFY_TPFP: self.draw_criteria()

			# 제외 영역 로드
			if self.exclusion_zone_manager:
				self.exclusion_zone_manager.load_zones(self.im_fn)

			self.load_bbox()

			# 바운딩 박스 그리기
			self.draw_bbox()

			if filesize != 0:
				if self.selid >= 0:
					rc = self.convert_abs2rel(self.bbox[self.selid])
					self.pre_rc = self.convert_rel2abs(rc)
			self.canvas.focus_set()
		except Exception as e:
			print(f"ERROR in draw_image: {e}")
			messagebox.showerror("Error", f"An error occurred while drawing image:\n{e}\n\nPlease check image path.")
			try:
				os.startfile(BASE_DIR + "RemoveDefaultdll.exe")
			except Exception:
				pass  # 프로그램 실행 실패 시 무시
		return
	def setup_label_list_ui(self):
		"""라벨 리스트와 크롭 프리뷰 UI 초기화 - 개선된 버전"""
		# 오른쪽 패널 생성 (테두리 두께 줄임)
		self.right_panel = tk.Frame(self.master, width=300, bg='lightgray', relief='solid', bd=1)
		
		# 라벨 리스트 프레임 (높이를 늘려서 더 많은 라벨 표시)
		self.label_list_frame = tk.LabelFrame(self.right_panel, text="All Labels", height=400, relief='solid', bd=1)
		self.label_list_frame.pack(fill="x", padx=3, pady=3)
		self.label_list_frame.pack_propagate(False)
		
		# 라벨 리스트박스와 스크롤바
		list_frame = tk.Frame(self.label_list_frame)
		list_frame.pack(fill="both", expand=True, padx=3, pady=3)
		
		# 리스트박스 설정 개선 (더 많은 항목 표시, 폰트 크기 조정)
		self.label_listbox = tk.Listbox(
			list_frame, 
			height=18,  # 높이 증가
			font=("Consolas", 8),  # 폰트 크기 줄임
			selectmode=tk.EXTENDED,  # 다중 선택 가능
			relief='solid',
			bd=1
		)
		self.label_listbox.pack(side=tk.LEFT, fill="both", expand=True)
		
		list_scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.label_listbox.yview)
		list_scrollbar.pack(side=tk.RIGHT, fill="y")
		self.label_listbox.config(yscrollcommand=list_scrollbar.set)
		
		# 라벨 통계 정보 프레임 추가
		self.stats_frame = tk.Frame(self.label_list_frame, height=30)
		self.stats_frame.pack(fill="x", padx=3, pady=2)
		self.stats_frame.pack_propagate(False)
		
		self.stats_label = tk.Label(
			self.stats_frame, 
			text="Total: 0 labels", 
			font=("Arial", 8), 
			bg='white',
			relief='solid',
			bd=1
		)
		self.stats_label.pack(fill="both", expand=True)
		
		# 크롭 프리뷰 프레임 (높이 줄임)
		self.crop_frame = tk.LabelFrame(self.right_panel, text="Selected Crop", relief='solid', bd=1)
		self.crop_frame.pack(fill="both", expand=True, padx=3, pady=3)
		
		# 크롭 캔버스 (크기 줄임)
		self.crop_canvas = tk.Canvas(self.crop_frame, width=260, height=300, bg='white', relief='solid', bd=1)
		self.crop_canvas.pack(padx=3, pady=3)
		
		# 크롭 정보 라벨
		self.crop_info_label = tk.Label(self.crop_frame, text="", font=("Arial", 9, "bold"))
		self.crop_info_label.pack(pady=2)
		
		# 이벤트 바인딩
		self.bind_label_list_events()

	def bind_label_list_events(self):
		"""라벨 리스트 관련 이벤트 바인딩 - 개선된 버전"""
		# 리스트박스 선택 이벤트
		self.label_listbox.bind("<<ListboxSelect>>", self.on_label_list_select)
		
		# 더블클릭으로 라벨로 이동
		self.label_listbox.bind("<Double-Button-1>", self.on_label_list_double_click)
		
		# 우클릭 메뉴
		self.label_listbox.bind("<Button-3>", self.on_label_list_right_click)
		
		# 크롭 캔버스 마우스 이벤트 (드래그 리사이즈/이동 + 외부클릭 삭제)
		self.crop_canvas.bind("<Button-1>",        self.on_crop_mouse_down)
		self.crop_canvas.bind("<B1-Motion>",        self.on_crop_mouse_drag)
		self.crop_canvas.bind("<ButtonRelease-1>",  self.on_crop_mouse_up)
		
		# 포커스 관리
		self.label_listbox.bind("<Button-1>", lambda e: self.master.after(50, self.canvas.focus_set))

	def on_label_list_double_click(self, event):
		"""라벨 리스트 더블클릭 시 해당 라벨 중앙으로 이동"""
		selection = self.label_listbox.curselection()
		if not selection:
			return

		listbox_index = selection[0]

		# listbox 인덱스를 bbox 인덱스로 변환
		if not hasattr(self, 'listbox_to_bbox_map') or listbox_index not in self.listbox_to_bbox_map:
			return

		bbox_index = self.listbox_to_bbox_map[listbox_index]
		if bbox_index < len(self.bbox):
			bbox = self.bbox[bbox_index]
			# 바운딩 박스 중앙 계산
			center_x = (bbox[3] + bbox[5]) / 2
			center_y = (bbox[4] + bbox[6]) / 2
			
			# 캔버스 뷰를 해당 위치로 이동
			canvas_width = self.canvas.winfo_width()
			canvas_height = self.canvas.winfo_height()
			
			scroll_x = (center_x - canvas_width/2) / self.imsize[0]
			scroll_y = (center_y - canvas_height/2) / self.imsize[1]
			
			scroll_x = max(0, min(1, scroll_x))
			scroll_y = max(0, min(1, scroll_y))
			
			self.canvas.xview_moveto(scroll_x)
			self.canvas.yview_moveto(scroll_y)

	def on_label_list_right_click(self, event):
		"""라벨 리스트 우클릭 메뉴"""
		# 우클릭한 위치의 항목 선택
		index = self.label_listbox.nearest(event.y)
		self.label_listbox.selection_clear(0, tk.END)
		self.label_listbox.selection_set(index)
		
		# 컨텍스트 메뉴 생성
		context_menu = tk.Menu(self.master, tearoff=0)
		context_menu.add_command(label="Delete Label", command=lambda: self.delete_label_from_list(index))
		context_menu.add_command(label="Center View", command=lambda: self.center_view_on_label(index))
		context_menu.add_separator()
		context_menu.add_command(label="Copy Label", command=lambda: self.copy_label_from_list(index))
		
		try:
			context_menu.tk_popup(event.x_root, event.y_root)
		finally:
			context_menu.grab_release()

	def delete_label_from_list(self, listbox_index):
		"""라벨 리스트에서 라벨 삭제"""
		# listbox 인덱스를 bbox 인덱스로 변환
		if not hasattr(self, 'listbox_to_bbox_map') or listbox_index not in self.listbox_to_bbox_map:
			return

		bbox_index = self.listbox_to_bbox_map[listbox_index]
		if 0 <= bbox_index < len(self.bbox):
			self.selid = bbox_index
			self.remove_bbox_rc()

	def center_view_on_label(self, listbox_index):
		"""라벨을 화면 중앙으로 이동"""
		# listbox 인덱스를 bbox 인덱스로 변환
		if not hasattr(self, 'listbox_to_bbox_map') or listbox_index not in self.listbox_to_bbox_map:
			return

		bbox_index = self.listbox_to_bbox_map[listbox_index]
		if 0 <= bbox_index < len(self.bbox):
			self.selid = bbox_index
			self.on_label_list_double_click(None)

	def copy_label_from_list(self, listbox_index):
		"""라벨 리스트에서 라벨 복사"""
		# listbox 인덱스를 bbox 인덱스로 변환
		if not hasattr(self, 'listbox_to_bbox_map') or listbox_index not in self.listbox_to_bbox_map:
			return

		bbox_index = self.listbox_to_bbox_map[listbox_index]
		if 0 <= bbox_index < len(self.bbox):
			self.selid = bbox_index
			self.copy_selected_label()
	def toggle_label_list_view(self):
		"""라벨 리스트 뷰 표시/숨기기 - 개선된 버전"""
		if self.show_label_list.get():
			if self.right_panel.winfo_viewable():
				return
				
			# 패널 설정 (테두리 두께 줄임)
			self.right_panel.config(
				width=300,
				bg='lightgray',
				relief='solid',  # raised에서 solid로 변경
				bd=1  # 2에서 1로 줄임
			)
			
			self.right_panel.pack_propagate(False)
			
			# 레이아웃 재배치
			self.canvas_frame.pack_forget()
			
			self.right_panel.pack(
				side=tk.RIGHT,
				fill="y",
				padx=2,  # 5에서 2로 줄임
				pady=2   # 5에서 2로 줄임
			)
			
			self.canvas_frame.pack(
				side=tk.LEFT,
				fill="both", 
				expand=True
			)
			
			self.master.update_idletasks()
			self.master.update()
			
			self.update_label_list()
			self.update_crop_preview()
			
		else:
			self.right_panel.pack_forget()
			self.canvas_frame.pack_forget()
			self.canvas_frame.pack(fill="both", expand=True)
	def get_selected_labels_from_list(self):
		"""라벨 리스트에서 선택된 항목들의 인덱스 반환"""
		if not hasattr(self, 'label_listbox'):
			return []
		
		selected_indices = self.label_listbox.curselection()
		return list(selected_indices)
	def update_label_list(self):
		"""전체 라벨 리스트 업데이트 - 개선된 버전"""
		if not hasattr(self, 'label_listbox') or not self.show_label_list.get():
			return

		if not self.right_panel.winfo_viewable():
			return

		# 리스트박스 초기화
		self.label_listbox.delete(0, tk.END)

		if not self.bbox:
			self.stats_label.config(text="Total: 0 labels")
			return

		# 디버깅: 필터 상태 출력
		print(f"\n[FILTER DEBUG] update_label_list() - Total bboxes: {len(self.bbox)}")
		print(f"[FILTER DEBUG] Filter active: {self.class_filter_manager.is_filter_active()}")
		if self.class_filter_manager.is_filter_active():
			print(f"[FILTER DEBUG] Visible classes in filter: {sorted(self.class_filter_manager.get_visible_classes())}")

		# 클래스별 개수 카운트
		class_counts = {}

		# 각 라벨을 리스트에 추가
		listbox_index = 0  # listbox에 실제로 추가된 항목의 인덱스
		self.listbox_to_bbox_map = {}  # listbox 인덱스 → bbox 인덱스 매핑
		for i, bbox in enumerate(self.bbox):
			# 클래스 필터 적용 - 필터에 해당하는 클래스만 표시
			class_id = int(bbox[2])
			print(f"[FILTER DEBUG] Checking bbox[{i}]: class_id={class_id}, class_name={bbox[1]}")
			if not self.class_filter_manager.is_class_visible(class_id):
				continue

			class_name_str = bbox[1]
			width = int(bbox[5] - bbox[3])
			height = int(bbox[6] - bbox[4])

			# 클래스별 개수 카운트
			if class_name_str in class_counts:
				class_counts[class_name_str] += 1
			else:
				class_counts[class_name_str] = 1

			# 선택된 라벨 표시용 마커
			marker = "●" if bbox[0] else "○"

			# 리스트 항목 텍스트 생성 (더 간결하게)
			item_text = f"{marker} {i+1:2d}. {class_name_str} ({width}x{height})"

			self.label_listbox.insert(tk.END, item_text)

			# 현재 선택된 라벨이면 리스트박스에서도 선택하고 색상 변경
			if bbox[0]:
				self.label_listbox.select_set(listbox_index)
				self.label_listbox.see(listbox_index)
				# 선택된 항목 배경색 변경
				self.label_listbox.itemconfig(listbox_index, {'bg': 'lightblue'})

			# listbox 인덱스와 bbox 인덱스 매핑 저장
			self.listbox_to_bbox_map[listbox_index] = i
			listbox_index += 1  # listbox 인덱스 증가
		
		# 통계 정보 업데이트
		total_labels = len(self.bbox)
		unique_classes = len(class_counts)
		stats_text = f"Total: {total_labels} labels ({unique_classes} classes)"
		
		# 가장 많은 클래스 표시
		if class_counts:
			most_common_class = max(class_counts.items(), key=lambda x: x[1])
			stats_text += f" | Most: {most_common_class[0]}({most_common_class[1]})"
		
		self.stats_label.config(text=stats_text)
	def update_crop_preview(self):
		"""선택된 라벨의 크롭 프리뷰 업데이트 (10% 패딩 + bbox overlay + 앵커 핸들)"""
		if not hasattr(self, 'crop_canvas') or not self.show_label_list.get():
			return

		# 드래그 중 재진입 시 overlay 만 빠르게 갱신하고 반환 (이미지 재로드 방지)
		if hasattr(self, 'crop_drag_active') and self.crop_drag_active:
			self._update_crop_canvas_overlay()
			return

		# 캔버스 전체 초기화
		self.crop_canvas.delete("all")
		self.crop_info_label.config(text="")
		self.crop_transform = None

		if self.selid < 0 or not self.bbox:
			self.crop_canvas.create_text(130, 150, text="No label selected",
										 fill="gray", font=("Arial", 12))
			return

		try:
			bbox = self.bbox[self.selid]
			x1, y1, x2, y2 = bbox[3:7]

			# 원본 이미지 좌표로 변환 (줌 비율 고려)
			orig_x1 = x1 / self.zoom_ratio
			orig_y1 = y1 / self.zoom_ratio
			orig_x2 = x2 / self.zoom_ratio
			orig_y2 = y2 / self.zoom_ratio

			# 이미지 경계 크기 확보
			if hasattr(self, 'original_width') and hasattr(self, 'original_height'):
				img_w = self.original_width
				img_h = self.original_height
			else:
				img_w = int(self.imsize[0] / self.zoom_ratio)
				img_h = int(self.imsize[1] / self.zoom_ratio)

			# 40% 패딩 계산 (최소 5픽셀)
			pad_x = max(5, int((orig_x2 - orig_x1) * 0.40))
			pad_y = max(5, int((orig_y2 - orig_y1) * 0.40))

			crop_x1 = max(0.0, orig_x1 - pad_x)
			crop_y1 = max(0.0, orig_y1 - pad_y)
			crop_x2 = min(float(img_w), orig_x2 + pad_x)
			crop_y2 = min(float(img_h), orig_y2 + pad_y)

			if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
				self.crop_canvas.create_text(130, 150, text="Invalid crop area",
											 fill="red", font=("Arial", 12))
				return

			# 원본 이미지에서 크롭 (패딩 포함)
			original_img = Image.open(self.im_fn)
			cropped_img = original_img.crop((int(crop_x1), int(crop_y1),
											 int(crop_x2), int(crop_y2)))

			canvas_width  = 260
			canvas_height = 300
			img_ratio    = cropped_img.width / cropped_img.height
			canvas_ratio = canvas_width / canvas_height
			max_width    = canvas_width  - 6
			max_height   = canvas_height - 6

			if img_ratio > canvas_ratio:
				new_width  = max_width
				new_height = int(max_width / img_ratio)
			else:
				new_height = max_height
				new_width  = int(max_height * img_ratio)

			new_width  = max(1, new_width)
			new_height = max(1, new_height)

			resized_img = cropped_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
			self.crop_image_tk = ImageTk.PhotoImage(resized_img)

			x_offset = (canvas_width  - new_width)  // 2
			y_offset = (canvas_height - new_height) // 2

			self.crop_canvas.create_image(x_offset, y_offset,
										  image=self.crop_image_tk,
										  anchor='nw', tags="crop_image")

			# 좌표 변환 파라미터 저장 (마우스 이벤트 처리용)
			self.crop_transform = {
				'crop_x1': crop_x1,
				'crop_y1': crop_y1,
				'scale_x': new_width  / (crop_x2 - crop_x1),
				'scale_y': new_height / (crop_y2 - crop_y1),
				'offset_x': x_offset,
				'offset_y': y_offset,
			}

			# bbox overlay + 8개 앵커 핸들 그리기
			self._update_crop_canvas_overlay()

		except Exception as e:
			print(f"Error updating crop preview: {e}")
			self.crop_canvas.delete("all")
			self.crop_canvas.create_text(130, 150, text="Error loading crop",
										 fill="red", font=("Arial", 10))
			self.crop_transform = None

	def on_label_list_select(self, event):
		"""라벨 리스트에서 항목 선택 시"""
		selection = self.label_listbox.curselection()
		if not selection:
			return

		listbox_index = selection[0]

		# listbox 인덱스를 bbox 인덱스로 변환
		if not hasattr(self, 'listbox_to_bbox_map') or listbox_index not in self.listbox_to_bbox_map:
			return

		bbox_index = self.listbox_to_bbox_map[listbox_index]

		# 기존 선택 해제
		for bbox in self.bbox:
			bbox[0] = False

		# 새로 선택
		if bbox_index < len(self.bbox):
			self.bbox[bbox_index][0] = True
			self.selid = bbox_index
			
			# 메인 화면 업데이트
			self.draw_bbox()
			
			# 크롭 프리뷰 업데이트
			self.update_crop_preview()

			self.canvas.focus_set()
	def on_crop_canvas_click(self, event):
		"""크롭 캔버스 클릭 시 삭제 (레거시 - on_crop_mouse_up 에서 처리됨)"""
		pass

	# ──────────────────────────────────────────────────────────────
	# crop canvas 드래그 리사이즈 / 이동 관련 헬퍼 및 이벤트 핸들러
	# ──────────────────────────────────────────────────────────────

	def _crop_anchor_positions(self):
		"""현재 bbox를 crop_canvas 좌표로 변환해 8개 앵커 위치 dict 반환"""
		ct = self.crop_transform
		bbox = self.bbox[self.selid]
		orig_x1 = bbox[3] / self.zoom_ratio
		orig_y1 = bbox[4] / self.zoom_ratio
		orig_x2 = bbox[5] / self.zoom_ratio
		orig_y2 = bbox[6] / self.zoom_ratio
		bx1 = ct['offset_x'] + (orig_x1 - ct['crop_x1']) * ct['scale_x']
		by1 = ct['offset_y'] + (orig_y1 - ct['crop_y1']) * ct['scale_y']
		bx2 = ct['offset_x'] + (orig_x2 - ct['crop_x1']) * ct['scale_x']
		by2 = ct['offset_y'] + (orig_y2 - ct['crop_y1']) * ct['scale_y']
		mx = (bx1 + bx2) / 2
		my = (by1 + by2) / 2
		return {
			'nw': (bx1, by1), 'n': (mx, by1), 'ne': (bx2, by1),
			'e':  (bx2, my),
			'se': (bx2, by2), 's': (mx, by2), 'sw': (bx1, by2),
			'w':  (bx1, my),
		}, bx1, by1, bx2, by2

	def _update_crop_canvas_overlay(self):
		"""crop_canvas 의 bbox 사각형과 8개 앵커 핸들만 빠르게 재그리기
		   (이미지 재로드 없음 ─ 드래그 중 실시간 갱신용)"""
		if not hasattr(self, 'crop_transform') or self.crop_transform is None:
			return
		if self.selid < 0 or not self.bbox:
			return

		self.crop_canvas.delete("crop_bbox")
		self.crop_canvas.delete("crop_anchor")

		anchor_pts, bx1, by1, bx2, by2 = self._crop_anchor_positions()

		# bbox overlay (빨간 테두리)
		self.crop_canvas.create_rectangle(bx1, by1, bx2, by2,
										  outline='red', width=2,
										  tags="crop_bbox")

		# 8개 앵커 핸들 (흰 테두리 빨간 사각형)
		ah = 5
		for ax, ay in anchor_pts.values():
			self.crop_canvas.create_rectangle(ax - ah, ay - ah, ax + ah, ay + ah,
											  outline='white', fill='red', width=1,
											  tags="crop_anchor")

		# 정보 라벨 갱신
		bbox = self.bbox[self.selid]
		w = int(bbox[5] - bbox[3])
		h = int(bbox[6] - bbox[4])
		self.crop_info_label.config(text=f"{bbox[1]} ({w}x{h})  ← 드래그로 크기/위치 조절")

	def on_crop_mouse_down(self, event):
		"""crop_canvas 마우스 버튼 다운 ─ 앵커 / bbox 내부 / 외부 판별"""
		self.crop_was_dragged = False
		self.crop_resize_anchor = None
		self.crop_drag_last = (event.x, event.y)

		if self.selid < 0 or not hasattr(self, 'crop_transform') or self.crop_transform is None:
			return

		mx, my = event.x, event.y
		ANCHOR_RADIUS = 8  # 앵커 감지 반경(픽셀)

		anchor_pts, bx1, by1, bx2, by2 = self._crop_anchor_positions()

		# 앵커 핸들 클릭 확인
		for anc_name, (ax, ay) in anchor_pts.items():
			if abs(mx - ax) <= ANCHOR_RADIUS and abs(my - ay) <= ANCHOR_RADIUS:
				self.crop_resize_anchor = anc_name
				return

		# bbox 내부 클릭 → 이동 모드
		if bx1 <= mx <= bx2 and by1 <= my <= by2:
			self.crop_resize_anchor = 'move'

	def on_crop_mouse_drag(self, event):
		"""crop_canvas 드래그 ─ bbox 실시간 리사이즈 / 이동 + 메인 캔버스 동기화"""
		if self.selid < 0 or self.crop_resize_anchor is None:
			return
		if not hasattr(self, 'crop_transform') or self.crop_transform is None:
			return

		self.crop_was_dragged = True
		mx, my = event.x, event.y
		ct = self.crop_transform

		# crop_canvas 마우스 좌표 → 메인 캔버스(screen) 좌표
		orig_x = ct['crop_x1'] + (mx - ct['offset_x']) / ct['scale_x']
		orig_y = ct['crop_y1'] + (my - ct['offset_y']) / ct['scale_y']
		screen_x = orig_x * self.zoom_ratio
		screen_y = orig_y * self.zoom_ratio

		rc = list(self.bbox[self.selid][3:])  # [x1, y1, x2, y2] screen coords
		a = self.crop_resize_anchor

		if a == 'move':
			# 이전 위치와의 델타로 전체 이동
			last_mx, last_my = self.crop_drag_last
			dx = (mx - last_mx) / ct['scale_x'] * self.zoom_ratio
			dy = (my - last_my) / ct['scale_y'] * self.zoom_ratio
			rc[0] += dx;  rc[1] += dy
			rc[2] += dx;  rc[3] += dy
		else:
			if   a == 'nw': rc[0] = screen_x; rc[1] = screen_y
			elif a == 'n':                     rc[1] = screen_y
			elif a == 'ne': rc[2] = screen_x; rc[1] = screen_y
			elif a == 'e':  rc[2] = screen_x
			elif a == 'se': rc[2] = screen_x; rc[3] = screen_y
			elif a == 's':                     rc[3] = screen_y
			elif a == 'sw': rc[0] = screen_x; rc[3] = screen_y
			elif a == 'w':  rc[0] = screen_x

		self.crop_drag_last = (mx, my)

		# 좌표 유효성 확인: 최소 크기 먼저, 그 다음 이미지 경계 클램핑
		# (순서 중요: 경계 먼저 하면 최소크기 강제 시 경계 초과 가능)
		if rc[2] - rc[0] < 4:     rc[2] = rc[0] + 4
		if rc[3] - rc[1] < 4:     rc[3] = rc[1] + 4
		if rc[0] < 0:              rc[0] = 0
		if rc[1] < 0:              rc[1] = 0
		if rc[2] > self.imsize[0]: rc[2] = self.imsize[0]
		if rc[3] > self.imsize[1]: rc[3] = self.imsize[1]

		self.bbox[self.selid][3:] = rc

		# 메인 캔버스 동기화 (draw_bbox → update_crop_preview 재진입 시 overlay 만 갱신)
		self.crop_drag_active = True
		self.draw_bbox()
		self.crop_drag_active = False

	def on_crop_mouse_up(self, event):
		"""crop_canvas 마우스 버튼 업 ─ 저장 or 외부클릭 삭제"""
		if self.crop_was_dragged and self.selid >= 0:
			# 드래그로 bbox 수정됨 → 파일 저장 + 라벨 리스트 갱신
			self.write_bbox()
			self.update_label_list()
		elif not self.crop_was_dragged and self.selid >= 0:
			# 순수 클릭 → bbox 외부 클릭이면 삭제 확인 (기존 동작 유지)
			if hasattr(self, 'crop_transform') and self.crop_transform is not None:
				try:
					_, bx1, by1, bx2, by2 = self._crop_anchor_positions()
					mx, my = event.x, event.y
					if not (bx1 <= mx <= bx2 and by1 <= my <= by2):
						bbox_data = self.bbox[self.selid]
						if messagebox.askyesno("삭제 확인",
								f"{bbox_data[1]} 라벨을 삭제하시겠습니까?"):
							self.remove_bbox_rc()
							self.update_label_list()
							self.update_crop_preview()
				except Exception as e:
					print(f"on_crop_mouse_up error: {e}")

		self.crop_resize_anchor = None
		self.crop_was_dragged   = False
		self.crop_drag_active   = False

	def on_label_list_key(self, event):
		"""라벨 리스트에서 키보드 입력"""
		if event.char == keysetting[8]:  # 삭제 키
			if self.selid >= 0:
				self.remove_bbox_rc()
				self.update_label_list()
				self.update_crop_preview()
	def draw_copy_image(self):
		if self.ci == self.pi: return
		self.pi = self.ci		
		self.im_fn = self.imlist[self.ci]
		self.gt_fn = image_to_label_path(self.im_fn)
		self.canvas.delete("img")
		im = Image.open(self.im_fn)
		self.imsize = im.size
		self.imsize = [(int)(i * self.zoom_ratio) for i in im.size]
		im = im.resize(self.imsize, Image.LANCZOS)
		
		self.canvas.config(width=self.imsize[0], height=self.imsize[1])
		self.canvas.image = ImageTk.PhotoImage(im)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
		self.master.title('[%d/%d] %s' % (self.ci+1, len(self.imlist), self.im_fn))

		if self.copy_region_source_lines is not None:
			existing_lines = []
			if os.path.exists(self.gt_fn):
				try:
					with open(self.gt_fn, 'r', encoding='utf-8') as f:
						existing_lines = f.readlines()
				except (OSError, UnicodeDecodeError) as e:
					print(f"[CopyRegion] target label read failed: {e}")
			merged_lines = merge_copy_region_label_lines(
				existing_lines,
				self.copy_region_source_lines,
				self.copy_region_manager.active_regions(),
			)
			self.bbox = []
			for line in merged_lines:
				try:
					values = [float(value) for value in line.strip().split()]
					if len(values) >= 5:
						values[0] = int(values[0])
						self.bbox.append(self.convert_rel2abs(values[:5]))
				except (ValueError, IndexError):
					continue
			self.write_bbox()
			self.copy_region_source_lines = None

		if self.CLASSIFY_TPFP: self.draw_criteria()
		#self.load_bbox()
		self.draw_bbox()
		return

	def get_masking_copy_range(self):
		try:
			start_frame = int(self.start_frame_entry.get())
			end_frame = int(self.end_frame_entry.get())
		except ValueError:
			messagebox.showerror("오류", "시작 및 종료 프레임 번호는 숫자여야 합니다.")
			return None

		if start_frame < 1 or end_frame > len(self.imlist) or start_frame > end_frame:
			messagebox.showerror("오류", f"프레임 범위는 1에서 {len(self.imlist)} 사이여야 합니다.")
			return None
		return start_frame, end_frame

	def collect_masking_delete_preview(self, start_frame, end_frame):
		if not hasattr(self, 'masking') or not self.has_saved_masking:
			messagebox.showwarning("경고", "저장된 마스킹이 없습니다. 먼저 마스킹을 생성하고 저장해주세요.")
			return None

		mask_width = self.maskingframewidth
		mask_height = self.maskingframeheight
		preview = []

		for i in range(start_frame - 1, end_frame):
			if i == self.ci:
				continue
			target_img_path = self.imlist[i]
			try:
				with Image.open(target_img_path) as target_img:
					if target_img.width != mask_width or target_img.height != mask_height:
						preview.append({
							'frame_idx': i,
							'image_path': target_img_path,
							'label_path': self.get_label_path_for_image(target_img_path),
							'original': 0,
							'deleted': 0,
							'skipped': True,
							'reason': 'size mismatch',
						})
						continue
			except Exception as e:
				preview.append({
					'frame_idx': i,
					'image_path': target_img_path,
					'label_path': self.get_label_path_for_image(target_img_path),
					'original': 0,
					'deleted': 0,
					'skipped': True,
					'reason': str(e),
				})
				continue

			label_path = self.get_label_path_for_image(target_img_path)
			_, original_count, deleted_count = self.filter_label_lines_by_current_mask(label_path, mask_width, mask_height)
			preview.append({
				'frame_idx': i,
				'image_path': target_img_path,
				'label_path': label_path,
				'original': original_count,
				'deleted': deleted_count,
				'skipped': False,
				'reason': '',
			})

		return preview

	def preview_masking_delete_to_range(self):
		range_values = self.get_masking_copy_range()
		if not range_values:
			return
		start_frame, end_frame = range_values
		preview = self.collect_masking_delete_preview(start_frame, end_frame)
		if preview is None:
			return

		total_deleted = sum(item['deleted'] for item in preview)
		affected_frames = sum(1 for item in preview if item['deleted'] > 0)
		skipped_frames = sum(1 for item in preview if item['skipped'])
		detail_lines = []
		for item in preview:
			if item['deleted'] > 0 or item['skipped']:
				if item['skipped']:
					detail_lines.append(f"{item['frame_idx'] + 1}: skipped ({item['reason']})")
				else:
					detail_lines.append(f"{item['frame_idx'] + 1}: delete {item['deleted']}/{item['original']}")
			if len(detail_lines) >= 20:
				break

		msg = (
			f"마스킹 삭제 Dry-run\n\n"
			f"범위: {start_frame} ~ {end_frame}\n"
			f"삭제 예정 라벨: {total_deleted}개\n"
			f"영향 프레임: {affected_frames}개\n"
			f"스킵 프레임: {skipped_frames}개"
		)
		if detail_lines:
			msg += "\n\n" + "\n".join(detail_lines)
			if len(detail_lines) < affected_frames + skipped_frames:
				msg += "\n..."
		messagebox.showinfo("마스킹 Dry-run", msg)

	def copy_masking_to_range(self):
		"""현재 저장된 마스킹을 지정된 범위의 이미지들에 복사"""
		# 저장된 마스킹이 없으면 경고 메시지 표시하고 종료
		if not hasattr(self, 'masking') or not self.has_saved_masking:
			messagebox.showwarning("경고", "저장된 마스킹이 없습니다. 먼저 마스킹을 생성하고 저장해주세요.")
			return
		
		# 시작 및 종료 프레임 번호 가져오기
		try:
			start_frame = int(self.start_frame_entry.get())
			end_frame = int(self.end_frame_entry.get())
		except ValueError:
			messagebox.showerror("오류", "시작 및 종료 프레임 번호는 숫자여야 합니다.")
			return
		
		# 프레임 범위 검증
		if start_frame < 1 or end_frame > len(self.imlist) or start_frame > end_frame:
			messagebox.showerror("오류", f"프레임 범위는 1에서 {len(self.imlist)} 사이여야 합니다.")
			return
		
		# 현재 보고 있는 이미지 인덱스 저장
		current_idx = self.ci
		
		# 확인 메시지 (라벨 삭제 여부 포함)
		confirm_msg = f"{start_frame}에서 {end_frame}까지의 이미지에 마스킹을 복사하시겠습니까?"
		if self.remove_overlapping_labels.get():
			confirm_msg += "\n마스킹과 겹치는 라벨도 함께 삭제됩니다."
		
		if not messagebox.askyesno("확인", confirm_msg):
			return
		
		# 진행 상황 창 생성
		progress_window = tk.Toplevel(self.master)
		progress_window.title("마스킹 복사 중...")
		progress_window.geometry("300x100")
		progress_window.transient(self.master)
		
		progress_label = tk.Label(progress_window, text="마스킹을 복사 중입니다...", pady=10)
		progress_label.pack()
		
		progress_bar = ttk.Progressbar(progress_window, orient="horizontal",
										length=250, mode="determinate")
		progress_bar.pack(pady=10)
		
		# 마스킹 크기 확인
		mask_width = self.maskingframewidth
		mask_height = self.maskingframeheight
		
		# 프로그레스 바 설정
		total_frames = end_frame - start_frame + 1
		progress_bar["maximum"] = total_frames
		progress_bar["value"] = 0
		
		# 첫 번째 이미지에 적용
		self.master.update()
		
		# 폴리곤 포인트 정보 저장 여부 확인
		
		# 지정된 범위의 이미지에 마스킹 적용
		success_count = 0
		total_labels_deleted = 0  # 전체 삭제된 라벨 개수 추적
		modified_label_files = []  # 수정된 라벨 파일 목록

		for i in range(start_frame - 1, end_frame):
			# 프로그레스 바 업데이트
			progress_bar["value"] = i - (start_frame - 1) + 1
			progress_label.config(text=f"처리 중: {i+1}/{end_frame} ({int(progress_bar['value']/total_frames*100)}%)")
			self.master.update()

			# 현재 이미지 건너뛰기
			if i == current_idx:
				continue

			try:
				# 대상 이미지 로드
				target_img_path = self.imlist[i]
				target_img = Image.open(target_img_path)
				target_label_path = image_to_label_path(target_img_path)

				# 이미지 크기 확인
				if target_img.width != mask_width or target_img.height != mask_height:
					print(f"이미지 {i+1}의 크기가 마스킹과 일치하지 않습니다. 건너뜁니다.")
					continue

				label_backup_path = target_label_path if self.remove_overlapping_labels.get() else None
				if not self.backup_original_pair(target_img_path, label_backup_path):
					print(f"[MaskCopy] Backup failed. Skipped frame: {target_img_path}")
					continue

				# 마스킹 적용
				target_img_array = array(target_img)
				target_img_array[self.masking] = [255, 0, 255]
				target_img = Image.fromarray(target_img_array)
				replacements = {}
				temp_paths = []
				deleted_label_count = 0
				original_label_count = 0

				try:
					temp_img_path = target_img_path + '.tmp_gtgen'
					image_format = Image.registered_extensions().get(os.path.splitext(target_img_path)[1].lower())
					if image_format:
						target_img.save(temp_img_path, format=image_format)
					else:
						target_img.save(temp_img_path)
					replacements[target_img_path] = temp_img_path
					temp_paths.append(temp_img_path)

					if self.remove_overlapping_labels.get():
						label_dir = os.path.dirname(target_label_path)
						if label_dir and not os.path.exists(label_dir):
							os.makedirs(label_dir)
						labels_to_keep, original_label_count, deleted_label_count = self.filter_label_lines_by_current_mask(
							target_label_path,
							mask_width,
							mask_height
						)
						temp_label_path = target_label_path + '.tmp_gtgen'
						with open(temp_label_path, 'w', encoding='utf-8') as f:
							f.writelines(labels_to_keep)
						replacements[target_label_path] = temp_label_path
						temp_paths.append(temp_label_path)

					if not self.replace_files_transaction(replacements):
						print(f"[MaskCopy] Transaction failed. Skipped frame: {target_img_path}")
						continue

					if deleted_label_count > 0:
						print(f"[MaskCopy] Frame {i+1}: deleted {deleted_label_count}/{original_label_count} labels by mask pixels")
						total_labels_deleted += deleted_label_count
						modified_label_files.append(target_label_path)

					success_count += 1
					continue
				except Exception as e:
					print(f"[MaskCopy] Prepare failed for frame {i+1}: {e}")
					for temp_path in temp_paths:
						try:
							if os.path.exists(temp_path):
								os.remove(temp_path)
						except Exception:
							pass
					continue

				# 이미지 저장

			except Exception as e:
				print(f"이미지 {i+1} 처리 중 오류 발생: {e}")
		
		# 진행 창 닫기
		progress_window.destroy()

		# 캔버스에서 폴리곤 및 마스킹 관련 요소들 삭제
		self.canvas.delete("polygon")
		self.canvas.delete("polygon_point")
		self.canvas.delete("temp_line")
		self.canvas.delete("masking")
		self.canvas.delete("masking_m")

		# 폴리곤 마스킹 관련 변수 초기화
		self.polygon_masking = False
		self.polygon_points = []
		self.is_polygon_closed = False

		# 완료 메시지 (라벨 삭제 정보 포함)
		completion_msg = f"마스킹 복사가 완료되었습니다.\n{success_count}개의 이미지에 성공적으로 적용되었습니다."
		if total_labels_deleted > 0:
			completion_msg += f"\n\n총 {total_labels_deleted}개의 라벨이 삭제되었습니다."
			completion_msg += f"\n수정된 라벨 파일: {len(modified_label_files)}개"
			completion_msg += "\n\n✓ 파일에 저장 완료 (다른 페이지 방문 시 자동 반영됨)"
			print(f"\n[CacheOptimization] 마스킹 복사 완료 - 총 {total_labels_deleted}개 라벨 삭제, {len(modified_label_files)}개 파일 수정 (캐시 업데이트 생략)")
		else:
			print(f"[CacheOptimization] 마스킹 복사 완료 - {success_count}개 이미지 처리 (캐시 업데이트 생략)")

		messagebox.showinfo("완료", completion_msg)

		# 현재 이미지 다시 표시
		self.draw_image()
		# rel: [clsidx, cx, cy, w, h]
	# abs: [sel, clsname, info, x1, y1, x2, y2]
	def crop_img(self):		
		minx = 100000
		miny = 100000
		maxx = 0
		maxy = 0
		for i in (0,2):
			if minx > self.area[i]:minx =self.area[i]
			if maxx < self.area[i]:maxx =self.area[i]
		for i in (1,3):
			if miny > self.area[i]:miny =self.area[i]
			if maxy < self.area[i]:maxy =self.area[i]
		self.area[0] = minx
		self.area[1] = miny
		self.area[2] = maxx
		self.area[3] = maxy

		cropped_img = self.img.crop(self.area)
		crop_im_fn = self.make_path(self.im_fn)
		crop_gt_fn = self.make_path(self.gt_fn)
		cropped_img.save(self.im_fn)

		f = open(self.gt_fn, 'wt')
		croprc=[]
		cropidx=0
		width = self.imsize[0]
		height = self.imsize[1]
		ori_x,ori_y = self.area[:2]
		
		# crop canvas에 반영
		self.l_region = False
		self.imsize = cropped_img.size
		self.imsize = [(int)(i * self.zoom_ratio) for i in cropped_img.size]
		im = cropped_img.resize(self.imsize, Image.LANCZOS)
		if os.path.exists(self.gt_fn):
			filesize = os.path.getsize(self.gt_fn)
		else:
			filesize = 0

		self.canvas.config(width=self.imsize[0], height=self.imsize[1])
		self.canvas.image = ImageTk.PhotoImage(cropped_img)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
		self.master.title('[%d/%d] %s' % (self.ci+1, len(self.imlist), self.im_fn))

		self.canvas.delete("bbox")
		bboxtemp = copy.deepcopy(self.bbox)
		inindex = []
		bboxindex = 0
		for orirc in bboxtemp:
			x1,y1,x2,y2 = orirc[3:]
			if self.get_iou(self.area,orirc[3:]) > 0 :
				if x1 <self.area[0] :
					x1 = self.area[0]
				if x2 > self.area[2]:
					x2 = self.area[2]
				if y1 < self.area[1] :
					y1 = self.area[1]
				if y2 > self.area[3]:
					y2 = self.area[3]
				orirc[3] = x1 - ori_x
				orirc[4] = y1 - ori_y
				orirc[5] = x2 - ori_x
				orirc[6] = y2 - ori_y			
				self.draw_bbox_rc(orirc)
				croprc.append(orirc)
				cropidx += 1
				inindex.append(bboxindex)
			bboxindex += 1

		okbbox = []
		for idx in inindex:
			bboxtemp[idx][0]=False
			okbbox.append(bboxtemp[idx])
		self.bbox = copy.deepcopy(okbbox)
		for rc in croprc:
			f.write(' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n')
		f.close()
		self.selid = -1
		self.bbox_crop = False
		self.bbox_add = False
		self.bbox_crop = False
		if len(self.bbox) <= 0: return
		self.bbox[self.selid][0] = False
		self.selid += 1
		self.selid = 0 if self.selid >= len(self.bbox) else self.selid
		self.bbox[self.selid][0] = True
		self.draw_bbox()
		rc = self.convert_abs2rel(self.bbox[self.selid])
		self.pre_rc = self.convert_rel2abs(rc)
		pass

	def masking_img(self):
		# self.img = array(self.img)
		
		# 화면상 마스킹 영역 좌표 정규화
		minx = min(self.m_area[0], self.m_area[2])
		miny = min(self.m_area[1], self.m_area[3])
		maxx = max(self.m_area[0], self.m_area[2])
		maxy = max(self.m_area[1], self.m_area[3])
		
		# print(f"화면 좌표 - minx:{minx}, miny:{miny}, maxx:{maxx}, maxy:{maxy}")


		# 현재 뷰 좌표를 원본 이미지 좌표로 변환
		orig_minx, orig_miny = self.convert_view_to_original(minx, miny)
		orig_maxx, orig_maxy = self.convert_view_to_original(maxx, maxy)

		# print(f"원본 좌표 - minx:{orig_minx}, miny:{orig_miny}, maxx:{orig_maxx}, maxy:{orig_maxy}")
		# print(f"이미지 크기 - width:{self.original_width}, height:{self.original_height}")
		# print(f"줌 비율: {self.zoom_ratio}")
	
		
		# 좌표가 이미지 크기를 벗어나지 않도록 보정
		orig_minx = max(0, orig_minx)
		orig_miny = max(0, orig_miny)
		orig_maxx = min(self.original_width, orig_maxx)
		orig_maxy = min(self.original_height, orig_maxy)

		# print(f"보정 후 좌표 - minx:{orig_minx}, miny:{orig_miny}, maxx:{orig_maxx}, maxy:{orig_maxy}")


		self.current_img_array[orig_miny:orig_maxy, orig_minx:orig_maxx, :] = [255, 0, 255]
		

		self.maskingframewidth = self.original_width
		self.maskingframeheight = self.original_height
		self.masking = np.where((self.current_img_array==[255,0,255]).all(axis=2))
		self.has_saved_masking = True
		self.is_masking_dirty = True  # 저장 필요 플래그 설정

		display_img = Image.fromarray(self.current_img_array)
		if self.remove_overlapping_labels.get():
			self.remove_labels_overlapping_with_mask()

		self.canvas.delete("masking")
		self.bbox_masking = False
		resized_img = display_img.resize(self.imsize, Image.LANCZOS)
		self.canvas.image = ImageTk.PhotoImage(resized_img)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")

		# # 원본 이미지에 마스킹 적용
		# self.img[orig_miny:orig_maxy, orig_minx:orig_maxx, :] = [255, 0, 255]
		# self.img = Image.fromarray(self.img)
		# self.maskingframewidth = self.original_width
		# self.maskingframeheight = self.original_height
		# tmp_img = array(self.img)
		# self.masking = np.where((tmp_img==[255,0,255]).all(axis=2))
		# self.has_saved_masking = True

		# # 마스킹 영역 정보 저장 (원본 이미지 기준 좌표)
		# self.img.save(self.im_fn)
		# self.original_mask_area = [orig_minx, orig_miny, orig_maxx, orig_maxy]
		
		# # 마스킹과 겹치는 라벨 삭제 옵션이 켜져 있는 경우
		# if self.remove_overlapping_labels.get():
		# 	self.remove_labels_overlapping_with_mask(self.m_area)
		
		# # 캔버스에서 마스킹 관련 요소들 삭제
		# self.canvas.delete("masking")
		
		# # 마스킹 모드 비활성화
		# self.bbox_masking = False
		
		# # 이미지 업데이트 (옵션)
		# self.canvas.image = ImageTk.PhotoImage(self.img.resize(self.imsize, Image.LANCZOS))
		# self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")

	def remove_labels_overlapping_with_mask(self, mask_area=None):
		"""마스킹 영역과 겹치는 라벨 삭제

		Args:
			mask_area: 하위 호환용 영역 값. 실제 삭제 판정은 마스크 픽셀을 기준으로 수행.
		"""
		if not self.bbox:
			return
		
		# 삭제할 라벨 인덱스 리스트 (역순으로 삭제하기 위해)
		to_remove = []
		
		# 겹치는 라벨 찾기
		for i, box in enumerate(self.bbox):
			if self.check_bbox_mask_pixel_overlap(box):
				to_remove.append(i)

		if to_remove and not self.backup_original_file(self.gt_fn, 'labels'):
			messagebox.showerror("Backup Error", f"Backup failed. Labels were not removed:\n{self.gt_fn}")
			return

		# 역순으로 삭제 (인덱스 변화 방지)
		for i in sorted(to_remove, reverse=True):
			self.bbox.pop(i)
		
		# 현재 선택 바운딩 박스 조정
		if to_remove and self.selid >= 0:
			if self.selid in to_remove:
				# 선택된 박스가 삭제된 경우
				self.selid = max(0, len(self.bbox) - 1) if self.bbox else -1
			else:
				# 선택된 박스의 인덱스 갱신
				new_selid = self.selid
				for i in to_remove:
					if i < self.selid:
						new_selid -= 1
				self.selid = new_selid
		
		# 바운딩 박스가 남아있으면 선택 상태 업데이트
		if self.bbox and self.selid >= 0:
			for i in range(len(self.bbox)):
				self.bbox[i][0] = (i == self.selid)
		
		# 라벨 파일 업데이트
		self.write_bbox()
	def m_masking_img(self,rc):
		# 현재 뷰 좌표를 원본 이미지 좌표로 변환
		orig_x, orig_y = self.convert_view_to_original(rc[0], rc[1])
		
		# 점 크기도 줌 비율에 맞게 조정 (최소 1픽셀)
		mask_size = max(1, int(3 / self.zoom_ratio))
		
		# 좌표가 이미지 크기를 벗어나지 않도록 보정
		x_min = max(0, orig_x - mask_size)
		y_min = max(0, orig_y - mask_size)
		x_max = min(self.original_width, orig_x + mask_size)
		y_max = min(self.original_height, orig_y + mask_size)
		
		# 메모리상에서만 마스킹 적용 (파일 저장 안함)
		self.current_img_array[y_min:y_max, x_min:x_max, :] = [255, 0, 255]
		self.is_masking_dirty = True  # 저장 필요 플래그 설정
	def convert_rel2abs(self, rc):
		try:
			w = rc[3] * self.imsize[0]
			h = rc[4] * self.imsize[1]
			x = (rc[1] - rc[3]/2) * self.imsize[0]
			y = (rc[2] - rc[4]/2) * self.imsize[1]
			# 왼쪽/위쪽으로 넘친 박스는 넘친 만큼 폭/높이를 줄여 경계에서 자른다
			# (시작점만 0으로 당기면 박스가 안쪽으로 밀려 들어가 좌표가 바뀐다)
			if x<0:
				w=max(w+x, 1)
				x=0
			if y<0:
				h=max(h+y, 1)
				y=0
			if x+w>self.imsize[0]:
				w=self.imsize[0]-x-1
			if y+h>self.imsize[1]:
				h=self.imsize[1]-y-1

			# 클래스 인덱스 범위 체크 - 원본 ID 유지
			class_idx = int(rc[0])
			if 0 <= class_idx < len(class_name):
				name = class_name[class_idx]
			else:
				# 설정에 없는 클래스는 원본 ID를 유지하고 Unknown으로 표시
				print(f"WARNING: Class index {class_idx} not in config, keeping original ID")
				name = f"Unknown({class_idx})"

			return [False, name, class_idx, (x), (y), (x+w), (y+h)]
		except (IndexError, ValueError, TypeError) as e:
			print(f"ERROR in convert_rel2abs: {e}, rc={rc}")
			return [False, class_name[0] if class_name else "unknown", 0, 0, 0, 10, 10]

	def convert_abs2rel(self, rc):
		r = rc[3:]

		# Division by zero 방어
		if self.imsize[0] == 0 or self.imsize[1] == 0:
			print(f"ERROR: Image size is zero: {self.imsize}")
			return [0, 0.5, 0.5, 0.1, 0.1]  # 기본값 반환

		try:
			cx = 0.5 * (float(r[0]) + float(r[2])) / float(self.imsize[0])
			cy = 0.5 * (float(r[1]) + float(r[3])) / float(self.imsize[1])
			w  = abs(float(r[2] - r[0])  / float(self.imsize[0]))
			h  = abs(float(r[3] - r[1])  / float(self.imsize[1]))
			# rc[2]에 저장된 원본 class_idx를 직접 사용 (rc[1] name에서 추출하지 않음)
			# 소수점 5자리까지 반올림
			return [int(rc[2]), round(cx, 5), round(cy, 5), round(w, 5), round(h, 5)]
		except (ValueError, ZeroDivisionError) as e:
			print(f"ERROR in convert_abs2rel: {e}, rc={rc}")
			return [0, 0.5, 0.5, 0.1, 0.1]

	def bound_box_coord(self, r):
		if r[2] < 0: r[2] = 0
		if r[3] < 0: r[3] = 0
		if r[2] > self.imsize[0]: r[2] = self.imsize[0]
		if r[3] > self.imsize[1]: r[3] = self.imsize[1]
		return r

	def bbox_dedupe_key(self, bbox):
		rel = self.convert_abs2rel(bbox)
		return (int(rel[0]),) + tuple(round(float(value), 5) for value in rel[1:])

	def dedupe_bboxes(self, bboxes, context="bbox"):
		seen = set()
		deduped = []
		removed = 0
		for bbox in bboxes:
			try:
				key = self.bbox_dedupe_key(bbox)
			except Exception as e:
				print(f"[LabelDedupe] key failed in {context}: {e}")
				deduped.append(bbox)
				continue
			if key in seen:
				removed += 1
				continue
			seen.add(key)
			deduped.append(bbox)
		if removed:
			print(f"[LabelDedupe] removed {removed} duplicate labels ({context})")
		return deduped, removed

	def has_same_bbox(self, candidate_bbox):
		try:
			candidate_key = self.bbox_dedupe_key(candidate_bbox)
		except Exception as e:
			print(f"[LabelDedupe] candidate key failed: {e}")
			return False
		for bbox in self.bbox:
			try:
				if self.bbox_dedupe_key(bbox) == candidate_key:
					return True
			except Exception:
				continue
		return False

	def load_bbox(self):
		# 페이지 이동 전 현재 페이지 데이터 저장 (자동 복사용)
		self.save_current_page_data()

		self.selid = -1
		self.bbox = []

		try:
			with open(self.gt_fn, 'r') as f:
				for l in f.readlines():
					try:
						# 빈 라인 무시
						if not l.strip():
							continue

						gt = [float(c) for c in l.replace('\r','').replace('\n','').split(' ')]
						gt[0] = int(gt[0])
						# if gt[0] > 0:
						# 	gt[0] = gt[0]+6

						self.bbox.append(self.convert_rel2abs(gt))
					except (ValueError, IndexError) as e:
						print(f"WARNING: Malformed label data: {l.strip()}, error: {e}")
						continue
			#self.bbox.append(self.remove_bbox_rc())
		except FileNotFoundError:
			# 라벨 파일이 없는 경우 - 정상 (새 이미지)
			pass
		except (IOError, PermissionError) as e:
			print(f"ERROR: Failed to load bbox from {self.gt_fn}: {e}")

		self.bbox, _ = self.dedupe_bboxes(self.bbox, "load")

		# === 자동 필터링 적용 ===
		total_deleted = 0

		# 1. 클래스 자동 삭제 필터링 (mode="auto"인 클래스만 페이지 이동 시 자동 삭제)
		if self.auto_delete_manager and self.auto_delete_manager.delete_class_config:
			before_count = len(self.bbox)
			# class_name은 전역 변수
			global class_name
			# mode_filter="auto"로 페이지 이동 시 자동 삭제되는 클래스만 필터링
			self.bbox = self.auto_delete_manager.filter_bboxes(self.bbox, class_name, mode_filter="auto")
			deleted_count = before_count - len(self.bbox)
			if deleted_count > 0:
				print(f"[AutoDelete] {deleted_count}개 라벨 자동 삭제됨 (페이지 이동 시)")
				total_deleted += deleted_count

		# 2. 제외 영역 필터링
		print(f"[DEBUG] 제외 영역 필터링 체크: enabled={self.exclusion_zone_enabled}, manager={self.exclusion_zone_manager is not None}")
		if self.exclusion_zone_enabled and self.exclusion_zone_manager:
			before_count = len(self.bbox)
			print(f"[DEBUG] 제외 영역 필터링 시작: {before_count}개 라벨 검사")
			self.bbox = [bbox for bbox in self.bbox if not self.exclusion_zone_manager.is_bbox_in_exclusion_zone(bbox, zoom_ratio=self.zoom_ratio)]
			deleted_count = before_count - len(self.bbox)
			print(f"[DEBUG] 제외 영역 필터링 완료: {deleted_count}개 삭제됨")
			if deleted_count > 0:
				print(f"[ExclusionZone] {deleted_count}개 라벨 제외 영역에서 삭제됨")
				total_deleted += deleted_count

		# 3. 클래스 변경 영역 자동 적용
		if self.class_change_zone_manager and self.class_change_zone_manager.zones:
			self.bbox, changed_count = self.class_change_zone_manager.apply_class_changes(
				self.bbox, class_name, self.zoom_ratio
			)
			if changed_count > 0:
				print(f"[ClassChangeZone] {changed_count}개 bbox 클래스가 자동 변경됨 (페이지 이동 시)")
				total_deleted += 1  # 변경 플래그 설정 (파일 저장 트리거)

		# 필터링으로 라벨이 삭제되었으면 파일에 반영
		if total_deleted > 0:
			self.write_bbox()
			print(f"[Filter] 총 {total_deleted}개 라벨이 자동 삭제되어 파일에 저장됨")

		# 자동 복사 적용 (라벨 및 마스킹)
		self.apply_auto_copy_to_page()

		if len(self.bbox) > 0:
			self.bbox[0][0] = True
			self.selid = 0
		return

	def write_bbox(self):
		if self.gt_fn is None:
			print("WARNING: gt_fn is None, cannot write bbox")
			return
		if self.im_fn and os.path.normcase(os.path.abspath(self.gt_fn)) == os.path.normcase(os.path.abspath(self.im_fn)):
			print(f"ERROR: label path equals image path, refusing to overwrite image: {self.im_fn}")
			return

		try:
			self.bbox, removed = self.dedupe_bboxes(self.bbox, "write")
			if self.selid >= len(self.bbox):
				self.selid = len(self.bbox) - 1
			output = ''.join(
				' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n'
				for rc in self.bbox
			)
			if not self.write_text_files_transaction({self.gt_fn: output}, backup_category='labels'):
				print(f"ERROR: Failed to save bbox transactionally: {self.gt_fn}")
				if not getattr(self, '_label_save_error_shown', False):
					self._label_save_error_shown = True
					messagebox.showerror("라벨 저장 실패", f"라벨을 저장하지 못했습니다 (백업 또는 쓰기 실패).\n{self.gt_fn}\n\n콘솔 로그를 확인하세요.")
				else:
					self.show_temporary_status(f"라벨 저장 실패: {os.path.basename(self.gt_fn)}", duration=3000, bg_color='#DC2626')
		except (IOError, PermissionError) as e:
			print(f"ERROR: Failed to write bbox to {self.gt_fn}: {e}")
			messagebox.showerror("File Write Error", f"Failed to save labels:\n{e}")
		return

	def get_label_path_for_image(self, image_path):
		return self.iou_track_manager.get_label_path_for_image(image_path)

	def calc_iou_original(self, box_a, box_b):
		return self.iou_track_manager.calc_iou(box_a, box_b)

	def get_bbox_original_coords(self, bbox):
		x1, y1 = self.convert_view_to_original(bbox[3], bbox[4])
		x2, y2 = self.convert_view_to_original(bbox[5], bbox[6])
		return [x1, y1, x2, y2]

	def build_current_label_line(self, bbox):
		return ' '.join(str(e) for e in self.convert_abs2rel(bbox)) + '\n'

	def load_tracking_label_records(self, image_path):
		return self.iou_track_manager.load_label_records(image_path)

	def find_label_line_index(self, label_path, label_line, preferred_index=-1):
		"""label_line과 같은 내용의 줄 번호를 파일에서 찾는다 (preferred_index 우선). 없으면 -1."""
		target = label_line.split()
		try:
			with open(label_path, 'r', encoding='utf-8') as f:
				file_lines = f.readlines()
		except UnicodeDecodeError:
			with open(label_path, 'r', encoding='cp949') as f:
				file_lines = f.readlines()
		except Exception:
			return -1
		if 0 <= preferred_index < len(file_lines) and file_lines[preferred_index].split() == target:
			return preferred_index
		for line_index, line in enumerate(file_lines):
			if line.split() == target:
				return line_index
		return -1

	def run_iou_track(self):
		if self.selid < 0 or self.selid >= len(self.bbox):
			messagebox.showwarning("IOU 추적", "먼저 추적할 bbox를 선택하세요.")
			return None

		try:
			track_range = int(self.track_range_entry.get())
		except ValueError:
			messagebox.showerror("IOU 추적", "추적 범위는 숫자여야 합니다.")
			return None

		try:
			iou_threshold = float(self.track_iou_entry.get())
		except ValueError:
			messagebox.showerror("IOU 추적", "IOU 값은 숫자여야 합니다.")
			return None

		if track_range < 1:
			messagebox.showerror("IOU 추적", "추적 범위는 1 이상이어야 합니다.")
			return None
		if iou_threshold < 0 or iou_threshold > 1:
			messagebox.showerror("IOU 추적", "IOU 값은 0~1 사이여야 합니다.")
			return None

		start_idx = self.ci
		end_idx = min(len(self.imlist) - 1, start_idx + track_range)
		selected_bbox = copy.deepcopy(self.bbox[self.selid])
		selected_label_line = self.build_current_label_line(selected_bbox)
		# self.bbox는 로드 시 중복/빈 줄이 제거되므로 selid가 파일 줄 번호와 다를 수 있다.
		# 현재 bbox를 먼저 저장해 파일과 맞춘 뒤, 파일에서 선택 박스의 실제 줄 번호를 찾는다.
		self.write_bbox()
		selected_line_index = self.find_label_line_index(self.gt_fn, selected_label_line, self.selid)
		selected_class_id = int(selected_bbox[2])
		same_class_only = self.track_same_class_var.get() if hasattr(self, 'track_same_class_var') else True
		result = self.iou_track_manager.track(
			self.imlist,
			self.gt_fn,
			start_idx,
			end_idx,
			self.get_bbox_original_coords(selected_bbox),
			selected_class_id,
			selected_label_line,
			selected_line_index,
			iou_threshold,
			same_class_only,
			max_missing=2
		)
		self.last_iou_track_result = result
		return result

	def preview_iou_track(self):
		result = self.run_iou_track()
		if not result:
			return

		match_count = len(result['matches'])
		missing_count = len(result['missing'])
		iou_values = [m['iou'] for m in result['matches'][1:]]
		avg_iou = sum(iou_values) / len(iou_values) if iou_values else 1.0
		last_frame = result['matches'][-1]['frame_idx'] + 1 if result['matches'] else result['start_idx'] + 1
		msg = (
			f"IOU 추적 미리보기\n\n"
			f"범위: {result['start_idx'] + 1} ~ {result['end_idx'] + 1}\n"
			f"매칭: {match_count} 프레임\n"
			f"미매칭: {missing_count} 프레임\n"
			f"평균 IOU: {avg_iou:.3f}\n"
			f"마지막 매칭 프레임: {last_frame}"
		)
		if result['stopped']:
			msg += "\n\n연속 미매칭으로 추적을 조기 중단했습니다."
		messagebox.showinfo("IOU 추적", msg)
		self.show_iou_track_review(result)
		self.show_temporary_status(f"IOU 추적 미리보기: {match_count}개 매칭, {missing_count}개 미매칭", duration=2500, bg_color='#2563EB')

	def show_iou_track_review(self, result):
		rows = []
		for item in result.get('matches', []):
			rows.append({
				'frame_idx': item['frame_idx'],
				'status': 'MATCH',
				'iou': item.get('iou', 1.0),
				'best_iou': item.get('iou', 1.0),
			})
		for item in result.get('missing', []):
			rows.append({
				'frame_idx': item['frame_idx'],
				'status': 'MISS',
				'iou': None,
				'best_iou': item.get('best_iou', 0.0),
			})
		rows.sort(key=lambda item: item['frame_idx'])

		window = tk.Toplevel(self.master)
		window.title("IOU Track Review")
		window.geometry("520x420")
		window.transient(self.master)

		threshold = result.get('threshold', result.get('iou_threshold', 0.0))
		header = tk.Label(
			window,
			text=f"Frames {result['start_idx'] + 1} - {result['end_idx'] + 1} / threshold {threshold:.2f}",
			anchor='w'
		)
		header.pack(fill=tk.X, padx=10, pady=(10, 4))

		list_frame = tk.Frame(window)
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
		scrollbar = tk.Scrollbar(list_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
		listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 10))
		listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		scrollbar.config(command=listbox.yview)

		for row in rows:
			if row['status'] == 'MATCH':
				text = f"{row['frame_idx'] + 1:5d}  MATCH  iou={row['iou']:.3f}"
			else:
				text = f"{row['frame_idx'] + 1:5d}  MISS   best={row['best_iou']:.3f}"
			listbox.insert(tk.END, text)

		def go_selected():
			selection = listbox.curselection()
			if not selection:
				return
			frame_idx = rows[selection[0]]['frame_idx']
			self.write_bbox()
			self.ci = frame_idx
			if hasattr(self, 'img_slider'):
				self.img_slider.set(self.ci + 1)
			if hasattr(self, 'slider_info'):
				self.slider_info.config(text=f"{self.ci + 1}/{len(self.imlist)}")
			self.pi = -1
			self.draw_image()

		def keep_only_and_close():
			window.destroy()
			# Go로 프레임/선택이 바뀌었어도 미리보기한 결과 그대로 적용
			self.apply_iou_track_keep_only(result)

		button_frame = tk.Frame(window)
		button_frame.pack(fill=tk.X, padx=10, pady=(4, 10))
		tk.Button(button_frame, text="Go", command=go_selected, width=10).pack(side=tk.LEFT, padx=(0, 6))
		tk.Button(button_frame, text="Keep Only", command=keep_only_and_close, width=12).pack(side=tk.LEFT, padx=(0, 6))
		tk.Button(button_frame, text="Close", command=window.destroy, width=10).pack(side=tk.RIGHT)

	def apply_iou_track_keep_only(self, result=None):
		if result is None:
			result = self.run_iou_track()
		if not result:
			return

		targets = result['matches']
		if not targets:
			messagebox.showwarning("IOU 추적", "적용할 매칭 결과가 없습니다.")
			return

		if not messagebox.askyesno(
			"IOU 추적 Keep Only",
			f"{len(targets)}개 프레임에서 추적된 bbox만 남기고 나머지 라벨을 삭제합니다.\n계속하시겠습니까?"
		):
			return

		preserve_other_classes = result.get('same_class_only', False)
		tracked_class_id = result.get('class_id')
		file_text_map = {}
		for item in targets:
			file_text_map[item['label_path']] = self.iou_track_manager.build_keep_only_label_text(
				item['label_path'],
				item['line'],
				item.get('line_index', -1),
				tracked_class_id,
				preserve_other_classes
			)
		if not self.write_text_files_transaction(file_text_map, backup_category='labels'):
			messagebox.showerror("IOU 추적", "라벨 저장 준비 또는 적용 중 오류가 발생했습니다. 변경은 중단되었습니다.")
			return

		self.pi = -1
		self.draw_image()
		mode_msg = "same-class only" if preserve_other_classes else "all labels"
		self.show_temporary_status(f"IOU Keep Only applied: {len(file_text_map)} frames ({mode_msg})", duration=2500, bg_color='#0F766E')

	def toggle_auto_copy_labels(self):
		"""라벨 자동 복사 기능 활성화/비활성화"""
		self.auto_copy_labels_enabled = self.auto_copy_labels_var.get()
		if self.auto_copy_labels_enabled:
			print("[AutoCopy] 라벨 자동 복사 활성화")
			messagebox.showinfo("라벨 자동 복사",
				"라벨 자동 복사가 활성화되었습니다.\n\n"
				"📌 복사 우선순위:\n"
				"  1. 다중 선택: 선택된 여러 라벨 복사\n"
				"  2. 단일 선택: 선택된 1개 라벨 복사\n"
				"  3. j로 복사: j키로 복사해둔 라벨 사용\n"
				"  4. 선택/복사 없음: 복사 안함\n\n"
				"페이지 이동 시 다음 페이지에 자동으로 복사됩니다.")
		else:
			print("[AutoCopy] 라벨 자동 복사 비활성화")
			self.prev_page_labels = None

	def toggle_auto_copy_masking(self):
		"""마스킹 자동 복사 기능 활성화/비활성화"""
		self.auto_copy_masking_enabled = self.auto_copy_masking_var.get()
		if self.auto_copy_masking_enabled:
			print("[AutoCopy] 마스킹 자동 복사 활성화")
			messagebox.showinfo("마스킹 자동 복사", "마스킹 자동 복사가 활성화되었습니다.\n페이지 이동 시 현재 페이지의 마스킹이 다음 페이지에 자동으로 복사됩니다.")
		else:
			print("[AutoCopy] 마스킹 자동 복사 비활성화")
			self.prev_page_masking = None
			self.prev_page_polygon_points = None

	def save_current_page_data(self):
		"""페이지 이동 전 현재 페이지 데이터 저장"""
		# 라벨 자동 복사가 활성화되어 있으면 선택된 라벨만 저장
		if self.auto_copy_labels_enabled:
			self.prev_page_labels = []

			# 다중 선택된 라벨이 있으면 다중 선택된 라벨들만 복사
			if hasattr(self, 'multi_selected') and self.multi_selected:
				for idx in sorted(self.multi_selected):
					if idx < len(self.bbox):
						bbox = self.bbox[idx]
						original_bbox = [
							bbox[0],  # sel
							bbox[1],  # clsname
							bbox[2],  # info (class_id)
							bbox[3] / self.zoom_ratio,  # x1 (원본)
							bbox[4] / self.zoom_ratio,  # y1 (원본)
							bbox[5] / self.zoom_ratio,  # x2 (원본)
							bbox[6] / self.zoom_ratio   # y2 (원본)
						]
						self.prev_page_labels.append(copy.deepcopy(original_bbox))
				print(f"[AutoCopy] 다중 선택된 라벨 저장됨: {len(self.prev_page_labels)}개")
			# 단일 선택된 라벨이 있으면 선택된 라벨만 복사
			elif self.selid >= 0 and self.selid < len(self.bbox):
				bbox = self.bbox[self.selid]
				original_bbox = [
					bbox[0],  # sel
					bbox[1],  # clsname
					bbox[2],  # info (class_id)
					bbox[3] / self.zoom_ratio,  # x1 (원본)
					bbox[4] / self.zoom_ratio,  # y1 (원본)
					bbox[5] / self.zoom_ratio,  # x2 (원본)
					bbox[6] / self.zoom_ratio   # y2 (원본)
				]
				self.prev_page_labels.append(copy.deepcopy(original_bbox))
				print(f"[AutoCopy] 선택된 라벨 저장됨: {bbox[1]}")
			else:
				# 선택된 라벨이 없으면 복사 안함
				print(f"[AutoCopy] 선택된 라벨 없음 - 복사 안함")

		# 마스킹 자동 복사가 활성화되어 있으면 현재 마스킹 저장
		if self.auto_copy_masking_enabled and hasattr(self, 'masking') and self.has_saved_masking:
			self.prev_page_masking = copy.deepcopy(self.masking)
			# 마스킹 크기 정보 저장
			if hasattr(self, 'maskingframewidth'):
				self.prev_page_masking_width = self.maskingframewidth
			if hasattr(self, 'maskingframeheight'):
				self.prev_page_masking_height = self.maskingframeheight
			# 폴리곤 포인트도 저장
			if hasattr(self, 'saved_polygon_points') and self.saved_polygon_points:
				self.prev_page_polygon_points = copy.deepcopy(self.saved_polygon_points)
			print(f"[AutoCopy] 마스킹 저장됨")

	def apply_auto_copy_to_page(self):
		"""페이지 이동 후 자동 복사 적용"""
		applied = False
		label_copied = False
		masking_copied = False
		allow_auto_copy = getattr(self, 'page_move_delta', 0) == 1
		if (self.auto_copy_labels_enabled or self.auto_copy_masking_enabled) and not allow_auto_copy:
			print(f"[AutoCopy] skipped: page_move_delta={getattr(self, 'page_move_delta', 0)}")
			return

		# 마스킹 자동 복사를 먼저 적용 (라벨 삭제 로직 실행)
		if self.auto_copy_masking_enabled and self.prev_page_masking is not None:
			# 마스킹 정보 복사
			self.masking = copy.deepcopy(self.prev_page_masking)
			self.has_saved_masking = True

			# 마스킹 크기 정보 복사
			if hasattr(self, 'prev_page_masking_width'):
				self.maskingframewidth = self.prev_page_masking_width
			if hasattr(self, 'prev_page_masking_height'):
				self.maskingframeheight = self.prev_page_masking_height

			# 폴리곤 포인트도 복사
			if self.prev_page_polygon_points:
				self.saved_polygon_points = copy.deepcopy(self.prev_page_polygon_points)

			print(f"[AutoCopy] 마스킹 자동 복사 적용")
			masking_copied = True

		# 라벨 자동 복사 적용 (마스킹 이후)
		if self.auto_copy_labels_enabled and self.prev_page_labels:
			copied_count = 0
			skipped_count = 0
			# 원본 좌표를 현재 줌 비율로 변환하여 적용
			for original_bbox in self.prev_page_labels:
				screen_bbox = [
					False,  # sel = False
					original_bbox[1],  # clsname
					original_bbox[2],  # info (class_id)
					original_bbox[3] * self.zoom_ratio,  # x1 (화면)
					original_bbox[4] * self.zoom_ratio,  # y1 (화면)
					original_bbox[5] * self.zoom_ratio,  # x2 (화면)
					original_bbox[6] * self.zoom_ratio   # y2 (화면)
				]
				if self.has_same_bbox(screen_bbox):
					skipped_count += 1
					continue
				self.bbox.append(copy.deepcopy(screen_bbox))
				copied_count += 1

			print(f"[AutoCopy] label auto-copy applied: copied={copied_count}, skipped_duplicates={skipped_count}")
			label_copied = copied_count > 0

		# 마스킹이 복사된 경우 load_masking()으로 화면 표시 및 파일 저장
		# 이때 내부에서 겹치는 라벨도 삭제됨
		if masking_copied:
			try:
				self.load_masking()  # 내부에서 write_bbox() 호출됨
				applied = True
			except Exception as e:
				print(f"[AutoCopy] 마스킹 적용 중 오류: {e}")
				# 마스킹 적용 실패 시 라벨만이라도 저장
				if label_copied:
					self.write_bbox()
		elif label_copied:
			# 라벨만 복사된 경우 저장 및 화면 갱신
			self.write_bbox()
			self.draw_bbox()
			applied = True

	def draw_bbox(self):
		self.canvas.delete("bbox")
		self.canvas.delete("anchor")
		self.canvas.delete("clsname")

		# 디버깅: draw_bbox 호출 시 필터 상태 출력
		print(f"\n[FILTER DEBUG] draw_bbox() called - Total bboxes: {len(self.bbox)}")
		print(f"[FILTER DEBUG] Filter active: {self.class_filter_manager.is_filter_active()}")
		if self.class_filter_manager.is_filter_active():
			print(f"[FILTER DEBUG] Visible classes in filter: {sorted(self.class_filter_manager.get_visible_classes())}")
		print(f"[ANCHOR DEBUG] onlybox={self.onlybox}, selid={self.selid}")

		if self.bbox_resize_anchor != None or self.bbox_move:
			# selid 범위 체크
			if 0 <= self.selid < len(self.bbox):
				# 클래스 필터 체크 - 필터에 의해 숨겨진 클래스는 표시 안함
				selected_class_id = int(self.bbox[self.selid][2])
				if self.class_filter_manager.is_class_visible(selected_class_id):
					self.draw_bbox_rc(self.bbox[self.selid])
					rc = self.bbox[self.selid]
					s = str(rc[5]-rc[3]) + 'x' + str(rc[6]-rc[4])
					self.canvas.create_text(rc[5]-3,rc[6]+14, font='Arial 7', fill='black', text=s, anchor='se', tags='bbox')
		elif self.onlyselect is True:
			# selid 범위 체크
			if 0 <= self.selid < len(self.bbox):
				# 클래스 필터 체크 - 필터에 의해 숨겨진 클래스는 표시 안함
				selected_class_id = int(self.bbox[self.selid][2])
				if self.class_filter_manager.is_class_visible(selected_class_id):
					self.draw_bbox_rc(self.bbox[self.selid])
					rc = self.bbox[self.selid]
					s = str(rc[5]-rc[3]) + 'x' + str(rc[6]-rc[4])
					self.canvas.create_text(rc[5]-3,rc[6]+14, font='Arial 7', fill='black', text=s, anchor='se', tags='bbox')
		else:
			labellst = []
			drawn_count = 0
			for i, rc in enumerate(self.bbox):
				# 클래스 필터 적용 - 필터에 해당하는 클래스만 표시
				class_id = int(rc[2])
				print(f"[FILTER DEBUG] draw_bbox: bbox[{i}] class_id={class_id}, class_name={rc[1]}")
				if not self.class_filter_manager.is_class_visible(class_id):
					continue

				self.draw_bbox_rc(rc, i) if rc[0] == False else None
				labellst.append(rc[1])
				drawn_count += 1
			print(f"[FILTER DEBUG] draw_bbox: Drew {drawn_count} out of {len(self.bbox)} bboxes")
			cnt = 0  # 표시할 라벨이 없어도 아래 작업 요약 위치 계산에 사용
			if len(labellst) > 0:
				counted_items = Counter(labellst)
				for item, count in counted_items.items():
					text = f'{item} = {count}'
					# 텍스트 길이에 따라 배경 사각형 너비 계산 (약 7픽셀/글자)
					text_width = len(text) * 7
					
					# 배경용 사각형 그리기 (약간 더 넓게 만들기 위해 패딩 추가)
					self.canvas.create_rectangle(
						8, 18 + (15*cnt),  # 좌상단 (x, y)
						8 + text_width, 18 + (15*cnt) + 14,  # 우하단 (x+width, y+height)
						fill='black',  # 배경색 (검정)
						outline='',  # 테두리 없음
						tags='clsname'  # 태그 (clsname과 동일하게)
					)
					
					# 텍스트 그리기 (기존과 동일)
					self.canvas.create_text(
						10, 20 +(15*cnt), 
						font='Arial 10 bold', 
						fill='white', 
						text=text, 
						anchor='nw', 
						tags='clsname'
					)
					cnt +=1

			# 작업 요약 표시 (삭제/변환된 라벨 수)
			if len(self.pending_deleted_labels) > 0 or len(self.pending_masked_labels) > 0:
				y_offset = 20 + (15 * cnt)  # 클래스 카운트 아래에 표시

				# 작업 요약 텍스트
				summary_parts = []
				if len(self.pending_deleted_labels) > 0:
					summary_parts.append(f"🔴 삭제: {len(self.pending_deleted_labels)}개")
				if len(self.pending_masked_labels) > 0:
					summary_parts.append(f"🟡 마스킹: {len(self.pending_masked_labels)}개")

				summary_text = " | ".join(summary_parts)
				text_width = len(summary_text) * 7

				# 배경 사각형
				self.canvas.create_rectangle(
					8, y_offset,
					8 + text_width, y_offset + 14,
					fill='darkblue',
					outline='',
					tags='clsname'
				)

				# 텍스트
				self.canvas.create_text(
					10, y_offset + 2,
					font='Arial 10 bold',
					fill='white',
					text=summary_text,
					anchor='nw',
					tags='clsname'
				)

			# 선택된 bbox 그리기 (필터 체크 적용)
			if self.selid >= 0 and self.selid < len(self.bbox):
				selected_bbox = self.bbox[self.selid]
				selected_class_id = int(selected_bbox[2])
				# 클래스 필터 체크 - 필터에 의해 숨겨진 클래스면 그리지 않음
				if self.class_filter_manager.is_class_visible(selected_class_id):
					self.draw_bbox_rc(self.bbox[self.selid])
			if hasattr(self, 'show_label_list') and self.show_label_list.get():
				self.update_label_list()
				self.update_crop_preview()

		# 제외 영역 표시
		self.draw_exclusion_zones()

		# 클래스 변경 영역 표시
		self.draw_class_change_zones()

		# 삭제/변환된 라벨에 동그라미 표시
		self.draw_pending_operation_markers()
		return

	def draw_bbox_rc(self, rc, index=None):
		# 색상과 스타일 결정
		if rc[0]:  # 현재 선택된 라벨
			color = 'red'
			width = 2
			dash = None
		elif index is not None and index in self.multi_selected:  # ✅ index 매개변수 추가
			color = 'yellow'
			width = 2
			dash = (5, 5)
		else:  # 일반 라벨 - 클래스별 색상 사용
			# 클래스 이름으로 색상 찾기
			try:
				global class_name, class_color
				class_idx = class_name.index(rc[1]) if rc[1] in class_name else -1
				if class_idx >= 0 and class_idx < len(class_color[1]):
					color = class_color[1][class_idx]
				else:
					color = 'white'  # 기본 색상
			except (NameError, ValueError, IndexError):
				# 전역 변수나 클래스 정보가 없을 경우 기본 색상
				color = 'white'
			width = 1
			dash = None
		
		# 바운딩 박스 그리기
		if dash:
			self.canvas.create_rectangle(rc[3:], outline=color, width=width, dash=dash, tags="bbox")
		else:
			self.canvas.create_rectangle(rc[3:], outline=color, width=width, tags="bbox")
		
		# 크기 정보 표시 체크박스가 켜져 있을 때만 크기 정보 표시
		if self.show_size_info.get():
			# 바운딩 박스 크기 정보 계산
			width_px = rc[5] - rc[3]  # 픽셀 단위 가로 길이
			height_px = rc[6] - rc[4]  # 픽셀 단위 세로 길이
			
			# 정규화된 값 계산
			width_norm = width_px / self.imsize[0]
			height_norm = height_px / self.imsize[1]
			
			# 크기 정보 텍스트 생성
			size_info = f"{int(width_px)}x{int(height_px)} px | {width_norm:.3f}x{height_norm:.3f}"
			
			# 텍스트 배경 생성
			text_width = len(size_info) * 5  # 텍스트 길이에 따른 대략적인 너비
			self.canvas.create_rectangle(
				rc[5]-3-text_width, rc[6]+4, 
				rc[5]-3, rc[6]+18, 
				fill='black', outline='', tags='bbox'
			)
			
			# 크기 정보 표시
			self.canvas.create_text(rc[5]-3, rc[6]+14, font='Arial 7', fill='white', text=size_info, anchor='se', tags='bbox')
	
		if self.bbox_resize_anchor == None and self.bbox_move == False and self.viewclass == True:
			self.canvas.create_rectangle([rc[3]-3,rc[4]-10,rc[3]+(len(rc[1])*6)+2,rc[4]], fill=color, outline='', tags='clsname')
			c = 'black' if color not in anchor_color else anchor_color[color]
			self.canvas.create_text(rc[3],rc[4]-10, font='Arial 6 bold', fill=c, text=rc[1].upper(), anchor='nw', tags='clsname')

		# 선택된 라벨에는 항상 앵커 표시 (onlybox와 무관)
		if rc[0]:
			print(f"[ANCHOR DEBUG] Drawing anchors for selected bbox - rc[0]={rc[0]}, selid={self.selid}")
			self.draw_bbox_anchor(rc, color)

	def draw_bbox_anchor(self, rc, color):
		print(f"[ANCHOR DEBUG] draw_bbox_anchor called - rc[0]={rc[0]}, onlybox={self.onlybox}, color={color}")
		margin = [-3,-3,3,3]
		x1,y1,x2,y2 = rc[3:]
		print(f"[ANCHOR DEBUG] bbox coords: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
		anchor_rc = [
			[x1,y1], [(x1+x2)/2,y1], [x2,y1], [x2,(y1+y2)/2],
			[x2,y2], [(x1+x2)/2,y2], [x1,y2], [x1,(y1+y2)/2]
		]
		anchor_rc = [ e*2 for e in anchor_rc ]
		anchor_rc = zip(anchor_name, anchor_rc)
		# [ ['nw', [x1, y1, x2, y2], .. ]
		anchor_count = 0
		for r in anchor_rc:
			c = 'black' if color not in anchor_color else anchor_color[color]
			self.canvas.create_rectangle([a + b for a, b in zip(r[1], margin)], outline=c, fill=color, width=1, tags=("anchor", r[0]))
			anchor_count += 1
		print(f"[ANCHOR DEBUG] Drew {anchor_count} anchors")
		return

	def draw_exclusion_zones(self):
		"""제외 영역 표시"""
		self.canvas.delete("exclusion_zone")

		if not self.exclusion_zone_manager:
			return

		# 전역 제외 영역 표시
		for i, zone in enumerate(self.exclusion_zone_manager.global_zones):
			zone_points = zone.get('points', [])
			if zone_points:
				# 폴리곤 색상 (활성화 여부에 따라)
				color = 'orange' if zone['enabled'] else 'gray'
				zone_type = zone.get('zone_type', 'point' if len(zone_points) == 1 else 'polygon')
				if zone_type == 'point':
					screen_x = zone_points[0][0] * self.zoom_ratio
					screen_y = zone_points[0][1] * self.zoom_ratio
					self.canvas.create_oval(screen_x-6, screen_y-6, screen_x+6, screen_y+6, fill=color, outline='white', width=2, tags="exclusion_zone")
					self.canvas.create_text(screen_x+10, screen_y-10, text=f"제외점 {i+1}", fill=color, font='Arial 10 bold', anchor='sw', tags="exclusion_zone")
					continue

				# 폴리곤 그리기 - 원본 좌표를 화면 좌표로 변환 (줌 비율 적용)
				points = []
				for point in zone_points:
					screen_x = point[0] * self.zoom_ratio
					screen_y = point[1] * self.zoom_ratio
					points.extend([screen_x, screen_y])
				self.canvas.create_polygon(points, outline=color, fill='', width=2, dash=(5, 5), tags="exclusion_zone")

				# 영역 번호 표시
				if zone_points:
					center_x = sum(p[0] * self.zoom_ratio for p in zone_points) / len(zone_points)
					center_y = sum(p[1] * self.zoom_ratio for p in zone_points) / len(zone_points)
					self.canvas.create_text(center_x, center_y, text=f"제외영역 {i+1}", fill=color, font='Arial 10 bold', tags="exclusion_zone")

		# 현재 그리고 있는 제외 영역 표시 (이미 화면 좌표로 저장되어 있음)
		if self.exclusion_zone_mode and self.exclusion_zone_points:
			# 선택한 점들 연결
			for i in range(len(self.exclusion_zone_points)):
				if i > 0:
					x1, y1 = self.exclusion_zone_points[i-1]
					x2, y2 = self.exclusion_zone_points[i]
					self.canvas.create_line(x1, y1, x2, y2, fill='cyan', width=2, tags="exclusion_zone")

			# 점 표시
			for point in self.exclusion_zone_points:
				x, y = point
				self.canvas.create_oval(x-4, y-4, x+4, y+4, fill='cyan', outline='white', width=2, tags="exclusion_zone")

	def draw_class_change_zones(self):
		"""클래스 변경 영역 표시"""
		self.canvas.delete("class_change_zone")

		if not self.class_change_zone_manager:
			return

		# 등록된 클래스 변경 영역 표시
		for i, zone in enumerate(self.class_change_zone_manager.zones):
			zone_points = zone.get('points', [])
			if zone_points:
				# 폴리곤 색상 (활성화 여부에 따라)
				color = 'lime' if zone['enabled'] else 'gray'
				target_class = self.class_config_manager.get_class_name(zone['target_class_id'])
				if zone['mode'] == 'all':
					mode_text = f"모두→{target_class}"
				else:
					source_class = self.class_config_manager.get_class_name(zone['source_class_id'])
					mode_text = f"{source_class}→{target_class}"

				zone_type = zone.get('zone_type', 'point' if len(zone_points) == 1 else 'polygon')
				if zone_type == 'point':
					screen_x = zone_points[0][0] * self.zoom_ratio
					screen_y = zone_points[0][1] * self.zoom_ratio
					self.canvas.create_oval(screen_x-6, screen_y-6, screen_x+6, screen_y+6, fill=color, outline='white', width=2, tags="class_change_zone")
					self.canvas.create_text(screen_x+10, screen_y-10, text=f"변경점 {i+1}\n{mode_text}", fill=color, font='Arial 10 bold', anchor='sw', tags="class_change_zone")
					continue

				# 폴리곤 그리기 - 원본 좌표를 화면 좌표로 변환 (줌 비율 적용)
				points = []
				for point in zone_points:
					screen_x = point[0] * self.zoom_ratio
					screen_y = point[1] * self.zoom_ratio
					points.extend([screen_x, screen_y])
				self.canvas.create_polygon(points, outline=color, fill='', width=2, dash=(5, 5), tags="class_change_zone")

				# 영역 번호 및 모드 정보 표시
				if zone_points:
					center_x = sum(p[0] * self.zoom_ratio for p in zone_points) / len(zone_points)
					center_y = sum(p[1] * self.zoom_ratio for p in zone_points) / len(zone_points)
					self.canvas.create_text(center_x, center_y, text=f"클래스변경 {i+1}\n{mode_text}",
											fill=color, font='Arial 10 bold', tags="class_change_zone")

		# 현재 그리고 있는 클래스 변경 영역 표시 (이미 화면 좌표로 저장되어 있음)
		if self.class_change_zone_mode and self.class_change_zone_points:
			# 선택한 점들 연결
			for i in range(len(self.class_change_zone_points)):
				if i > 0:
					x1, y1 = self.class_change_zone_points[i-1]
					x2, y2 = self.class_change_zone_points[i]
					self.canvas.create_line(x1, y1, x2, y2, fill='magenta', width=2, tags="class_change_zone")

			# 점 표시
			for point in self.class_change_zone_points:
				x, y = point
				self.canvas.create_oval(x-4, y-4, x+4, y+4, fill='magenta', outline='white', width=2, tags="class_change_zone")

	def draw_pending_operation_markers(self):
		"""삭제/변환된 라벨에 동그라미 표시"""
		self.canvas.delete("pending_marker")

		# 삭제된 라벨에 빨간색 동그라미 표시
		for label_info in self.pending_deleted_labels:
			x1, y1, x2, y2 = label_info['x1'], label_info['y1'], label_info['x2'], label_info['y2']
			center_x = (x1 + x2) / 2
			center_y = (y1 + y2) / 2
			radius = 10

			# 빨간색 동그라미
			self.canvas.create_oval(
				center_x - radius, center_y - radius,
				center_x + radius, center_y + radius,
				outline='red', fill='red', width=3,
				tags="pending_marker"
			)

		# 마스킹으로 변환된 라벨에 노란색 동그라미 표시
		for label_info in self.pending_masked_labels:
			x1, y1, x2, y2 = label_info['x1'], label_info['y1'], label_info['x2'], label_info['y2']
			center_x = (x1 + x2) / 2
			center_y = (y1 + y2) / 2
			radius = 10

			# 노란색 동그라미
			self.canvas.create_oval(
				center_x - radius, center_y - radius,
				center_x + radius, center_y + radius,
				outline='yellow', fill='yellow', width=3,
				tags="pending_marker"
			)

	def on_viewclass(self, event):
		if self.viewclass is True : self.viewclass = False
		else : self.viewclass = True
		# UI 체크박스 동기화
		self.show_class_name_var.set(self.viewclass)
		pyautogui.press('ctrl')

	def on_copylabeling(self, event):
		"""레이블 복사 단축키 처리 - UI 기반 복사 함수 호출"""
		self.copy_label_to_range()
		return

	def on_onlyselect(self, event):
		if self.onlyselect is True : self.onlyselect = False
		else : self.onlyselect = True
		pyautogui.press('ctrl')

	def on_onlybox(self, event):
		if self.onlybox is True : self.onlybox = False
		else : self.onlybox = True
		# UI 체크박스 동기화
		self.show_only_box_var.set(self.onlybox)
		pyautogui.press('ctrl')

	def on_reload_backup(self, event):
		image_backup_path = self.get_backup_path(self.im_fn, 'JPEGImages')
		legacy_image_backup_path = os.path.join('original_backup', 'JPEGImages', self.make_path(self.im_fn))
		if not os.path.exists(image_backup_path) and os.path.exists(legacy_image_backup_path):
			image_backup_path = legacy_image_backup_path
		if os.path.exists(image_backup_path):
			self.img = Image.open(image_backup_path)
			self.img.save(self.im_fn)

			label_backup_path = self.get_backup_path(self.gt_fn, 'labels')
			legacy_label_backup_path = legacy_image_backup_path.replace('JPEGImages', 'labels')
			legacy_label_backup_path = legacy_label_backup_path.replace('.jpg', '.txt')
			legacy_label_backup_path = legacy_label_backup_path.replace('.png', '.txt')
			if not os.path.exists(label_backup_path) and os.path.exists(legacy_label_backup_path):
				label_backup_path = legacy_label_backup_path
			if os.path.exists(label_backup_path):
				shutil.copyfile(label_backup_path, self.gt_fn)
		self.canvas.delete("img")
		im = Image.open(self.im_fn)
		self.imsize = im.size
		self.imsize = [(int)(i * self.zoom_ratio) for i in im.size]
		im = im.resize(self.imsize, Image.LANCZOS)		
		self.canvas.config(width=self.imsize[0], height=self.imsize[1])
		self.canvas.image = ImageTk.PhotoImage(im)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
		self.master.title('[%d/%d] %s' % (self.ci+1, len(self.imlist), self.im_fn))		
		self.load_bbox()		
		self.draw_bbox()

	def on_mouse_wheel(self, event):
		if not self.imlist: return
		# Ctrl 키와 함께 사용 시 확대/축소
		if event.state & 0x4:  # Ctrl 키가 눌린 경우 (0x4 = Control modifier)
			# 마우스 휠 위: 확대, 아래: 축소
			if event.num == 4 or event.delta == 120:  # wheel up
				self.zoom(True)
			elif event.num == 5 or event.delta == -120:  # wheel down
				self.zoom(False)
			return

		# 일반 마우스 휠: 페이지 이동 (기존 동작)
		if   event.num == 5 or event.delta == -120: self.ci += 1 # wheel down
		elif event.num == 4 or event.delta ==  120: self.ci -= 1 # wheel up
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		return

	def on_key_page_up(self, event):
		self.bbox_add = False
		self.bbox_crop = False
		self.ci -= 1
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		return

	def on_key_page_down(self, event):
		self.bbox_add = False
		self.bbox_crop = False
		self.ci += 1
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		return

	def on_key_up(self, event):
		# selid 범위 체크
		if self.selid < 0 or self.selid >= len(self.bbox):
			print("Not Exist Bbox")
			return
		try:
			rc = self.convert_abs2rel(self.bbox[self.selid])
			if self.pre_rc==None:
				rc = self.convert_rel2abs(rc)
			else:
				rc = self.pre_rc
			rc[4]=rc[4]-3
			rc[6]=rc[6]-3
			if rc[4]<0:
				rc[4]=0
				rc[6]=rc[6]+3
			self.bbox[self.selid][1:] = rc[1:]
			if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
			if   self.ci < 0                 : self.ci = 0
			if   self.ci == self.pi          : self.draw_bbox()
			else                             : self.write_bbox(); self.draw_image()
			self.pre_rc = rc
		except Exception as e:
			print(f"Error in on_key_up: {e}")
		return

	def on_key_down(self, event):
		# selid 범위 체크
		if self.selid < 0 or self.selid >= len(self.bbox):
			print("Not Exist Bbox")
			return
		try:
			rc = self.convert_abs2rel(self.bbox[self.selid])
			if self.pre_rc==None:
				rc = self.convert_rel2abs(rc)
			else:
				rc = self.pre_rc
			rc[4]=rc[4]+3
			rc[6]=rc[6]+3
			if rc[6]>self.imsize[1]:
				rc[6]=self.imsize[1]-1
				rc[4]=rc[4]-3
			self.bbox[self.selid][1:] = rc[1:]
			if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
			if   self.ci < 0                 : self.ci = 0
			if   self.ci == self.pi          : self.draw_bbox()
			else                             : self.write_bbox(); self.draw_image()
			self.pre_rc = rc
		except Exception as e:
			print(f"Error in on_key_down: {e}")
		return

	def on_key_left(self, event):
		# selid 범위 체크
		if self.selid < 0 or self.selid >= len(self.bbox):
			print("Not Exist Bbox")
			return
		try:
			rc = self.convert_abs2rel(self.bbox[self.selid])
			if self.pre_rc==None:
				rc = self.convert_rel2abs(rc)
			else:
				rc = self.pre_rc
			rc[3]=rc[3]-3
			rc[5]=rc[5]-3
			if rc[3]<0:
				rc[3]=0
				rc[5]=rc[5]+3
			self.bbox[self.selid][1:] = rc[1:]
			if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
			if   self.ci < 0                 : self.ci = 0
			if   self.ci == self.pi          : self.draw_bbox()
			else                             : self.write_bbox(); self.draw_image()
			self.pre_rc = rc
		except Exception as e:
			print(f"Error in on_key_left: {e}")
		return

	def on_key_right(self, event):
		# selid 범위 체크
		if self.selid < 0 or self.selid >= len(self.bbox):
			print("Not Exist Bbox")
			return
		try:
			rc = self.convert_abs2rel(self.bbox[self.selid])
			if self.pre_rc==None:
				rc = self.convert_rel2abs(rc)
			else:
				rc = self.pre_rc
			rc[3]=rc[3]+3
			rc[5]=rc[5]+3
			if rc[5]>self.imsize[0]:
				rc[5]=self.imsize[0]-1
				rc[3]=rc[3]-3
			self.bbox[self.selid][1:] = rc[1:]
			if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
			if   self.ci < 0                 : self.ci = 0
			if   self.ci == self.pi          : self.draw_bbox()
			else                             : self.write_bbox(); self.draw_image()
			self.pre_rc = rc
		except Exception as e:
			print(f"Error in on_key_right: {e}")
		return

	def on_key_shift_up(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[4]=rc[4]-3
		if rc[4]<0:
			rc[4]=0
		self.bbox[self.selid][1:] = rc[1:]

		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_shift_down(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[6]=rc[6]+3
		
		if rc[6]>self.imsize[1]:
			rc[6]=self.imsize[1]-1
		self.bbox[self.selid][1:] = rc[1:]
		
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_shift_left(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[3]=rc[3]-3
		if rc[3]<0:
			rc[3]=0
		self.bbox[self.selid][1:] = rc[1:]
		
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_shift_right(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[5]=rc[5]+3
		if rc[5]>self.imsize[0]:
			rc[5]=self.imsize[0]-1
		self.bbox[self.selid][1:] = rc[1:]
		
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_control_up(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[6]=rc[6]-3
		if rc[6]<rc[4]:
			rc[6]=rc[4]
		self.bbox[self.selid][1:] = rc[1:]

		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_control_down(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[4]=rc[4]+3
		if rc[4]>rc[6]:
			rc[4]=rc[6]
		self.bbox[self.selid][1:] = rc[1:]
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_control_left(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[5]=rc[5]-3
		if rc[5]<rc[3]:
			rc[5]=rc[3]
		self.bbox[self.selid][1:] = rc[1:]
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return

	def on_key_control_right(self, event):
		rc = self.convert_abs2rel(self.bbox[self.selid])
		if self.pre_rc==None:
			rc = self.convert_rel2abs(rc)
		else:
			rc = self.pre_rc
		rc[3]=rc[3]+3
		if rc[3]>rc[5]:
			rc[3]=rc[5]
		self.bbox[self.selid][1:] = rc[1:]
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		else                             : self.write_bbox(); self.draw_image()
		self.pre_rc = rc
		return
	def bind_event_handlers(self):
		# 마우스 이벤트는 캔버스에만 바인딩
		self.canvas.bind("<Button-1>", self.on_mouse_down)
		self.canvas.bind("<Button-3>", self.on_mouse_right_click)  # 우클릭 추가
		self.canvas.bind("<B1-Motion>", self.on_click_mouse_move)
		self.canvas.bind("<Motion>", self.on_mouse_move)
		self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
		self.canvas.bind("<Control-1>", self.on_mouse_ctrl_down)
		
		# 마우스 휠 이벤트도 캔버스에만 바인딩
		self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows
		self.canvas.bind('<Button-4>', self.on_mouse_wheel)    # Linux 위로
		self.canvas.bind('<Button-5>', self.on_mouse_wheel)    # Linux 아래로
		
		# 키보드 이벤트를 캔버스에 바인딩 (단축키가 작동하도록)
		self.canvas.bind("<Key>", self.on_key)
		
		# 방향키
		self.canvas.bind('<Up>', self.on_key_up)
		self.canvas.bind('<Down>', self.on_key_down)
		self.canvas.bind('<Left>', self.on_key_left)
		self.canvas.bind('<Right>', self.on_key_right)
		
		# 설정된 키 바인딩 - 빈 값 체크 추가
		if keysetting[18]:
			self.canvas.bind(keysetting[18], self.on_key_tab)
		if keysetting[19]:
			self.canvas.bind(keysetting[19], self.on_key_shift_tab)
		if keysetting[20]:
			self.canvas.bind(keysetting[20], self.on_key_shift_up)
		if keysetting[21]:
			self.canvas.bind(keysetting[21], self.on_key_shift_down)
		if keysetting[22]:
			self.canvas.bind(keysetting[22], self.on_key_shift_right)
		if keysetting[23]:
			self.canvas.bind(keysetting[23], self.on_key_shift_left)
		if keysetting[24]:
			self.canvas.bind(keysetting[24], self.on_key_control_up)
		if keysetting[25]:
			self.canvas.bind(keysetting[25], self.on_key_control_down)
		if keysetting[26]:
			self.canvas.bind(keysetting[26], self.on_key_control_right)
		if keysetting[27]:
			self.canvas.bind(keysetting[27], self.on_key_control_left)
		if keysetting[33]:
			self.canvas.bind(keysetting[33], self.on_reload_backup)
		if keysetting[34]:
			self.canvas.bind(keysetting[34], self.on_viewclass)
		if keysetting[35]:
			self.canvas.bind(keysetting[35], self.on_onlyselect)
		if keysetting[36]:
			self.canvas.bind(keysetting[36], self.on_copylabeling)
		if keysetting[37]:
			self.canvas.bind(keysetting[37], self.on_onlybox)
		# if keysetting[38]:  # ResetLabeling 기능 제거됨
		# 	self.canvas.bind(keysetting[38], self.on_resetlabeling)
		self.canvas.bind('p', self.on_polygon_masking_key)  # 폴리곤 마스킹 활성화/비활성화
		self.canvas.bind('h', self.on_close_polygon_key)    # 폴리곤 닫기
		
		if self.CLASSIFY_TPFP:
			self.canvas.bind("<F1>", self.on_F1)
			self.canvas.bind("<F2>", self.on_F2)
			self.canvas.bind("<F3>", self.on_F3)

		self.canvas.bind('j', self.copy_selected_label)
		self.canvas.bind('k', self.paste_label)
		self.canvas.bind('o', self.toggle_multi_select_mode)  # 다중선택 모드 토글
		self.canvas.bind('<Control-j>', self.copy_multi_selected)  # 다중선택 복사
		self.canvas.bind('<Control-k>', self.paste_multi_selected)  # 다중선택 붙여넣기
		self.canvas.bind('<Control-a>', self.select_all_labels)  # 모든 라벨 선택
		self.canvas.bind('<Escape>', self.clear_multi_selection)  # 다중선택 해제
		# 캔버스에 포커스 설정
		self.canvas.focus_set()
		
		# 버튼 클릭 후에도 캔버스가 다시 포커스를 얻도록 설정
		# 고정된 버튼들
		standard_buttons = [self.btnBack, self.btnNext, self.btnAdd, self.btnRemove,
						self.btnLoadFolder, self.btnLoadList, self.btnHelp]
		
		# 클래스 버튼들 (btn1~btn9)
		class_buttons = [btn for btn in self.button_class_map.keys()]
		
		# 모든 버튼에 이벤트 바인딩
		for button in standard_buttons + class_buttons:
			button.bind("<ButtonRelease-1>", lambda e: self.canvas.focus_set())
		self.bind_class_shortcuts()

		return

	def bind_class_shortcuts(self):
		for key, button in list(self.key_button_map.items()):
			normalized_key = normalize_shortcut_key(key)
			if not normalized_key:
				continue
			self.key_button_map[normalized_key] = button
			try:
				self.canvas.bind(
					normalized_key,
					lambda event, btn=button: self.handle_class_shortcut(btn)
				)
			except tk.TclError as e:
				print(f"[Shortcut] Failed to bind class shortcut {normalized_key}: {e}")

	def handle_class_shortcut(self, button):
		if button in self.button_class_map:
			self.change_class(self.button_class_map[button])
		return "break"

	def toggle_size_display(self):
		# 크기 정보 표시 여부가 변경되면 현재 바운딩 박스 다시 그리기
		self.draw_bbox()

	def toggle_class_name_display(self):
		"""클래스 이름 표시 토글"""
		self.viewclass = self.show_class_name_var.get()
		self.draw_bbox()

	def toggle_only_box_display(self):
		"""박스만 표시 토글"""
		self.onlybox = self.show_only_box_var.get()
		self.draw_bbox()

	def goodbye(self):
		list_path = getattr(self, 'loaded_list_file_path', None)
		if list_path and os.path.exists(list_path):
			try:
				valid_images = []
				for image_path in getattr(self, 'imlist', []):
					normalized_path = str(image_path).replace('/s_mnt/253/','//192.168.79.253/')
					if os.path.exists(normalized_path):
						valid_images.append(normalized_path)

				if not valid_images:
					print(f"[ListSort] 존재하는 이미지가 없어 리스트 파일을 그대로 둡니다: {list_path}")
					return
				valid_images = sort_image_paths(valid_images)
				with open(list_path, "wt", encoding='utf-8') as outfile:
					for image_path in valid_images:
						outfile.write(to_list_file_path(image_path))
			except Exception as e:
				print(f"[ListSort] Failed to save sorted list file: {e}")
		print("GTGEN_Tool Exited.\n")
		try:
			os.startfile(BASE_DIR + "RemoveDefaultdll.exe")
		except (OSError, PermissionError) as e:
			# UAC 거부 또는 권한 문제 시 무시하고 계속 진행
			print(f"RemoveDefaultdll.exe 실행 실패 (무시됨): {e}")
		return

	def change_class(self, clsid):
		if self.selid < 0:
			return

		# 클래스 인덱스가 유효한지 확인
		if 0 <= clsid < len(class_name):
			# 선택된 바운딩 박스의 클래스 이름과 ID를 업데이트
			self.bbox[self.selid][1] = class_name[clsid]
			self.bbox[self.selid][2] = clsid  # class_id도 함께 업데이트

			# pre_rc가 있는 경우 업데이트
			if self.pre_rc is not None:
				self.pre_rc[1] = class_name[clsid]
				self.pre_rc[2] = clsid  # class_id도 함께 업데이트

			# 화면에 바운딩 박스 다시 그리기 (라벨만 업데이트, 전체 갱신 X)
			self.draw_bbox()

			# 파일에 즉시 저장
			self.write_bbox()

			# pending 카운터 증가 및 상태 표시
			self.pending_operation_count += 1
			self.show_temporary_status(
				f"✓ 클래스 변경 (파일 저장, 화면 갱신 생략) - 작업: {self.pending_operation_count}개",
				duration=1000,
				bg_color='#2563EB'
			)
			print(f"[SpeedOptimization] 클래스 변경 - txt 저장 완료, draw_image() 생략")
		return
		# if self.selid < 0:
		# 	return
		# if   clsid == 0: self.bbox[self.selid][1] = "person"
		# elif clsid == 1: self.bbox[self.selid][1] = "slip"
		# elif clsid == 2: self.bbox[self.selid][1] = "head"
		# elif clsid == 3: self.bbox[self.selid][1] = "helmet"
		# elif clsid == 6: self.bbox[self.selid][1] = "sitting"
		# elif clsid == 8: self.bbox[self.selid][1] = "car"
		# elif clsid == 13: self.bbox[self.selid][1] = "truck"
		# elif clsid == 17: self.bbox[self.selid][1] = "stop sign"
		# elif clsid == 9: self.bbox[self.selid][1] = "motorbike"
		
		# for index in range (len(self.bbox)) :
		# 	if self.bbox[index][0] == True :
		# 		self.pre_rc[1] = self.bbox[index][1]
		# self.draw_bbox()
		# return

	def on_F1(self, event):
		self.change_criteria(0)
		self.write_bbox()
		self.draw_image()
		return

	def on_F2(self, event):
		self.change_criteria(1)
		self.write_bbox()
		self.draw_image()
		return

	def on_F3(self, event):
		self.change_criteria(2)
		self.write_bbox()
		self.draw_image()
		return

	def change_criteria(self, c):
		_c = self.get_current_criteria()
		if c == _c:
			if self.ci==self.pi:
				return
			self.ci += 1
			return
		a_path = os.path.abspath(self.im_fn).split('\\' if os.name == 'nt' else '/')

		if _c == 0: 
			a_path[-1] = judge_string[c][0] + '/' + a_path[-1]
		else:
			if   c == 0: a_path[-2] = ''
			else       : a_path[-2] = judge_string[c][0]

		new_im_fn = '/'.join(a_path).replace('/','/')
		new_gt_fn = image_to_label_path(new_im_fn)
		os.rename(self.im_fn, new_im_fn)
		os.rename(self.gt_fn, new_gt_fn)
		self.im_fn = new_im_fn  
		self.gt_fn = new_gt_fn
		self.imlist[self.ci] = new_im_fn
		self.ci += 1
		if self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		return

	def delete_current_file(self):
		"""현재 파일 삭제 (연속 삭제 옵션 지원)"""
		# 삭제할 장 수 가져오기
		delete_count = self.delete_count_var.get() if hasattr(self, 'delete_count_var') else 1

		# 직접 입력 모드인 경우 Entry에서 값 가져오기
		if delete_count == 0 and hasattr(self, 'delete_custom_entry'):
			try:
				custom_value = int(self.delete_custom_entry.get())
				if custom_value > 0:
					delete_count = custom_value
				else:
					messagebox.showwarning("경고", "1 이상의 숫자를 입력하세요.")
					return
			except ValueError:
				messagebox.showwarning("경고", "올바른 숫자를 입력하세요.")
				return

		# 실제 삭제 가능한 장 수 계산
		remaining = len(self.imlist) - self.ci
		actual_delete = min(delete_count, remaining)

		if actual_delete <= 0:
			messagebox.showwarning("경고", "삭제할 파일이 없습니다.")
			return

		# 확인 메시지
		if actual_delete > 1:
			msg = f"현재 페이지부터 {actual_delete}장을 삭제하시겠습니까?"
			if not messagebox.askyesno("삭제 확인", msg):
				return

		# 백업 설정 확인
		enable_backup = self.class_config_manager.enable_backup if hasattr(self.class_config_manager, 'enable_backup') else True

		# 연속 삭제
		deleted_count = 0
		for i in range(actual_delete):
			if self.ci >= len(self.imlist):
				break

			# 현재 파일 경로
			current_im_fn = self.imlist[self.ci]
			current_gt_fn = image_to_label_path(current_im_fn)
			if enable_backup and not self.backup_original_pair(current_im_fn, current_gt_fn):
				messagebox.showerror("Backup Error", f"Backup failed. Delete stopped:\n{current_im_fn}")
				break

			# 파일 삭제
			try:
				os.remove(current_im_fn)
				if os.path.exists(current_gt_fn):
					os.remove(current_gt_fn)
				deleted_count += 1
			except Exception as e:
				print(f"[Delete] 파일 삭제 오류: {e}")
				break

			# 리스트에서 제거
			self.imlist = self.imlist[:self.ci] + self.imlist[self.ci+1:]

		# UI 업데이트
		if self.ci >= len(self.imlist):
			self.ci = len(self.imlist) - 1 if len(self.imlist) > 0 else 0

		if len(self.imlist) > 0:
			self.img_slider.config(to=len(self.imlist))
			self.img_slider.set(self.ci + 1)
			self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
			self.pi = -1
			self.draw_image()
		else:
			messagebox.showinfo("완료", "모든 파일이 삭제되었습니다.")

		print(f"[Delete] {deleted_count}장 삭제 완료 (백업: {'O' if enable_backup else 'X'})")
		return

	def zoom(self, is_zoom_in):
		self.pi = -1
		self.zoom_ratio += (0.1 if is_zoom_in else -0.1)
		if self.zoom_ratio < 0.1:  # 최소 줌 비율 설정
			self.zoom_ratio = 0.1
		print('zoom: %d' % int(self.zoom_ratio*100))
		self.draw_image()
		return

	def fit_to_window(self):
		"""이미지를 캔버스(화면) 크기에 맞춰 자동 조정"""
		self.pi = -1

		# 캔버스 크기 가져오기
		canvas_width = self.canvas.winfo_width()
		canvas_height = self.canvas.winfo_height()

		# 원본 이미지 크기 확인
		if not hasattr(self, 'original_width') or not hasattr(self, 'original_height'):
			print("원본 이미지 크기 정보 없음")
			return

		img_width = self.original_width
		img_height = self.original_height

		if img_width <= 0 or img_height <= 0:
			print(f"잘못된 이미지 크기: {img_width}x{img_height}")
			return

		if canvas_width <= 0 or canvas_height <= 0:
			print(f"잘못된 캔버스 크기: {canvas_width}x{canvas_height}")
			return

		# 비율 계산 (전체가 보이도록 작은 쪽 선택)
		ratio_w = canvas_width / img_width
		ratio_h = canvas_height / img_height

		self.zoom_ratio = min(ratio_w, ratio_h)

		# 최소/최대 제한 (너무 작거나 크지 않게)
		if self.zoom_ratio < 0.1:
			self.zoom_ratio = 0.1
		elif self.zoom_ratio > 10.0:
			self.zoom_ratio = 10.0

		print(f'Fit to Window - 이미지: {img_width}x{img_height}, 캔버스: {canvas_width}x{canvas_height}, zoom: {int(self.zoom_ratio*100)}%')
		self.draw_image()
		return

	def resize_bbox(self, ratio):
		if not self.bbox : return
		rc = self.convert_abs2rel(self.bbox[self.selid])
		rc = rc[0:3] + [ratio * i for i in rc[3:]]
		self.bbox[self.selid][3:] = self.convert_rel2abs(rc)[3:]
		return

	def get_masking(self):
		if self.bbox_masking == True or self.mouse_masking == True or self.polygon_masking == True:
			# 원본 이미지 크기 저장
			if not hasattr(self, 'original_width') or not hasattr(self, 'original_height'):
				# 원본 이미지 크기 설정이 안된 경우 현재 이미지에서 가져옴
				if hasattr(self, 'img') and self.img is not None:
					self.original_width = self.img.width
					self.original_height = self.img.height
				elif hasattr(self, 'current_img_array') and self.current_img_array is not None:
					self.original_height, self.original_width = self.current_img_array.shape[:2]

			# 마스킹 프레임 크기 설정
			self.maskingframewidth = self.original_width
			self.maskingframeheight = self.original_height
			
			# === 메모리상 마스킹 정보만 업데이트 (파일 저장 안함) ===
			if self.current_img_array is not None:
				# 현재 작업중인 배열에서 마스킹된 픽셀 좌표 찾기
				self.masking = np.where((self.current_img_array==[255,0,255]).all(axis=2))
				self.has_saved_masking = True
				self.is_masking_dirty = True  # 저장 필요 플래그 설정
				
				# 화면 업데이트 (현재 줌 배율 유지)
				display_img = Image.fromarray(self.current_img_array)
				resized_img = display_img.resize([(int)(i * self.zoom_ratio) for i in display_img.size], Image.LANCZOS)
				self.canvas.image = ImageTk.PhotoImage(resized_img)
				self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
			# === 메모리상 마스킹 처리 끝 ===
			
			# 캔버스에서 마스킹 관련 요소들 삭제
			self.canvas.delete("masking")
			self.canvas.delete("masking_m")
			self.canvas.delete("polygon")
			self.canvas.delete("polygon_point")
			self.canvas.delete("temp_line")
			
			# 마스킹 모드 플래그 초기화
			self.s_region = False
			self.bbox_masking = False
			self.mouse_masking = False
			self.polygon_masking = False
			self.is_polygon_closed = False
			self.polygon_points = []
			
			print("마스킹 정보가 메모리에 저장되었습니다. 프레임 이동 시 파일에 저장됩니다.")
			
	def load_masking(self):
		"""저장된 마스킹을 현재 이미지에 적용"""
		# 저장된 마스킹 정보가 없는 경우
		if not hasattr(self, 'masking') or self.masking is None or not self.has_saved_masking:
			messagebox.showwarning("경고", "저장된 마스킹이 없습니다. 먼저 마스킹을 생성하고 저장해주세요.")
			return
		
		im = Image.open(self.im_fn)

		current_img = Image.open(self.im_fn)
		print(f"=== 마스킹 복사 디버깅 ===")
		print(f"현재 이미지: {current_img.width}x{current_img.height}")
		print(f"저장된 마스킹: {self.maskingframewidth}x{self.maskingframeheight}")
		print(f"현재 줌 비율: {self.zoom_ratio}")

	
		# 마스킹 크기와 현재 이미지 크기 확인
		if (not hasattr(self, 'maskingframewidth') or not hasattr(self, 'maskingframeheight') or
			im.height != self.maskingframeheight or im.width != self.maskingframewidth):
			print("Size Not Match")
			messagebox.showwarning("경고", "저장된 마스킹과 현재 이미지의 크기가 일치하지 않습니다.")
			return
		if not self.backup_original_pair(self.im_fn, self.gt_fn):
			messagebox.showerror("Backup Error", f"Backup failed. Masking was not applied:\n{self.im_fn}")
			return

		try:
			# === 메모리상에서 마스킹 적용 ===
			# 현재 이미지를 배열로 변환하여 작업 배열 생성
			self.original_img_array = array(im.copy())
			self.current_img_array = array(im.copy())
			
			# 저장된 마스킹 정보 적용
			self.current_img_array[self.masking] = [255, 0, 255]
			self.is_masking_dirty = True  # 저장 필요 플래그 설정
			
			# 마스킹과 겹치는 라벨 삭제 옵션이 켜져 있는 경우
			if self.remove_overlapping_labels.get():
				print(f"[AutoCopy] 마스킹과 겹치는 라벨 삭제 시작 - 현재 라벨 수: {len(self.bbox)}")
				# 마스킹 영역 계산 (마스킹된 픽셀의 최소/최대 좌표)
				if len(self.masking[0]) > 0:  # 마스킹된 픽셀이 있는 경우
					mask_y1 = min(self.masking[0]) if len(self.masking[0]) > 0 else 0
					mask_y2 = max(self.masking[0]) if len(self.masking[0]) > 0 else 0
					mask_x1 = min(self.masking[1]) if len(self.masking[1]) > 0 else 0
					mask_x2 = max(self.masking[1]) if len(self.masking[1]) > 0 else 0

					# 원본 이미지 좌표를 캔버스 좌표로 변환
					view_x1, view_y1 = self.convert_original_to_view(mask_x1, mask_y1)
					view_x2, view_y2 = self.convert_original_to_view(mask_x2, mask_y2)

					# 마스킹 영역 (캔버스 좌표)
					mask_area = [view_x1, view_y1, view_x2, view_y2]
					print(f"[AutoCopy] 마스킹 영역: {mask_area}")

					# 겹치는 라벨 삭제
					before_count = len(self.bbox)
					self.remove_labels_overlapping_with_mask(mask_area)
					after_count = len(self.bbox)
					deleted = before_count - after_count
					print(f"[AutoCopy] 마스킹과 겹치는 라벨 삭제 완료 - 삭제된 라벨 수: {deleted}, 남은 라벨 수: {after_count}")
				else:
					print(f"[AutoCopy] 마스킹 영역이 비어있음")
			
			# === 화면 업데이트 ===
			# 마스킹이 적용된 이미지로 화면 표시
			display_img = Image.fromarray(self.current_img_array)
			
			# 현재 zoom_ratio에 맞게 이미지 리사이즈
			self.imsize = [(int)(i * self.zoom_ratio) for i in display_img.size]
			resized_img = display_img.resize(self.imsize, Image.LANCZOS)
			
			# 캔버스 업데이트 (줌 상태 유지)
			self.canvas.image = ImageTk.PhotoImage(resized_img)
			self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
			self.master.title('[%d/%d] %s' % (self.ci+1, len(self.imlist), self.im_fn))

			# === 이미지 파일에 마스킹 저장 (중요!) ===
			img_to_save = Image.fromarray(self.current_img_array)
			if self.im_fn.lower().endswith('.jpg') or self.im_fn.lower().endswith('.jpeg'):
				img_to_save.save(self.im_fn, quality=95, optimize=True)
			else:
				img_to_save.save(self.im_fn)
			print(f"마스킹이 이미지 파일에 저장되었습니다: {self.im_fn}")

			# 캔버스에서 폴리곤 및 마스킹 관련 요소들 삭제
			self.canvas.delete("polygon")
			self.canvas.delete("polygon_point")
			self.canvas.delete("temp_line")
			self.canvas.delete("masking")
			self.canvas.delete("masking_m")
			
			# 플래그 초기화
			self.l_region = False
			self.bbox_masking = False

			print("마스킹이 메모리에 로드되었습니다.")

			# 라벨(bbox) 다시 그리기
			self.draw_bbox()

		except Exception as e:
			print(f"마스킹 로드 중 오류 발생: {e}")
			messagebox.showerror("오류", f"마스킹 로드 중 오류가 발생했습니다: {e}")

	def add_bbox_rc(self):
		self.bbox_add = True; self.cross_line = True; self.bbox_masking = False; self.mouse_masking = False; self.bbox_crop = False
		if hasattr(self, 'show_label_list') and self.show_label_list.get():
			self.update_label_list()
			self.update_crop_preview()
		return

	def remove_bbox_rc(self):
		if len(self.bbox) <= 0:
			return

		self.bbox_add = False;  self.cross_line = False;  bbox_crop = False
		copyflag = False

		# 삭제 전 라벨 정보 저장 (빨간색 동그라미 표시용)
		deleted_bbox = self.bbox[self.selid]
		self.pending_deleted_labels.append({
			'bbox': deleted_bbox,
			'class_name': deleted_bbox[1],
			'x1': deleted_bbox[3],
			'y1': deleted_bbox[4],
			'x2': deleted_bbox[5],
			'y2': deleted_bbox[6]
		})

		self.bbox = self.bbox[:self.selid] + self.bbox[self.selid+1:]
		self.pi = -1
		self.selid -= 1
		self.draw_bbox()
		# if len(self.bbox) <= 0 | len(self.bbox) <= 80:
		if len(self.bbox) <= 0:
			return
		self.bbox[self.selid][0] = True
		self.draw_bbox()
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		if   self.ci < 0                 : self.ci = 0
		if   self.ci == self.pi          : self.draw_bbox()
		elif copyflag==True              : self.write_bbox();self.draw_copy_image()
		else                             :
			self.write_bbox()  # txt 파일에 즉시 저장

			# pending 카운터 증가 및 상태 표시 (캐시 업데이트 제거로 속도 개선)
			self.pending_operation_count += 1
			self.show_temporary_status(
				f"✓ 라벨 삭제 (파일 저장, 화면 갱신 생략) - 작업: {self.pending_operation_count}개",
				duration=1500,
				bg_color='#059669'
			)
			print(f"[SpeedOptimization] 라벨 삭제 - txt 저장 완료, draw_image() 생략")

			# draw_image() 제거 - 전체 화면 갱신 생략으로 속도 개선
			# 데이터는 write_bbox()로 이미 저장됨

		if hasattr(self, 'show_label_list') and self.show_label_list.get():
			self.update_label_list()
			self.update_crop_preview()
		return
	def save_masking_info_to_file(self):
		"""마스킹 정보를 별도 파일에 저장 (복사 기능을 위해)"""
		if not self.has_saved_masking or self.masking is None:
			return
		
		try:
			# 마스킹 정보 파일 경로
			mask_info_file = os.path.splitext(self.im_fn)[0] + '_mask.npz'
			
			# numpy 형식으로 마스킹 정보 저장
			np.savez_compressed(mask_info_file, 
							masking_y=self.masking[0],
							masking_x=self.masking[1],
							width=self.maskingframewidth,
							height=self.maskingframeheight)
			print(f"마스킹 정보 저장됨: {mask_info_file}")
			
		except Exception as e:
			print(f"마스킹 정보 저장 오류: {e}")

	def load_masking_info_from_file(self):
		"""파일에서 마스킹 정보 로드"""
		mask_info_file = os.path.splitext(self.im_fn)[0] + '_mask.npz'
		
		if not os.path.exists(mask_info_file):
			return False
		
		try:
			# 마스킹 정보 로드
			data = np.load(mask_info_file)
			
			# 마스킹 정보 복원
			self.masking = (data['masking_y'], data['masking_x'])
			self.maskingframewidth = int(data['width'])
			self.maskingframeheight = int(data['height'])
			self.has_saved_masking = True
			
			print(f"마스킹 정보 로드됨: {mask_info_file}")
			return True
			
		except Exception as e:
			print(f"마스킹 정보 로드 오류: {e}")
			return False
	def save_masking_if_dirty(self):
		if self.is_masking_dirty and self.current_img_array is not None:
			try:
				if not self.backup_original_pair(self.im_fn, self.gt_fn):
					messagebox.showerror("Backup Error", f"Backup failed. Masking was not saved:\n{self.im_fn}")
					return

				# 현재 작업중인 이미지를 파일에 저장
				masked_img = Image.fromarray(self.current_img_array)
				
				if self.im_fn.lower().endswith('.jpg'):
					masked_img.save(self.im_fn, quality=95, optimize=True)
				else:
					masked_img.save(self.im_fn)
				
				# print(f"마스킹이 저장됨: {self.im_fn}")
				
				# 마스킹 메모리 정리 (복사용 정보는 보존)
				self.clear_masking_memory()
				
			except Exception as e:
				print(f"마스킹 저장 오류: {e}")

	def clear_masking_memory(self):
		"""마스킹 관련 메모리 정리 (복사용 정보는 보존)"""
		# 더티 플래그만 초기화
		self.is_masking_dirty = False
		
		# 이미지 배열 메모리만 해제 (용량이 큰 부분)
		self.original_img_array = None
		self.current_img_array = None
		
		# 마스킹 정보는 복사 기능을 위해 보존
		# self.masking - 보존
		# self.has_saved_masking - 보존  
		# self.maskingframewidth - 보존
		# self.maskingframeheight - 보존
		
		# 폴리곤 관련 정보는 정리 (복사 기능에 불필요)
		if hasattr(self, 'saved_polygon_points'):
			self.saved_polygon_points = None
		if hasattr(self, 'saved_orig_polygon_points'):
			self.saved_orig_polygon_points = None
		
		# 마스킹 모드 플래그들만 초기화
		self.bbox_masking = False
		self.mouse_masking = False
		self.polygon_masking = False
		self.is_polygon_closed = False
		self.polygon_points = []
		
		print("마스킹 메모리가 정리되었습니다 (복사용 정보는 보존).")

	def back_frame(self):
		# 현재 프레임의 마스킹 저장
		self.save_masking_if_dirty()

		self.ci -= 1
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1; return
		if   self.ci < 0                 : self.ci = 0; return
		self.img_slider.set(self.ci + 1)
		self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
		self.write_bbox(); self.draw_image()

		return

	def next_frame(self):
		# 현재 프레임의 마스킹 저장
		self.save_masking_if_dirty()

		self.ci += 1
		if   self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1; return
		if   self.ci < 0                 : self.ci = 0; return
		self.img_slider.set(self.ci + 1)
		self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
		self.write_bbox(); self.draw_image()

		return
	def on_polygon_masking_key(self, event):
		"""폴리곤 마스킹 모드 토글"""
		if not self.polygon_masking:
			# 다른 마스킹 모드 비활성화
			self.bbox_masking = False
			self.mouse_masking = False
			self.bbox_crop = False
			self.bbox_add = False
			
			# 폴리곤 마스킹 활성화
			self.polygon_masking = True
			self.polygon_points = []
			self.is_polygon_closed = False
			
			# 폴리곤 마스킹에 필요한 백업 생성
			if not self.backup_current_image_and_bbox():
				messagebox.showerror("Backup Error", f"Backup failed. Polygon masking was not started:\n{self.im_fn}")
				self.polygon_masking = False
				return
				
			# 원본 이미지 로드
			self.img = Image.open(self.im_fn)
			
			# 마스킹용 원본 이미지 크기 저장
			self.original_width = self.img.width
			self.original_height = self.img.height
			
			print("폴리곤 마스킹 모드를 시작합니다. 점을 클릭하여 폴리곤을 그리세요.")
			print("폴리곤을 완성하려면 'h' 키를 누르거나 첫 번째 점을 다시 클릭하세요.")
		# else:
		# 	# 폴리곤 마스킹 비활성화
		# 	self.polygon_masking = False
		# 	self.polygon_points = []
		# 	self.is_polygon_closed = False
		# 	self.canvas.delete("polygon")
		# 	self.canvas.delete("polygon_point")
		# 	print("폴리곤 마스킹 모드를 종료합니다.")

	def on_close_polygon_key(self, event):
		"""폴리곤 닫기 (최소 3개 점 필요)"""
		if self.polygon_masking and len(self.polygon_points) >= 3:
			self.is_polygon_closed = True
			self.apply_polygon_masking()

	def toggle_polygon_points_display(self):
		"""폴리곤 점 표시 토글"""
		self.show_polygon_points = self.show_polygon_points_var.get()
		# 점 표시 상태 변경 시 다시 그리기
		if self.polygon_masking:
			self.draw_polygon()

	def setup_input_validation(self):
		"""모든 숫자 입력 필드에 유효성 검사 추가"""
		# tkinter에서 유효성 검사를 위한 등록 정의
		validate_cmd = self.master.register(self.validate_number_input)
		
		# 모든 숫자 입력 필드에 유효성 검사 적용
		# 마스킹 복사 관련 입력 필드
		self.start_frame_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))
		self.end_frame_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))
		
		# 삭제 관련 입력 필드
		self.delete_start_frame_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))
		self.delete_end_frame_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))
		
		# 라벨 복사 관련 입력 필드
		self.label_start_frame_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))
		self.label_end_frame_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))

		self.page_entry.config(validate="key", validatecommand=(validate_cmd, '%P'))

	def validate_number_input(self, P):
		"""Entry 위젯에 숫자만 입력 가능하게 하는 유효성 검사 함수"""
		# 비어있는 경우 허용 (삭제 가능하도록)
		if P == "":
			return True
		# 숫자만 허용
		if P.isdigit():
			return True
		# 그 외는 거부
		return False
	def setup_input_focus_handling(self):
		"""입력 필드에서 포커스가 벗어날 때 캔버스로 포커스 이동"""
		all_entries = [
			self.start_frame_entry, 
			self.end_frame_entry,
			self.delete_start_frame_entry, 
			self.delete_end_frame_entry,
			self.label_start_frame_entry, 
			self.label_end_frame_entry,
			self.page_entry
		]
		
		for entry in all_entries:
			# 포커스 아웃 이벤트에 캔버스로 포커스 이동 함수 바인딩
			entry.bind("<FocusOut>", lambda e: self.canvas.focus_set())
			# Tab 키 입력 시 다음 위젯으로 이동 후 캔버스로 포커스
			entry.bind("<Tab>", lambda e: (self.master.focus_set(), self.canvas.focus_set()))
			# Enter 키 입력 시 실행 함수 호출 또는 캔버스로 포커스 이동
			entry.bind("<Return>", self.handle_entry_return)
	def handle_entry_return(self, event):
		"""입력 필드에서 Enter 키 입력 시 처리"""
		widget = event.widget
		
		# 어떤 입력 필드인지 확인하고 적절한 실행 함수 호출
		if widget in [self.start_frame_entry, self.end_frame_entry]:
			# 마스킹 복사 입력 필드면 복사 실행
			self.copy_masking_btn.invoke()
		elif widget in [self.delete_start_frame_entry, self.delete_end_frame_entry]:
			# 삭제 입력 필드면 삭제 실행
			self.delete_range_btn.invoke()
		elif widget in [self.label_start_frame_entry, self.label_end_frame_entry]:
			# 라벨 복사 입력 필드면 복사 실행
			self.copy_label_btn.invoke()
		elif widget == self.page_entry:
			# 페이지 입력 필드면 이동 실행
			self.page_move_btn.invoke()
		
		# 캔버스로 포커스 이동
		self.canvas.focus_set()
		return "break"  # 이벤트 전파 중지

	# 5. 캔버스에 키 입력 이벤트 재설정 (단축키 문제 해결)
	def global_key_handler(self, event):
		"""Handle shortcuts outside the canvas without stealing dialog/input typing."""
		if event.widget == getattr(self, 'canvas', None):
			return

		focused_widget = self.master.focus_get()
		if self.should_ignore_global_shortcut(focused_widget):
			return

		if focused_widget != self.canvas:
			self.canvas.focus_set()

		shortcut_key = self.event_to_shortcut_key(event)
		if shortcut_key in self.key_button_map:
			button = self.key_button_map[shortcut_key]
			if button in self.button_class_map:
				self.change_class(self.button_class_map[button])
				return "break"
		if event.char and event.char in self.key_button_map:
			button = self.key_button_map[event.char]
			if button in self.button_class_map:
				self.change_class(self.button_class_map[button])
				return "break"

		if event.char == 'p':
			self.on_polygon_masking_key(event)
			return "break"
		if event.char == 'h':
			self.on_close_polygon_key(event)
			return "break"

		if self.polygon_masking or self.bbox_masking or self.mouse_masking:
			return
		if event.char == keysetting[29]:
			return
		if event.char:
			self.on_key(event)
			return "break"

	def should_ignore_global_shortcut(self, focused_widget):
		if focused_widget is None:
			return False
		try:
			if focused_widget.winfo_toplevel() != self.master:
				return True
		except Exception:
			return True

		widget = focused_widget
		while widget is not None:
			try:
				widget_class = widget.winfo_class()
			except Exception:
				return True
			if widget_class in ('Entry', 'Text', 'Spinbox', 'TEntry', 'TCombobox'):
				return True
			if widget == self.master:
				break
			widget = getattr(widget, 'master', None)
		return False

	def event_to_shortcut_key(self, event):
		has_control = bool(event.state & 0x0004)
		has_shift = bool(event.state & 0x0001)
		has_alt = bool(event.state & 0x0008 or event.state & 0x20000)
		if event.char and len(event.char) == 1 and not (has_control or has_shift or has_alt):
			return event.char

		modifiers = []
		if has_control:
			modifiers.append('Control')
		if has_shift:
			modifiers.append('Shift')
		if has_alt:
			modifiers.append('Alt')

		keysym = getattr(event, 'keysym', '') or ''
		if modifiers and keysym:
			return '<' + '-'.join(modifiers + [keysym]) + '>'
		return normalize_shortcut_key(keysym)
	def improve_key_bindings(self):
		"""캔버스의 키 입력 이벤트 우선순위 설정"""
		# 기존의 키 바인딩을 유지하되 캔버스 포커스 설정 강화
		self.master.bind_all("<Key>", self.global_key_handler)

	def on_key(self, event):
		if not self.imlist: return
		# print(f"on_key 함수 호출: {event.char}")
		self.bbox_add = False;  self.cross_line = False;  bbox_crop = False
		ckey = event.char
		copyflag = False
		
		# 숫자 키 처리 - 동적 매핑 사용
		if ckey in self.key_button_map:
			# 해당 키에 매핑된 버튼 가져오기
			button = self.key_button_map[ckey]
			# 버튼에 매핑된 현재 클래스 인덱스 가져오기
			class_idx = self.button_class_map[button]
			# 해당 클래스로 변경
			print(f"Pressed {ckey} - Button: {button.cget('text')} - Using class: {class_name[class_idx]} (index: {class_idx})")
			self.change_class(class_idx)
		elif ckey == keysetting[8]:
			# 범위 삭제 UI가 있으면 그것을 사용하고, 없으면 단일 파일 삭제
			if hasattr(self, 'delete_range_frame'):
				# 삭제 UI에 현재 프레임 번호 설정
				self.delete_start_frame_entry.delete(0, tk.END)
				self.delete_start_frame_entry.insert(0, str(self.ci + 1))
				self.delete_end_frame_entry.delete(0, tk.END)
				self.delete_end_frame_entry.insert(0, str(self.ci + 1))
				# 삭제 UI로 포커스 이동
				self.delete_start_frame_entry.focus_set()
			else:
				self.delete_current_file()
		elif ckey == keysetting[9]:
			self.add_bbox_rc()
		elif ckey == keysetting[10]:
			self.remove_bbox_rc()
		elif ckey == keysetting[1]:
			self.ci -= int(keysetting[0]); self.get_masking()
		elif ckey == keysetting[2]:
			self.ci += int(keysetting[0]); self.get_masking()
		elif ckey == keysetting[3]:
			self.back_frame()
		elif ckey == keysetting[4]:
			self.next_frame()
		elif ckey == keysetting[13]:
			bboxtmp = self.bbox
			if self.copy_region_manager.active_regions():
				self.copy_region_source_lines = [
					' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n'
					for rc in self.bbox
				]
			else:
				self.copy_region_source_lines = None
			self.ci += 1
			self.bbox = bboxtmp
			copyflag = True
		elif ckey == keysetting[5]:
			self.ci = 0
		elif ckey == keysetting[6]:
			self.ci = len(self.imlist)
		elif ckey == keysetting[7]:
			self.load_bbox()
		# keysetting[8] 중복 제거 - 위 5337-5348 라인에서 이미 처리됨
		elif ckey == keysetting[14]:
			self.zoom(True)
		elif ckey == keysetting[15]:
			self.zoom(False)
		elif ckey == 'f':
			self.fit_to_window()
		elif ckey == 'g':
			self.manual_delete_auto_classes()
			return
		elif ckey == keysetting[16]:
			self.cross_line = not self.cross_line
		elif ckey == keysetting[11]:
			self.resize_bbox(0.95)
		elif ckey == keysetting[12]:
			self.resize_bbox(1.05)
		elif ckey == keysetting[28]:
			self.bbox_crop = True; self.write_bbox(); self.draw_image(); self.pi = -1; print("zoom: 100"); self.zoom_ratio = 1.0; self.draw_image()
		elif ckey == keysetting[29]:
			# print(f"Masking key pressed. bbox_masking: {self.bbox_masking}, mouse_masking: {self.mouse_masking}")
			# print(f"Label to mask mode: {self.label_to_mask_mode.get()}, Selected ID: {self.selid}")
			
			if self.bbox_masking == False and self.mouse_masking == False:
				self.write_bbox()
				self.pi = -1
				
				# 라벨→마스킹 모드 체크 여부에 따라 다르게 처리
				if self.label_to_mask_mode.get() and self.selid >= 0:
					print("Converting label to mask")
					self.convert_label_to_mask()
				else:
					print("Activating bbox masking mode")
					self.bbox_masking = True
					self.img = Image.open(self.im_fn)
					# 마스킹용 원본 이미지 크기 저장
					self.original_width = self.img.width
					self.original_height = self.img.height
		elif ckey == keysetting[30]:
			if self.bbox_masking == False and self.mouse_masking == False:
				self.write_bbox()
				self.pi = -1
				# 현재 줌 상태 유지 (zoom_ratio 변경하지 않음)
				# print(f"zoom: {int(self.zoom_ratio*100)}")
				# self.draw_image() 호출하지 않고 원본 이미지만 로드
				self.mouse_masking = True
				self.img = Image.open(self.im_fn)
				# 마스킹용 원본 이미지 크기 저장
				self.original_width = self.img.width
				self.original_height = self.img.height
		elif ckey == keysetting[31]:
			self.s_region = True; self.get_masking()
			return  # get_masking() 후 즉시 리턴 (draw_image 호출 방지)
		elif ckey == keysetting[32]:
			self.l_region = True; self.load_masking()
			return  # load_masking() 후 즉시 리턴 (draw_image 호출 방지)
		elif ckey == 'p':
			self.on_polygon_masking_key(event)
			return
		# c 키 처리 (폴리곤 닫기)
		elif ckey == 'h':
			self.on_close_polygon_key(event)
			return
		# 나머지 업데이트
		if self.ci >= len(self.imlist):
			self.ci = len(self.imlist) - 1
		if self.ci < 0:
			self.ci = 0
		if self.ci == self.pi:
			self.draw_bbox()
		elif copyflag == True:
			self.write_bbox(); self.draw_copy_image()
		else:
			self.write_bbox(); self.draw_image()
		return

	def on_key_tab(self, event):
		self.bbox_add = False
		self.bbox_crop = False
		if len(self.bbox) <= 0: return
		self.bbox[self.selid][0] = False
		self.selid += 1
		self.selid = 0 if self.selid >= len(self.bbox) else self.selid
		self.bbox[self.selid][0] = True
		self.draw_bbox()
		rc = self.convert_abs2rel(self.bbox[self.selid])
		self.pre_rc = self.convert_rel2abs(rc)
		if hasattr(self, 'show_label_list') and self.show_label_list.get():
			self.update_label_list()
			self.update_crop_preview()
		return
		
	def on_key_shift_tab(self, event):
		self.bbox_add = False
		self.bbox_crop = False
		if len(self.bbox) <= 0: return
		self.bbox[self.selid][0] = False
		self.selid -= 1
		self.selid = len(self.bbox) - 1 if self.selid < 0 else self.selid
		self.bbox[self.selid][0] = True
		self.draw_bbox()
		rc = self.convert_abs2rel(self.bbox[self.selid])
		self.pre_rc = self.convert_rel2abs(rc)
		if hasattr(self, 'show_label_list') and self.show_label_list.get():
			self.update_label_list()
			self.update_crop_preview()
		return

	def pt_in_current_rc(self, x, y):
		rc = self.bbox[self.selid][3:]
		if x > rc[0] and x < rc[2] and y > rc[1] and y < rc[3]:
			return True
		return False

	def make_path(self,path):
		p = copy.deepcopy(path)[::-1]
		if '/' in p:
			index = p.index('/')
		elif '\\' in p:
			index = p.index('\\')
		else:
			# 처리할 슬래시가 없는 경우
			return None
		p = p[:index][::-1]
		return p

	def get_backup_path(self, source_path, category):
		"""Return a stable backup path under BASE_DIR/original_backup."""
		return self.file_safety_manager.get_backup_path(source_path, category)

	def is_backup_enabled(self):
		config_manager = getattr(self, 'class_config_manager', None)
		return bool(getattr(config_manager, 'enable_backup', True))

	def backup_original_file(self, source_path, category):
		if not self.is_backup_enabled():
			return True
		return self.file_safety_manager.backup_file(source_path, category)

	def backup_original_pair(self, image_path, label_path=None):
		if not self.is_backup_enabled():
			return True
		return self.file_safety_manager.backup_pair(image_path, label_path)

	def backup_current_image_and_bbox(self):
		if not self.is_backup_enabled():
			return True
		if not self.backup_original_file(self.im_fn, 'JPEGImages'):
			return False
		lines = [' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n' for rc in copy.deepcopy(self.bbox)]
		return self.file_safety_manager.write_backup_text_if_missing(self.gt_fn, 'labels', lines)

	def replace_files_transaction(self, replacements):
		"""Replace prepared temp files atomically enough for local batch operations."""
		return self.file_safety_manager.replace_files_transaction(replacements)

	def write_text_files_transaction(self, file_text_map, backup_category='labels'):
		return self.file_safety_manager.write_text_files_transaction(
			file_text_map,
			backup_category,
			enable_backup=self.is_backup_enabled()
		)

	def apply_modern_theme(self):
		colors = {
			'app_bg': '#e9edf3',
			'panel_bg': '#f8fafc',
			'surface_bg': '#ffffff',
			'toolbar_bg': '#eef2f7',
			'canvas_bg': '#d8dee7',
			'input_bg': '#ffffff',
			'text_fg': '#111827',
			'muted_fg': '#475569',
			'border': '#cbd5e1',
			'button_bg': '#334155',
			'button_active': '#1f2937',
			'primary_bg': '#2563eb',
			'primary_active': '#1d4ed8',
			'danger_bg': '#dc2626',
			'danger_active': '#b91c1c',
			'success_bg': '#059669',
			'success_active': '#047857',
			'accent_bg': '#0f766e',
			'accent_active': '#115e59',
			'selected_bg': '#dbeafe',
			'disabled_fg': '#94a3b8'
		}
		self.theme_colors = colors

		def safe_config(widget, **options):
			for option, value in options.items():
				try:
					widget.configure(**{option: value})
				except Exception:
					pass

		try:
			self.master.configure(bg=colors['app_bg'])
			self.master.option_add('*Font', ('맑은 고딕', 9))
			self.master.option_add('*Background', colors['panel_bg'])
			self.master.option_add('*Foreground', colors['text_fg'])
			self.master.option_add('*Toplevel.Background', colors['panel_bg'])
			self.master.option_add('*Frame.Background', colors['panel_bg'])
			self.master.option_add('*LabelFrame.Background', colors['panel_bg'])
			self.master.option_add('*LabelFrame.Foreground', colors['muted_fg'])
			self.master.option_add('*Label.Background', colors['panel_bg'])
			self.master.option_add('*Label.Foreground', colors['text_fg'])
			self.master.option_add('*Checkbutton.Background', colors['panel_bg'])
			self.master.option_add('*Checkbutton.Foreground', colors['text_fg'])
			self.master.option_add('*Checkbutton.activeBackground', colors['panel_bg'])
			self.master.option_add('*Checkbutton.activeForeground', colors['text_fg'])
			self.master.option_add('*Radiobutton.Background', colors['panel_bg'])
			self.master.option_add('*Radiobutton.Foreground', colors['text_fg'])
			self.master.option_add('*Radiobutton.activeBackground', colors['panel_bg'])
			self.master.option_add('*Radiobutton.activeForeground', colors['text_fg'])
			self.master.option_add('*Canvas.Background', colors['surface_bg'])
			self.master.option_add('*selectBackground', colors['selected_bg'])
			self.master.option_add('*selectForeground', colors['text_fg'])
			self.master.option_add('*Button.Background', colors['button_bg'])
			self.master.option_add('*Button.Foreground', colors['surface_bg'])
			self.master.option_add('*Button.activeBackground', colors['button_active'])
			self.master.option_add('*Button.activeForeground', colors['surface_bg'])
			self.master.option_add('*Entry.Background', colors['input_bg'])
			self.master.option_add('*Entry.Foreground', colors['text_fg'])
			self.master.option_add('*Entry.insertBackground', colors['text_fg'])
			self.master.option_add('*Listbox.Background', colors['surface_bg'])
			self.master.option_add('*Listbox.Foreground', colors['text_fg'])
			self.master.option_add('*Text.Background', colors['surface_bg'])
			self.master.option_add('*Text.Foreground', colors['text_fg'])
			self.master.option_add('*Text.insertBackground', colors['text_fg'])
			style = ttk.Style()
			try:
				style.theme_use('clam')
			except Exception:
				pass
			style.configure(
				'TProgressbar',
				troughcolor=colors['surface_bg'],
				background=colors['primary_bg'],
				bordercolor=colors['border'],
				lightcolor=colors['primary_bg'],
				darkcolor=colors['primary_bg']
			)
			style.configure(
				'TCombobox',
				fieldbackground=colors['input_bg'],
				background=colors['surface_bg'],
				foreground=colors['text_fg'],
				bordercolor=colors['border'],
				arrowcolor=colors['muted_fg']
			)
		except Exception:
			pass

		def button_colors(widget):
			class_buttons = getattr(self, 'button_class_map', {})
			if widget in class_buttons:
				return colors['surface_bg'], colors['text_fg'], colors['selected_bg']

			text = ''
			try:
				text = str(widget.cget('text')).lower()
			except Exception:
				pass

			danger_words = ('remove', 'delete', '삭제', '모두 삭제', '자동삭제')
			primary_words = ('open', 'load', '로드', '실행', 'execute', 'go', 'preview', 'keep only', '적용', '저장', '확인')
			success_words = ('add', '추가', 'copy', '복사')
			accent_words = ('filter', '필터', 'config', '설정', 'help', '도움')

			if any(word in text for word in danger_words):
				return colors['danger_bg'], colors['surface_bg'], colors['danger_active']
			if any(word in text for word in primary_words):
				return colors['primary_bg'], colors['surface_bg'], colors['primary_active']
			if any(word in text for word in success_words):
				return colors['success_bg'], colors['surface_bg'], colors['success_active']
			if any(word in text for word in accent_words):
				return colors['accent_bg'], colors['surface_bg'], colors['accent_active']
			return colors['button_bg'], colors['surface_bg'], colors['button_active']

		def style_widget(widget):
			try:
				if isinstance(widget, (tk.Frame, tk.LabelFrame)):
					safe_config(widget, bg=colors['panel_bg'], highlightbackground=colors['border'], highlightcolor=colors['border'])
					if isinstance(widget, tk.LabelFrame):
						safe_config(widget, fg=colors['muted_fg'], bd=1, relief=tk.SOLID)
				elif isinstance(widget, tk.Label):
					safe_config(widget, bg=colors['panel_bg'])
					current_fg = str(widget.cget('fg')).lower()
					if current_fg in ('blue', '#0000ff'):
						safe_config(widget, fg=colors['primary_bg'])
					elif current_fg in ('green', '#008000'):
						safe_config(widget, fg=colors['success_bg'])
					elif current_fg in ('red', '#ff0000'):
						safe_config(widget, fg=colors['danger_bg'])
					elif current_fg in ('gray', 'grey', '#808080'):
						safe_config(widget, fg=colors['muted_fg'])
					else:
						safe_config(widget, fg=colors['text_fg'])
				elif isinstance(widget, (tk.Checkbutton, tk.Radiobutton)):
					safe_config(
						widget,
						bg=colors['panel_bg'],
						fg=colors['text_fg'],
						activebackground=colors['panel_bg'],
						activeforeground=colors['text_fg'],
						selectcolor=colors['surface_bg']
					)
				elif isinstance(widget, tk.Canvas):
					canvas_bg = colors['canvas_bg'] if widget is getattr(self, 'canvas', None) else colors['surface_bg']
					safe_config(widget, bg=canvas_bg, highlightthickness=1, highlightbackground=colors['border'])
				elif isinstance(widget, tk.Button):
					bg, fg, active_bg = button_colors(widget)
					safe_config(
						widget,
						bg=bg,
						fg=fg,
						activebackground=active_bg,
						activeforeground=colors['surface_bg'],
						disabledforeground=colors['disabled_fg'],
						relief=tk.FLAT,
						bd=0,
						highlightthickness=1,
						highlightbackground=colors['border'],
						padx=6,
						pady=2,
						cursor='hand2'
					)
				elif isinstance(widget, (tk.Entry, tk.Spinbox)):
					safe_config(
						widget,
						bg=colors['input_bg'],
						fg=colors['text_fg'],
						insertbackground=colors['text_fg'],
						relief=tk.FLAT,
						bd=1,
						highlightthickness=1,
						highlightbackground=colors['border'],
						highlightcolor=colors['primary_bg']
					)
				elif isinstance(widget, tk.Listbox):
					safe_config(
						widget,
						bg=colors['surface_bg'],
						fg=colors['text_fg'],
						selectbackground=colors['selected_bg'],
						selectforeground=colors['text_fg'],
						relief=tk.FLAT,
						bd=1,
						highlightthickness=1,
						highlightbackground=colors['border'],
						highlightcolor=colors['primary_bg']
					)
				elif isinstance(widget, tk.Text):
					safe_config(
						widget,
						bg=colors['surface_bg'],
						fg=colors['text_fg'],
						insertbackground=colors['text_fg'],
						selectbackground=colors['selected_bg'],
						selectforeground=colors['text_fg'],
						relief=tk.FLAT,
						highlightthickness=1,
						highlightbackground=colors['border']
					)
				elif isinstance(widget, tk.Scrollbar):
					safe_config(widget, bg=colors['toolbar_bg'], activebackground=colors['border'], troughcolor=colors['surface_bg'])
			except Exception:
				pass
			for child in widget.winfo_children():
				style_widget(child)

		style_widget(self.master)

	def _zone_type_label(self, zone_type):
		return "점" if zone_type == 'point' else "다각형"

	def start_exclusion_zone_drawing(self, zone_type='polygon'):
		zone_type = 'point' if zone_type == 'point' else 'polygon'
		self.exclusion_zone_mode = True
		self.exclusion_zone_points = []
		self.exclusion_zone_draw_type = zone_type
		if zone_type == 'point':
			message = "캔버스에서 좌클릭으로 기준 점을 찍으세요.\n점이 bbox 안에 들어오면 제외됩니다."
		else:
			message = "캔버스에서 좌클릭으로 점을 추가하세요.\n우클릭 또는 첫 점을 다시 클릭하면 완성됩니다."
		messagebox.showinfo("제외 영역 추가", message)

	def finish_exclusion_point_zone(self):
		if len(self.exclusion_zone_points) < 1:
			return False
		selected_class_ids = self.select_classes_for_exclusion_zone(title="제외 영역 클래스 선택")
		if selected_class_ids is not None:
			original_points = [(px / self.zoom_ratio, py / self.zoom_ratio)
							  for px, py in self.exclusion_zone_points[:1]]
			added = self.exclusion_zone_manager.add_zone(
				original_points,
				use_global=True,
				class_ids=selected_class_ids,
				zone_type='point'
			)
			if added:
				self.exclusion_zone_manager.save_global_zones()
				if selected_class_ids:
					class_names = [self.class_config_manager.get_class_name(cid) for cid in selected_class_ids]
					class_info = f"적용 클래스: {', '.join(class_names)}"
				else:
					class_info = "적용 클래스: 모든 클래스"
				messagebox.showinfo("제외 점 추가", f"전역 제외 점이 추가되었습니다.\n{class_info}")
		self.exclusion_zone_mode = False
		self.exclusion_zone_points = []
		self.exclusion_zone_draw_type = 'polygon'
		self.draw_bbox()
		return True

	def start_class_change_zone_drawing(self, config, zone_type='polygon'):
		zone_type = 'point' if zone_type == 'point' else 'polygon'
		self.class_change_zone_mode = True
		self.class_change_zone_points = []
		self.class_change_zone_draw_type = zone_type
		self.class_change_zone_config = config
		if zone_type == 'point':
			message = "캔버스에서 좌클릭으로 기준 점을 찍으세요.\n점이 bbox 안에 들어오면 클래스가 변경됩니다."
		else:
			message = "캔버스에서 좌클릭으로 점을 추가하세요.\n우클릭 또는 첫 점을 다시 클릭하면 완성됩니다."
		messagebox.showinfo("클래스 변경 영역 추가", message)

	def finish_class_change_point_zone(self):
		if len(self.class_change_zone_points) < 1:
			return False
		config = self.class_change_zone_config
		if not config:
			self.class_change_zone_mode = False
			self.class_change_zone_points = []
			self.class_change_zone_draw_type = 'polygon'
			return False
		original_points = [(px / self.zoom_ratio, py / self.zoom_ratio)
						  for px, py in self.class_change_zone_points[:1]]
		self.class_change_zone_manager.add_zone(
			original_points,
			mode=config['mode'],
			target_class_id=config['target_class_id'],
			source_class_id=config.get('source_class_id'),
			zone_type='point'
		)
		self.class_change_zone_manager.save_zones()

		target_class = self.class_config_manager.get_class_name(config['target_class_id'])
		if config['mode'] == 'all':
			mode_info = f"모든 클래스 → {target_class}"
		else:
			source_class = self.class_config_manager.get_class_name(config['source_class_id'])
			mode_info = f"{source_class} → {target_class}"
		messagebox.showinfo("클래스 변경 점 추가", f"클래스 변경 점이 추가되었습니다.\n{mode_info}")

		self.class_change_zone_mode = False
		self.class_change_zone_points = []
		self.class_change_zone_draw_type = 'polygon'
		self.class_change_zone_config = None
		self.draw_bbox()
		return True

	def on_mouse_right_click(self, event):
		if not self.imlist: return
		if getattr(self, 'copy_region_mode', False):
			self.finish_copy_region_drawing()
			return
		"""우클릭 이벤트 처리"""
		x, y = self.get_canvas_coordinates(event)
		if not self.exclusion_zone_mode and not self.class_change_zone_mode:
			point = (x / self.imsize[0], y / self.imsize[1]) if self.imsize[0] and self.imsize[1] else (0, 0)
			self.show_copy_region_context_menu(event, point)
			return

		if self.exclusion_zone_mode and getattr(self, 'exclusion_zone_draw_type', 'polygon') == 'point':
			self.exclusion_zone_mode = False
			self.exclusion_zone_points = []
			self.exclusion_zone_draw_type = 'polygon'
			self.draw_bbox()
			return

		if self.class_change_zone_mode and getattr(self, 'class_change_zone_draw_type', 'polygon') == 'point':
			self.class_change_zone_mode = False
			self.class_change_zone_points = []
			self.class_change_zone_draw_type = 'polygon'
			self.class_change_zone_config = None
			self.draw_bbox()
			return

		# 제외 영역 그리기 모드에서 우클릭 시 폴리곤 완성
		if self.exclusion_zone_mode and len(self.exclusion_zone_points) >= 3:
			# 클래스 선택 다이얼로그
			selected_class_ids = self.select_classes_for_exclusion_zone(title="제외 영역 클래스 선택")

			if selected_class_ids is not None:  # 취소하지 않은 경우
				# 화면 좌표를 원본 좌표로 변환 (줌 비율 적용)
				original_points = [(px / self.zoom_ratio, py / self.zoom_ratio)
								  for px, py in self.exclusion_zone_points]

				# 폴리곤 완성 (전역 영역에 추가)
				self.exclusion_zone_manager.add_zone(original_points, use_global=True, class_ids=selected_class_ids)
				self.exclusion_zone_manager.save_global_zones()

				# 클래스 정보 메시지
				if selected_class_ids:
					class_names = [self.class_config_manager.get_class_name(cid) for cid in selected_class_ids]
					class_info = f"적용 클래스: {', '.join(class_names)}"
				else:
					class_info = "적용 클래스: 모든 클래스"

				messagebox.showinfo("제외 영역 추가", f"전역 제외 영역이 추가되었습니다.\n점 개수: {len(self.exclusion_zone_points)}\n{class_info}")

			self.exclusion_zone_mode = False
			self.exclusion_zone_points = []
			self.draw_bbox()  # 화면 갱신
			return

		# 클래스 변경 영역 그리기 모드에서 우클릭 시 폴리곤 완성
		if self.class_change_zone_mode and len(self.class_change_zone_points) >= 3:
			print(f"[DEBUG] 우클릭으로 클래스 변경 영역 폴리곤 완성: 점 개수 = {len(self.class_change_zone_points)}")
			# 화면 좌표를 원본 좌표로 변환 (줌 비율 적용)
			original_points = [(px / self.zoom_ratio, py / self.zoom_ratio)
							  for px, py in self.class_change_zone_points]

			# 폴리곤 완성
			config = self.class_change_zone_config
			print(f"[DEBUG] 우클릭 - 클래스 변경 영역 config = {config}")
			self.class_change_zone_manager.add_zone(
				original_points,
				mode=config['mode'],
				target_class_id=config['target_class_id'],
				source_class_id=config.get('source_class_id')
			)
			self.class_change_zone_manager.save_zones()

			# 모드 정보 메시지
			target_class = self.class_config_manager.get_class_name(config['target_class_id'])
			if config['mode'] == 'all':
				mode_info = f"모든 클래스 → {target_class}"
			else:
				source_class = self.class_config_manager.get_class_name(config['source_class_id'])
				mode_info = f"{source_class} → {target_class}"

			messagebox.showinfo("클래스 변경 영역 추가", f"클래스 변경 영역이 추가되었습니다.\n점 개수: {len(self.class_change_zone_points)}\n{mode_info}")

			self.class_change_zone_mode = False
			self.class_change_zone_points = []
			self.draw_bbox()  # 화면 갱신
			return

	def on_mouse_down(self, event):
		if not self.imlist: return
		if getattr(self, 'copy_region_mode', False):
			x, y = self.get_canvas_coordinates(event)
			if self.imsize[0] and self.imsize[1]:
				self.copy_region_points.append((x / self.imsize[0], y / self.imsize[1]))
			self.draw_bbox()
			return
		x, y = self.get_canvas_coordinates(event)

		# 제외 영역 그리기 모드
		if self.exclusion_zone_mode:
			if getattr(self, 'exclusion_zone_draw_type', 'polygon') == 'point':
				self.exclusion_zone_points = [(x, y)]
				self.finish_exclusion_point_zone()
				return

			# 첫 점을 다시 클릭했는지 확인 (폴리곤 닫기)
			if len(self.exclusion_zone_points) >= 3:
				first_point = self.exclusion_zone_points[0]
				# 첫 점 근처 클릭 확인 (10픽셀 이내)
				if ((x - first_point[0])**2 + (y - first_point[1])**2) <= 100:
					# 클래스 선택 다이얼로그
					selected_class_ids = self.select_classes_for_exclusion_zone(title="제외 영역 클래스 선택")

					if selected_class_ids is not None:  # 취소하지 않은 경우
						# 화면 좌표를 원본 좌표로 변환 (줌 비율 적용)
						original_points = [(px / self.zoom_ratio, py / self.zoom_ratio)
										  for px, py in self.exclusion_zone_points]

						# 폴리곤 완성 (전역 영역에 추가)
						self.exclusion_zone_manager.add_zone(original_points, use_global=True, class_ids=selected_class_ids)
						self.exclusion_zone_manager.save_global_zones()

						# 클래스 정보 메시지
						if selected_class_ids:
							class_names = [self.class_config_manager.get_class_name(cid) for cid in selected_class_ids]
							class_info = f"적용 클래스: {', '.join(class_names)}"
						else:
							class_info = "적용 클래스: 모든 클래스"

						messagebox.showinfo("제외 영역 추가", f"전역 제외 영역이 추가되었습니다.\n점 개수: {len(self.exclusion_zone_points)}\n{class_info}")

					self.exclusion_zone_mode = False
					self.exclusion_zone_points = []
					self.draw_bbox()  # 화면 갱신
					return

			# 점 추가
			self.exclusion_zone_points.append((x, y))
			self.draw_bbox()  # 화면 갱신
			return

		# 클래스 변경 영역 그리기 모드
		if self.class_change_zone_mode:
			if getattr(self, 'class_change_zone_draw_type', 'polygon') == 'point':
				self.class_change_zone_points = [(x, y)]
				self.finish_class_change_point_zone()
				return

			print(f"[DEBUG] 클래스 변경 영역 그리기 모드: 점 개수 = {len(self.class_change_zone_points)}")
			# 첫 점을 다시 클릭했는지 확인 (폴리곤 닫기)
			if len(self.class_change_zone_points) >= 3:
				first_point = self.class_change_zone_points[0]
				# 첫 점 근처 클릭 확인 (10픽셀 이내)
				if ((x - first_point[0])**2 + (y - first_point[1])**2) <= 100:
					print(f"[DEBUG] 폴리곤 완성 - 첫 점 근처 클릭")
					# 화면 좌표를 원본 좌표로 변환 (줌 비율 적용)
					original_points = [(px / self.zoom_ratio, py / self.zoom_ratio)
									  for px, py in self.class_change_zone_points]

					# 폴리곤 완성
					config = self.class_change_zone_config
					print(f"[DEBUG] 클래스 변경 영역 config = {config}")
					self.class_change_zone_manager.add_zone(
						original_points,
						mode=config['mode'],
						target_class_id=config['target_class_id'],
						source_class_id=config.get('source_class_id')
					)
					self.class_change_zone_manager.save_zones()

					# 모드 정보 메시지
					target_class = self.class_config_manager.get_class_name(config['target_class_id'])
					if config['mode'] == 'all':
						mode_info = f"모든 클래스 → {target_class}"
					else:
						source_class = self.class_config_manager.get_class_name(config['source_class_id'])
						mode_info = f"{source_class} → {target_class}"

					messagebox.showinfo("클래스 변경 영역 추가", f"클래스 변경 영역이 추가되었습니다.\n점 개수: {len(self.class_change_zone_points)}\n{mode_info}")

					self.class_change_zone_mode = False
					self.class_change_zone_points = []
					self.draw_bbox()  # 화면 갱신
					return

			# 점 추가
			print(f"[DEBUG] 클래스 변경 영역 점 추가: ({x}, {y})")
			self.class_change_zone_points.append((x, y))
			self.draw_bbox()  # 화면 갱신
			return

		if self.bbox_crop:
			self.area = [x, y, x+10, y+10]
			self.bbox_move_start_pt = [x, y]
			if not self.backup_current_image_and_bbox():
				messagebox.showerror("Backup Error", f"Backup failed. Crop was not started:\n{self.im_fn}")
				return
			self.img = Image.open(self.im_fn)
		elif self.bbox_add:
			for rc in self.bbox: rc[0] = False
			#self.bbox.append([True, class_name[0], -1, x, y, x+10, y+10])
			default_class_idx = self.get_default_class_for_new_bbox()
			default_class_name = self.get_default_class_name_for_new_bbox()
			self.bbox.append([True, default_class_name, default_class_idx, x, y, x+10, y+10])
			self.selid = len(self.bbox) - 1
			self.bbox_resize_anchor = ('se', )

			self.draw_bbox()
		elif self.bbox_masking:
			self.m_area = [x, y, x+10, y+10]
			self.bbox_move_start_pt = [x, y]
			if not self.backup_current_image_and_bbox():
				messagebox.showerror("Backup Error", f"Backup failed. Rect masking was not started:\n{self.im_fn}")
				return
		elif self.mouse_masking:
			self.bbox_move_start_pt = [x, y]
			if not self.backup_current_image_and_bbox():
				messagebox.showerror("Backup Error", f"Backup failed. Mouse masking was not started:\n{self.im_fn}")
				return
			point_size = max(3, int(3 * self.zoom_ratio))
			# self.canvas.create_rectangle([x-3, y-3, x+3, y+3], fill='magenta2', outline='', tags='masking_m')
			self.canvas.create_rectangle(
            [x-point_size, y-point_size, x+point_size, y+point_size], 
            fill='magenta2', outline='', tags='masking_m'
			)
			self.m_masking_img([x, y])
		elif self.polygon_masking:
			# 폴리곤이 닫혀있지 않은 경우에만 점 추가
			if not self.is_polygon_closed:
				# 첫 점을 다시 클릭했는지 확인 (폴리곤 닫기)
				if len(self.polygon_points) >= 3:
					first_point = self.polygon_points[0]
					# 첫 점 근처 클릭 확인 (10픽셀 이내)
					if ((x - first_point[0])**2 + (y - first_point[1])**2) <= 100:
						self.polygon_points.append(first_point)  # 첫 점 다시 추가
						self.is_polygon_closed = True
						self.apply_polygon_masking()
						return
				
				# 점 추가
				self.polygon_points.append((x, y))
				self.draw_polygon()
			return
		else:
			h = self.canvas.find_withtag("current")
			t = self.canvas.gettags(h)
			print(f"[ANCHOR DEBUG] Mouse down at ({x},{y}) - canvas handle: {h}, tags: {t}")

			# 마우스 위치에서 모든 겹치는 객체 찾기
			overlapping = self.canvas.find_overlapping(x-2, y-2, x+2, y+2)
			print(f"[ANCHOR DEBUG] Overlapping objects: {overlapping}")
			for obj in overlapping:
				obj_tags = self.canvas.gettags(obj)
				print(f"[ANCHOR DEBUG]   Object {obj}: {obj_tags}")
				if 'anchor' in obj_tags:
					print(f"[ANCHOR DEBUG] ✓ Found anchor in overlapping! tags={obj_tags}")
					self.bbox_resize_anchor = obj_tags
					return

			if 'anchor'in t:
				print(f"[ANCHOR DEBUG] Anchor clicked! tags={t}")
				self.bbox_resize_anchor = t
			elif self.selid >= 0:
				if self.pt_in_current_rc(x, y):
					self.bbox_move = True
					self.bbox_move_start_pt = [x, y]
				else:
					if event.state & 0x4:  # Ctrl 키가 눌린 상태
						for i in range(len(self.bbox)):
							rc = self.bbox[i]
							if int(rc[3]) <= x <= int(rc[5]) and int(rc[4]) <= y <= int(rc[6]):
								self.toggle_multi_selection(i)
								return
					else:
						for i in range(len(self.bbox)):
							rc = self.bbox[i]
							if int(rc[3]) <= x <= int(rc[5]) and int(rc[4]) <= y <= int(rc[6]):
								# 다중 선택 모드가 아닌 경우 기존 동작
								if not self.multi_select_mode:
									self.bbox[self.selid][0] = False
									self.selid = i
									self.bbox[i][0] = True
								else:
									# 다중 선택 모드인 경우 추가/제거
									self.toggle_multi_selection(i)
								self.draw_bbox()
								if not self.multi_select_mode:
									rc = self.convert_abs2rel(self.bbox[self.selid])
									self.pre_rc = self.convert_rel2abs(rc)
								return
		return

	def on_mouse_ctrl_down(self, event):
		if not self.imlist: return
		x, y = self.get_canvas_coordinates(event)

		for i in range(len(self.bbox)):
			rc = self.bbox[i]
			if int(rc[3]) <= x <= int(rc[5]) and int(rc[4]) <= y <= int(rc[6]):
				self.bbox[self.selid][0] = False
				self.selid = i
				self.bbox[i][0] = True
				self.draw_bbox()
				rc = self.convert_abs2rel(self.bbox[self.selid])
				self.pre_rc = self.convert_rel2abs(rc)
				return
	def convert_label_to_mask(self):
		if self.selid < 0:
			messagebox.showwarning("경고", "선택된 라벨이 없습니다.")
			return
		
		# 현재 선택된 라벨의 좌표 정보
		bbox = self.bbox[self.selid]
		if not self.backup_original_pair(self.im_fn, self.gt_fn):
			messagebox.showerror("Backup Error", f"Backup failed. Label-to-mask was not applied:\n{self.im_fn}")
			return

		# 이미지 로드
		self.img = Image.open(self.im_fn)
		self.original_width = self.img.width
		self.original_height = self.img.height
		
		# 좌표 계산 - 직접 줌 비율 적용
		view_x1, view_y1, view_x2, view_y2 = bbox[3:7]
		
		# 줌 비율을 적용해서 원본 이미지 좌표로 변환
		orig_x1 = int(view_x1 / self.zoom_ratio)
		orig_y1 = int(view_y1 / self.zoom_ratio)
		orig_x2 = int(view_x2 / self.zoom_ratio)
		orig_y2 = int(view_y2 / self.zoom_ratio)
		
		# 좌표 순서 보정 (min/max 확실히)
		orig_x1, orig_x2 = min(orig_x1, orig_x2), max(orig_x1, orig_x2)
		orig_y1, orig_y2 = min(orig_y1, orig_y2), max(orig_y1, orig_y2)
		
		# 좌표가 이미지 크기를 벗어나지 않도록 보정
		orig_x1 = max(0, min(orig_x1, self.original_width - 1))
		orig_y1 = max(0, min(orig_y1, self.original_height - 1))
		orig_x2 = max(orig_x1 + 1, min(orig_x2, self.original_width))  # 최소 1픽셀 크기 보장
		orig_y2 = max(orig_y1 + 1, min(orig_y2, self.original_height))
		
		print(f"라벨→마스크: 캔버스({view_x1},{view_y1},{view_x2},{view_y2}) → 원본({orig_x1},{orig_y1},{orig_x2},{orig_y2})")
		print(f"마스킹 영역 크기: {orig_x2-orig_x1} x {orig_y2-orig_y1}")
		
		# 메모리상 마스킹 적용
		self.original_img_array = array(self.img.copy())
		self.current_img_array = array(self.img.copy())
		
		# 바운딩 박스 영역만 마스킹
		self.current_img_array[orig_y1:orig_y2, orig_x1:orig_x2, :] = [255, 0, 255]
		
		# 마스킹 정보 저장
		self.masking = np.where((self.current_img_array==[255,0,255]).all(axis=2))
		self.maskingframewidth = self.original_width
		self.maskingframeheight = self.original_height
		self.has_saved_masking = True
		self.is_masking_dirty = True
		
		# 디버깅: 마스킹된 픽셀 개수 확인
		print(f"마스킹된 픽셀 개수: {len(self.masking[0])}")

		if len(self.masking[0]) == 0:
			print("경고: 마스킹이 적용되지 않았습니다!")
			return

		# 마스킹으로 변환되는 라벨 정보 저장 (노란색 동그라미 표시용)
		self.pending_masked_labels.append({
			'bbox': bbox,
			'class_name': bbox[1],
			'x1': view_x1,
			'y1': view_y1,
			'x2': view_x2,
			'y2': view_y2
		})

		# 현재 라벨 삭제
		self.bbox.pop(self.selid)
		self.write_bbox()

		# === 이미지 파일에 마스킹 저장 (중요!) ===
		img_to_save = Image.fromarray(self.current_img_array)
		if self.im_fn.lower().endswith('.jpg') or self.im_fn.lower().endswith('.jpeg'):
			img_to_save.save(self.im_fn, quality=95, optimize=True)
		else:
			img_to_save.save(self.im_fn)
		print(f"마스킹이 이미지 파일에 저장되었습니다: {self.im_fn}")

		# 마스킹 정보 파일 삭제 (중복 저장 방지)
		mask_info_file = os.path.splitext(self.im_fn)[0] + '_mask.npz'
		if os.path.exists(mask_info_file):
			try:
				os.remove(mask_info_file)
				print(f"마스킹 정보 파일 삭제됨: {mask_info_file}")
			except Exception as e:
				print(f"마스킹 정보 파일 삭제 오류: {e}")

		# pending 카운터 증가 및 상태 표시 (화면 갱신 생략)
		self.pending_operation_count += 1
		self.show_temporary_status(
			f"✓ 라벨→마스크 변환 (파일 저장, 화면 갱신 생략) - 작업: {self.pending_operation_count}개",
			duration=2000,
			bg_color='#9C27B0'
		)
		print(f"[SpeedOptimization] 라벨→마스크 - 이미지/txt 저장 완료, draw_image() 생략")

		# draw_image() 제거 - 전체 화면 갱신 생략으로 속도 개선
		# 이미지 파일에 이미 마스킹이 저장되었으므로, 페이지 전환 시 자동 반영됨
	def on_mouse_up(self, event):
		if not self.imlist: return
		x, y = self.get_canvas_coordinates(event)

		# bbox 수정 여부 플래그 저장 (False로 변경하기 전에)
		bbox_was_modified = self.bbox_add or self.bbox_resize_anchor is not None or self.bbox_move

		if self.bbox_crop:
			self.canvas.create_rectangle(self.area[0], self.area[1], self.area[2], self.area[3], tags="crop")
			self.crop_img()
		elif self.bbox_masking:
			self.canvas.delete("masking")
			self.canvas.create_rectangle(self.m_area[0], self.m_area[1], self.m_area[2], self.m_area[3], outline='', fill='magenta2')
			self.masking_img()
		self.bbox_add = False
		self.cross_line = False
		if self.bbox_resize_anchor is not None:
			print(f"[RESIZE DEBUG] Mouse up - resetting anchor from {self.bbox_resize_anchor}")
		self.bbox_resize_anchor = None
		self.bbox_move = False
		if len(self.bbox) != 0:
			self.draw_bbox()
			if self.bbox_crop:
				self.draw_image()
				self.bbox_crop = False
			if self.selid >= 0:
				rc = self.convert_abs2rel(self.bbox[self.selid])
				self.pre_rc = self.convert_rel2abs(rc)

			# bbox가 추가/수정/이동되었으면 파일에 저장
			if bbox_was_modified:
				self.write_bbox()
		return

	def draw_cross_line(self, event):
		self.canvas.delete("crossline")
		if self.cross_line:
			self.canvas.create_line(0, event.y, self.imsize[0], event.y, fill="red", dash=(1,1), tags="crossline")
			self.canvas.create_line(event.x, 0, event.x, self.imsize[1], fill="red", dash=(1,1), tags="crossline")
		return

	def on_mouse_move(self, event):
		if not self.imlist: return
		x, y = self.get_canvas_coordinates(event)
			
		# 크로스 라인 그리기
		self.canvas.delete("crossline")
		if self.polygon_masking and not self.is_polygon_closed and len(self.polygon_points) > 0:
			# 임시 선 업데이트 (마지막 포인트에서 현재 마우스 위치까지)
			self.canvas.delete("temp_line")
			last_point = self.polygon_points[-1]
			self.canvas.create_line(
				last_point[0], last_point[1], x, y,
				fill="yellow", dash=(5, 5), tags="temp_line"
			)
		if self.cross_line:
			# 전체 캔버스 영역에 대해 라인 그리기 (스크롤 영역 고려)
			self.canvas.create_line(0, y, self.imsize[0], y, fill="red", dash=(1,1), tags="crossline")
			self.canvas.create_line(x, 0, x, self.imsize[1], fill="red", dash=(1,1), tags="crossline")
		return

	def convert_view_to_original(self, x, y):
		"""현재 뷰 좌표를 원본 이미지 좌표로 변환"""
		# 현재 스크롤 위치 고려 - 이미 캔버스 좌표인 경우 스크롤 적용하지 않음
		view_x = x  # self.canvas.canvasx(x) 대신
		view_y = y  # self.canvas.canvasy(y) 대신
		
		# 줌 비율 적용하여 원본 좌표 계산
		original_x = int(view_x / self.zoom_ratio)
		original_y = int(view_y / self.zoom_ratio)
		
		print(f"좌표 변환: ({x},{y}) -> ({view_x},{view_y}) -> ({original_x},{original_y}) [줌:{self.zoom_ratio}]")
		
		return original_x, original_y

	def convert_original_to_view(self, original_x, original_y):
		"""원본 이미지 좌표를 현재 뷰 좌표로 변환"""
		view_x = int(original_x * self.zoom_ratio)
		view_y = int(original_y * self.zoom_ratio)
		return view_x, view_y
	def on_click_mouse_move(self, event):
		if not self.imlist: return
		x, y = self.get_canvas_coordinates(event)
		if self.polygon_masking and not self.is_polygon_closed and len(self.polygon_points) > 0:
			# 임시 선 업데이트 (마지막 포인트에서 현재 마우스 위치까지)
			self.canvas.delete("temp_line")
			last_point = self.polygon_points[-1]
			self.canvas.create_line(
				last_point[0], last_point[1], x, y,
				fill="yellow", dash=(5, 5), tags="temp_line"
			)
			return
		if self.bbox_resize_anchor != None:
			print(f"[RESIZE DEBUG] Mouse move - anchor={self.bbox_resize_anchor}, x={x}, y={y}")
			rc = self.bbox[self.selid][3:]
			a = self.bbox_resize_anchor
			print(f"[RESIZE DEBUG] Before resize - rc={rc}")
			self.cross_line = True
			if   'nw' in a: rc[0] = x; rc[1] = y
			elif 'n'  in a:           rc[1] = y
			elif 'ne' in a: rc[2] = x; rc[1] = y
			elif 'e'  in a: rc[2] = x
			elif 'se' in a: rc[2] = x; rc[3] = y
			elif 's'  in a:           rc[3] = y
			elif 'sw' in a: rc[0] = x; rc[3] = y
			elif 'w'  in a: rc[0] = x
			print(f"[RESIZE DEBUG] After resize - rc={rc}")
			if rc[0] >= 0 and rc[1] >= 0 and rc[2] < self.imsize[0] and rc[3] < self.imsize[1]:
				self.bbox[self.selid][3:] = self.bound_box_coord(rc)
				print(f"[RESIZE DEBUG] Applied resize")
			else:
				print(f"[RESIZE DEBUG] Out of bounds - imsize={self.imsize}")
			self.draw_bbox()
		elif self.bbox_move:
			rc = self.bbox[self.selid][3:]
			rc[0] += (x - self.bbox_move_start_pt[0])
			rc[1] += (y - self.bbox_move_start_pt[1])
			rc[2] += (x - self.bbox_move_start_pt[0])
			rc[3] += (y - self.bbox_move_start_pt[1])
			if rc[0] >= 0 and rc[1] >= 0 and rc[2] < self.imsize[0] and rc[3] < self.imsize[1]:
				self.bbox[self.selid][3:] = self.bound_box_coord(rc)
			self.bbox_move_start_pt = [x, y]
			self.draw_bbox()
		elif self.bbox_crop:
			self.canvas.delete("crop")
			rc = self.area
			rc[0] = self.bbox_move_start_pt[0]
			rc[1] = self.bbox_move_start_pt[1]
			rc[2] = x
			rc[3] = y
			self.area = rc
			self.canvas.create_rectangle(self.area[0], self.area[1], self.area[2], self.area[3], tags="crop")
		elif self.bbox_masking:
			self.canvas.delete("masking")
			rc = self.m_area
			rc[0] = self.bbox_move_start_pt[0]
			rc[1] = self.bbox_move_start_pt[1]
			rc[2] = x
			rc[3] = y
			self.m_area = rc
			self.canvas.create_rectangle(self.m_area[0], self.m_area[1], self.m_area[2], self.m_area[3], tags="masking")
		elif self.mouse_masking:
			self.canvas.create_rectangle([x-3, y-3, x+3, y+3], fill='magenta2', outline='', tags='masking_m')
			self.m_masking_img([x, y])
		
		if self.selid >= 0:
			rc = self.convert_abs2rel(self.bbox[self.selid])
			self.pre_rc = self.convert_rel2abs(rc)
		
		# 크로스 라인 업데이트
		self.draw_cross_line(event)
		return
	def create_class_button(self, label, class_idx, key=None):
		button = tk.Button(
        self.button_frame, 
        text=label, 
        command=lambda idx=class_idx: self.change_class(idx),
        bd=1
    )
		pack_options = {'side': tk.LEFT, 'padx': 0}
		if hasattr(self, 'loadLabel'):
			pack_options['before'] = self.loadLabel
		button.pack(**pack_options)
		
		# 우클릭 이벤트 바인딩
		button.bind("<Button-3>", lambda event, btn=button, idx=class_idx:
					self.show_class_menu(event, btn, idx))
		if hasattr(self, 'canvas'):
			button.bind("<ButtonRelease-1>", lambda e: self.canvas.focus_set())
		
		# 버튼과 클래스 인덱스 매핑 저장
		self.button_class_map[button] = class_idx
		
		# 키 매핑 저장 (키가 지정된 경우)
		normalized_key = normalize_shortcut_key(key)
		if normalized_key is not None:
			self.key_button_map[normalized_key] = button
		
		return button

	def show_class_menu(self, event, button, current_idx):
		"""버튼 우클릭 시 클래스 선택 메뉴 표시"""
		menu = tk.Menu(self.master, tearoff=0)

		# 검색 옵션 추가
		menu.add_command(label="🔍 Search Classes...",
						command=lambda: self.open_class_search_dialog(button))
		menu.add_separator()

		# 모든 클래스를 평면 구조로 표시
		for idx in range(len(class_name)):
			menu.add_command(
				label=f"{idx}: {class_name[idx]}",
				command=lambda btn=button, idx=idx: self.set_button_class(btn, idx)
			)

		# 메뉴 표시
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()

	def open_class_search_dialog(self, button):
		"""클래스 검색 다이얼로그 열기"""
		search_dialog = tk.Toplevel(self.master)
		search_dialog.title("Search Classes")
		search_dialog.geometry("400x500")
		search_dialog.resizable(False, False)
		search_dialog.transient(self.master)  # 부모 윈도우에 종속
		search_dialog.grab_set()  # 모달 다이얼로그로 설정
		
		# 검색 프레임
		search_frame = tk.Frame(search_dialog)
		search_frame.pack(fill="x", padx=10, pady=10)
		
		# 검색 레이블
		search_label = tk.Label(search_frame, text="Search:")
		search_label.pack(side=tk.LEFT, padx=5)
		
		# 검색어 입력 필드
		search_var = tk.StringVar()
		search_entry = tk.Entry(search_frame, textvariable=search_var, width=30)
		search_entry.pack(side=tk.LEFT, fill="x", expand=True, padx=5)
		search_entry.focus_set()  # 자동 포커스
		
		# 결과 리스트박스 프레임
		result_frame = tk.Frame(search_dialog)
		result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
		
		# 결과 리스트박스
		result_listbox = tk.Listbox(result_frame, width=50, height=20, font=("Courier", 10))
		result_listbox.pack(side=tk.LEFT, fill="both", expand=True)
		
		# 스크롤바
		scrollbar = tk.Scrollbar(result_frame, orient="vertical", command=result_listbox.yview)
		scrollbar.pack(side=tk.RIGHT, fill="y")
		result_listbox.config(yscrollcommand=scrollbar.set)
		
		# 버튼 프레임
		button_frame = tk.Frame(search_dialog)
		button_frame.pack(fill="x", padx=10, pady=(0, 10))
		
		# 선택 버튼
		select_btn = tk.Button(
			button_frame, 
			text="Select", 
			command=lambda: self.select_class_from_search(button, result_listbox, search_dialog)
		)
		select_btn.pack(side=tk.RIGHT, padx=5)
		
		# 취소 버튼
		cancel_btn = tk.Button(button_frame, text="Cancel", command=search_dialog.destroy)
		cancel_btn.pack(side=tk.RIGHT, padx=5)
		
		# 검색 함수
		def perform_search(*args):
			# 리스트박스 초기화
			result_listbox.delete(0, tk.END)
			
			# 검색어
			query = search_var.get().lower()
			
			# 검색 결과 추가
			for idx, name in enumerate(class_name):
				if query in name.lower() or query in str(idx):
					result_listbox.insert(tk.END, f"{idx:3d}: {name}")
		
		# 리스트박스 더블 클릭 이벤트
		def on_double_click(event):
			self.select_class_from_search(button, result_listbox, search_dialog)
		
		# 리스트박스 엔터 키 이벤트
		def on_enter(event):
			self.select_class_from_search(button, result_listbox, search_dialog)
		
		# 이벤트 바인딩
		search_var.trace("w", perform_search)  # 입력 시 실시간 검색
		result_listbox.bind("<Double-Button-1>", on_double_click)  # 더블 클릭
		result_listbox.bind("<Return>", on_enter)  # 엔터 키
		search_entry.bind("<Return>", lambda e: result_listbox.focus_set())  # 검색 필드에서 엔터 키
		
		# 초기 검색 (모든 클래스 표시)
		perform_search()

	def select_class_from_search(self, button, listbox, dialog):
		"""검색 결과에서 클래스 선택"""
		# 선택된 항목 가져오기
		selected = listbox.curselection()
		if not selected:
			return
		
		# 선택된 텍스트에서 클래스 인덱스 추출
		selected_text = listbox.get(selected[0])
		class_idx = int(selected_text.split(":")[0])
		
		# 버튼 클래스 설정
		self.set_button_class(button, class_idx)
		
		# 다이얼로그 닫기
		dialog.destroy()
	def get_canvas_coordinates(self, event):
		"""스크롤 위치를 고려한 캔버스 좌표 계산"""
		# 캔버스의 현재 스크롤 위치 가져오기
		x = self.canvas.canvasx(event.x)
		y = self.canvas.canvasy(event.y)
		return int(x), int(y)
	def get_iou(self, box1, box2):
		# box = (x1, y1, x2, y2)
		box1_area = (box1[2] - box1[0] + 1) * (box1[3] - box1[1] + 1)
		box2_area = (box2[2] - box2[0] + 1) * (box2[3] - box2[1] + 1)    
		# obtain x1, y1, x2, y2 of the intersection
		x1 = max(box1[0], box2[0])
		y1 = max(box1[1], box2[1])
		x2 = min(box1[2], box2[2])
		y2 = min(box1[3], box2[3])
		# compute the width and height of the intersection
		w = max(0, x2 - x1 + 1)
		h = max(0, y2 - y1 + 1)
		inter = w * h
		iou = inter / (box1_area + box2_area - inter)
		return iou
	def draw_polygon(self):
		"""현재 폴리곤 포인트를 캔버스에 그립니다"""
		# 이전 폴리곤 지우기
		self.canvas.delete("polygon")
		self.canvas.delete("polygon_point")
		
		# 점이 부족하면 그리지 않음
		if len(self.polygon_points) < 2:
			return
		
		# 선 그리기
		points_flat = [coord for point in self.polygon_points for coord in point]
		self.canvas.create_line(
			points_flat, 
			fill="magenta", 
			width=2,
			tags="polygon"
		)
		
		# 점 표시 (옵션에 따라)
		if self.show_polygon_points:
			point_radius = 4
			for i, (px, py) in enumerate(self.polygon_points):
				# 첫 점은 다른 색상으로 표시
				fill_color = "green" if i == 0 else "yellow"
				self.canvas.create_oval(
					px - point_radius, py - point_radius,
					px + point_radius, py + point_radius,
					fill=fill_color, outline="black",
					tags="polygon_point"
				)

	def apply_polygon_masking(self):
		if len(self.polygon_points) < 3:
			messagebox.showwarning("경고", "폴리곤 마스킹을 적용하려면 최소 3개의 점이 필요합니다.")
			return
		
		# 폴리곤 관련 UI 요소 정리
		self.canvas.delete("polygon")
		self.canvas.delete("polygon_point")
		self.canvas.delete("temp_line")
		
		# 폴리곤 포인트를 원본 이미지 좌표계로 변환
		orig_polygon_points = []
		for x, y in self.polygon_points:
			orig_x, orig_y = self.convert_view_to_original(x, y)
			orig_polygon_points.append((orig_x, orig_y))
		
		# === 메모리상에서만 마스킹 처리 (수정된 부분) ===
		# 폴리곤 마스크 생성 (OpenCV 사용)
		mask = np.zeros((self.original_height, self.original_width), dtype=np.uint8)
		
		# 폴리곤 포인트 포맷 변환 (OpenCV 요구 형식)
		cv_polygon_points = np.array([orig_polygon_points], dtype=np.int32)
		
		# 폴리곤 내부 채우기
		cv2.fillPoly(mask, cv_polygon_points, 255)
		
		# 현재 작업중인 배열에 마스킹 적용 (파일 저장 안함)
		self.current_img_array[mask == 255] = [255, 0, 255]  # 마젠타 색상
		
		# 마스킹 정보 저장
		self.maskingframewidth = self.original_width
		self.maskingframeheight = self.original_height
		self.masking = np.where((self.current_img_array==[255,0,255]).all(axis=2))
		self.has_saved_masking = True
		self.is_masking_dirty = True  # 저장 필요 플래그 설정
		
		# 폴리곤 좌표 정보도 저장
		self.saved_polygon_points = self.polygon_points.copy()  # 캔버스 좌표
		self.saved_orig_polygon_points = orig_polygon_points.copy()  # 원본 이미지 좌표
		# === 메모리상 마스킹 처리 끝 ===
		
		# 마스킹 라벨 삭제 옵션이 켜져 있는 경우
		if self.remove_overlapping_labels.get():
			self.remove_labels_overlapping_with_polygon()
		
		# 폴리곤 마스킹 모드 종료
		self.polygon_masking = False
		self.polygon_points = []
		self.is_polygon_closed = False
		
		# === 화면 업데이트만 (파일 저장 안함) ===
		# 마스킹이 적용된 이미지로 화면 업데이트
		display_img = Image.fromarray(self.current_img_array)
		resized_img = display_img.resize([(int)(i * self.zoom_ratio) for i in display_img.size], Image.LANCZOS)
		self.canvas.image = ImageTk.PhotoImage(resized_img)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
		# === 화면 업데이트 끝 ===
		
		print("폴리곤 마스킹이 적용되었습니다.")

	def remove_labels_overlapping_with_polygon(self):
		"""폴리곤 마스크 픽셀과 겹치는 라벨 삭제"""
		if not hasattr(self, 'masking') or self.masking is None:
			return

		if not self.bbox:
			return
		
		# 삭제할 라벨 인덱스 리스트 (역순으로 삭제하기 위해)
		to_remove = []
		
		# 겹치는 라벨 찾기
		for i, box in enumerate(self.bbox):
			if self.check_bbox_mask_pixel_overlap(box):
				to_remove.append(i)

		if to_remove and not self.backup_original_file(self.gt_fn, 'labels'):
			messagebox.showerror("Backup Error", f"Backup failed. Labels were not removed:\n{self.gt_fn}")
			return

		# 역순으로 삭제 (인덱스 변화 방지)
		for i in sorted(to_remove, reverse=True):
			self.bbox.pop(i)
		
		# 현재 선택 바운딩 박스 조정
		if to_remove and self.selid >= 0:
			if self.selid in to_remove:
				# 선택된 박스가 삭제된 경우
				self.selid = min(len(self.bbox) - 1, 0) if self.bbox else -1
			else:
				# 선택된 박스의 인덱스 갱신
				new_selid = self.selid
				for i in to_remove:
					if i < self.selid:
						new_selid -= 1
				self.selid = new_selid
		
		# 바운딩 박스가 남아있으면 선택 상태 업데이트
		if self.bbox and self.selid >= 0:
			for i in range(len(self.bbox)):
				self.bbox[i][0] = (i == self.selid)
		
		# 라벨 파일 업데이트
		self.write_bbox()
	def print_help(self):
		"""도움말 텍스트 다이얼로그 표시"""
		# 도움말 파일 경로
		help_file = os.path.join(os.getcwd(), "help.txt")

		# 기본 도움말 내용
		default_help = """=== GTGEN Tool 도움말 ===

[기본 조작]
- 좌클릭: 객체 선택
- 우클릭: 선택한 객체 삭제
- Ctrl + 좌클릭: 새 객체 추가 시작
- 드래그: 객체 이동 또는 크기 조정

[키보드 단축키]
- 1~9, 0: 클래스 선택 (설정된 클래스)
- ←/→: 이전/다음 프레임
- ↑/↓: 다음/이전 객체 선택
- Shift + ←/→: 선택한 객체를 좌/우로 1픽셀 이동
- Shift + ↑/↓: 선택한 객체를 상/하로 1픽셀 이동
- Ctrl + ←/→: 선택한 객체 폭 1픽셀 조정
- Ctrl + ↑/↓: 선택한 객체 높이 1픽셀 조정
- Delete: 선택한 객체 삭제
- Tab: 다음 객체 선택
- Shift + Tab: 이전 객체 선택
- g: 자동 삭제 대상 클래스 수동 삭제 (단축키 모드일 때)

[버튼 기능]
- Back/Next: 이전/다음 프레임
- Add: 새 객체 추가 모드
- Remove: 선택한 객체 삭제
- Open Folder: 새 폴더 열기
- Open List: 이미지 리스트 파일 열기
- 클래스 설정: 클래스 설정 변경
- 자동삭제: 특정 클래스 자동 삭제 설정
- 제외영역: 폴리곤 제외 영역 관리
- Help: 이 도움말 표시

[체크박스]
- Show Size: 객체 크기 정보 표시
- Label→Mask: 라벨을 마스킹 영역으로 변환
- Mask→Del Labels: 마스킹 영역과 겹치는 라벨 삭제
- Show Poly Pts: 폴리곤 점 표시
- Show Label List: 라벨 리스트 표시
- Track Labels: 프레임 간 라벨 추적

[제외 영역 기능]
1. '제외영역' 버튼 클릭
2. '다각형 추가' 또는 '점 추가' 선택
3. 다각형은 캔버스에서 좌클릭으로 점 추가 후 우클릭 또는 첫 점 재클릭으로 완성
4. 점은 캔버스에서 좌클릭 한 번으로 추가
5. '기능 활성화' 체크 시 다음 페이지부터 해당 영역/점의 라벨 자동 삭제

[클래스 자동 삭제 기능]
1. '자동삭제' 버튼 클릭
2. 각 클래스별로 설정:
   - 체크박스: 자동 삭제 대상 여부 선택
   - 모드 선택 (클래스별 개별 설정):
     * 페이지 이동: 다음 페이지로 이동 시 자동 삭제
     * 단축키 'g': 'g' 키를 눌렀을 때만 삭제
3. '저장' 클릭
4. 설정에 따라:
   - 페이지 이동 모드: 다음 페이지부터 자동 삭제
   - 단축키 'g' 모드: 'g' 키 입력 시 삭제

====================
이 도움말은 편집할 수 있습니다.
"""

		# 도움말 파일이 없으면 생성
		if not os.path.exists(help_file):
			try:
				with open(help_file, 'w', encoding='utf-8') as f:
					f.write(default_help)
			except Exception as e:
				print(f"[ERROR] Failed to create help file: {e}")

		# 도움말 파일 읽기
		help_text = default_help
		if os.path.exists(help_file):
			try:
				with open(help_file, 'r', encoding='utf-8') as f:
					help_text = f.read()
			except Exception as e:
				print(f"[ERROR] Failed to read help file: {e}")

		# 도움말 다이얼로그 생성
		help_dialog = tk.Toplevel(self.master)
		help_dialog.title("도움말")
		help_dialog.geometry("700x600")
		help_dialog.transient(self.master)

		# 텍스트 위젯 (스크롤바 포함)
		text_frame = tk.Frame(help_dialog)
		text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		scrollbar = tk.Scrollbar(text_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

		text_widget = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=("맑은 고딕", 10))
		text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		scrollbar.config(command=text_widget.yview)

		text_widget.insert(tk.END, help_text)

		# 버튼 프레임
		button_frame = tk.Frame(help_dialog)
		button_frame.pack(pady=5)

		def save_help():
			"""도움말 내용 저장"""
			try:
				content = text_widget.get("1.0", tk.END)
				with open(help_file, 'w', encoding='utf-8') as f:
					f.write(content)
				messagebox.showinfo("저장 완료", "도움말이 저장되었습니다.")
			except Exception as e:
				messagebox.showerror("저장 실패", f"도움말 저장 실패:\n{e}")

		tk.Button(button_frame, text="저장", command=save_help, width=10).pack(side=tk.LEFT, padx=5)
		tk.Button(button_frame, text="닫기", command=help_dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)

		return

	def manage_exclusion_zones(self):
		"""제외 영역 관리 다이얼로그"""
		dialog = tk.Toplevel(self.master)
		dialog.title("제외 영역 관리")
		dialog.geometry("650x500")
		dialog.transient(self.master)
		dialog.grab_set()

		# 설명 레이블
		tk.Label(dialog, text="제외 영역을 관리합니다", font=("맑은 고딕", 10, "bold")).pack(pady=10)

		# 기능 활성화 체크박스
		enable_var = tk.BooleanVar()
		enable_var.set(self.exclusion_zone_enabled)

		def toggle_enabled():
			self.exclusion_zone_enabled = enable_var.get()
			self.exclusion_zone_manager.save_enabled_state(self.exclusion_zone_enabled)
			print(f"[ExclusionZone] 기능 {'활성화' if self.exclusion_zone_enabled else '비활성화'}")

		tk.Checkbutton(dialog, text="기능 활성화 (모든 페이지에 적용)", variable=enable_var, command=toggle_enabled, font=("맑은 고딕", 10)).pack(pady=5)

		# 영역 리스트
		list_frame = tk.LabelFrame(dialog, text="전역 제외 영역 목록")
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		scrollbar = tk.Scrollbar(list_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

		listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
		listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		scrollbar.config(command=listbox.yview)

		def refresh_list():
			listbox.delete(0, tk.END)
			for i, zone in enumerate(self.exclusion_zone_manager.global_zones):
				status = "✓" if zone['enabled'] else "✗"
				zone_points = zone.get('points', [])
				point_count = len(zone_points)
				zone_type = zone.get('zone_type', 'point' if point_count == 1 else 'polygon')
				type_label = self._zone_type_label(zone_type)

				# 클래스 정보 표시
				zone_class_ids = zone.get('class_ids', [])
				if zone_class_ids:
					class_names = [self.class_config_manager.get_class_name(cid) for cid in zone_class_ids]
					class_info = f" - {', '.join(class_names)}"
				else:
					class_info = " - 모든 클래스"

				listbox.insert(tk.END, f"{status} {type_label} {i+1} ({point_count}개 점){class_info}")

		refresh_list()

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def add_zone():
			"""제외 영역 추가 모드 활성화"""
			self.start_exclusion_zone_drawing('polygon')
			dialog.destroy()

		def add_point_zone():
			"""제외 점 추가 모드 활성화"""
			self.start_exclusion_zone_drawing('point')
			dialog.destroy()

		def remove_zone():
			"""선택한 영역 삭제"""
			selection = listbox.curselection()
			if selection:
				index = selection[0]
				self.exclusion_zone_manager.remove_zone(index)
				# 전역 영역 저장
				self.exclusion_zone_manager.save_global_zones()
				refresh_list()
				self.draw_bbox()  # 화면 갱신

		def toggle_zone():
			"""선택한 영역 활성화/비활성화"""
			selection = listbox.curselection()
			if selection:
				index = selection[0]
				self.exclusion_zone_manager.toggle_zone(index)
				# 전역 영역 저장
				self.exclusion_zone_manager.save_global_zones()
				refresh_list()
				self.draw_bbox()  # 화면 갱신

		def clear_all():
			"""모든 영역 삭제"""
			if messagebox.askyesno("확인", "모든 제외 영역을 삭제하시겠습니까?"):
				self.exclusion_zone_manager.clear_zones()
				# 전역 영역 저장
				self.exclusion_zone_manager.save_global_zones()
				refresh_list()
				self.draw_bbox()  # 화면 갱신

		def edit_classes():
			"""선택한 영역의 적용 클래스 편집"""
			selection = listbox.curselection()
			if selection:
				index = selection[0]
				zone = self.exclusion_zone_manager.global_zones[index]
				current_class_ids = zone.get('class_ids', [])

				# 클래스 선택 다이얼로그
				new_class_ids = self.select_classes_for_exclusion_zone(
					title=f"영역 {index+1} 클래스 편집",
					initial_class_ids=current_class_ids
				)

				if new_class_ids is not None:  # 취소하지 않은 경우
					self.exclusion_zone_manager.update_zone_classes(index, new_class_ids)
					self.exclusion_zone_manager.save_global_zones()
					refresh_list()
					self.draw_bbox()  # 화면 갱신
					messagebox.showinfo("클래스 편집", "적용 클래스가 업데이트되었습니다.")

		tk.Button(button_frame, text="다각형 추가", command=add_zone, width=12).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="점 추가", command=add_point_zone, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="삭제", command=remove_zone, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="클래스 편집", command=edit_classes, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="활성화/비활성화", command=toggle_zone, width=15).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="모두 삭제", command=clear_all, width=10).pack(side=tk.LEFT, padx=2)

		tk.Button(dialog, text="닫기", command=dialog.destroy, width=10).pack(pady=5)

	def select_classes_for_exclusion_zone(self, title="클래스 선택", initial_class_ids=None):
		"""제외 영역에 적용할 클래스를 선택하는 다이얼로그
		Args:
			title: 다이얼로그 제목
			initial_class_ids: 초기 선택 클래스 ID 리스트
		Returns:
			선택한 클래스 ID 리스트 (취소 시 None)
		"""
		result = {'class_ids': None}

		dialog = tk.Toplevel(self.master)
		dialog.title(title)
		dialog.geometry("500x400")
		dialog.transient(self.master)
		dialog.grab_set()

		# 설명 레이블
		tk.Label(dialog, text="제외 영역에 적용할 클래스를 선택하세요", font=("맑은 고딕", 10, "bold")).pack(pady=10)
		tk.Label(dialog, text="클래스를 선택하지 않으면 모든 클래스에 적용됩니다", fg="blue").pack()

		# 클래스 리스트
		list_frame = tk.LabelFrame(dialog, text="클래스 목록")
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		# 스크롤 가능 프레임
		canvas = tk.Canvas(list_frame)
		scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
		scrollable_frame = tk.Frame(canvas)

		scrollable_frame.bind(
			"<Configure>",
			lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
		)

		canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
		canvas.configure(yscrollcommand=scrollbar.set)

		# 체크박스 변수
		class_check_vars = {}
		initial_class_ids = initial_class_ids if initial_class_ids else []

		for cls in self.class_config_manager.classes:
			class_id = cls['id']
			class_name = cls['name']

			check_var = tk.BooleanVar()
			check_var.set(class_id in initial_class_ids)
			class_check_vars[class_id] = check_var

			chk = tk.Checkbutton(
				scrollable_frame,
				text=f"{class_name} (ID: {class_id})",
				variable=check_var,
				font=("맑은 고딕", 9),
				anchor='w'
			)
			chk.pack(fill=tk.X, padx=5, pady=2)

		canvas.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def on_ok():
			"""확인 버튼"""
			selected_class_ids = [class_id for class_id, var in class_check_vars.items() if var.get()]
			result['class_ids'] = selected_class_ids
			dialog.destroy()

		def on_cancel():
			"""취소 버튼"""
			result['class_ids'] = None
			dialog.destroy()

		def select_all():
			"""전체 선택"""
			for var in class_check_vars.values():
				var.set(True)

		def deselect_all():
			"""전체 해제"""
			for var in class_check_vars.values():
				var.set(False)

		tk.Button(button_frame, text="전체 선택", command=select_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="전체 해제", command=deselect_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="확인", command=on_ok, width=10, bg="lightblue").pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="취소", command=on_cancel, width=10).pack(side=tk.LEFT, padx=2)

		# 모달 대기
		self.master.wait_window(dialog)
		return result['class_ids']

	def manage_class_change_zones(self):
		"""클래스 변경 영역 관리 다이얼로그"""
		dialog = tk.Toplevel(self.master)
		dialog.title("클래스 변경 영역 관리")
		dialog.geometry("820x550")
		dialog.transient(self.master)
		dialog.grab_set()

		# 설명 레이블
		tk.Label(dialog, text="클래스 변경 영역을 관리합니다", font=("맑은 고딕", 10, "bold")).pack(pady=10)
		tk.Label(dialog, text="다각형 영역 또는 기준 점이 닿는 bbox의 클래스를 변경합니다", fg="blue").pack()

		# 영역 리스트
		list_frame = tk.LabelFrame(dialog, text="클래스 변경 영역 목록")
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		scrollbar = tk.Scrollbar(list_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

		listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
		listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		scrollbar.config(command=listbox.yview)

		def refresh_list():
			listbox.delete(0, tk.END)
			for i, zone in enumerate(self.class_change_zone_manager.zones):
				status = "✓" if zone['enabled'] else "✗"
				zone_points = zone.get('points', [])
				point_count = len(zone_points)
				zone_type = zone.get('zone_type', 'point' if point_count == 1 else 'polygon')
				type_label = self._zone_type_label(zone_type)
				mode = zone['mode']
				target_class = self.class_config_manager.get_class_name(zone['target_class_id'])

				if mode == 'all':
					mode_info = f"모든 클래스 → {target_class}"
				else:  # filter
					source_class = self.class_config_manager.get_class_name(zone['source_class_id'])
					mode_info = f"{source_class} → {target_class}"

				listbox.insert(tk.END, f"{status} {type_label} {i+1} ({point_count}개 점) - {mode_info}")

		refresh_list()

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def add_zone_all(zone_type='polygon'):
			"""모든 클래스 변경 영역 추가"""
			# 목표 클래스 선택
			target_class_id = self.select_single_class_dialog("목표 클래스 선택", "모든 클래스를 변경할 목표 클래스를 선택하세요")
			if target_class_id is not None:
				self.start_class_change_zone_drawing(
					{'mode': 'all', 'target_class_id': target_class_id},
					zone_type
				)
				dialog.destroy()

		def add_zone_filter(zone_type='polygon'):
			"""특정 클래스 필터 변경 영역 추가"""
			# 원본 클래스 선택
			source_class_id = self.select_single_class_dialog("원본 클래스 선택", "변경할 원본 클래스를 선택하세요")
			if source_class_id is not None:
				# 목표 클래스 선택
				target_class_id = self.select_single_class_dialog("목표 클래스 선택", "변경할 목표 클래스를 선택하세요")
				if target_class_id is not None:
					self.start_class_change_zone_drawing(
						{
							'mode': 'filter',
							'source_class_id': source_class_id,
							'target_class_id': target_class_id
						},
						zone_type
					)
					dialog.destroy()

		def remove_zone():
			"""선택한 영역 삭제"""
			selection = listbox.curselection()
			if selection:
				index = selection[0]
				self.class_change_zone_manager.remove_zone(index)
				self.class_change_zone_manager.save_zones()
				refresh_list()
				self.draw_bbox()

		def toggle_zone():
			"""선택한 영역 활성화/비활성화"""
			selection = listbox.curselection()
			if selection:
				index = selection[0]
				self.class_change_zone_manager.toggle_zone(index)
				self.class_change_zone_manager.save_zones()
				refresh_list()
				self.draw_bbox()

		def clear_all():
			"""모든 영역 삭제"""
			if messagebox.askyesno("확인", "모든 클래스 변경 영역을 삭제하시겠습니까?"):
				self.class_change_zone_manager.clear_zones()
				self.class_change_zone_manager.save_zones()
				refresh_list()
				self.draw_bbox()

		def apply_now():
			"""현재 페이지에 즉시 적용"""
			if self.class_change_zone_manager.zones:
				original_bbox_count = len(self.bbox)
				self.bbox, changed_count = self.class_change_zone_manager.apply_class_changes(
					self.bbox, class_name, self.zoom_ratio
				)
				if changed_count > 0:
					self.write_bbox()  # 변경 사항 저장
					self.draw_bbox()  # 화면 갱신
					messagebox.showinfo("적용 완료", f"{changed_count}개의 bbox 클래스가 변경되었습니다.")
				else:
					messagebox.showinfo("적용 완료", "변경할 bbox가 없습니다.")
			else:
				messagebox.showwarning("경고", "등록된 클래스 변경 영역이 없습니다.")

		tk.Button(button_frame, text="다각형 추가 (전체)", command=lambda: add_zone_all('polygon'), width=16).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="점 추가 (전체)", command=lambda: add_zone_all('point'), width=14).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="다각형 추가 (필터)", command=lambda: add_zone_filter('polygon'), width=16).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="점 추가 (필터)", command=lambda: add_zone_filter('point'), width=14).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="삭제", command=remove_zone, width=10).pack(side=tk.LEFT, padx=2)

		button_frame2 = tk.Frame(dialog)
		button_frame2.pack(pady=5)
		tk.Button(button_frame2, text="활성화/비활성화", command=toggle_zone, width=15).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame2, text="모두 삭제", command=clear_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame2, text="현재 페이지 적용", command=apply_now, width=15, bg="lightgreen").pack(side=tk.LEFT, padx=2)

		tk.Button(dialog, text="닫기", command=dialog.destroy, width=10).pack(pady=5)

	def select_single_class_dialog(self, title, message):
		"""단일 클래스 선택 다이얼로그
		Args:
			title: 다이얼로그 제목
			message: 설명 메시지
		Returns:
			선택한 클래스 ID (취소 시 None)
		"""
		global class_name
		result = {'class_id': None}

		dialog = tk.Toplevel(self.master)
		dialog.title(title)
		dialog.geometry("400x500")
		dialog.transient(self.master)
		dialog.grab_set()

		tk.Label(dialog, text=message, font=("맑은 고딕", 10, "bold")).pack(pady=10)

		# 클래스 리스트
		list_frame = tk.LabelFrame(dialog, text="클래스 목록")
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		scrollbar = tk.Scrollbar(list_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

		listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, selectmode=tk.SINGLE)
		listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		scrollbar.config(command=listbox.yview)

		# 클래스 목록 채우기
		for class_id, class_name_str in enumerate(class_name):
			listbox.insert(tk.END, f"[{class_id}] {class_name_str}")

		def on_ok():
			selection = listbox.curselection()
			if selection:
				result['class_id'] = selection[0]
				dialog.destroy()
			else:
				messagebox.showwarning("경고", "클래스를 선택하세요.")

		def on_cancel():
			result['class_id'] = None
			dialog.destroy()

		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)
		tk.Button(button_frame, text="확인", command=on_ok, width=10, bg="lightblue").pack(side=tk.LEFT, padx=5)
		tk.Button(button_frame, text="취소", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)

		self.master.wait_window(dialog)
		return result['class_id']

	def manage_auto_delete_classes(self):
		"""클래스 자동 삭제 관리 다이얼로그 (클래스별 개별 모드 설정)"""
		dialog = tk.Toplevel(self.master)
		dialog.title("클래스 자동 삭제 관리")
		dialog.geometry("600x550")
		dialog.transient(self.master)
		dialog.grab_set()

		# 설명 레이블
		tk.Label(dialog, text="클래스별로 자동 삭제 모드를 설정하세요", font=("맑은 고딕", 10, "bold")).pack(pady=10)
		tk.Label(dialog, text="체크박스를 선택하고 각 클래스의 삭제 모드를 선택하세요", fg="blue").pack()

		# 클래스 리스트
		list_frame = tk.LabelFrame(dialog, text="클래스 목록 및 삭제 모드")
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		# 체크박스를 위한 스크롤 가능 프레임
		canvas = tk.Canvas(list_frame)
		scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
		scrollable_frame = tk.Frame(canvas)

		scrollable_frame.bind(
			"<Configure>",
			lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
		)

		canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
		canvas.configure(yscrollcommand=scrollbar.set)

		# 각 클래스에 대한 체크박스 + 모드 선택 라디오 버튼
		class_check_vars = {}  # {class_id: BooleanVar}
		class_mode_vars = {}   # {class_id: StringVar}

		for cls in self.class_config_manager.classes:
			class_id = cls['id']
			class_name = cls['name']

			# 현재 설정 가져오기
			current_mode = self.auto_delete_manager.get_class_mode(class_id)
			is_enabled = current_mode is not None

			# 클래스별 프레임
			class_frame = tk.Frame(scrollable_frame)
			class_frame.pack(fill=tk.X, padx=5, pady=3)

			# 체크박스
			check_var = tk.BooleanVar()
			check_var.set(is_enabled)
			class_check_vars[class_id] = check_var

			chk = tk.Checkbutton(
				class_frame,
				text=f"{class_name} (ID: {class_id})",
				variable=check_var,
				font=("맑은 고딕", 9),
				width=20,
				anchor='w'
			)
			chk.pack(side=tk.LEFT, padx=5)

			# 모드 선택 라디오 버튼
			mode_var = tk.StringVar()
			mode_var.set(current_mode if current_mode else "auto")
			class_mode_vars[class_id] = mode_var

			radio_frame = tk.Frame(class_frame)
			radio_frame.pack(side=tk.LEFT, padx=10)

			tk.Radiobutton(
				radio_frame,
				text="페이지 이동",
				variable=mode_var,
				value="auto",
				font=("맑은 고딕", 8)
			).pack(side=tk.LEFT, padx=2)

			tk.Radiobutton(
				radio_frame,
				text="단축키 'g'",
				variable=mode_var,
				value="shortcut",
				font=("맑은 고딕", 8)
			).pack(side=tk.LEFT, padx=2)

		canvas.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def save_and_close():
			"""설정 저장하고 닫기"""
			# 새로운 설정 적용
			self.auto_delete_manager.delete_class_config.clear()

			for class_id in class_check_vars:
				if class_check_vars[class_id].get():
					# 체크된 경우 모드와 함께 저장
					mode = class_mode_vars[class_id].get()
					self.auto_delete_manager.delete_class_config[class_id] = mode

			self.auto_delete_manager.save_config()

			# 결과 메시지
			if self.auto_delete_manager.delete_class_config:
				summary_lines = []
				auto_classes = []
				shortcut_classes = []

				for class_id, mode in self.auto_delete_manager.delete_class_config.items():
					if class_id < len(self.class_config_manager.classes):
						class_name = self.class_config_manager.classes[class_id]['name']
						if mode == "auto":
							auto_classes.append(class_name)
						else:
							shortcut_classes.append(class_name)

				if auto_classes:
					summary_lines.append(f"[페이지 이동 시 자동 삭제]\n  " + ", ".join(auto_classes))
				if shortcut_classes:
					summary_lines.append(f"[단축키 'g' 입력 시 삭제]\n  " + ", ".join(shortcut_classes))

				messagebox.showinfo("저장 완료", "클래스별 자동 삭제 설정이 완료되었습니다.\n\n" + "\n\n".join(summary_lines))
			else:
				messagebox.showinfo("저장 완료", "자동 삭제 클래스가 없습니다.")

			dialog.destroy()

		def select_all():
			"""모두 선택"""
			for var in class_check_vars.values():
				var.set(True)

		def deselect_all():
			"""모두 선택 해제"""
			for var in class_check_vars.values():
				var.set(False)

		tk.Button(button_frame, text="모두 선택", command=select_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="모두 해제", command=deselect_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="저장", command=save_and_close, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="취소", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=2)

	def manual_delete_auto_classes(self):
		"""단축키 'g'로 수동 삭제 실행 (mode="shortcut"인 클래스만 삭제)"""
		if not self.auto_delete_manager or not self.auto_delete_manager.delete_class_config:
			print("[AutoDelete] 자동 삭제 설정이 없습니다.")
			messagebox.showinfo("자동 삭제", "자동 삭제 설정이 없습니다.")
			return

		# mode="shortcut"인 클래스가 있는지 확인
		shortcut_classes = [class_id for class_id, mode in self.auto_delete_manager.delete_class_config.items() if mode == "shortcut"]
		if not shortcut_classes:
			print("[AutoDelete] 단축키 삭제 모드로 설정된 클래스가 없습니다.")
			messagebox.showinfo("자동 삭제", "단축키 'g' 모드로 설정된 클래스가 없습니다.\n자동삭제 설정에서 모드를 변경하세요.")
			return

		before_count = len(self.bbox)
		# class_name은 전역 변수
		global class_name
		# mode_filter="shortcut"으로 단축키 모드 클래스만 필터링
		self.bbox = self.auto_delete_manager.filter_bboxes(self.bbox, class_name, mode_filter="shortcut")
		deleted_count = before_count - len(self.bbox)

		if deleted_count > 0:
			print(f"[AutoDelete] {deleted_count}개 라벨 삭제됨 (단축키 'g' 입력)")
			# bbox 저장 및 화면 갱신
			self.write_bbox()
			self.draw_bbox()
			messagebox.showinfo("자동 삭제", f"{deleted_count}개 라벨이 삭제되었습니다.")
		else:
			print("[AutoDelete] 삭제할 라벨이 없습니다.")
			messagebox.showinfo("자동 삭제", "삭제할 대상이 없습니다.")

	def change_class_config(self):
		"""클래스 설정 변경"""
		print(f"[DEBUG] change_class_config 호출")
		print(f"[DEBUG] self.class_config_manager: {self.class_config_manager}")
		print(f"[DEBUG] self.class_config_manager.base_dir: {self.class_config_manager.base_dir}")

		# 현재 설정을 기반으로 다이얼로그 표시
		dialog = ClassConfigDialog(self.master, self.class_config_manager)
		print(f"[DEBUG] ClassConfigDialog 생성 완료")

		# 현재 파일명 설정
		current_filename = self.class_config_manager.get_config_filename().replace('.json', '')
		dialog.filename_entry.delete(0, tk.END)
		dialog.filename_entry.insert(0, current_filename)

		# 기존 설정으로 초기화
		for i, entry in enumerate(dialog.class_entries):
			if i < len(self.class_config_manager.classes):
				cls = self.class_config_manager.classes[i]
				entry['name'].delete(0, tk.END)
				entry['name'].insert(0, cls['name'])
				entry['key'].delete(0, tk.END)
				if cls.get('key'):
					entry['key'].insert(0, cls['key'])
				entry['color'].set(cls['color'])

		classes, config_filename, enable_backup = dialog.show()

		if classes is not None:
			# 설정 저장
			self.class_config_manager.save_config(classes, config_filename, enable_backup)
			self.apply_class_config_runtime()
			backup_status = "활성화" if enable_backup else "비활성화"
			messagebox.showinfo("클래스 설정 변경",
				f"클래스 설정이 저장되고 즉시 적용되었습니다.\n설정 파일: {self.class_config_manager.config_file}\n백업 설정: {backup_status}")

	def apply_class_config_runtime(self):
		"""Apply class names, colors, buttons, and shortcuts without restarting."""
		global class_name, class_color
		class_name = self.class_config_manager.get_class_names()
		class_color = self.class_config_manager.get_class_colors()

		for button in list(getattr(self, 'class_buttons', [])):
			try:
				button.destroy()
			except Exception:
				pass
		self.class_buttons = []
		self.button_class_map = {}
		self.key_button_map = {}

		for name, class_id, key in self.class_config_manager.get_button_configs():
			button = self.create_class_button(name, class_id, key)
			self.class_buttons.append(button)

		if hasattr(self, 'canvas'):
			self.bind_class_shortcuts()
			self.canvas.focus_set()
		if hasattr(self, 'configFileLabel'):
			self.configFileLabel.config(text=f"[{self.class_config_manager.get_config_filename()}]")
		if hasattr(self, 'class_filter_manager'):
			self.class_filter_manager.clear_filter()
		if hasattr(self, 'bbox'):
			for bbox in self.bbox:
				if len(bbox) > 2 and isinstance(bbox[2], int) and 0 <= bbox[2] < len(class_name):
					bbox[1] = class_name[bbox[2]]
		try:
			self.apply_modern_theme()
			self.draw_bbox()
			self.update_label_list()
		except Exception as e:
			print(f"[ClassConfig] Runtime refresh warning: {e}")

	def manage_class_filter(self):
		"""클래스 필터 관리 다이얼로그"""
		dialog = tk.Toplevel(self.master)
		dialog.title("클래스 필터 설정")
		dialog.geometry("500x550")
		dialog.transient(self.master)
		dialog.grab_set()

		# 설명 레이블
		tk.Label(dialog, text="화면에 표시할 클래스를 선택하세요", font=("맑은 고딕", 10, "bold")).pack(pady=10)
		tk.Label(dialog, text="체크된 클래스만 화면에 표시됩니다 (저장되는 파일에는 영향 없음)", fg="blue").pack()

		# 클래스 리스트
		list_frame = tk.LabelFrame(dialog, text="클래스 목록")
		list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

		# 체크박스를 위한 스크롤 가능 프레임
		canvas = tk.Canvas(list_frame)
		scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
		scrollable_frame = tk.Frame(canvas)

		scrollable_frame.bind(
			"<Configure>",
			lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
		)

		canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
		canvas.configure(yscrollcommand=scrollbar.set)

		# 각 클래스에 대한 체크박스
		class_check_vars = {}  # {class_id: BooleanVar}

		# 현재 필터 설정 가져오기
		current_visible_classes = self.class_filter_manager.get_visible_classes()
		filter_active = self.class_filter_manager.is_filter_active()

		for cls in self.class_config_manager.classes:
			class_id = cls['id']
			class_name_str = cls['name']

			# 현재 필터가 활성화되어 있으면 현재 필터 설정을 따르고,
			# 비활성화되어 있으면 모두 선택
			is_checked = class_id in current_visible_classes if filter_active else True

			# 체크박스
			check_var = tk.BooleanVar()
			check_var.set(is_checked)
			class_check_vars[class_id] = check_var

			chk = tk.Checkbutton(
				scrollable_frame,
				text=f"{class_name_str} (ID: {class_id})",
				variable=check_var,
				font=("맑은 고딕", 9),
				anchor='w'
			)
			chk.pack(fill=tk.X, padx=10, pady=2)

		canvas.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def apply_filter():
			"""필터 적용"""
			selected_classes = [class_id for class_id, var in class_check_vars.items() if var.get()]

			# 디버깅: 사용자가 선택한 클래스 출력
			print(f"\n[FILTER DEBUG] ===== apply_filter() called =====")
			print(f"[FILTER DEBUG] User selected {len(selected_classes)} classes:")
			for cid in sorted(selected_classes):
				cname = self.class_config_manager.get_class_name(cid)
				print(f"[FILTER DEBUG]   - class_id={cid}, class_name={cname}")

			if not selected_classes:
				messagebox.showwarning("경고", "최소 1개 이상의 클래스를 선택해야 합니다.")
				return

			# 필터 적용
			self.class_filter_manager.set_visible_classes(selected_classes)

			# 화면 갱신
			self.draw_bbox()
			self.update_label_list()

			# 결과 메시지
			class_names = [self.class_config_manager.get_class_name(cid) for cid in selected_classes]
			messagebox.showinfo("필터 적용", f"선택된 {len(selected_classes)}개 클래스만 표시됩니다:\n\n" + ", ".join(class_names))
			dialog.destroy()

		def reset_filter():
			"""필터 초기화 (전체 표시)"""
			self.class_filter_manager.clear_filter()
			self.draw_bbox()
			self.update_label_list()
			messagebox.showinfo("필터 초기화", "모든 클래스가 표시됩니다.")
			dialog.destroy()

		def select_all():
			"""모두 선택"""
			for var in class_check_vars.values():
				var.set(True)

		def deselect_all():
			"""모두 선택 해제"""
			for var in class_check_vars.values():
				var.set(False)

		tk.Button(button_frame, text="모두 선택", command=select_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="모두 해제", command=deselect_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="적용", command=apply_filter, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="초기화", command=reset_filter, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="닫기", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=2)

	def on_slider_change(self, value):
		if not self.imlist: return
    # 슬라이더 값을 정수로 변환하고 0-인덱스로 조정
		new_index = int(float(value)) - 1

		if new_index != self.ci:
			self.ci = new_index
			if self.ci >= len(self.imlist):
				self.ci = len(self.imlist) - 1
			if self.ci < 0:
				self.ci = 0

			self.write_bbox()
			self.draw_image()

	# show_class_menu 중복 함수 제거됨 (원본은 6078번 줄에 있음)

	def set_button_class(self, button, class_idx):
		if 0 <= class_idx < len(class_name):
			# 버튼 텍스트 변경
			button.config(text=class_name[class_idx])
			
			# 버튼 명령 업데이트 - 클래스 인덱스를 직접 전달
			button.config(command=partial(self.change_class, class_idx))
			
			# 우클릭 이벤트 업데이트
			button.bind("<Button-3>", lambda event: self.show_class_menu(event, button, class_idx))
			self.button_class_map[button] = class_idx


	def implement_multi_class_selection(self):
		"""Adds multi-class selection functionality to the tool"""
		
		# Create a new top-level window for multi-class selection
		multi_class_window = tk.Toplevel(self.master)
		multi_class_window.title("Multi-Class Selection")
		multi_class_window.geometry("400x500")
		multi_class_window.transient(self.master)
		
		# Add explanation label
		explanation = tk.Label(multi_class_window, text="Select multiple classes for batch operations")
		explanation.pack(pady=10)
		
		# Frame for checkboxes with scrollbar
		checkbox_frame = tk.Frame(multi_class_window)
		checkbox_frame.pack(fill="both", expand=True, padx=10, pady=5)
		
		# Add scrollbar
		scrollbar = tk.Scrollbar(checkbox_frame)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
		
		# Canvas for scrolling
		canvas = tk.Canvas(checkbox_frame, yscrollcommand=scrollbar.set)
		canvas.pack(side=tk.LEFT, fill="both", expand=True)
		
		scrollbar.config(command=canvas.yview)
		
		# Frame inside canvas for checkboxes
		class_frame = tk.Frame(canvas)
		canvas.create_window((0, 0), window=class_frame, anchor="nw")
		
		# Create variables and checkboxes for each class
		class_vars = {}
		for i, cls in enumerate(class_name):
			var = tk.BooleanVar(value=False)
			class_vars[i] = var
			
			cb = tk.Checkbutton(class_frame, text=f"{i}: {cls}", variable=var)
			cb.grid(row=i//2, column=i%2, sticky="w", padx=5, pady=2)
		
		# Update scroll region when frame size changes
		class_frame.update_idletasks()
		canvas.config(scrollregion=canvas.bbox("all"))
		
		# Action buttons
		button_frame = tk.Frame(multi_class_window)
		button_frame.pack(fill="x", pady=10)
		
		# Add action buttons based on different operations
		select_all_btn = tk.Button(button_frame, text="Select All", 
								command=lambda: [var.set(True) for var in class_vars.values()])
		select_all_btn.pack(side=tk.LEFT, padx=5)
		
		deselect_all_btn = tk.Button(button_frame, text="Deselect All", 
								command=lambda: [var.set(False) for var in class_vars.values()])
		deselect_all_btn.pack(side=tk.LEFT, padx=5)
		
		# Operation buttons
		operation_frame = tk.Frame(multi_class_window)
		operation_frame.pack(fill="x", pady=10, padx=10)
		
		# Function to get selected class IDs
		def get_selected_classes():
			return [class_id for class_id, var in class_vars.items() if var.get()]
		
		# Batch delete button - removes all bounding boxes of selected classes
		delete_btn = tk.Button(operation_frame, text="Delete Selected Classes", 
							command=lambda: self.delete_selected_classes(get_selected_classes(), multi_class_window))
		delete_btn.pack(side=tk.LEFT, padx=5)
		
		# Batch copy button - batch copy operation for selected classes
		copy_btn = tk.Button(operation_frame, text="Copy Selected Classes", 
						command=lambda: self.copy_selected_classes(get_selected_classes(), multi_class_window))
		copy_btn.pack(side=tk.LEFT, padx=5)
		
		# Close button
		close_btn = tk.Button(multi_class_window, text="Close", command=multi_class_window.destroy)
		close_btn.pack(pady=10)
		
		return multi_class_window

	# Implementation of supporting methods
	def delete_selected_classes(self, selected_classes, window=None):
		"""Deletes all bounding boxes of the selected classes in the current image"""
		if not selected_classes:
			messagebox.showinfo("Information", "No classes selected")
			return
		
		# Store indices of bboxes to remove (in reverse order to avoid index shifting)
		to_remove = []
		for i, bbox in enumerate(self.bbox):
			if class_name.index(bbox[1]) in selected_classes:
				to_remove.append(i)
		
		# Remove in reverse order
		for idx in sorted(to_remove, reverse=True):
			self.bbox.pop(idx)
			if self.selid == idx:
				self.selid = -1
			elif self.selid > idx:
				self.selid -= 1
		
		# Update display
		self.write_bbox()
		self.draw_bbox()
		
		messagebox.showinfo("Success", f"Removed {len(to_remove)} bounding boxes of selected classes")
		if window:
			window.focus_set()

	def copy_selected_classes(self, selected_classes, window=None):
		"""Opens dialog to copy selected classes to a range of images"""
		if not selected_classes:
			messagebox.showinfo("Information", "No classes selected")
			return
		
		# Create a dialog for range selection
		range_dialog = tk.Toplevel(self.master)
		range_dialog.title("Copy Selected Classes")
		range_dialog.geometry("300x150")
		range_dialog.transient(self.master)
		
		# Range selection widgets
		frame = tk.Frame(range_dialog, padx=10, pady=10)
		frame.pack(fill="both", expand=True)
		
		tk.Label(frame, text="Start Frame:").grid(row=0, column=0, sticky="w", pady=5)
		start_entry = tk.Entry(frame, width=10)
		start_entry.grid(row=0, column=1, sticky="w", pady=5)
		start_entry.insert(0, "1")
		
		tk.Label(frame, text="End Frame:").grid(row=1, column=0, sticky="w", pady=5)
		end_entry = tk.Entry(frame, width=10)
		end_entry.grid(row=1, column=1, sticky="w", pady=5)
		end_entry.insert(0, str(len(self.imlist)))
		
		# Operation modes
		replace_var = tk.BooleanVar(value=False)
		replace_cb = tk.Checkbutton(frame, text="Replace existing annotations", variable=replace_var)
		replace_cb.grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
		
		# Execute function
		def execute_copy():
			try:
				start_frame = int(start_entry.get())
				end_frame = int(end_entry.get())
				
				if start_frame < 1 or end_frame > len(self.imlist) or start_frame > end_frame:
					messagebox.showerror("Error", f"Frame range must be between 1 and {len(self.imlist)}")
					return
				
				# Store current annotations to copy
				annotations_to_copy = []
				for bbox in self.bbox:
					if class_name.index(bbox[1]) in selected_classes:
						annotations_to_copy.append(bbox)
				
				if not annotations_to_copy:
					messagebox.showinfo("Information", "No annotations to copy for selected classes")
					return
				
				# Backup current selection
				current_idx = self.ci
				
				# Progress dialog
				progress = tk.Toplevel(range_dialog)
				progress.title("Copying...")
				progress.geometry("300x80")
				progress.transient(range_dialog)
				
				progress_label = tk.Label(progress, text="Processing...")
				progress_label.pack(pady=5)
				
				progress_bar = ttk.Progressbar(progress, orient="horizontal", length=250, mode="determinate")
				progress_bar.pack(pady=10)
				progress_bar["maximum"] = end_frame - start_frame + 1
				
				# Process each frame
				success_count = 0
				for i in range(start_frame - 1, end_frame):
					# Skip current image
					if i == current_idx:
						continue
					
					progress_bar["value"] = i - (start_frame - 1) + 1
					progress_label.config(text=f"Processing frame {i+1}/{end_frame}...")
					self.master.update()
					
					try:
						# Get target label file path
						target_img_path = self.imlist[i]
						target_label_path = image_to_label_path(target_img_path)
						
						# Create directory if needed
						target_dir = os.path.dirname(target_label_path)
						if not os.path.exists(target_dir):
							os.makedirs(target_dir)
						
						# Read existing annotations if not replacing
						existing_annotations = []
						if not replace_var.get() and os.path.exists(target_label_path):
							with open(target_label_path, 'r') as f:
								for line in f:
									values = line.strip().split()
									if len(values) >= 5:
										class_id = int(float(values[0]))
										# Keep only annotations not in selected classes
										if class_id not in selected_classes:
											existing_annotations.append(line)
						
						output_lines = list(existing_annotations)
						for bbox in annotations_to_copy:
							rel_coords = self.convert_abs2rel(bbox)
							output_lines.append(' '.join(str(e) for e in rel_coords) + '\n')
						if not self.write_text_files_transaction({target_label_path: ''.join(output_lines)}, backup_category='labels'):
							print(f"Error processing frame {i+1}: transaction failed")
							continue

						success_count += 1
						
					except Exception as e:
						print(f"Error processing frame {i+1}: {e}")
				
				progress.destroy()
				messagebox.showinfo("Success", f"Copied annotations to {success_count} frames")
				range_dialog.destroy()
				
			except ValueError:
				messagebox.showerror("Error", "Please enter valid numbers for start and end frames")
		
		# Button frame
		btn_frame = tk.Frame(frame)
		btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
		
		execute_btn = tk.Button(btn_frame, text="Execute", command=execute_copy)
		execute_btn.pack(side=tk.LEFT, padx=5)
		
		cancel_btn = tk.Button(btn_frame, text="Cancel", command=range_dialog.destroy)
		cancel_btn.pack(side=tk.LEFT, padx=5)
		
		if window:
			window.focus_set()
	def copy_selected_label(self, event=None):
		"""현재 선택된 라벨을 복사합니다."""
		if self.selid < 0 or len(self.bbox) == 0:
			messagebox.showwarning("경고", "복사할 라벨이 선택되지 않았습니다. 먼저 라벨을 선택해주세요.")
			return

		# 현재 선택된 라벨을 원본 좌표로 변환하여 복사 (줌 비율 고려)
		selected_bbox = self.bbox[self.selid]

		# bbox를 원본 좌표로 변환 (화면 좌표 / zoom_ratio)
		original_bbox = [
			selected_bbox[0],  # sel
			selected_bbox[1],  # clsname
			selected_bbox[2],  # info (class_id)
			selected_bbox[3] / self.zoom_ratio,  # x1 (원본)
			selected_bbox[4] / self.zoom_ratio,  # y1 (원본)
			selected_bbox[5] / self.zoom_ratio,  # x2 (원본)
			selected_bbox[6] / self.zoom_ratio   # y2 (원본)
		]

		self.copied_label = copy.deepcopy(original_bbox)

		# 사용자에게 피드백 제공
		label_class = self.copied_label[1]
		bbox_width = int((self.copied_label[5] - self.copied_label[3]) * self.zoom_ratio)
		bbox_height = int((self.copied_label[6] - self.copied_label[4]) * self.zoom_ratio)

		# 임시 메시지 표시 (캔버스에)
		self.canvas.delete("copy_message")
		self.canvas.create_text(
			self.imsize[0] // 2, 20,
			text=f"라벨 복사됨: {label_class} ({bbox_width}x{bbox_height})",
			fill="white", font=("Arial", 12), tags="copy_message"
		)

		# 잠시 후 메시지 삭제
		self.master.after(1500, lambda: self.canvas.delete("copy_message"))

	def paste_label(self, event=None):
		"""복사된 라벨을 현재 프레임에 붙여넣습니다."""
		if self.copied_label is None:
			messagebox.showwarning("경고", "붙여넣을 라벨이 없습니다. 먼저 라벨을 복사해주세요.")
			return

		# 원본 좌표를 현재 줌 비율로 변환 (원본 좌표 * zoom_ratio)
		screen_bbox = [
			self.copied_label[0],  # sel
			self.copied_label[1],  # clsname
			self.copied_label[2],  # info (class_id)
			self.copied_label[3] * self.zoom_ratio,  # x1 (화면)
			self.copied_label[4] * self.zoom_ratio,  # y1 (화면)
			self.copied_label[5] * self.zoom_ratio,  # x2 (화면)
			self.copied_label[6] * self.zoom_ratio   # y2 (화면)
		]

		# 자동 필터링 충돌 확인 (화면 좌표 사용)
		warning_messages = []

		# 1. 자동 삭제 클래스 확인
		if self.auto_delete_manager and self.auto_delete_manager.delete_class_config:
			global class_name
			class_id = int(screen_bbox[2])
			if class_id in self.auto_delete_manager.delete_class_config:
				class_str = class_name[class_id] if class_id < len(class_name) else str(class_id)
				warning_messages.append(f"자동 삭제 대상 클래스: {class_str}")

		# 2. 제외 영역 확인 (화면 좌표 사용)
		if self.exclusion_zone_enabled and self.exclusion_zone_manager:
			if self.exclusion_zone_manager.is_bbox_in_exclusion_zone(screen_bbox, zoom_ratio=self.zoom_ratio):
				warning_messages.append("제외 영역 내 라벨")

		# 경고가 있으면 사용자에게 확인
		if warning_messages:
			warning_text = "\n".join(warning_messages)
			msg = f"⚠️ 붙여넣을 라벨이 자동 필터링 대상입니다:\n\n{warning_text}\n\n다음 페이지로 이동 시 자동으로 삭제됩니다.\n계속하시겠습니까?"
			if not messagebox.askyesno("자동 필터링 경고", msg):
				return

		# 화면 좌표로 변환된 라벨을 사용
		new_label = copy.deepcopy(screen_bbox)

		# 선택 상태 초기화 (모든 라벨 선택 해제)
		for rc in self.bbox:
			rc[0] = False

		# 새 라벨 추가하고 선택
		new_label[0] = True  # 선택 상태로 설정
		self.bbox.append(new_label)
		self.selid = len(self.bbox) - 1
		self.pre_rc = None  # 방향키 이동을 위해 pre_rc 초기화

		# 파일에 저장 (중요!)
		self.write_bbox()

		# 화면 갱신
		self.draw_bbox()

		# 임시 메시지 표시
		self.canvas.delete("paste_message")
		self.canvas.create_text(
			self.imsize[0] // 2, 20,
			text=f"라벨 붙여넣기 완료: {new_label[1]}",
			fill="white", font=("Arial", 12), tags="paste_message"
		)

		# 잠시 후 메시지 삭제
		self.master.after(1500, lambda: self.canvas.delete("paste_message"))
	def get_default_class_for_new_bbox(self):
		"""새 바운딩 박스를 생성할 때 사용할 기본 클래스 인덱스를 반환합니다."""
		# key_button_map에서 '1' 키에 매핑된 버튼 찾기
		if '1' in self.key_button_map:
			button = self.key_button_map['1']
			if button in self.button_class_map:
				return self.button_class_map[button]
		
		# '1' 키 매핑이 없거나 문제가 있으면 첫 번째 버튼의 클래스 사용
		if self.button_class_map:
			first_button = next(iter(self.button_class_map))
			return self.button_class_map[first_button]
		
		# 모든 매핑이 없으면 0번 클래스 사용 (기존 동작)
		return 0

	def get_default_class_name_for_new_bbox(self):
		"""새 바운딩 박스를 생성할 때 사용할 기본 클래스 이름을 반환합니다."""
		class_idx = self.get_default_class_for_new_bbox()
		return class_name[class_idx] if class_idx < len(class_name) else class_name[0]
	def toggle_multi_select_mode(self, event=None):
		"""다중 선택 모드 토글"""
		self.multi_select_mode = not self.multi_select_mode

		if not self.multi_select_mode:
			# 다중 선택 모드 해제 시 선택 해제
			self.multi_selected.clear()

		# UI 업데이트 (간결하게)
		bg_color = "lightblue" if self.multi_select_mode else "lightgray"
		self.multi_mode_btn.config(bg=bg_color)

		self.update_multi_info()
		self.draw_bbox()

	def toggle_multi_selection(self, index):
		"""특정 라벨의 다중 선택 상태 토글"""
		if index in self.multi_selected:
			self.multi_selected.remove(index)
		else:
			self.multi_selected.add(index)
		
		self.update_multi_info()
		self.draw_bbox()

	def update_multi_info(self):
		"""다중 선택 정보 표시 업데이트 (간결하게)"""
		count = len(self.multi_selected)
		if count > 0:
			self.multi_info_label.config(text=f"({count}개)")
		else:
			self.multi_info_label.config(text="")

	def copy_multi_selected(self, event=None):
		"""다중 선택된 라벨들을 복사"""
		if not self.multi_selected:
			messagebox.showwarning("경고", "다중 선택된 라벨이 없습니다.")
			return

		# 선택된 라벨들을 원본 좌표로 변환하여 복사 (줌 비율 고려)
		self.copied_multi_labels = []
		for idx in sorted(self.multi_selected):
			if idx < len(self.bbox):
				selected_bbox = self.bbox[idx]

				# bbox를 원본 좌표로 변환 (화면 좌표 / zoom_ratio)
				original_bbox = [
					selected_bbox[0],  # sel
					selected_bbox[1],  # clsname
					selected_bbox[2],  # info (class_id)
					selected_bbox[3] / self.zoom_ratio,  # x1 (원본)
					selected_bbox[4] / self.zoom_ratio,  # y1 (원본)
					selected_bbox[5] / self.zoom_ratio,  # x2 (원본)
					selected_bbox[6] / self.zoom_ratio   # y2 (원본)
				]

				self.copied_multi_labels.append(copy.deepcopy(original_bbox))

		# 피드백 메시지
		count = len(self.copied_multi_labels)
		self.canvas.delete("copy_message")
		self.canvas.create_text(
			self.imsize[0] // 2, 20,
			text=f"다중 라벨 복사됨: {count}개",
			fill="white", font=("Arial", 12), tags="copy_message"
		)
		self.master.after(1500, lambda: self.canvas.delete("copy_message"))

	def paste_multi_selected(self, event=None):
		"""복사된 다중 라벨들을 붙여넣기"""
		if not hasattr(self, 'copied_multi_labels') or not self.copied_multi_labels:
			messagebox.showwarning("경고", "붙여넣을 다중 라벨이 없습니다.")
			return

		# 원본 좌표를 현재 줌 비율로 변환 (원본 좌표 * zoom_ratio)
		screen_bboxes = []
		for label in self.copied_multi_labels:
			screen_bbox = [
				label[0],  # sel
				label[1],  # clsname
				label[2],  # info (class_id)
				label[3] * self.zoom_ratio,  # x1 (화면)
				label[4] * self.zoom_ratio,  # y1 (화면)
				label[5] * self.zoom_ratio,  # x2 (화면)
				label[6] * self.zoom_ratio   # y2 (화면)
			]
			screen_bboxes.append(screen_bbox)

		# 자동 필터링 충돌 확인 (화면 좌표 사용)
		warning_messages = []

		# 1. 자동 삭제 클래스 확인
		if self.auto_delete_manager and self.auto_delete_manager.delete_class_config:
			global class_name
			filtered_labels = []
			for bbox in screen_bboxes:
				class_id = int(bbox[2])
				if class_id in self.auto_delete_manager.delete_class_config:
					class_str = class_name[class_id] if class_id < len(class_name) else str(class_id)
					filtered_labels.append(class_str)

			if filtered_labels:
				warning_messages.append(f"자동 삭제 대상 클래스: {', '.join(filtered_labels)}")

		# 2. 제외 영역 확인 (화면 좌표 사용)
		if self.exclusion_zone_enabled and self.exclusion_zone_manager:
			in_exclusion_count = 0
			for bbox in screen_bboxes:
				if self.exclusion_zone_manager.is_bbox_in_exclusion_zone(bbox, zoom_ratio=self.zoom_ratio):
					in_exclusion_count += 1

			if in_exclusion_count > 0:
				warning_messages.append(f"제외 영역 내 라벨: {in_exclusion_count}개")

		# 경고가 있으면 사용자에게 확인
		if warning_messages:
			warning_text = "\n".join(warning_messages)
			msg = f"⚠️ 붙여넣을 라벨이 자동 필터링 대상입니다:\n\n{warning_text}\n\n다음 페이지로 이동 시 자동으로 삭제됩니다.\n계속하시겠습니까?"
			if not messagebox.askyesno("자동 필터링 경고", msg):
				return

		# 모든 라벨 선택 해제
		for rc in self.bbox:
			rc[0] = False

		# 화면 좌표로 변환된 라벨들 추가
		for screen_bbox in screen_bboxes:
			new_label = copy.deepcopy(screen_bbox)
			new_label[0] = False  # 선택 해제 상태로 추가
			self.bbox.append(new_label)

		# 파일에 저장 (중요!)
		self.write_bbox()

		self.draw_bbox()

		# 피드백 메시지
		count = len(screen_bboxes)
		self.canvas.delete("paste_message")
		self.canvas.create_text(
			self.imsize[0] // 2, 20,
			text=f"다중 라벨 붙여넣기 완료: {count}개",
			fill="white", font=("Arial", 12), tags="paste_message"
		)
		self.master.after(1500, lambda: self.canvas.delete("paste_message"))

	def select_all_labels(self, event=None):
		"""모든 라벨을 다중 선택"""
		self.multi_selected = set(range(len(self.bbox)))
		self.update_multi_info()
		self.draw_bbox()

	def clear_multi_selection(self, event=None):
		"""다중 선택 해제"""
		self.multi_selected.clear()
		self.update_multi_info()
		self.draw_bbox()
	def move_to_page(self):
		"""입력된 페이지 번호로 이동"""
		try:
			target_page = int(self.page_entry.get())
		except ValueError:
			messagebox.showerror("오류", "페이지 번호는 숫자여야 합니다.")
			return
		
		# 페이지 범위 검증
		if target_page < 1 or target_page > len(self.imlist):
			messagebox.showerror("오류", f"페이지 범위는 1에서 {len(self.imlist)} 사이여야 합니다.")
			return
		
		# 현재 편집 내용 저장
		self.write_bbox()
		
		# 페이지 이동
		self.ci = target_page - 1
		
		# 슬라이더 업데이트
		self.img_slider.set(self.ci + 1)
		self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
		
		# 이미지 다시 로드
		self.draw_image()
		
		# 입력 필드 초기화
		self.page_entry.delete(0, tk.END)
def main():
    print("objmk version 2017-10-27")
    wdir = sys.argv[1] if len(sys.argv) == 2 else None
    # RemoveDefaultdll.exe 실행은 여기서 한 번만 실행
    try:
        os.startfile(BASE_DIR + "RemoveDefaultdll.exe")
    except (OSError, PermissionError) as e:
        # UAC 거부 또는 권한 문제 시 무시하고 계속 진행
        print(f"RemoveDefaultdll.exe 실행 실패 (무시됨): {e}")
    app = MainApp(wdir)
    return

if __name__=="__main__":
    # 여기서 RemoveDefaultdll.exe 실행 코드 제거
    # os.startfile(BASE_DIR + "RemoveDefaultdll.exe") <- 이 줄 제거
    main()
    sys.exit(0)
