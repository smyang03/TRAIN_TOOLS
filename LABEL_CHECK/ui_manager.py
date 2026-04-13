"""
UI manager for the label check tool.
Keeps layout logic separate from the main viewer and applies a cleaner,
more modern visual style to the Tkinter interface.
"""

import tkinter as tk


PALETTE = {
    "bg": "#f3f6fb",
    "panel": "#ffffff",
    "panel_alt": "#eef3f9",
    "canvas": "#edf2f7",
    "text": "#17212f",
    "muted": "#5b6472",
    "border": "#d8e0ea",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "success": "#0f766e",
    "danger": "#dc2626",
    "danger_bg": "#fee2e2",
}


def _style_label(widget, *, size=9, bold=False, fg=None, bg=None):
    widget.configure(
        bg=bg or PALETTE["panel"],
        fg=fg or PALETTE["text"],
        font=("맑은 고딕", size, "bold" if bold else "normal"),
    )


def _style_button(widget, variant="default", width=None):
    colors = {
        "default": (PALETTE["panel"], PALETTE["text"], PALETTE["panel_alt"]),
        "primary": (PALETTE["accent"], "#ffffff", PALETTE["accent_hover"]),
        "danger": (PALETTE["danger_bg"], PALETTE["danger"], "#fecaca"),
        "muted": (PALETTE["panel_alt"], PALETTE["muted"], "#e3eaf3"),
        "success": ("#d1fae5", PALETTE["success"], "#a7f3d0"),
    }
    bg, fg, active = colors[variant]
    widget.configure(
        bg=bg,
        fg=fg,
        activebackground=active,
        activeforeground=fg,
        relief=tk.FLAT,
        bd=0,
        padx=10,
        pady=7,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        font=("맑은 고딕", 9, "bold"),
    )
    if width is not None:
        widget.configure(width=width)


def _style_checkbutton(widget):
    widget.configure(
        bg=PALETTE["panel"],
        fg=PALETTE["text"],
        activebackground=PALETTE["panel"],
        activeforeground=PALETTE["text"],
        selectcolor="#fbfdff",
        relief=tk.FLAT,
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        font=("맑은 고딕", 9),
    )


def _style_radiobutton(widget):
    widget.configure(
        bg=PALETTE["panel"],
        fg=PALETTE["text"],
        activebackground=PALETTE["panel"],
        activeforeground=PALETTE["text"],
        selectcolor="#fbfdff",
        relief=tk.FLAT,
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        font=("맑은 고딕", 9),
    )


def _style_entry(widget, width=None):
    widget.configure(
        relief=tk.FLAT,
        bd=0,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        bg="#fbfdff",
        fg=PALETTE["text"],
        font=("맑은 고딕", 9),
        insertbackground=PALETTE["text"],
    )
    if width is not None:
        widget.configure(width=width)


def _style_option_menu(widget):
    widget.configure(
        bg="#fbfdff",
        fg=PALETTE["text"],
        activebackground=PALETTE["panel_alt"],
        activeforeground=PALETTE["text"],
        relief=tk.FLAT,
        bd=0,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        font=("맑은 고딕", 9),
        padx=8,
        pady=3,
        cursor="hand2",
    )
    widget["menu"].config(
        bg="#fbfdff",
        fg=PALETTE["text"],
        activebackground=PALETTE["panel_alt"],
        activeforeground=PALETTE["text"],
        font=("맑은 고딕", 9),
    )


