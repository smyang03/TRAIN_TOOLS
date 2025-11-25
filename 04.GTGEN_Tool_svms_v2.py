#!/usr/bin/env python
from ast import dump
import os
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

	def add_zone(self, points, use_global=True):
		"""새로운 제외 영역 추가 (points는 [(x,y), ...] 형태)"""
		if len(points) >= 3:  # 최소 3개의 점이 있어야 폴리곤 형성
			zone = {'points': points, 'enabled': True}
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

	def clear_zones(self):
		"""모든 제외 영역 삭제"""
		self.global_zones = []

	def is_bbox_in_exclusion_zone(self, bbox):
		"""bbox가 제외 영역과 겹치는지 확인
		Args:
			bbox: [sel, clsname, info, x1, y1, x2, y2] 형태
		Returns:
			bool: 겹치면 True
		"""
		zones_to_check = self.global_zones if self.use_global else self.zones
		if not zones_to_check:
			return False

		x1, y1, x2, y2 = bbox[3], bbox[4], bbox[5], bbox[6]
		bbox_center = ((x1 + x2) / 2, (y1 + y2) / 2)

		for zone in zones_to_check:
			if zone['enabled'] and self._point_in_polygon(bbox_center, zone['points']):
				return True
		return False

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
					self.global_zones = json.load(f)
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

# 클래스 자동 삭제 관리 클래스
class AutoDeleteClassManager:
	"""특정 클래스를 자동으로 삭제하는 기능을 관리하는 클래스"""

	def __init__(self, base_dir=None):
		self.base_dir = base_dir or os.getcwd()
		self.config_file = os.path.join(self.base_dir, ".auto_delete_classes.json")
		self.delete_class_ids = set()  # 자동 삭제할 클래스 ID 집합
		self.load_config()

	def add_class(self, class_id):
		"""자동 삭제 대상에 클래스 추가"""
		self.delete_class_ids.add(class_id)
		self.save_config()

	def remove_class(self, class_id):
		"""자동 삭제 대상에서 클래스 제거"""
		self.delete_class_ids.discard(class_id)
		self.save_config()

	def toggle_class(self, class_id):
		"""클래스 자동 삭제 토글"""
		if class_id in self.delete_class_ids:
			self.delete_class_ids.remove(class_id)
		else:
			self.delete_class_ids.add(class_id)
		self.save_config()

	def is_class_marked_for_deletion(self, class_id):
		"""해당 클래스가 자동 삭제 대상인지 확인"""
		return class_id in self.delete_class_ids

	def filter_bboxes(self, bbox_list, class_name_list):
		"""bbox 리스트에서 자동 삭제 대상 클래스 제거
		Args:
			bbox_list: bbox 리스트 ([sel, clsname, info, x1, y1, x2, y2] 형태)
			class_name_list: 클래스 이름 리스트 (전역 class_name)
		Returns:
			filtered_list: 필터링된 bbox 리스트
		"""
		if not self.delete_class_ids:
			return bbox_list

		# bbox[1]에서 클래스 이름을 가져와서 class_id로 변환
		filtered = []
		for bbox in bbox_list:
			class_name_str = bbox[1]  # 클래스 이름 (문자열)
			try:
				# 클래스 이름을 인덱스(class_id)로 변환
				class_id = class_name_list.index(class_name_str)
				# 삭제 대상이 아니면 유지
				if class_id not in self.delete_class_ids:
					filtered.append(bbox)
			except ValueError:
				# 클래스 이름을 찾을 수 없으면 유지
				print(f"[WARNING] Unknown class name: {class_name_str}, keeping bbox")
				filtered.append(bbox)

		return filtered

	def save_config(self):
		"""설정을 파일로 저장"""
		try:
			with open(self.config_file, 'w') as f:
				json.dump(list(self.delete_class_ids), f)
		except Exception as e:
			print(f"[ERROR] Failed to save auto delete config: {e}")

	def load_config(self):
		"""설정을 파일에서 로드"""
		if os.path.exists(self.config_file):
			try:
				with open(self.config_file, 'r') as f:
					self.delete_class_ids = set(json.load(f))
			except Exception as e:
				print(f"[ERROR] Failed to load auto delete config: {e}")
				self.delete_class_ids = set()

