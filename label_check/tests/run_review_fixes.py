import importlib
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def install_stub_modules():
    """외부 GUI/PIL/numpy dependency 없이 module import가 가능하도록 최소 stub을 등록합니다."""
    if "tkinter" not in sys.modules:
        ttk_module = types.ModuleType("tkinter.ttk")
        tkinter_module = types.ModuleType("tkinter")
        tkinter_module.TclError = Exception
        tkinter_module.filedialog = types.SimpleNamespace()
        tkinter_module.messagebox = types.SimpleNamespace(
            showwarning=lambda *args, **kwargs: None,
            askyesno=lambda *args, **kwargs: True,
        )
        tkinter_module.ttk = ttk_module
        sys.modules["tkinter"] = tkinter_module
        sys.modules["tkinter.ttk"] = ttk_module

    if "PIL" not in sys.modules:
        pil_module = types.ModuleType("PIL")
        pil_module.Image = types.SimpleNamespace()
        pil_module.ImageTk = types.SimpleNamespace()
        pil_module.ImageDraw = types.SimpleNamespace()
        pil_module.ImageFont = types.SimpleNamespace()
        sys.modules["PIL"] = pil_module

    if "numpy" not in sys.modules:
        sys.modules["numpy"] = types.ModuleType("numpy")


def make_viewer_stub(main_module, label_lines=None):
    label_lines = label_lines or []
    viewer = types.SimpleNamespace()
    viewer.selected_image_labels = []
    viewer.selected_label_info = []
    viewer.selected_full_image_labels = []
    viewer.checklist = []
    viewer.selection_state = types.SimpleNamespace(set=lambda *_args, **_kwargs: None)
    viewer.selection_toggle_texts = {"select_all": "Select All", "clear": "Clear Selection"}
    viewer.selection_toggle_button = types.SimpleNamespace(config=lambda **_kwargs: None)
    viewer.selection_info_label = types.SimpleNamespace(config=lambda **_kwargs: None)
    viewer._update_dataset_info = lambda: None
    viewer.update_selection_info = lambda: main_module.ImageViewer.update_selection_info(viewer)
    viewer.data_mgr = types.SimpleNamespace(get_label_data=lambda _path: list(label_lines))
    viewer._get_selected_info = lambda label_path: main_module.ImageViewer._get_selected_info(viewer, label_path)
    viewer._has_path_selection = lambda label_path: main_module.ImageViewer._has_path_selection(viewer, label_path)
    viewer._sync_selected_image_labels = lambda: main_module.ImageViewer._sync_selected_image_labels(viewer)
    viewer.deselect_all_images = lambda: main_module.ImageViewer.deselect_all_images(viewer)
    viewer._clear_selection_for_view_change = lambda: main_module.ImageViewer._clear_selection_for_view_change(viewer)
    viewer.update_display_called = 0
    viewer.update_display = lambda: setattr(viewer, "update_display_called", viewer.update_display_called + 1)
    return viewer


def run():
    install_stub_modules()

    main_module = importlib.import_module("main")
    label_ops_module = importlib.import_module("label_operations")
    utils_module = importlib.import_module("utils")

    path_a = r"D:\dataset_a\labels\same_name.txt"
    path_b = r"D:\dataset_b\labels\same_name.txt"
    safe_a = utils_module.make_path(path_a)
    safe_b = utils_module.make_path(path_b)
    assert safe_a != safe_b, "make_path should avoid basename collisions"
    assert os.path.join("D", "dataset_a", "labels") in safe_a
    assert os.path.join("D", "dataset_b", "labels") in safe_b

    viewer = make_viewer_stub(
        main_module,
        [
            "0 0.5 0.5 0.2 0.2",
            "0 0.4 0.4 0.1 0.1",
        ],
    )
    widget = types.SimpleNamespace(label_path=r"D:\dataset\labels\sample.txt", line_idx=None)
    main_module.ImageViewer._save_label_info_for_widget(viewer, widget)
    assert viewer.selected_full_image_labels == [widget.label_path]
    assert viewer.selected_image_labels == [widget.label_path]
    assert viewer.selected_label_info == []

    viewer = make_viewer_stub(main_module)
    viewer._updating_display = False
    viewer.selected_image_labels = [r"D:\dataset\labels\sample.txt"]
    viewer.selected_full_image_labels = [r"D:\dataset\labels\sample.txt"]
    viewer.selected_label_info = [{"path": r"D:\dataset\labels\sample.txt", "boxes": [{"line_idx": 0}]}]
    main_module.ImageViewer.on_box_image_mode_changed(viewer)
    assert viewer.selected_image_labels == []
    assert viewer.selected_full_image_labels == []
    assert viewer.selected_label_info == []
    assert viewer.update_display_called == 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        target_a = tmp_path / "a.txt"
        target_b = tmp_path / "b.txt"
        staged_a = tmp_path / "a.tmp.txt"
        staged_b = tmp_path / "b.tmp.txt"

        target_a.write_text("original-a", encoding="utf-8")
        target_b.write_text("original-b", encoding="utf-8")
        staged_a.write_text("updated-a", encoding="utf-8")
        staged_b.write_text("updated-b", encoding="utf-8")

        real_replace = os.replace
        call_count = {"value": 0}

        def flaky_replace(src, dst):
            call_count["value"] += 1
            if call_count["value"] == 2:
                raise OSError("second replace failed")
            return real_replace(src, dst)

        original_module_replace = label_ops_module.os.replace
        label_ops_module.os.replace = flaky_replace
        try:
            try:
                label_ops_module._replace_files_with_rollback(
                    [
                        (str(staged_a), str(target_a)),
                        (str(staged_b), str(target_b)),
                    ]
                )
                raise AssertionError("rollback helper should re-raise replace failure")
            except OSError:
                pass
        finally:
            label_ops_module.os.replace = original_module_replace

        assert target_a.read_text(encoding="utf-8") == "original-a"
        assert target_b.read_text(encoding="utf-8") == "original-b"
        assert not staged_a.exists()
        assert not staged_b.exists()

    class StubParent:
        def __init__(self):
            self.updated = False

        def winfo_exists(self):
            return True

        def update_idletasks(self):
            self.updated = True

    class StubWindow:
        def __init__(self):
            self.master = StubParent()
            self.destroyed = False
            self.grab_released = False
            self.updated = False

        def winfo_exists(self):
            return not self.destroyed

        def grab_release(self):
            self.grab_released = True

        def update_idletasks(self):
            self.updated = True

        def destroy(self):
            self.destroyed = True

    stub_window = StubWindow()
    label_ops_module._safe_destroy_window(stub_window)
    assert stub_window.grab_released is True
    assert stub_window.updated is True
    assert stub_window.destroyed is True
    assert stub_window.master.updated is True

    print("review_fixes: ok")


if __name__ == "__main__":
    run()