def setup_ui(viewer):
    viewer.root.configure(bg=PALETTE["bg"])
    viewer.main_frame = tk.Frame(viewer.root, bg=PALETTE["bg"])
    viewer.main_frame.pack(fill="both", expand=True)

    viewer.control_panel_top = tk.Frame(
        viewer.main_frame, bg=PALETTE["panel"], highlightthickness=1, highlightbackground=PALETTE["border"]
    )
    viewer.control_panel_top.pack(fill="x", padx=10, pady=(10, 6), ipady=6)

    viewer.control_panel_bottom = tk.Frame(
        viewer.main_frame, bg=PALETTE["panel"], highlightthickness=1, highlightbackground=PALETTE["border"]
    )
    viewer.control_panel_bottom.pack(fill="x", padx=10, pady=(0, 6), ipady=4)

    basic_frame = tk.Frame(viewer.control_panel_top, bg=PALETTE["panel"])
    basic_frame.pack(side=tk.LEFT, padx=8)

    viewer.load_button = tk.Button(basic_frame, text="Load Data", command=viewer.load_data)
    viewer.load_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.load_button, "primary")

    viewer.file_slice_button = tk.Button(basic_frame, text="File Slice", command=viewer.file_slice)
    viewer.file_slice_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.file_slice_button, "muted")

    class_frame = tk.Frame(basic_frame, bg=PALETTE["panel"])
    class_frame.pack(side=tk.LEFT, padx=10)
    class_label = tk.Label(class_frame, text="Select Class:")
    class_label.pack(side=tk.LEFT, padx=(0, 6))
    _style_label(class_label, size=9, bold=True)

    viewer.class_selector = tk.StringVar(value="Select Class")
    viewer.class_dropdown = tk.OptionMenu(class_frame, viewer.class_selector, "Select Class")
    viewer.class_dropdown.pack(side=tk.LEFT)
    _style_option_menu(viewer.class_dropdown)

    iou_frame = tk.Frame(viewer.control_panel_top, bg=PALETTE["panel"])
    iou_frame.pack(side=tk.LEFT, padx=8)
    iou_label = tk.Label(iou_frame, text="IoU 임계값:")
    iou_label.pack(side=tk.LEFT)
    _style_label(iou_label, size=9, bold=True)

    viewer.iou_threshold_var = tk.DoubleVar(value=0.0)
    iou_slider = tk.Scale(
        iou_frame,
        from_=0.0,
        to=1.0,
        resolution=0.05,
        orient=tk.HORIZONTAL,
        length=120,
        variable=viewer.iou_threshold_var,
        command=lambda _v: viewer.update_iou_value(),
    )
    iou_slider.configure(
        bg=PALETTE["panel"],
        fg=PALETTE["text"],
        troughcolor=PALETTE["panel_alt"],
        activebackground=PALETTE["accent"],
        highlightthickness=0,
        bd=0,
        font=("맑은 고딕", 8),
    )
    iou_slider.pack(side=tk.LEFT)
    viewer.iou_value_label = tk.Label(iou_frame, text="0.00", width=4)
    viewer.iou_value_label.pack(side=tk.LEFT, padx=4)
    _style_label(viewer.iou_value_label, size=9, bold=True)

    control_frame = tk.Frame(viewer.control_panel_top, bg=PALETTE["panel"])
    control_frame.pack(side=tk.LEFT, padx=8)

    viewer.save_button = tk.Button(control_frame, text="Save Label Data", command=viewer.save_labeldata)
    viewer.save_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.save_button, "success")

    viewer.box_image_var = tk.IntVar(value=1)
    viewer.box_image_checkbox = tk.Checkbutton(
        control_frame, text="Box Images", variable=viewer.box_image_var, onvalue=1, offvalue=0, command=viewer.update_display
    )
    viewer.box_image_checkbox.pack(side=tk.LEFT, padx=2)
    viewer.box_image_checkbox.select()
    _style_checkbutton(viewer.box_image_checkbox)

    viewer.keep_aspect_var = tk.IntVar(value=0)
    viewer.keep_aspect_checkbox = tk.Checkbutton(
        control_frame, text="비율 유지", variable=viewer.keep_aspect_var, onvalue=1, offvalue=0, command=viewer.update_display
    )
    viewer.keep_aspect_checkbox.pack(side=tk.LEFT, padx=2)
    _style_checkbutton(viewer.keep_aspect_checkbox)

    viewer.reset_button = tk.Button(control_frame, text="Reset View", command=viewer.reset_view)
    viewer.reset_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.reset_button, "muted")

    selection_frame = tk.Frame(control_frame, bg=PALETTE["panel"])
    selection_frame.pack(side=tk.LEFT, padx=6)
    viewer.selection_state = tk.BooleanVar(value=False)
    viewer.selection_toggle_button = tk.Button(
        selection_frame, text="전체 선택", command=viewer.toggle_all_selection, width=10
    )
    viewer.selection_toggle_button.pack(side=tk.LEFT)
    _style_button(viewer.selection_toggle_button, "primary", width=10)
    viewer.root.bind("<Control-a>", lambda e: viewer.toggle_all_selection())

    viewer.delete_labels_button = tk.Button(control_frame, text="선택 삭제", command=viewer.delete_selected_labels)
    viewer.delete_labels_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.delete_labels_button, "danger")

    viewer.change_class_button = tk.Button(control_frame, text="클래스 변경", command=viewer.change_class_labels)
    viewer.change_class_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.change_class_button, "default")

    viewer.label_to_mask_button = tk.Button(control_frame, text="Label→Mask", command=viewer.convert_label_to_mask)
    viewer.label_to_mask_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.label_to_mask_button, "default")

    viewer.refresh_button = tk.Button(control_frame, text="데이터 리프레시", command=viewer.refresh_data)
    viewer.refresh_button.pack(side=tk.LEFT, padx=2)
    _style_button(viewer.refresh_button, "muted")

    setup_pagination_ui(viewer)

    similar_box_button = tk.Button(viewer.control_panel_top, text="유사 박스 처리", command=viewer.select_similar_boxes)
    similar_box_button.pack(side=tk.LEFT, padx=10)
    _style_button(similar_box_button, "default")

    _setup_overlap_filter_ui(viewer)
    _setup_canvas(viewer)

    viewer._updating_display = False
    viewer.canvas.bind("<Configure>", viewer.on_canvas_configure)
    viewer.canvas.bind_all("<MouseWheel>", viewer.on_mousewheel)
    viewer.class_selector.trace_add("write", viewer.on_class_selector_changed)
    viewer.class_selector.trace_add("write", viewer.on_class_changed)
    viewer.overlap_class_selector.trace_add("write", lambda *args: viewer.data_mgr.reset_overlap_cache())
    viewer.overlap_class_selector.trace_add("write", viewer.on_overlap_selector_changed)
    viewer.root.bind("<Button-1>", viewer.handle_left_click)

    setup_keyboard_events(viewer)
    viewer.add_similar_label_controls()