# 클래스 설정 관리 클래스
class ClassConfigManager:
	def __init__(self, config_file="class_config.json"):
		# 현재 작업 디렉토리를 기준으로 설정 파일 저장/로드
		self.base_dir = os.getcwd()
		self.config_file = os.path.join(self.base_dir, config_file)
		self.last_config_file = os.path.join(self.base_dir, ".last_class_config.txt")
		self.classes = []
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
			self.save_last_config()
			return True
		except Exception as e:
			print(f"설정 파일 로드 실패: {e}")
			return False

	def save_config(self, classes, config_file=None):
		"""설정 파일 저장"""
		if config_file:
			self.set_config_file(config_file)

		self.classes = classes
		try:
			with open(self.config_file, 'w', encoding='utf-8') as f:
				json.dump({'classes': self.classes}, f, ensure_ascii=False, indent=2)
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

	def get_button_configs(self):
		"""버튼 생성에 필요한 정보 반환 [(name, id, key), ...]"""
		return [(c['name'], c['id'], c.get('key', None)) for c in self.classes]

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
			if key and key in used_keys:
				messagebox.showwarning("경고", f"단축키 '{key}'가 중복됩니다.")
				return

			if key:
				used_keys.add(key)

			classes.append({
				'id': i,
				'name': name,
				'key': key if key else None,
				'color': color
			})

		if not classes:
			messagebox.showwarning("경고", "최소 1개 이상의 클래스를 설정해야 합니다.")
			return

		self.result = classes
		self.config_filename = filename + '.json'
		self.dialog.destroy()

	def cancel(self):
		self.result = None
		self.config_filename = None
		self.dialog.destroy()

	def show(self):
		self.dialog.wait_window()
		return (self.result, self.config_filename)

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
	return [_dir + '/' + f for f in os.listdir(_dir) if f.find('.jpg') >= 0 or f.find('.png') >= 0 ]

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
	exclusion_zone_enabled = False  # 제외 영역 기능 활성화 여부

	def __init__(self, _dir):
		# 클래스 설정 관리자 초기화
		self.class_config_manager = ClassConfigManager()

		# 제외 영역 관리자 초기화
		self.exclusion_zone_manager = ExclusionZoneManager()
		# 제외 영역 활성화 상태 로드
		self.exclusion_zone_enabled = self.exclusion_zone_manager.load_enabled_state()
		print(f"[ExclusionZone] 기능 활성화 상태: {self.exclusion_zone_enabled}")

		# 클래스 자동 삭제 관리자 초기화
		self.auto_delete_manager = AutoDeleteClassManager()
		print(f"[AutoDelete] 자동 삭제 클래스: {self.auto_delete_manager.delete_class_ids}")

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
				classes, config_filename = dialog.show()

				if classes is None:
					# 사용자가 취소한 경우 프로그램 종료
					print("클래스 설정이 취소되었습니다. 프로그램을 종료합니다.")
					self.master.destroy()
					sys.exit(0)

				# 설정 저장
				self.class_config_manager.save_config(classes, config_filename)
				print(f"클래스 설정이 저장되었습니다: {self.class_config_manager.config_file}")

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
		cfg.read(BASE_DIR + 'config.ini')
		
		# TP/FP 분류 설정
		if(cfg['Setting']['NATPFP']=='True'):
			self.CLASSIFY_TPFP=True
		else:
			self.CLASSIFY_TPFP=False
		
		# 키 설정 로드
		keysetting[0]=cfg['Setting']['SkipFrame']
		keysetting[1]=cfg['BasicKeySetting']['SkipLkey']
		keysetting[2]=cfg['BasicKeySetting']['SkipRkey']
		keysetting[3]=cfg['BasicKeySetting']['Lkey']
		keysetting[4]=cfg['BasicKeySetting']['Rkey']
		keysetting[5]=cfg['BasicKeySetting']['FirstPage']
		keysetting[6]=cfg['BasicKeySetting']['LastPage']
		keysetting[7]=cfg['BasicKeySetting']['Reload']
		keysetting[8]=cfg['BasicKeySetting']['Delete']
		keysetting[9]=cfg['BasicKeySetting']['Add']
		keysetting[10]=cfg['BasicKeySetting']['Remove']
		keysetting[11]=cfg['BasicKeySetting']['ResizeDown']
		keysetting[12]=cfg['BasicKeySetting']['ResizeUp']
		keysetting[13]=cfg['BasicKeySetting']['CopyKey']
		keysetting[14]=cfg['BasicKeySetting']['ZoomIn']
		keysetting[15]=cfg['BasicKeySetting']['ZoomOut']
		keysetting[16]=cfg['BasicKeySetting']['CrossLine']
		keysetting[17]=cfg['BasicKeySetting']['Help']        
		keysetting[18]=cfg['SpecialKeySetting']['NextRect']
		keysetting[19]=cfg['SpecialKeySetting']['PreRect']
		keysetting[20]=cfg['SpecialKeySetting']['ReduceUp']
		keysetting[21]=cfg['SpecialKeySetting']['ReduceDown']
		keysetting[22]=cfg['SpecialKeySetting']['ReduceRight']
		keysetting[23]=cfg['SpecialKeySetting']['ReduceLeft']
		keysetting[24]=cfg['SpecialKeySetting']['IncreaseUp']
		keysetting[25]=cfg['SpecialKeySetting']['IncreaseDown']
		keysetting[26]=cfg['SpecialKeySetting']['IncreaseRight']
		keysetting[27]=cfg['SpecialKeySetting']['IncreaseLeft']
		keysetting[28]=cfg['BasicKeySetting']['Crop']
		keysetting[29]=cfg['BasicKeySetting']['Masking']
		keysetting[30]=cfg['BasicKeySetting']['Mmasking']
		keysetting[31]=cfg['BasicKeySetting']['MaskingSave']
		keysetting[32]=cfg['BasicKeySetting']['LoadMasking']
		keysetting[33]=cfg['BasicKeySetting']['ReLoadBackup']
		keysetting[34]=cfg['SpecialKeySetting']['ViewClass']
		keysetting[35]=cfg['SpecialKeySetting']['OnlySelect']
		keysetting[36]=cfg['BasicKeySetting']['CopyLabeling']
		keysetting[37]=cfg['SpecialKeySetting']['OnlyBox']
		# keysetting[38]=cfg['BasicKeySetting']['ResetLabeling']  # 제거됨 - 위험한 기능

		# 버튼별 클래스 ID를 저장할 딕셔너리
		self.button_class_map = {}
		
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
		
		self.btnHelp = tk.Button(self.button_frame, text="Help", command=self.print_help, bd=1)
		self.btnHelp.pack(side=tk.RIGHT, padx=0)

		# 제외 영역 관련 버튼
		self.btnExclusionZone = tk.Button(self.button_frame, text="제외영역", command=self.manage_exclusion_zones, bd=1)
		self.btnExclusionZone.pack(side=tk.RIGHT, padx=2)

		# 클래스 자동 삭제 버튼
		self.btnAutoDelete = tk.Button(self.button_frame, text="자동삭제", command=self.manage_auto_delete_classes, bd=1)
		self.btnAutoDelete.pack(side=tk.RIGHT, padx=2)

		self.btnConfigClass = tk.Button(self.button_frame, text="클래스 설정", command=self.change_class_config, bd=1)
		self.btnConfigClass.pack(side=tk.RIGHT, padx=2)

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

		# 왼쪽 절반에 마스킹 복사 UI 배치
		self.mask_copy_frame = tk.Frame(self.copy_functions_frame)
		self.mask_copy_frame.pack(side=tk.LEFT, padx=5, fill="x", expand=True)

		self.mask_copy_label = tk.Label(self.mask_copy_frame, text="마스킹 복사:", bd=0)
		self.mask_copy_label.pack(side=tk.LEFT, padx=5)

		self.start_frame_label = tk.Label(self.mask_copy_frame, text="시작:", bd=0)
		self.start_frame_label.pack(side=tk.LEFT, padx=2)

		self.start_frame_entry = tk.Entry(self.mask_copy_frame, width=5)
		self.start_frame_entry.pack(side=tk.LEFT, padx=2)

		self.end_frame_label = tk.Label(self.mask_copy_frame, text="종료:", bd=0)
		self.end_frame_label.pack(side=tk.LEFT, padx=2)

		self.end_frame_entry = tk.Entry(self.mask_copy_frame, width=5)
		self.end_frame_entry.pack(side=tk.LEFT, padx=2)

		self.copy_masking_btn = tk.Button(self.mask_copy_frame, text="실행", command=self.copy_masking_to_range, bd=1)
		self.copy_masking_btn.pack(side=tk.LEFT, padx=5)

		self.delete_range_label = tk.Label(self.mask_copy_frame, text="삭제:", bd=0)
		self.delete_range_label.pack(side=tk.LEFT, padx=5)

		self.delete_start_frame_label = tk.Label(self.mask_copy_frame, text="시작:", bd=0)
		self.delete_start_frame_label.pack(side=tk.LEFT, padx=2)

		self.delete_start_frame_entry = tk.Entry(self.mask_copy_frame, width=5)
		self.delete_start_frame_entry.pack(side=tk.LEFT, padx=2)

		self.delete_end_frame_label = tk.Label(self.mask_copy_frame, text="종료:", bd=0)
		self.delete_end_frame_label.pack(side=tk.LEFT, padx=2)

		self.delete_end_frame_entry = tk.Entry(self.mask_copy_frame, width=5)
		self.delete_end_frame_entry.pack(side=tk.LEFT, padx=2)

		self.delete_range_btn = tk.Button(self.mask_copy_frame, text="실행", command=self.delete_range, bd=1)
		self.delete_range_btn.pack(side=tk.LEFT, padx=5)
		
		self.page_move_label = tk.Label(self.mask_copy_frame, text="이동:", bd=0)
		self.page_move_label.pack(side=tk.LEFT, padx=10)

		self.page_entry = tk.Entry(self.mask_copy_frame, width=5)
		self.page_entry.pack(side=tk.LEFT, padx=2)

		self.page_move_btn = tk.Button(self.mask_copy_frame, text="Go", command=self.move_to_page, bd=1)
		self.page_move_btn.pack(side=tk.LEFT, padx=5)
		# 구분자 추가
		tk.Frame(self.copy_functions_frame, bd=1, width=1, bg="gray").pack(side=tk.LEFT, fill="y", padx=10, pady=2)

		# 오른쪽 절반에 라벨 복사 UI 배치
		self.label_copy_frame = tk.Frame(self.copy_functions_frame)
		self.label_copy_frame.pack(side=tk.LEFT, padx=5, fill="x", expand=True)

		# 기존 코드를 대체하는 메서드 호출 - UI를 별도 함수로 분리
		self.update_label_copy_ui()
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
		
		# 기존 이미지 로드 코드
		while True:
			try: 
				_dir = self.get_directory() 
			except Exception as e:
				print(e) 
				if _dir == None:                    
					return
			print(_dir)
			fname, ext = os.path.splitext(_dir)
			if ext != '.evaluation':
				break
		
		# 이미지 리스트 로드 코드
		if ext != '.txt':
			cdir = os.path.abspath(_dir)
			if self.CLASSIFY_TPFP:
				self.imlist = get_list_jpg(cdir)
				self.imlist += get_list_jpg(cdir + '/TP')
				self.imlist += get_list_jpg(cdir + '/FP')
				self.imlist = [p[1] for p in natsort.natsorted([[os.path.basename(f), f] for f in self.imlist])]
				labelsname = cdir.replace('JPEGImages','labels')
				if not(os.path.isdir(labelsname + '/TP')):
					os.makedirs(os.path.join(labelsname + '/TP'))
				if not(os.path.isdir(labelsname + '/FP')):
					os.makedirs(os.path.join(labelsname + '/FP'))
			else:
				self.imlist = [cdir + '/' + f for f in natsort.natsorted(os.listdir(cdir)) if f.find('.jpg') >= 0 or f.find('.png') >= 0]
				for f in self.imlist:
					label = f.replace('JPEGImages','labels')
					label = label.replace('jpg','txt')
					label = label.replace('png','txt')
					label = label.replace('/','\\')
					if os.path.exists(label) is False:
						pathstr = os.path.split(label)
						if os.path.isdir(pathstr[0]) is False:
							os.makedirs(os.path.join(pathstr[0]))
						flabel = open(label, "wt")
						flabel.close()
		
		self._dir = _dir
		_dir_goodbye = _dir
		self.setup_input_validation()
		self.setup_input_focus_handling()
		# self.improve_key_bindings()

			# 초기에 캔버스에 포커스 설정
		self.canvas.focus_set()

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
			image_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
			image_files = []

			for root, dirs, files in os.walk(search_path):
				for file in files:
					if any(file.endswith(ext) for ext in image_extensions):
						full_path = os.path.join(root, file)
						image_files.append(full_path)

			# 자연스러운 정렬
			image_files = natsort.natsorted(image_files)

			if len(image_files) == 0:
				print(f"[WARNING] 폴더에서 이미지 파일을 찾을 수 없습니다: {folder_path}")
				messagebox.showwarning("경고", "선택한 폴더에서 이미지 파일을 찾을 수 없습니다.")
				return

			# 이미지 리스트 설정
			self.imlist = image_files
			print(f"[INFO] {len(image_files)}개의 이미지 파일을 로드했습니다.")

			# 첫 번째 이미지 로드
			if len(self.imlist) > 0:
				self.ci = 0
				self.load_image()

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
				encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1', 'shift-jis']
				success = False

				for encoding in encodings:
					try:
						with open(dirname, "rt", encoding=encoding) as file:
							lineidx = 0
							nofile = []
							self.imlist = []  # 리스트 초기화
							
							while True:
								line = file.readline()
								if not line:
									break
								line = line.replace('/s_mnt/253/','//192.168.79.253/')
								line = line.replace('\n','')
								print(f"{str(lineidx)} : {line}")
								if os.path.exists(line):					
									self.imlist.insert(lineidx, line)
									lineidx += 1
								else: 
									nofile.append(line)
							
							# 파일에 없는 경로 출력
							for nofilename in nofile:
								print(f"no file : {nofilename}")
							
							# 존재하는 파일만 다시 저장
							with open(dirname, "wt", encoding=encoding) as f:
								self.imlist = [p[1] for p in natsort.natsorted([[os.path.basename(f), f] for f in self.imlist])]
								for existfilename in self.imlist:
									existfilename = existfilename.replace('//192.168.79.253/','/s_mnt/253/')
									existfilename = existfilename.replace('.png','.png\n')
									existfilename = existfilename.replace('.jpg','.jpg\n')
									f.write(existfilename)
							
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
				_dir = dirname
		elif ext != '.jpg' and ext != '.png':
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
	def load_new_folder(self):
		try:
			a = tk.Tk()
			a.withdraw()
			a.update()
			new_dir = tk.filedialog.askdirectory()
			if new_dir:  # 폴더가 선택된 경우
				self.reset_data()
				if self.CLASSIFY_TPFP:
					self.imlist = get_list_jpg(new_dir)
					self.imlist += get_list_jpg(new_dir + '/TP')
					self.imlist += get_list_jpg(new_dir + '/FP')
					self.imlist = [p[1] for p in natsort.natsorted([[os.path.basename(f), f] for f in self.imlist])]
					
					# TP/FP 폴더 생성
					labels_dir = new_dir.replace('JPEGImages','labels')
					if not(os.path.isdir(labels_dir + '/TP')):
						os.makedirs(os.path.join(labels_dir + '/TP'))
					if not(os.path.isdir(labels_dir + '/FP')):
						os.makedirs(os.path.join(labels_dir + '/FP'))
				else:
					self.imlist = [new_dir + '/' + f for f in natsort.natsorted(os.listdir(new_dir)) 
								if f.find('.jpg') >= 0 or f.find('.png') >= 0]
					
					# 각 이미지에 대한 라벨 파일 확인/생성
					for f in self.imlist:
						label = f.replace('JPEGImages','labels')
						label = label.replace('jpg','txt')
						label = label.replace('png','txt')
						label = label.replace('/','\\')
						if os.path.exists(label) is False:
							pathstr = os.path.split(label)
							if os.path.isdir(pathstr[0]) is False:
								os.makedirs(os.path.join(pathstr[0]))
							flabel = open(label, "wt")
							flabel.close()
				if self.imlist:
					self.img_slider.config(to=len(self.imlist))
					self.img_slider.set(self.ci + 1)
					self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
					self._dir = new_dir
					self.draw_image()
			a.destroy()
		except Exception as e:
			print(f"Error loading folder: {e}")
			messagebox.showerror("Error", f"Failed to load folder: {e}")
	def check_bbox_mask_overlap(self, mask_area, bbox):
		"""마스킹 영역과 바운딩 박스가 겹치는지 확인
		
		Args:
			mask_area: 마스킹 영역 [x1, y1, x2, y2] (뷰 좌표)
			bbox: 바운딩 박스 [sel, clsname, info, x1, y1, x2, y2]
			
		Returns:
			bool: 겹치면 True, 아니면 False
		"""
		# 바운딩 박스 좌표
		bbox_x1, bbox_y1, bbox_x2, bbox_y2 = bbox[3:]
		
		# 마스킹 영역 좌표 정규화 (x1 < x2, y1 < y2 보장)
		mask_x1 = min(mask_area[0], mask_area[2])
		mask_y1 = min(mask_area[1], mask_area[3])
		mask_x2 = max(mask_area[0], mask_area[2])
		mask_y2 = max(mask_area[1], mask_area[3])
		
		# 두 사각형이 겹치지 않는 경우 체크
		if bbox_x2 < mask_x1 or bbox_x1 > mask_x2 or bbox_y2 < mask_y1 or bbox_y1 > mask_y2:
			return False
		
		return True
	def load_new_list(self):
		"""새로운 이미지 리스트 파일 로드"""
		try:
			a = tk.Tk()
			a.withdraw()
			a.update()
			file_path = tk.filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
			if file_path:  # 파일이 선택된 경우
				self.reset_data()
				encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1', 'shift-jis']
				success = False
		
				for encoding in encodings:
					try:
						with open(file_path, "rt", encoding=encoding) as file:
							self.imlist = []
							for line in file:
								line = line.strip()
								line = line.replace('/s_mnt/253/','//192.168.79.253/')
								if os.path.exists(line):
									self.imlist.append(line)
								else:
									print(f"Warning: File not found - {line}")
						
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
					a.destroy()
					return
				
				if self.imlist:  # 유효한 이미지가 있는 경우
					self.img_slider.config(to=len(self.imlist))
					self.img_slider.set(self.ci + 1)
					self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
					self._dir = os.path.dirname(self.imlist[0])
					self.draw_image()
				else:
					messagebox.showwarning("Warning", "No valid images found in the list")
			a.destroy()
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
		
		progress_bar = tk.ttk.Progressbar(progress_window, orient="horizontal", 
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
		
		# backup 폴더 확인
		d_path = 'original_backup/JPEGImages/'            
		if not(os.path.isdir(d_path)):
			os.makedirs(os.path.join(d_path))
		if not(os.path.isdir('original_backup/labels/')):
			os.makedirs(os.path.join('original_backup/labels/'))
		
		# 삭제 진행
		deleted_count = 0
		for idx, i in enumerate(to_delete_indices):
			# 프로그레스 바 업데이트
			progress_bar["value"] = idx + 1
			progress_label.config(text=f"처리 중: {idx+1}/{total_frames} ({int(progress_bar['value']/total_frames*100)}%)")
			self.master.update()
			
			try:
				# 현재 인덱스가 현재 보는 이미지보다 크면 현재 인덱스 조정 필요 없음
				if i > current_idx:
					pass
				# 현재 인덱스가 현재 보는 이미지와 같거나 작으면 현재 인덱스 감소
				elif i <= current_idx:
					current_idx -= 1
				
				# 현재 파일 경로
				img_path = self.imlist[i]
				label_path = img_path.replace('JPEGImages', 'labels')
				label_path = label_path.replace('.jpg', '.txt')
				label_path = label_path.replace('.png', '.txt')
				
				# 백업
				backup_img_path = d_path + self.make_path(img_path)
				backup_label_path = 'original_backup/labels/' + self.make_path(label_path)
				
				# 백업이 없는 경우에만 백업 생성
				if not os.path.exists(backup_img_path) and os.path.exists(img_path):
					img = Image.open(img_path)
					img.save(backup_img_path)
				
				if not os.path.exists(backup_label_path) and os.path.exists(label_path):
					shutil.copyfile(label_path, backup_label_path)
				
				# 파일 삭제
				if os.path.exists(img_path):
					os.remove(img_path)
				
				if os.path.exists(label_path):
					os.remove(label_path)
				
				# 이미지 리스트에서 삭제
				self.imlist.pop(i)
				deleted_count += 1
				
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
		
		# 라벨 복사 기본 UI 재생성
		self.label_copy_label = tk.Label(self.label_copy_frame, text="라벨 복사:", bd=0)
		self.label_copy_label.pack(side=tk.LEFT, padx=5)
		
		# 복사 모드 선택을 위한 라디오 버튼
		self.copy_mode = tk.StringVar(value="all")  # 기본값: 모든 라벨 복사
		
		# 라디오 버튼을 담을 프레임
		self.copy_mode_frame = tk.Frame(self.label_copy_frame)
		self.copy_mode_frame.pack(side=tk.LEFT, padx=2)
		
		# 모든 라벨 모드 라디오 버튼
		self.rb_all = tk.Radiobutton(
			self.copy_mode_frame, 
			text="전체", 
			variable=self.copy_mode, 
			value="all",
			command=self.toggle_copy_mode
		)
		self.rb_all.pack(side=tk.LEFT)
		
		# 선택 라벨 모드 라디오 버튼
		self.rb_selected = tk.Radiobutton(
			self.copy_mode_frame, 
			text="선택", 
			variable=self.copy_mode, 
			value="selected",
			command=self.toggle_copy_mode
		)
		self.rb_selected.pack(side=tk.LEFT)
		# 다중 선택 라벨 모드 라디오 버튼 (새로 추가)
		self.rb_multi = tk.Radiobutton(
			self.copy_mode_frame, 
			text="다중선택", 
			variable=self.copy_mode, 
			value="selected_multi",
			command=self.toggle_copy_mode
		)
		self.rb_multi.pack(side=tk.LEFT)

		# 다중 선택 정보 표시 라벨 (새로 추가)
		self.multi_info_label = tk.Label(
			self.label_copy_frame, 
			text="선택된 라벨: 0개", 
			font=("Arial", 8),
			fg="blue"
		)
		self.multi_info_label.pack(side=tk.LEFT, padx=5)

		# 다중 선택 모드 토글 버튼 (새로 추가)
		self.multi_mode_btn = tk.Button(
			self.label_copy_frame,  # ✅ 수정: button_frame → label_copy_frame
			text="다중선택모드: OFF",
			command=self.toggle_multi_select_mode,
			bd=1,
			bg="lightgray"
		)
		self.multi_mode_btn.pack(side=tk.LEFT, padx=5)
		# 대상 이미지의 기존 라벨 처리 옵션 (선택 모드일 때만 활성화)
		self.label_preserve_frame = tk.Frame(self.label_copy_frame)
		self.label_preserve_frame.pack(side=tk.LEFT, padx=5)
		
		self.preserve_mode = tk.StringVar(value="preserve")  # 기본값: 기존 라벨 유지
		
		# 유지/삭제 라디오 버튼 그룹
		self.rb_preserve = tk.Radiobutton(
			self.label_preserve_frame,
			text="유지",
			variable=self.preserve_mode,
			value="preserve"
		)
		self.rb_preserve.pack(side=tk.LEFT)
		
		self.rb_replace = tk.Radiobutton(
			self.label_preserve_frame,
			text="삭제",
			variable=self.preserve_mode,
			value="replace"
		)
		self.rb_replace.pack(side=tk.LEFT)
		
		# 시작/종료 프레임 입력 UI
		self.label_start_frame_label = tk.Label(self.label_copy_frame, text="시작:", bd=0)
		self.label_start_frame_label.pack(side=tk.LEFT, padx=2)
		
		self.label_start_frame_entry = tk.Entry(self.label_copy_frame, width=5)
		self.label_start_frame_entry.pack(side=tk.LEFT, padx=2)
		
		self.label_end_frame_label = tk.Label(self.label_copy_frame, text="종료:", bd=0)
		self.label_end_frame_label.pack(side=tk.LEFT, padx=2)
		
		self.label_end_frame_entry = tk.Entry(self.label_copy_frame, width=5)
		self.label_end_frame_entry.pack(side=tk.LEFT, padx=2)
		
		# 실행 버튼
		self.copy_label_btn = tk.Button(
			self.label_copy_frame, 
			text="실행", 
			command=self.copy_label_to_range, 
			bd=1
		)
		self.copy_label_btn.pack(side=tk.LEFT, padx=5)
		
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
		
		# 복사할 라벨 정보 준비
		if copy_mode == "all":
			# 모든 라벨 복사
			with open(self.gt_fn, 'rt') as f:
				copytext = f.readlines()
			
			if not copytext: 
				messagebox.showwarning("경고", "복사할 라벨 내용이 없습니다.")
				return
		elif copy_mode == "selected":
			# 선택된 라벨만 복사
			selected_bbox = self.bbox[self.selid]
			selected_label_rel = self.convert_abs2rel(selected_bbox)
			copytext = [' '.join(str(e) for e in selected_label_rel) + '\n']
		else:  # selected_multi
			# 다중 선택된 라벨들 복사
			copytext = []
			for idx in sorted(self.multi_selected):
				if idx < len(self.bbox):
					selected_bbox = self.bbox[idx]
					selected_label_rel = self.convert_abs2rel(selected_bbox)
					copytext.append(' '.join(str(e) for e in selected_label_rel) + '\n')
		
		# 진행 상황 창 생성
		progress_window = tk.Toplevel(self.master)
		progress_window.title("라벨 복사 중...")
		progress_window.geometry("300x100")
		progress_window.transient(self.master)
		
		progress_label = tk.Label(progress_window, text="라벨을 복사 중입니다...", pady=10)
		progress_label.pack()
		
		progress_bar = tk.ttk.Progressbar(progress_window, orient="horizontal", 
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
				target_label_path = target_img_path.replace('JPEGImages', 'labels')
				target_label_path = target_label_path.replace('.jpg', '.txt')
				target_label_path = target_label_path.replace('.png', '.txt')
				
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
					
				# 백업 생성은 별도 try 블록
				try:
					if os.path.exists(target_label_path):
						backup_dir = 'original_backup/labels/'
						if not os.path.isdir(backup_dir):
							os.makedirs(backup_dir)
						
						backup_path = backup_dir + self.make_path(target_label_path)
						if not os.path.exists(backup_path):
							shutil.copyfile(target_label_path, backup_path)
				except Exception as e:
					print(f"백업 생성 오류: {e}")
					
				# 라벨 쓰기는 별도 try 블록
				try:
					with open(target_label_path, 'w', encoding='utf-8') as f:
						f.writelines(existing_labels)
						if copy_mode == "selected" and preserve_mode == "preserve":
							# 중복 검사
							is_duplicate = False
							for existing_label in existing_labels:
								if existing_label.strip() == copytext[0].strip():
									is_duplicate = True
									break
							
							# 중복이 아닌 경우 새 라벨 추가
							if not is_duplicate:
								f.writelines(copytext)
						else:
							f.writelines(copytext)
				except Exception as e:
					print(f"라벨 쓰기 오류: {e}")
					# 쓰기 실패 시 백업에서 복원 시도
					try:
						if os.path.exists(backup_path):
							shutil.copyfile(backup_path, target_label_path)
					except:
						print("백업 복원 실패")
						
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
	def draw_image(self):
		self.canvas.delete("all")
		try:
			if self.ci == self.pi: return
			self.pi = self.ci	

			if len(self.imlist) > 0:
				self.img_slider.config(to=len(self.imlist))
				self.img_slider.set(self.ci + 1)  # 1-인덱스로 표시
				self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
			
			self.im_fn = self.imlist[self.ci]
			self.gt_fn = self.im_fn
			self.gt_fn = self.gt_fn.replace('JPEGImages','labels')
			self.gt_fn = self.gt_fn.replace('images','annotations')
			self.gt_fn = self.gt_fn.replace('.jpg','.txt')
			self.gt_fn = self.gt_fn.replace('.png','.txt')
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
			
			# 기존에 저장된 마스킹이 있는지 확인하고 로드
			try:
				# 현재 이미지에 이미 마스킹이 적용되어 있는지 확인
				temp_array = array(im)
				existing_masking = np.where((temp_array==[255,0,255]).all(axis=2))
				
				if len(existing_masking[0]) > 0:
					# 이미 마스킹이 적용된 이미지인 경우
					self.current_img_array = temp_array
					self.masking = existing_masking
					self.has_saved_masking = True
					self.maskingframewidth = im.width
					self.maskingframeheight = im.height
			except Exception as e:
				print(f"마스킹 복원 중 오류: {e}")
						
			self.imsize = im.size
			self.imsize = [(int)(i * self.zoom_ratio) for i in im.size]
			self.original_width = im.width
			self.original_height = im.height
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
		self.crop_canvas = tk.Canvas(self.crop_frame, width=260, height=150, bg='white', relief='solid', bd=1)
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
		
		# 크롭 캔버스 클릭 이벤트
		self.crop_canvas.bind("<Button-1>", self.on_crop_canvas_click)
		
		# 포커스 관리
		self.label_listbox.bind("<Button-1>", lambda e: self.master.after(50, self.canvas.focus_set))

	def on_label_list_double_click(self, event):
		"""라벨 리스트 더블클릭 시 해당 라벨 중앙으로 이동"""
		selection = self.label_listbox.curselection()
		if not selection:
			return
		
		selected_index = selection[0]
		if selected_index < len(self.bbox):
			bbox = self.bbox[selected_index]
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

	def delete_label_from_list(self, index):
		"""라벨 리스트에서 라벨 삭제"""
		if 0 <= index < len(self.bbox):
			self.selid = index
			self.remove_bbox_rc()

	def center_view_on_label(self, index):
		"""라벨을 화면 중앙으로 이동"""
		if 0 <= index < len(self.bbox):
			self.selid = index
			self.on_label_list_double_click(None)

	def copy_label_from_list(self, index):
		"""라벨 리스트에서 라벨 복사"""
		if 0 <= index < len(self.bbox):
			self.selid = index
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
		
		# 클래스별 개수 카운트
		class_counts = {}
		
		# 각 라벨을 리스트에 추가
		for i, bbox in enumerate(self.bbox):
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
				self.label_listbox.select_set(i)
				self.label_listbox.see(i)
				# 선택된 항목 배경색 변경
				self.label_listbox.itemconfig(i, {'bg': 'lightblue'})
		
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
		"""선택된 라벨의 크롭 프리뷰 업데이트"""
		if not hasattr(self, 'crop_canvas') or not self.show_label_list.get():
			return
		
		# 캔버스 초기화
		self.crop_canvas.delete("all")
		self.crop_info_label.config(text="")
		
		if self.selid < 0 or not self.bbox:
			self.crop_canvas.create_text(130, 100, text="No label selected", 
									fill="gray", font=("Arial", 12))
			return
		
		try:
			# 현재 선택된 바운딩 박스 정보
			bbox = self.bbox[self.selid]
			x1, y1, x2, y2 = bbox[3:7]
			
			# 원본 이미지 좌표로 변환 (줌 비율 고려)
			orig_x1 = int(x1 / self.zoom_ratio)
			orig_y1 = int(y1 / self.zoom_ratio)
			orig_x2 = int(x2 / self.zoom_ratio)
			orig_y2 = int(y2 / self.zoom_ratio)
			
			# 좌표 보정
			if hasattr(self, 'original_width') and hasattr(self, 'original_height'):
				orig_x1 = max(0, min(orig_x1, self.original_width))
				orig_y1 = max(0, min(orig_y1, self.original_height))
				orig_x2 = max(0, min(orig_x2, self.original_width))
				orig_y2 = max(0, min(orig_y2, self.original_height))
			
			# 원본 이미지에서 크롭
			original_img = Image.open(self.im_fn)
			
			if orig_x2 > orig_x1 and orig_y2 > orig_y1:
				crop_region = (orig_x1, orig_y1, orig_x2, orig_y2)
				cropped_img = original_img.crop(crop_region)
				
				# 비율 유지하면서 리사이즈
				canvas_width = 250
				canvas_height = 180
				
				img_ratio = cropped_img.width / cropped_img.height
				canvas_ratio = canvas_width / canvas_height
				
				if img_ratio > canvas_ratio:
					new_width = canvas_width
					new_height = int(canvas_width / img_ratio)
				else:
					new_height = canvas_height
					new_width = int(canvas_height * img_ratio)
				
				resized_img = cropped_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
				
				# 캔버스에 표시
				self.crop_image_tk = ImageTk.PhotoImage(resized_img)
				
				x_offset = (260 - new_width) // 2
				y_offset = (180 - new_height) // 2
				
				self.crop_canvas.create_image(
					x_offset, y_offset, 
					image=self.crop_image_tk, 
					anchor='nw',
					tags="crop_image"
				)
				
				# 클릭 가능 영역 표시
				self.crop_canvas.create_rectangle(
					x_offset-1, y_offset-1, 
					x_offset+new_width+1, y_offset+new_height+1,
					outline="red", width=2, tags="click_area"
				)
				
				# 정보 업데이트
				class_name = bbox[1]
				width = int(bbox[5] - bbox[3])
				height = int(bbox[6] - bbox[4])
				self.crop_info_label.config(text=f"{class_name} ({width}x{height})")
				
			else:
				self.crop_canvas.create_text(130, 100, text="Invalid crop area", 
										fill="red", font=("Arial", 12))
		
		except Exception as e:
			print(f"Error updating crop preview: {e}")
			self.crop_canvas.create_text(130, 100, text="Error loading crop", 
									fill="red", font=("Arial", 10))

	def on_label_list_select(self, event):
		"""라벨 리스트에서 항목 선택 시"""
		selection = self.label_listbox.curselection()
		if not selection:
			return
		
		selected_index = selection[0]
		
		# 기존 선택 해제
		for bbox in self.bbox:
			bbox[0] = False
		
		# 새로 선택
		if selected_index < len(self.bbox):
			self.bbox[selected_index][0] = True
			self.selid = selected_index
			
			# 메인 화면 업데이트
			self.draw_bbox()
			
			# 크롭 프리뷰 업데이트
			self.update_crop_preview()

			self.canvas.focus_set()
	def on_crop_canvas_click(self, event):
		"""크롭 캔버스 클릭 시 삭제"""
		if self.selid >= 0:
			bbox = self.bbox[self.selid]
			if messagebox.askyesno("삭제 확인", f"{bbox[1]} 라벨을 삭제하시겠습니까?"):
				self.remove_bbox_rc()
				self.update_label_list()
				self.update_crop_preview()

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
		self.gt_fn = self.im_fn
		self.gt_fn = self.gt_fn.replace('JPEGImages','labels')
		self.gt_fn = self.gt_fn.replace('images','annotations')
		self.gt_fn = self.gt_fn.replace('.jpg','.txt')
		self.gt_fn = self.gt_fn.replace('.png','.txt')
		self.canvas.delete("img")
		im = Image.open(self.im_fn)
		self.imsize = im.size
		self.imsize = [(int)(i * self.zoom_ratio) for i in im.size]
		im = im.resize(self.imsize, Image.LANCZOS)
		
		self.canvas.config(width=self.imsize[0], height=self.imsize[1])
		self.canvas.image = ImageTk.PhotoImage(im)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
		self.master.title('[%d/%d] %s' % (self.ci+1, len(self.imlist), self.im_fn))

		if self.CLASSIFY_TPFP: self.draw_criteria()
		#self.load_bbox()
		self.draw_bbox()
		return
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
		
		progress_bar = tk.ttk.Progressbar(progress_window, orient="horizontal", 
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
		has_polygon = hasattr(self, 'saved_polygon_points') and self.saved_polygon_points
		
		# 지정된 범위의 이미지에 마스킹 적용
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
				# 대상 이미지 로드
				target_img_path = self.imlist[i]
				target_img = Image.open(target_img_path)
				
				# 이미지 크기 확인
				if target_img.width != mask_width or target_img.height != mask_height:
					print(f"이미지 {i+1}의 크기가 마스킹과 일치하지 않습니다. 건너뜁니다.")
					continue
				
				# 백업 폴더 및 파일 확인
				d_path = 'original_backup/JPEGImages/'
				if not(os.path.isdir(d_path)):
					os.makedirs(os.path.join(d_path))
				
				img_path = d_path + self.make_path(target_img_path)
				if not os.path.exists(img_path):
					shutil.copyfile(target_img_path, img_path)
				
				# 마스킹 적용
				target_img_array = array(target_img)
				target_img_array[self.masking] = [255, 0, 255]
				target_img = Image.fromarray(target_img_array)
				
				# 이미지 저장
				target_img.save(target_img_path)
				
				# 마스킹과 겹치는 라벨 삭제 옵션이 켜져 있는 경우
				if self.remove_overlapping_labels.get():
					try:
						# 대상 라벨 파일 경로
						target_label_path = target_img_path.replace('JPEGImages', 'labels')
						target_label_path = target_label_path.replace('.jpg', '.txt')
						target_label_path = target_label_path.replace('.png', '.txt')
						
						# 라벨 디렉토리 확인
						label_dir = os.path.dirname(target_label_path)
						if not os.path.exists(label_dir):
							os.makedirs(label_dir)
						
						# 백업 생성
						if os.path.exists(target_label_path):
							backup_dir = 'original_backup/labels/'
							if not os.path.isdir(backup_dir):
								os.makedirs(backup_dir)
							
							backup_path = backup_dir + self.make_path(target_label_path)
							if not os.path.exists(backup_path):
								shutil.copyfile(target_label_path, backup_path)
						
						# 마스킹 영역 계산 (원본 이미지 기준)
						if has_polygon:
							# 폴리곤 마스킹의 경우 저장된 폴리곤 좌표 사용
							min_x = min(p[0] for p in self.saved_polygon_points)
							min_y = min(p[1] for p in self.saved_polygon_points)
							max_x = max(p[0] for p in self.saved_polygon_points)
							max_y = max(p[1] for p in self.saved_polygon_points)
							
							mask_area = [min_x, min_y, max_x, max_y]
						else:
							# 일반 마스킹의 경우 마스킹된 픽셀 영역 계산
							if len(self.masking[0]) > 0:  # 마스킹된 픽셀이 있는 경우
								mask_y1 = min(self.masking[0]) if len(self.masking[0]) > 0 else 0
								mask_y2 = max(self.masking[0]) if len(self.masking[0]) > 0 else 0
								mask_x1 = min(self.masking[1]) if len(self.masking[1]) > 0 else 0
								mask_x2 = max(self.masking[1]) if len(self.masking[1]) > 0 else 0
								
								# 원본 이미지 좌표를 캔버스 좌표로 변환
								view_x1, view_y1 = self.convert_original_to_view(mask_x1, mask_y1)
								view_x2, view_y2 = self.convert_original_to_view(mask_x2, mask_y2)
								
								mask_area = [view_x1, view_y1, view_x2, view_y2]
						
						# 기존 라벨 로드
						labels_to_keep = []
						if os.path.exists(target_label_path):
							with open(target_label_path, 'r') as f:
								lines = f.readlines()
								
								for line in lines:
									values = line.strip().split()
									if len(values) >= 5:
										cls_id, cx, cy, w, h = map(float, values)
										
										# YOLO 형식에서 절대 좌표 계산 (픽셀 단위)
										abs_x1 = int((cx - w/2) * mask_width)
										abs_y1 = int((cy - h/2) * mask_height)
										abs_x2 = int((cx + w/2) * mask_width)
										abs_y2 = int((cy + h/2) * mask_height)
										
										# 캔버스 좌표로 변환
										view_x1, view_y1 = self.convert_original_to_view(abs_x1, abs_y1)
										view_x2, view_y2 = self.convert_original_to_view(abs_x2, abs_y2)
										
										# 바운딩 박스 (캔버스 좌표)
										bbox = [False, class_name[int(cls_id)], -1, view_x1, view_y1, view_x2, view_y2]
										
										# 바운딩 박스가 마스킹 영역과 겹치는지 확인
										if not self.check_bbox_mask_overlap(mask_area, bbox):
											# 겹치지 않는 경우 (유지)
											labels_to_keep.append(line)
										# 겹치는 경우는 무시 (삭제)
						
						# 라벨 파일 다시 쓰기
						with open(target_label_path, 'w') as f:
							f.writelines(labels_to_keep)
					
					except Exception as e:
						print(f"라벨 처리 중 오류 발생: {e}")
				
				success_count += 1
				
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
		
		# 완료 메시지
		messagebox.showinfo("완료", f"마스킹 복사가 완료되었습니다. {success_count}개의 이미지에 성공적으로 적용되었습니다.")
		
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
			self.remove_labels_overlapping_with_mask(self.m_area)

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

	def remove_labels_overlapping_with_mask(self, mask_area):
		"""마스킹 영역과 겹치는 라벨 삭제
		
		Args:
			mask_area: 마스킹 영역 [x1, y1, x2, y2] (뷰 좌표)
		"""
		if not self.bbox:
			return
		
		# 삭제할 라벨 인덱스 리스트 (역순으로 삭제하기 위해)
		to_remove = []
		
		# 겹치는 라벨 찾기
		for i, box in enumerate(self.bbox):
			if self.check_bbox_mask_overlap(mask_area, box):
				to_remove.append(i)
		
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
			if x<0:
				x=0
			if y<0:
				y=0
			if x+w>self.imsize[0]:
				w=self.imsize[0]-x-1
			if y+h>self.imsize[1]:
				h=self.imsize[1]-y-1

			# 클래스 인덱스 범위 체크
			class_idx = int(rc[0])
			if 0 <= class_idx < len(class_name):
				name = class_name[class_idx]
			else:
				print(f"WARNING: Invalid class index {class_idx}, using default")
				name = class_name[0] if class_name else "unknown"

			return [False, name, -1, (x), (y), (x+w), (y+h)]
		except (IndexError, ValueError, TypeError) as e:
			print(f"ERROR in convert_rel2abs: {e}, rc={rc}")
			return [False, class_name[0] if class_name else "unknown", -1, 0, 0, 10, 10]

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
			return [class_name.index(rc[1]), cx, cy, w, h]
		except (ValueError, ZeroDivisionError) as e:
			print(f"ERROR in convert_abs2rel: {e}, rc={rc}")
			return [0, 0.5, 0.5, 0.1, 0.1]

	def bound_box_coord(self, r):
		if r[2] < 0: r[2] = 0
		if r[3] < 0: r[3] = 0
		if r[2] > self.imsize[0]: r[2] = self.imsize[0]
		if r[3] > self.imsize[1]: r[3] = self.imsize[1]
		return r

	def load_bbox(self):
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

		# === 자동 필터링 적용 ===
		total_deleted = 0

		# 1. 클래스 자동 삭제 필터링
		if self.auto_delete_manager and self.auto_delete_manager.delete_class_ids:
			before_count = len(self.bbox)
			# class_name은 전역 변수
			global class_name
			self.bbox = self.auto_delete_manager.filter_bboxes(self.bbox, class_name)
			deleted_count = before_count - len(self.bbox)
			if deleted_count > 0:
				print(f"[AutoDelete] {deleted_count}개 라벨 자동 삭제됨")
				total_deleted += deleted_count

		# 2. 제외 영역 필터링
		if self.exclusion_zone_enabled and self.exclusion_zone_manager:
			before_count = len(self.bbox)
			self.bbox = [bbox for bbox in self.bbox if not self.exclusion_zone_manager.is_bbox_in_exclusion_zone(bbox)]
			deleted_count = before_count - len(self.bbox)
			if deleted_count > 0:
				print(f"[ExclusionZone] {deleted_count}개 라벨 제외 영역에서 삭제됨")
				total_deleted += deleted_count

		# 필터링으로 라벨이 삭제되었으면 파일에 반영
		if total_deleted > 0:
			self.write_bbox()
			print(f"[Filter] 총 {total_deleted}개 라벨이 자동 삭제되어 파일에 저장됨")

		if len(self.bbox) > 0:
			self.bbox[0][0] = True
			self.selid = 0
		return

	def write_bbox(self):
		if self.gt_fn is None:
			print("WARNING: gt_fn is None, cannot write bbox")
			return

		try:
			with open(self.gt_fn, 'wt') as f:
				for rc in self.bbox:
					f.write(' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n')
		except (IOError, PermissionError) as e:
			print(f"ERROR: Failed to write bbox to {self.gt_fn}: {e}")
			messagebox.showerror("File Write Error", f"Failed to save labels:\n{e}")
		return

	def draw_bbox(self):
		self.canvas.delete("bbox")
		self.canvas.delete("anchor")
		self.canvas.delete("clsname")

		if self.bbox_resize_anchor != None or self.bbox_move:
			self.draw_bbox_rc(self.bbox[self.selid])
			rc = self.bbox[self.selid]
			s = str(rc[5]-rc[3]) + 'x' + str(rc[6]-rc[4])
			self.canvas.create_text(rc[5]-3,rc[6]+14, font='Arial 7', fill='black', text=s, anchor='se', tags='bbox')
		elif self.onlyselect is True:
			self.draw_bbox_rc(self.bbox[self.selid])
			rc = self.bbox[self.selid]
			s = str(rc[5]-rc[3]) + 'x' + str(rc[6]-rc[4])
			self.canvas.create_text(rc[5]-3,rc[6]+14, font='Arial 7', fill='black', text=s, anchor='se', tags='bbox')
		else:
			labellst = []
			for i, rc in enumerate(self.bbox):
				self.draw_bbox_rc(rc, i) if rc[0] == False else None
				labellst.append(rc[1])
			if len(labellst) > 0:
				counted_items = Counter(labellst)
				cnt = 0
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
			if self.selid >= 0:
				self.draw_bbox_rc(self.bbox[self.selid])
			if hasattr(self, 'show_label_list') and self.show_label_list.get():
				self.update_label_list()
				self.update_crop_preview()

		# 제외 영역 표시
		self.draw_exclusion_zones()
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

		if self.onlybox == True:
			self.draw_bbox_anchor(rc, color) if rc[0] else None

	def draw_bbox_anchor(self, rc, color):
		margin = [-3,-3,3,3]
		x1,y1,x2,y2 = rc[3:]
		anchor_rc = [
			[x1,y1], [(x1+x2)/2,y1], [x2,y1], [x2,(y1+y2)/2],
			[x2,y2], [(x1+x2)/2,y2], [x1,y2], [x1,(y1+y2)/2]
		]
		anchor_rc = [ e*2 for e in anchor_rc ]
		anchor_rc = zip(anchor_name, anchor_rc)
		# [ ['nw', [x1, y1, x2, y2], .. ]
		for r in anchor_rc:
			c = 'black' if color not in anchor_color else anchor_color[color]
			self.canvas.create_rectangle([a + b for a, b in zip(r[1], margin)], outline=c, fill=color, width=1, tags=("anchor", r[0]))
		return

	def draw_exclusion_zones(self):
		"""제외 영역 표시"""
		self.canvas.delete("exclusion_zone")

		if not self.exclusion_zone_manager:
			return

		# 전역 제외 영역 표시
		for i, zone in enumerate(self.exclusion_zone_manager.global_zones):
			if zone['points']:
				# 폴리곤 색상 (활성화 여부에 따라)
				color = 'orange' if zone['enabled'] else 'gray'
				# 폴리곤 그리기
				points = []
				for point in zone['points']:
					points.extend([point[0], point[1]])
				self.canvas.create_polygon(points, outline=color, fill='', width=2, dash=(5, 5), tags="exclusion_zone")

				# 영역 번호 표시
				if zone['points']:
					center_x = sum(p[0] for p in zone['points']) / len(zone['points'])
					center_y = sum(p[1] for p in zone['points']) / len(zone['points'])
					self.canvas.create_text(center_x, center_y, text=f"제외영역 {i+1}", fill=color, font='Arial 10 bold', tags="exclusion_zone")

		# 현재 그리고 있는 제외 영역 표시
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
		path = self.make_path(self.im_fn)
		origin_path = 'original_backup/JPEGImages/'+path
		if os.path.exists(origin_path):
			self.img = Image.open(origin_path)
			self.img.save(self.im_fn)			
			origin_path = origin_path.replace('JPEGImages','labels')
			origin_path = origin_path.replace('.jpg','.txt')
			origin_path = origin_path.replace('.png','.txt')
			shutil.copyfile(origin_path, self.gt_fn)
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
		except:
			print("Not Exist Bbox")
		return

	def on_key_down(self, event):
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
		except:
			print("Not Exist Bbox")
		return

	def on_key_left(self, event):
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
		except:
			print("Not Exist Bbox")
		return

	def on_key_right(self, event):
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
		except:
			print("Not Exist Bbox")
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
		for key, button in self.key_button_map.items():
			if key:  # 키가 빈 값이 아닌 경우에만 바인딩
				self.canvas.bind(key, lambda event, btn=button: 
					self.change_class(self.button_class_map[btn]))
		
		return
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

	def goodbye():
		fname, ext = os.path.splitext(_dir_goodbye)
		if ext == '.txt' :
			with open(self._dir, "r") as infile:
				lines = infile.readlines()

			with open(self._dir, "wt") as outfile:
				for pos, line in enumerate(lines):					
					line = line.replace('/s_mnt/253/','//192.168.79.253/')
					line = line.replace('\n','')
					if os.path.exists(line) is False :
						line = line.replace('//192.168.79.253/','/s_mnt/253/')
						line = line.replace('.png','.png\n')
						line = line.replace('.jpg','.jpg\n')
						outfile.write(line)
		print("GTGEN_Tool Exited.\n")
		os.startfile(BASE_DIR + "RemoveDefaultdll.exe")
		return
	atexit.register(goodbye)
	
	def change_class(self, clsid):
		if self.selid < 0:
			return
		
		# 클래스 인덱스가 유효한지 확인
		if 0 <= clsid < len(class_name):
			# 선택된 바운딩 박스의 클래스 이름을 업데이트
			self.bbox[self.selid][1] = class_name[clsid]
			
			# pre_rc가 있는 경우 업데이트
			if self.pre_rc is not None:
				self.pre_rc[1] = class_name[clsid]
			
			# 화면에 바운딩 박스 다시 그리기
			self.draw_bbox()
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
		new_gt_fn = new_im_fn.replace('.jpg','.txt')
		new_gt_fn = new_gt_fn.replace('.png','.txt')
		new_gt_fn = new_gt_fn.replace('JPEGImages','labels')
		os.rename(self.im_fn, new_im_fn)
		os.rename(self.gt_fn, new_gt_fn)
		self.im_fn = new_im_fn  
		self.gt_fn = new_gt_fn
		self.imlist[self.ci] = new_im_fn
		self.ci += 1
		if self.ci >= len(self.imlist) : self.ci = len(self.imlist) - 1
		return

	def delete_current_file(self):
		#var = tk.messagebox.askquestion("Confirm", "Do you want to really delete file?")
		#if var == 'yes':
		d_path = 'original_backup/JPEGImages/'			
		if not(os.path.isdir(d_path)):
			os.makedirs(os.path.join(d_path))
		if not(os.path.isdir('original_backup/labels/')):
			os.makedirs(os.path.join('original_backup/labels'))
		img_path = d_path + self.make_path(self.im_fn)
		curimg = self.im_fn.replace('\\','/')		
		img = Image.open(curimg)
		img.save(img_path)
		gt_fn = self.make_path(self.gt_fn)
		f = open("original_backup/labels/"+gt_fn, 'wt')
		box = copy.deepcopy(self.bbox)
		for rc in box:
			f.write(' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n')
		
		os.remove(self.im_fn)
		os.remove(self.gt_fn) if os.path.exists(self.gt_fn) else None
		self.imlist = self.imlist[:self.ci] + self.imlist[self.ci+1:]
		if self.ci >= len(self.imlist):
			self.ci -= 1

		if len(self.imlist) > 0:
			self.img_slider.config(to=len(self.imlist))
			self.img_slider.set(self.ci + 1)
			self.slider_info.config(text=f"{self.ci+1}/{len(self.imlist)}")
		self.pi = -1
		self.draw_image()
		return

	def zoom(self, is_zoom_in):
		self.pi = -1
		self.zoom_ratio += (0.1 if is_zoom_in else -0.1)
		if self.zoom_ratio < 0.1:  # 최소 줌 비율 설정
			self.zoom_ratio = 0.1
		print('zoom: %d' % int(self.zoom_ratio*100))
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
		
		try:
			# 백업 디렉토리 확인 및 생성
			d_path = 'original_backup/JPEGImages/'
			if not(os.path.isdir(d_path)):
				os.makedirs(os.path.join(d_path))
			if not(os.path.isdir('original_backup/labels/')):
				os.makedirs(os.path.join('original_backup/labels'))
			
			# 이미지 백업 생성
			img_path = d_path + self.make_path(self.im_fn)
			if not os.path.exists(img_path):
				shutil.copyfile(self.im_fn, img_path)
			
			# 라벨 백업 생성
			gt_path = "original_backup/labels/"+self.make_path(self.gt_fn)
			if not os.path.exists(gt_path):
				shutil.copyfile(self.gt_fn, gt_path)
			
			# === 메모리상에서 마스킹 적용 ===
			# 현재 이미지를 배열로 변환하여 작업 배열 생성
			self.original_img_array = array(im.copy())
			self.current_img_array = array(im.copy())
			
			# 저장된 마스킹 정보 적용
			self.current_img_array[self.masking] = [255, 0, 255]
			self.is_masking_dirty = True  # 저장 필요 플래그 설정
			
			# 마스킹과 겹치는 라벨 삭제 옵션이 켜져 있는 경우
			if self.remove_overlapping_labels.get():
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
					
					# 겹치는 라벨 삭제
					self.remove_labels_overlapping_with_mask(mask_area)
			
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
		else                             : self.write_bbox(); self.draw_image()

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
			mask_info_file = self.im_fn.replace('.jpg', '_mask.npz').replace('.png', '_mask.npz')
			
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
		mask_info_file = self.im_fn.replace('.jpg', '_mask.npz').replace('.png', '_mask.npz')
		
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
			d_path = 'original_backup/JPEGImages/'
			if not os.path.isdir(d_path):
				os.makedirs(os.path.join(d_path))
			if not os.path.isdir('original_backup/labels/'):
				os.makedirs(os.path.join('original_backup/labels/'))
				
			img_path = d_path + self.make_path(self.im_fn)
			if not os.path.exists(img_path):
				self.img = Image.open(self.im_fn)
				path = self.make_path(self.im_fn)
				img_path = 'original_backup/JPEGImages/'+path
				self.img.save(img_path)
				
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
		"""전역 키 이벤트 핸들러"""
		focused_widget = self.master.focus_get()
		
		# 현재 포커스가 입력 필드에 있는 경우 단축키 처리하지 않음
		entry_widgets = [
			self.start_frame_entry, 
			self.end_frame_entry,
			self.delete_start_frame_entry, 
			self.delete_end_frame_entry,
			self.label_start_frame_entry, 
			self.label_end_frame_entry
		]
		
		if focused_widget in entry_widgets:
			# 입력 필드에 포커스가 있으면 일반적인 입력 처리
			return
		
		# 입력 필드에 포커스가 없는 경우 캔버스로 포커스 설정 후 키 이벤트 처리
		if focused_widget != self.canvas:
			self.canvas.focus_set()

		if event.char == 'p':
			print("글로벌 핸들러: p 키 감지됨")
			self.on_polygon_masking_key(event)
			return "break"  # 이벤트 전파 중지
    
		elif event.char == 'h':
			print("글로벌 핸들러: h 키 감지됨")
			self.on_close_polygon_key(event)
			return "break"  # 이벤트 전파 중지
		if focused_widget != self.canvas:
			self.canvas.focus_set()
		# 기존의 on_key 메서드 호출
		if self.polygon_masking or self.bbox_masking or self.mouse_masking:
				# 캔버스에 포커스 설정만 하고 on_key는 호출하지 않음
			if focused_widget != self.canvas:
				self.canvas.focus_set()
			return
		
		# 일반 모드일 때만 on_key 호출
		if focused_widget != self.canvas:
			self.canvas.focus_set()
		# 기존의 on_key 메서드 호출
		if event.char == keysetting[29]:  # 마스킹 키
			return  # 이벤트 전파 중지
		self.on_key(event)
	def improve_key_bindings(self):
		"""캔버스의 키 입력 이벤트 우선순위 설정"""
		# 기존의 키 바인딩을 유지하되 캔버스 포커스 설정 강화
		self.master.bind_all("<Key>", self.global_key_handler)

	def on_key(self, event):
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
			self.ci += 1
			self.bbox = bboxtmp
			copyflag = True
		elif ckey == keysetting[5]:
			self.ci = 0
		elif ckey == keysetting[6]:
			self.ci = len(self.imlist)
		elif ckey == keysetting[7]:
			self.load_bbox()
		elif ckey == keysetting[8]:
			self.delete_current_file()
		elif ckey == keysetting[14]:
			self.zoom(True)
		elif ckey == keysetting[15]:
			self.zoom(False)
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
		elif ckey == keysetting[32]:
			self.l_region = True; self.load_masking()
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

	def on_mouse_right_click(self, event):
		"""우클릭 이벤트 처리"""
		x, y = self.get_canvas_coordinates(event)

		# 제외 영역 그리기 모드에서 우클릭 시 폴리곤 완성
		if self.exclusion_zone_mode and len(self.exclusion_zone_points) >= 3:
			# 폴리곤 완성 (전역 영역에 추가)
			self.exclusion_zone_manager.add_zone(self.exclusion_zone_points, use_global=True)
			self.exclusion_zone_manager.save_global_zones()
			messagebox.showinfo("제외 영역 추가", f"전역 제외 영역이 추가되었습니다.\n점 개수: {len(self.exclusion_zone_points)}")
			self.exclusion_zone_mode = False
			self.exclusion_zone_points = []
			self.draw_bbox()  # 화면 갱신
			return

	def on_mouse_down(self, event):
		x, y = self.get_canvas_coordinates(event)

		# 제외 영역 그리기 모드
		if self.exclusion_zone_mode:
			# 첫 점을 다시 클릭했는지 확인 (폴리곤 닫기)
			if len(self.exclusion_zone_points) >= 3:
				first_point = self.exclusion_zone_points[0]
				# 첫 점 근처 클릭 확인 (10픽셀 이내)
				if ((x - first_point[0])**2 + (y - first_point[1])**2) <= 100:
					# 폴리곤 완성 (전역 영역에 추가)
					self.exclusion_zone_manager.add_zone(self.exclusion_zone_points, use_global=True)
					self.exclusion_zone_manager.save_global_zones()
					messagebox.showinfo("제외 영역 추가", f"전역 제외 영역이 추가되었습니다.\n점 개수: {len(self.exclusion_zone_points)}")
					self.exclusion_zone_mode = False
					self.exclusion_zone_points = []
					self.draw_bbox()  # 화면 갱신
					return

			# 점 추가
			self.exclusion_zone_points.append((x, y))
			self.draw_bbox()  # 화면 갱신
			return

		if self.bbox_crop:
			self.area = [x, y, x+10, y+10]
			self.bbox_move_start_pt = [x, y]
			d_path = 'original_backup/JPEGImages/'            
			if not(os.path.isdir(d_path)):
				os.makedirs(os.path.join(d_path))
			if not(os.path.isdir('original_backup/labels/')):
				os.makedirs(os.path.join('original_backup/labels'))
			img_path = d_path + self.make_path(self.im_fn)
			if not os.path.exists(img_path):
				self.img = Image.open(self.im_fn)
				path = self.make_path(self.im_fn)
				img_path = 'original_backup/JPEGImages/'+path
				self.img.save(img_path)
				gt_fn = self.make_path(self.gt_fn)
				f = open("original_backup/labels/"+gt_fn, 'wt')
				box = copy.deepcopy(self.bbox)
				for rc in box:
					f.write(' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n')
			else:
				self.img = Image.open(self.im_fn)
		elif self.bbox_add:
			for rc in self.bbox: rc[0] = False
			#self.bbox.append([True, class_name[0], -1, x, y, x+10, y+10])
			default_class_name = self.get_default_class_name_for_new_bbox()
			self.bbox.append([True, default_class_name, -1, x, y, x+10, y+10])
			self.selid = len(self.bbox) - 1
			self.bbox_resize_anchor = ('se', )

			self.draw_bbox()
		elif self.bbox_masking:
			self.m_area = [x, y, x+10, y+10]
			self.bbox_move_start_pt = [x, y]
			d_path = 'original_backup/JPEGImages/'
			if not(os.path.isdir(d_path)):
				os.makedirs(os.path.join(d_path))
			if not(os.path.isdir('original_backup/labels/')):
				os.makedirs(os.path.join('original_backup/labels'))
			img_path = d_path + self.make_path(self.im_fn)
			if not os.path.exists(img_path):
				self.img = Image.open(self.im_fn)
				path = self.make_path(self.im_fn)
				img_path = 'original_backup/JPEGImages/'+path
				self.img.save(img_path)
			gt_fn = self.make_path(self.gt_fn)
			f = open("original_backup/labels/"+gt_fn, 'wt')
			box = copy.deepcopy(self.bbox)
			for rc in box:
				f.write(' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n')
		elif self.mouse_masking:
			self.bbox_move_start_pt = [x, y]
			point_size = max(3, int(3 * self.zoom_ratio))
			# self.canvas.create_rectangle([x-3, y-3, x+3, y+3], fill='magenta2', outline='', tags='masking_m')
			self.canvas.create_rectangle(
            [x-point_size, y-point_size, x+point_size, y+point_size], 
            fill='magenta2', outline='', tags='masking_m'
        	)
			self.m_masking_img([x, y])
			d_path = 'original_backup/JPEGImages/'
			if not(os.path.isdir(d_path)):
				os.makedirs(os.path.join(d_path))
			if not(os.path.isdir('original_backup/labels/')):
				os.makedirs(os.path.join('original_backup/labels'))
			img_path = d_path + self.make_path(self.im_fn)
			if not os.path.exists(img_path):
				self.img = Image.open(self.im_fn)
				path = self.make_path(self.im_fn)
				img_path = 'original_backup/JPEGImages/'+path
				self.img.save(img_path)
			gt_fn = self.make_path(self.gt_fn)
			f = open("original_backup/labels/"+gt_fn, 'wt')
			box = copy.deepcopy(self.bbox)
			for rc in box:
				f.write(' '.join(str(e) for e in self.convert_abs2rel(rc)) + '\n')
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
			if 'anchor'in t:
				self.bbox_resize_anchor = t
			elif self.selid >= 0:
				if self.pt_in_current_rc(x, y):
					self.bbox_move = True
					self.bbox_move_start_pt = [x, y]
				else:
					if event.state & 0x4:  # Ctrl 키가 눌린 상태
						for i in range(len(self.bbox)):
							rc = self.bbox[i]
							if x in range(int(rc[3]), int(rc[5])) and y in range(int(rc[4]), int(rc[6])):
								self.toggle_multi_selection(i)
								return
					else:
						for i in range(len(self.bbox)):
							rc = self.bbox[i]
							if x in range(int(rc[3]), int(rc[5])) and y in range(int(rc[4]), int(rc[6])):
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
		x, y = self.get_canvas_coordinates(event)
    
		for i in range(len(self.bbox)):
			rc = self.bbox[i]
			if x in range(rc[3], rc[5]) and y in range(rc[4], rc[6]):
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
		
		# 백업 생성
		d_path = 'original_backup/JPEGImages/'
		if not os.path.isdir(d_path):
			os.makedirs(os.path.join(d_path))
		if not os.path.isdir('original_backup/labels/'):
			os.makedirs(os.path.join('original_backup/labels/'))
		
		img_path = d_path + self.make_path(self.im_fn)
		if not os.path.exists(img_path):
			shutil.copyfile(self.im_fn, img_path)
		
		gt_path = "original_backup/labels/" + self.make_path(self.gt_fn)
		if not os.path.exists(gt_path):
			shutil.copyfile(self.gt_fn, gt_path)
		
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

		# 화면 표시
		display_img = Image.fromarray(self.current_img_array)
		self.imsize = [(int)(i * self.zoom_ratio) for i in display_img.size]
		resized_img = display_img.resize(self.imsize, Image.LANCZOS)
		
		self.canvas.delete("img")
		self.canvas.image = ImageTk.PhotoImage(resized_img)
		self.canvas.create_image(0, 0, image=self.canvas.image, anchor='nw', tags="img")
		
		# 선택 상태 업데이트
		self.selid = -1 if len(self.bbox) == 0 else 0
		if self.bbox and self.selid >= 0:
			for i in range(len(self.bbox)):
				self.bbox[i][0] = (i == self.selid)
			
			# 남은 라벨들만 그리기
			self.canvas.delete("bbox")
			self.canvas.delete("anchor")  
			self.canvas.delete("clsname")
			
			for i, box in enumerate(self.bbox):
				self.draw_bbox_rc(box, i)
		
		print("라벨이 마스킹으로 변환되었습니다.")
	def on_mouse_up(self, event):
		x, y = self.get_canvas_coordinates(event)
		
		if self.bbox_crop: 
			self.canvas.create_rectangle(self.area[0], self.area[1], self.area[2], self.area[3], tags="crop")
			self.crop_img()
		elif self.bbox_masking:
			self.canvas.delete("masking")
			self.canvas.create_rectangle(self.m_area[0], self.m_area[1], self.m_area[2], self.m_area[3], outline='', fill='magenta2')
			self.masking_img()
		self.bbox_add = False
		self.cross_line = False
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
		return

	def draw_cross_line(self, event):
		self.canvas.delete("crossline")
		if self.cross_line:
			self.canvas.create_line(0, event.y, self.imsize[0], event.y, fill="red", dash=(1,1), tags="crossline")
			self.canvas.create_line(event.x, 0, event.x, self.imsize[1], fill="red", dash=(1,1), tags="crossline")
		return

	def on_mouse_move(self, event):
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
			rc = self.bbox[self.selid][3:]
			a = self.bbox_resize_anchor
			self.cross_line = True
			if   'nw' in a: rc[0] = x; rc[1] = y
			elif 'n'  in a:           rc[1] = y
			elif 'ne' in a: rc[2] = x; rc[1] = y
			elif 'e'  in a: rc[2] = x
			elif 'se' in a: rc[2] = x; rc[3] = y
			elif 's'  in a:           rc[3] = y
			elif 'sw' in a: rc[0] = x; rc[3] = y
			elif 'w'  in a: rc[0] = x
			if rc[0] >= 0 and rc[1] >= 0 and rc[2] < self.imsize[0] and rc[3] < self.imsize[1]:
				self.bbox[self.selid][3:] = self.bound_box_coord(rc)
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
		button.pack(side=tk.LEFT, padx=0)
		
		# 우클릭 이벤트 바인딩
		button.bind("<Button-3>", lambda event, btn=button, idx=class_idx: 
					self.show_class_menu(event, btn, idx))
		
		# 버튼과 클래스 인덱스 매핑 저장
		self.button_class_map[button] = class_idx
		
		# 키 매핑 저장 (키가 지정된 경우)
		if key is not None:
			self.key_button_map[key] = button
		
		return button

	def show_class_menu(self, event, button, current_idx):
		"""버튼 우클릭 시 클래스 선택 메뉴 표시"""
		menu = tk.Menu(self.master, tearoff=0)
		
		# 검색 옵션 추가
		menu.add_command(label="🔍 Search Classes...", 
						command=lambda: self.open_class_search_dialog(button))
		menu.add_separator()
		
		# 클래스 그룹화 (가독성을 위해)
		groups = {
			"Person": [0, 1, 2,3],  # person, slip, head, helmet, gasmask, Drum, sitting
			"Vehicles": [6,7,8],  # bicycle, car, motorbike, aeroplane, bus, train, truck, boat, van
			"Traffic": [15, 16, 17, 18],  # trafficlight, firehydrant, stop sign, parking meter
			"Animals": [13,14],  # bird, cat, dog, etc.
			"Accessories": [11,12]  # backpack, umbrella, handbag, tie, suitcase
		}
		
		# 각 그룹의 하위 메뉴 생성
		for group_name, indices in groups.items():
			submenu = tk.Menu(menu, tearoff=0)
			for idx in indices:
				if idx < len(class_name):
					submenu.add_command(
						label=f"{idx}: {class_name[idx]}", 
						command=lambda btn=button, idx=idx: self.set_button_class(btn, idx)
					)
			menu.add_cascade(label=group_name, menu=submenu)
		
		# 메뉴 표시
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()

	def set_button_class(self, button, class_idx):
		"""버튼의 클래스 ID 변경"""
		if 0 <= class_idx < len(class_name):
			# 버튼 텍스트 변경
			button.config(text=class_name[class_idx])
			
			# 버튼 명령 업데이트
			button.config(command=lambda idx=class_idx: self.change_class(idx))
			
			# 매핑 업데이트
			self.button_class_map[button] = class_idx

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
		"""폴리곤과 겹치는 라벨 삭제"""
		if not hasattr(self, 'saved_polygon_points') or not self.saved_polygon_points:
			return
		
		if not self.bbox:
			return
		
		# 삭제할 라벨 인덱스 리스트 (역순으로 삭제하기 위해)
		to_remove = []
		
		# 폴리곤 영역의 바운딩 박스 계산 (간단한 접근)
		min_x = min(p[0] for p in self.saved_polygon_points)
		min_y = min(p[1] for p in self.saved_polygon_points)
		max_x = max(p[0] for p in self.saved_polygon_points)
		max_y = max(p[1] for p in self.saved_polygon_points)
		
		# 마스킹 영역 (캔버스 좌표)
		mask_area = [min_x, min_y, max_x, max_y]
		
		# 겹치는 라벨 찾기
		for i, box in enumerate(self.bbox):
			if self.check_bbox_mask_overlap(mask_area, box):
				to_remove.append(i)
		
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
2. '영역 추가' 클릭하여 폴리곤 그리기 모드 활성화
3. 캔버스에서 좌클릭으로 점 추가
4. 우클릭 또는 첫 점을 다시 클릭하여 폴리곤 완성
5. '기능 활성화' 체크 시 다음 페이지부터 해당 영역의 라벨 자동 삭제

[클래스 자동 삭제 기능]
1. '자동삭제' 버튼 클릭
2. 삭제할 클래스 선택
3. 다음 페이지부터 해당 클래스의 라벨이 자동으로 삭제됨

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
		dialog.geometry("400x500")
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
				point_count = len(zone['points'])
				listbox.insert(tk.END, f"{status} 영역 {i+1} ({point_count}개 점)")

		refresh_list()

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def add_zone():
			"""제외 영역 추가 모드 활성화"""
			self.exclusion_zone_mode = True
			self.exclusion_zone_points = []
			messagebox.showinfo("제외 영역 추가", "캔버스에서 좌클릭으로 점을 추가하세요.\n우클릭 또는 첫 점을 다시 클릭하면 완성됩니다.")
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

		tk.Button(button_frame, text="영역 추가", command=add_zone, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="삭제", command=remove_zone, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="활성화/비활성화", command=toggle_zone, width=15).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="모두 삭제", command=clear_all, width=10).pack(side=tk.LEFT, padx=2)

		tk.Button(dialog, text="닫기", command=dialog.destroy, width=10).pack(pady=5)

	def manage_auto_delete_classes(self):
		"""클래스 자동 삭제 관리 다이얼로그"""
		dialog = tk.Toplevel(self.master)
		dialog.title("클래스 자동 삭제 관리")
		dialog.geometry("400x500")
		dialog.transient(self.master)
		dialog.grab_set()

		# 설명 레이블
		tk.Label(dialog, text="자동으로 삭제할 클래스를 선택하세요", font=("맑은 고딕", 10, "bold")).pack(pady=10)
		tk.Label(dialog, text="(다음 페이지부터 자동 삭제됨)", fg="red").pack()

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

		# 각 클래스에 대한 체크박스 생성
		class_vars = {}
		for cls in self.class_config_manager.classes:
			class_id = cls['id']
			class_name = cls['name']

			var = tk.BooleanVar()
			var.set(self.auto_delete_manager.is_class_marked_for_deletion(class_id))
			class_vars[class_id] = var

			chk = tk.Checkbutton(
				scrollable_frame,
				text=f"{class_name} (ID: {class_id})",
				variable=var,
				font=("맑은 고딕", 10)
			)
			chk.pack(anchor='w', padx=10, pady=2)

		canvas.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		# 버튼 프레임
		button_frame = tk.Frame(dialog)
		button_frame.pack(pady=10)

		def save_and_close():
			"""설정 저장하고 닫기"""
			# 현재 선택 상태를 manager에 반영
			self.auto_delete_manager.delete_class_ids.clear()
			for class_id, var in class_vars.items():
				if var.get():
					self.auto_delete_manager.delete_class_ids.add(class_id)

			self.auto_delete_manager.save_config()

			deleted_classes = [self.class_config_manager.classes[i]['name'] for i in self.auto_delete_manager.delete_class_ids if i < len(self.class_config_manager.classes)]
			if deleted_classes:
				messagebox.showinfo("저장 완료", f"다음 클래스가 자동 삭제로 설정되었습니다:\n" + ", ".join(deleted_classes))
			else:
				messagebox.showinfo("저장 완료", "자동 삭제 클래스가 없습니다.")

			dialog.destroy()

		def select_all():
			"""모두 선택"""
			for var in class_vars.values():
				var.set(True)

		def deselect_all():
			"""모두 선택 해제"""
			for var in class_vars.values():
				var.set(False)

		tk.Button(button_frame, text="모두 선택", command=select_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="모두 해제", command=deselect_all, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="저장", command=save_and_close, width=10).pack(side=tk.LEFT, padx=2)
		tk.Button(button_frame, text="취소", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=2)

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

		classes, config_filename = dialog.show()

		if classes is not None:
			# 설정 저장
			self.class_config_manager.save_config(classes, config_filename)
			messagebox.showinfo("클래스 설정 변경",
				f"클래스 설정이 저장되었습니다.\n설정 파일: {self.class_config_manager.config_file}\n\n변경사항을 적용하려면 프로그램을 재시작해주세요.")

	def on_slider_change(self, value):
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

	def show_class_menu(self, event, button, current_idx):
		"""버튼 우클릭 시 클래스 선택 메뉴 표시"""
		menu = tk.Menu(self.master, tearoff=0)
		
		# 검색 옵션 추가
		menu.add_command(label="🔍 Search Classes...", 
						command=lambda: self.open_class_search_dialog(button))
		menu.add_separator()
		
		# 클래스 그룹화 (가독성을 위해)
		groups = {
			"Person": [0, 1, 2, 3, 4, 5, 6],  # person, slip, head, helmet, gasmask, Drum, sitting
			"Vehicles": [7, 8, 9, 10, 11, 12, 13, 14, 29],  # bicycle, car, motorbike, aeroplane, bus, train, truck, boat, van
			"Traffic": [15, 16, 17, 18],  # trafficlight, firehydrant, stop sign, parking meter
			"Animals": [20, 21, 22, 23, 24, 25, 26, 27, 28],  # bird, cat, dog, etc.
			"Accessories": [30, 31, 32, 33, 34],  # backpack, umbrella, handbag, tie, suitcase
			"Sports": [35, 36, 37, 38, 39, 40, 41, 42, 43, 44],  # frisbee, skis, etc.
			"Kitchen": [45, 46, 47, 48, 49, 50, 51],  # bottle, wine glass, cup, etc.
			"Food": [52, 53, 54, 55, 56, 57, 58, 59, 60, 61],  # banana, apple, etc.
			"Furniture": [19, 62, 63, 64, 65, 66, 67],  # bench, chair, sofa, etc.
			"Electronics": [68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78],  # tv, laptop, etc.
			"Other": [79,80,81,82,83,84,85,89,87,88,89,90,91,92,93,94,95,96,97,98,99]  # book
		}
		
		# 각 그룹의 하위 메뉴 생성
		for group_name, indices in groups.items():
			submenu = tk.Menu(menu, tearoff=0)
			for idx in indices:
				if idx < len(class_name):
					submenu.add_command(
						label=f"{idx}: {class_name[idx]}", 
						command=lambda btn=button, idx=idx: self.set_button_class(btn, idx)
					)
			menu.add_cascade(label=group_name, menu=submenu)
		
		# 메뉴 표시
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()

	def set_button_class(self, button, class_idx):
		if 0 <= class_idx < len(class_name):
			# 버튼 텍스트 변경
			button.config(text=class_name[class_idx])
			
			# 버튼 명령 업데이트 - 클래스 인덱스를 직접 전달
			button.config(command=partial(self.change_class, class_idx))
			
			# 우클릭 이벤트 업데이트
			button.bind("<Button-3>", lambda event: self.show_class_menu(event, button, class_idx))
			self.button_class_map[button] = class_idx


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
				
				progress_bar = tk.ttk.Progressbar(progress, orient="horizontal", length=250, mode="determinate")
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
						target_label_path = target_img_path.replace('JPEGImages', 'labels')
						target_label_path = target_label_path.replace('.jpg', '.txt')
						target_label_path = target_label_path.replace('.png', '.txt')
						
						# Create directory if needed
						target_dir = os.path.dirname(target_label_path)
						if not os.path.exists(target_dir):
							os.makedirs(target_dir)
						
						# Backup if exists
						if os.path.exists(target_label_path):
							backup_dir = 'original_backup/labels/'
							if not os.path.isdir(backup_dir):
								os.makedirs(backup_dir)
							
							backup_path = backup_dir + self.make_path(target_label_path)
							if not os.path.exists(backup_path):
								shutil.copyfile(target_label_path, backup_path)
						
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
						
						# Write annotations
						with open(target_label_path, 'w') as f:
							# Write existing annotations not in selected classes
							f.writelines(existing_annotations)
							
							# Add new annotations of selected classes
							for bbox in annotations_to_copy:
								rel_coords = self.convert_abs2rel(bbox)
								f.write(' '.join(str(e) for e in rel_coords) + '\n')
						
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

		# 현재 선택된 라벨을 복사
		self.copied_label = copy.deepcopy(self.bbox[self.selid])
		
		# 사용자에게 피드백 제공
		label_class = self.copied_label[1]
		bbox_width = self.copied_label[5] - self.copied_label[3]
		bbox_height = self.copied_label[6] - self.copied_label[4]
		
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

		# 복사된 라벨의 사본 생성
		new_label = copy.deepcopy(self.copied_label)
		
		# 선택 상태 초기화 (모든 라벨 선택 해제)
		for rc in self.bbox:
			rc[0] = False
		
		# 새 라벨 추가하고 선택
		new_label[0] = True  # 선택 상태로 설정
		self.bbox.append(new_label)
		self.selid = len(self.bbox) - 1
		
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
		
		# UI 업데이트
		mode_text = "ON" if self.multi_select_mode else "OFF"
		bg_color = "lightblue" if self.multi_select_mode else "lightgray"
		self.multi_mode_btn.config(text=f"다중선택모드: {mode_text}", bg=bg_color)
		
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
		"""다중 선택 정보 표시 업데이트"""
		count = len(self.multi_selected)
		if count > 0:
			selected_classes = []
			for idx in sorted(self.multi_selected):
				if idx < len(self.bbox):
					selected_classes.append(self.bbox[idx][1])
			class_text = ", ".join(set(selected_classes))
			self.multi_info_label.config(text=f"선택된 라벨: {count}개 ({class_text})")
		else:
			self.multi_info_label.config(text="선택된 라벨: 0개")

	def copy_multi_selected(self, event=None):
		"""다중 선택된 라벨들을 복사"""
		if not self.multi_selected:
			messagebox.showwarning("경고", "다중 선택된 라벨이 없습니다.")
			return
		
		# 선택된 라벨들을 복사 변수에 저장
		self.copied_multi_labels = []
		for idx in sorted(self.multi_selected):
			if idx < len(self.bbox):
				self.copied_multi_labels.append(copy.deepcopy(self.bbox[idx]))
		
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
		
		# 모든 라벨 선택 해제
		for rc in self.bbox:
			rc[0] = False
		
		# 복사된 라벨들 추가
		for label in self.copied_multi_labels:
			new_label = copy.deepcopy(label)
			new_label[0] = False  # 선택 해제 상태로 추가
			self.bbox.append(new_label)
		
		self.draw_bbox()
		
		# 피드백 메시지
		count = len(self.copied_multi_labels)
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
    os.startfile(BASE_DIR + "RemoveDefaultdll.exe")
    app = MainApp(wdir)
    return

if __name__=="__main__":
    # 여기서 RemoveDefaultdll.exe 실행 코드 제거
    # os.startfile(BASE_DIR + "RemoveDefaultdll.exe") <- 이 줄 제거
    main()
    sys.exit(0)