def _setup_overlap_filter_ui(viewer):
    filter_frame = tk.Frame(viewer.control_panel_bottom, bg=PALETTE["panel"])
    filter_frame.pack(side=tk.LEFT, fill="x", padx=8)

    filter_header_frame = tk.Frame(filter_frame, bg=PALETTE["panel"])
    filter_header_frame.pack(side=tk.TOP, fill="x")

    filter_title = tk.Label(filter_header_frame, text="겹침 필터:")
    filter_title.pack(side=tk.LEFT, padx=4)
    _style_label(filter_title, size=9, bold=True)

    color_legend_frame = tk.Frame(filter_header_frame, bg=PALETTE["panel"])
    color_legend_frame.pack(side=tk.LEFT, padx=10)
    legend_label = tk.Label(color_legend_frame, text="색상 구분:")
    legend_label.pack(side=tk.LEFT)
    _style_label(legend_label, size=8, fg=PALETTE["muted"])

    for color, desc, iou_range in [
        ("yellow", "낮음", "<0.3"),
        ("orange", "중간", "0.3-0.5"),
        ("red", "높음", "0.5-0.7"),
        ("purple", "매우 높음", ">0.7"),
    ]:
        tk.Frame(color_legend_frame, bg=color, width=15, height=15).pack(side=tk.LEFT, padx=1)
        legend_item = tk.Label(color_legend_frame, text=f"{desc}({iou_range})")
        legend_item.pack(side=tk.LEFT, padx=1)
        _style_label(legend_item, size=7, fg=PALETTE["muted"])

    viewer.ctrl_status_label = tk.Label(viewer.control_panel_bottom, text="Ctrl: ⬛", bg=PALETTE["panel"], fg=PALETTE["muted"])
    viewer.ctrl_status_label.configure(font=("맑은 고딕", 9, "bold"))

    filter_controls_frame = tk.Frame(filter_frame, bg=PALETTE["panel"])
    filter_controls_frame.pack(side=tk.TOP, fill="x")

    target_label = tk.Label(filter_controls_frame, text="대상 클래스:")
    target_label.pack(side=tk.LEFT, padx=4)
    _style_label(target_label, size=9, bold=True)

    viewer.overlap_class_selector = tk.StringVar(value="선택 안함")
    viewer.overlap_class_dropdown = tk.OptionMenu(filter_controls_frame, viewer.overlap_class_selector, "선택 안함")
    viewer.overlap_class_dropdown.pack(side=tk.LEFT, padx=2)
    _style_option_menu(viewer.overlap_class_dropdown)

    viewer.overlap_filter_var = tk.StringVar(value="모두 보기")
    filter_options_frame = tk.Frame(filter_controls_frame, bg=PALETTE["panel"])
    filter_options_frame.pack(side=tk.LEFT, padx=8)

    all_radio = tk.Radiobutton(filter_options_frame, text="모두 보기", variable=viewer.overlap_filter_var, value="모두 보기", command=viewer.update_display)
    all_radio.pack(side=tk.LEFT)
    overlap_radio = tk.Radiobutton(filter_options_frame, text="겹치는 것만", variable=viewer.overlap_filter_var, value="겹치는 것만", command=viewer.update_display)
    overlap_radio.pack(side=tk.LEFT)
    non_overlap_radio = tk.Radiobutton(
        filter_options_frame, text="겹치지 않는 것만", variable=viewer.overlap_filter_var, value="겹치지 않는 것만", command=viewer.update_display
    )
    non_overlap_radio.pack(side=tk.LEFT)
    for widget in (all_radio, overlap_radio, non_overlap_radio):
        _style_radiobutton(widget)

    viewer.filter_info_label = tk.Label(filter_controls_frame, text="")
    viewer.filter_info_label.pack(side=tk.LEFT, padx=8)
    _style_label(viewer.filter_info_label, size=9, fg=PALETTE["muted"])

    selection_frame = tk.Frame(viewer.control_panel_bottom, bg=PALETTE["panel"])
    selection_frame.pack(side=tk.RIGHT, padx=8)

    viewer.dataset_info_label = tk.Label(selection_frame, text="")
    viewer.dataset_info_label.pack(side=tk.RIGHT, padx=2)
    _style_label(viewer.dataset_info_label, size=8, fg=PALETTE["muted"])

    viewer.selection_info_label = tk.Label(selection_frame, text="Selected Images: 0", width=18)
    viewer.selection_info_label.pack(side=tk.RIGHT, padx=6)
    _style_label(viewer.selection_info_label, size=9, bold=True)


def _setup_canvas(viewer):
    viewer.canvas_frame = tk.Frame(viewer.main_frame, bg=PALETTE["bg"])
    viewer.canvas_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    viewer.canvas = tk.Canvas(
        viewer.canvas_frame,
        borderwidth=0,
        background=PALETTE["canvas"],
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
    )
    viewer.scrollbar = tk.Scrollbar(viewer.canvas_frame, orient="vertical", command=viewer.canvas.yview)

    viewer.canvas.pack(side="left", fill="both", expand=True)
    viewer.scrollbar.pack(side="right", fill="y")

    viewer.canvas.configure(yscrollcommand=viewer.scrollbar.set)
    viewer.frame = tk.Frame(viewer.canvas, bg=PALETTE["canvas"])
    viewer.canvas_window = viewer.canvas.create_window((0, 0), window=viewer.frame, anchor="nw")


def setup_pagination_ui(viewer):
    viewer.pagination_frame = tk.Frame(viewer.control_panel_bottom, bg=PALETTE["panel"])
    viewer.pagination_frame.pack(side=tk.RIGHT, padx=8)

    page_size_frame = tk.Frame(viewer.pagination_frame, bg=PALETTE["panel"])
    page_size_frame.pack(side=tk.LEFT, padx=(0, 15))

    total_label = tk.Label(page_size_frame, text="전체:")
    total_label.pack(side=tk.LEFT, padx=2)
    _style_label(total_label, size=9, bold=True)

    viewer.total_files_label = tk.Label(page_size_frame, text="0개")
    viewer.total_files_label.pack(side=tk.LEFT, padx=2)
    _style_label(viewer.total_files_label, size=9, bold=True)

    page_size_label = tk.Label(page_size_frame, text=" | 페이지 크기:")
    page_size_label.pack(side=tk.LEFT, padx=(10, 2))
    _style_label(page_size_label, size=9, fg=PALETTE["muted"])

    viewer.page_size_entry = tk.Entry(page_size_frame, justify=tk.CENTER)
    viewer.page_size_entry.insert(0, str(viewer.data_mgr.page_size))
    viewer.page_size_entry.pack(side=tk.LEFT, padx=2)
    _style_entry(viewer.page_size_entry, width=5)

    apply_button = tk.Button(page_size_frame, text="적용", command=viewer.apply_page_size)
    apply_button.pack(side=tk.LEFT, padx=2)
    _style_button(apply_button, "primary", width=4)

    tk.Frame(viewer.pagination_frame, width=2, bg=PALETTE["border"]).pack(side=tk.LEFT, fill="y", padx=10)

    viewer.prev_button = tk.Button(viewer.pagination_frame, text="◀", command=viewer.prev_page)
    viewer.prev_button.pack(side=tk.LEFT)
    _style_button(viewer.prev_button, "muted", width=3)

    page_input_frame = tk.Frame(viewer.pagination_frame, bg=PALETTE["panel"])
    page_input_frame.pack(side=tk.LEFT, padx=3)

    viewer.page_entry = tk.Entry(page_input_frame, justify=tk.CENTER)
    viewer.page_entry.pack(side=tk.LEFT)
    _style_entry(viewer.page_entry, width=5)

    viewer.total_pages_label = tk.Label(page_input_frame, text="/0")
    viewer.total_pages_label.pack(side=tk.LEFT, padx=2)
    _style_label(viewer.total_pages_label, size=9, fg=PALETTE["muted"])

    viewer.page_range_label = tk.Label(page_input_frame, text="(0-0)")
    viewer.page_range_label.pack(side=tk.LEFT, padx=5)
    _style_label(viewer.page_range_label, size=9, fg=PALETTE["muted"])

    move_button = tk.Button(viewer.pagination_frame, text="이동", command=viewer.go_to_entered_page)
    move_button.pack(side=tk.LEFT, padx=3)
    _style_button(move_button, "primary", width=4)

    viewer.next_button = tk.Button(viewer.pagination_frame, text="▶", command=viewer.next_page)
    viewer.next_button.pack(side=tk.LEFT)
    _style_button(viewer.next_button, "muted", width=3)

    viewer.page_entry.bind("<Return>", lambda event: viewer.go_to_entered_page())
    update_pagination_controls(viewer)


def update_pagination_controls(viewer):
    dm = viewer.data_mgr
    viewer.page_entry.delete(0, tk.END)
    viewer.page_entry.insert(0, str(dm.current_page + 1))
    viewer.total_pages_label.config(text=f"/{dm.total_pages}")

    viewer.prev_button.config(state="normal" if dm.current_page > 0 else "disabled")
    viewer.next_button.config(state="normal" if dm.current_page < dm.total_pages - 1 else "disabled")

    if dm.total_pages > 0:
        start = dm.current_page * dm.page_size + 1
        selected_class = viewer.class_selector.get()
        if selected_class != "Select Class":
            try:
                class_idx = int(float(selected_class))
                class_images = dm.get_class_images(class_idx)
                total = len(class_images)
                end = min(start + dm.page_size - 1, total)
                viewer.page_range_label.config(text=f"({start}-{end})")
                viewer.total_files_label.config(text=f"{total}개")
            except (ValueError, IndexError):
                viewer.page_range_label.config(text="(0-0)")
        else:
            viewer.page_range_label.config(text="(0-0)")


def setup_keyboard_events(viewer):
    viewer.root.bind("<KeyPress>", viewer.on_key_press)
    viewer.root.bind("<KeyRelease>", viewer.on_key_release)
    viewer.root.bind("<KeyPress-Shift_L>", viewer.on_shift_press)
    viewer.root.bind("<KeyRelease-Shift_L>", viewer.on_shift_release)
    viewer.root.bind("<KeyPress-Shift_R>", viewer.on_shift_press)
    viewer.root.bind("<KeyRelease-Shift_R>", viewer.on_shift_release)
    viewer.root.bind("<KeyPress-Caps_Lock>", viewer.on_caps_lock_press)
    viewer.root.bind("<KeyRelease-Caps_Lock>", viewer.on_caps_lock_release)


def create_tooltip(viewer, widget, text):
    if viewer.tooltip_window:
        viewer.tooltip_window.destroy()

    x = widget.winfo_rootx() + widget.winfo_width() + 5
    y = widget.winfo_rooty()

    viewer.tooltip_window = tw = tk.Toplevel(viewer.root)
    tw.wm_overrideredirect(True)

    screen_width = viewer.root.winfo_screenwidth()
    if x + 220 > screen_width:
        x = widget.winfo_rootx() - 220

    tw.wm_geometry(f"+{x}+{y}")

    label = tk.Label(
        tw,
        text=text,
        justify=tk.LEFT,
        background="#fffaf0",
        foreground=PALETTE["text"],
        relief=tk.SOLID,
        borderwidth=1,
        font=("맑은 고딕", 9),
    )
    label.pack(ipadx=6, ipady=4)

    viewer.tooltip_timer = viewer.root.after(3000, viewer.remove_tooltip)


def remove_tooltip(viewer):
    if viewer.tooltip_timer:
        viewer.root.after_cancel(viewer.tooltip_timer)
        viewer.tooltip_timer = None
    if viewer.tooltip_window:
        viewer.tooltip_window.destroy()
        viewer.tooltip_window = None


def refresh_bindings(viewer):
    viewer._last_click_time = 0

    try:
        viewer.canvas.unbind_all("<MouseWheel>")
        viewer.root.unbind_all("<MouseWheel>")
        viewer.root.unbind_all("<KeyPress>")
        viewer.root.unbind_all("<KeyRelease>")
        viewer.root.unbind_all("<KeyPress-Shift_L>")
        viewer.root.unbind_all("<KeyRelease-Shift_L>")
        viewer.root.unbind_all("<KeyPress-Shift_R>")
        viewer.root.unbind_all("<KeyRelease-Shift_R>")
        viewer.root.unbind_all("<KeyPress-Caps_Lock>")
        viewer.root.unbind_all("<KeyRelease-Caps_Lock>")
        viewer.root.unbind_all("<Button-1>")
    except Exception:
        pass

    viewer.canvas.bind_all("<MouseWheel>", viewer.on_mousewheel)
    viewer.canvas.bind("<Configure>", viewer.on_canvas_configure)
    viewer.root.bind("<Button-1>", viewer.handle_left_click)
    setup_keyboard_events(viewer)

    for widget in viewer.frame.winfo_children():
        if isinstance(widget, tk.Label) and hasattr(widget, "label_path"):
            from utils import convert_labels_to_jpegimages

            img_path = convert_labels_to_jpegimages(widget.label_path)
            viewer.setup_drag_select_events(widget, widget.label_path)
            widget.bind(
                "<Button-3>",
                lambda event, ip=img_path, lp=widget.label_path, li=getattr(widget, "line_idx", None): viewer.show_full_image(ip, lp, li),
            )
