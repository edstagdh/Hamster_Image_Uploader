import sys
import asyncio
import json
import copy
from pathlib import Path
from loguru import logger
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QFileDialog, QMessageBox, QCheckBox, QMenuBar, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon

from uploader import hamster_upload_single_image  # your async upload function

# ---------------------- Version ----------------------
VERSION_FILE = Path(__file__).parent / "VERSION"

try:
    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        __version__ = f.read().strip()
except Exception:
    __version__ = "unknown"

# ---------------------- Themes ----------------------
DEFAULT_THEMES = {
    "light": {
        "stylesheet": (
            "QWidget { background: #ffffff; color: #000000; }\n"
            "QTextEdit { background: #b3b3b3; color: #000000; border: 2px solid #ccc; }\n"
            "QMenuBar, QMenu, QMenu::item { background: #f7f7f7; color: #000000; }\n"
            "QMenuBar::item:selected { background: #e0e0e0; color: #000000; }\n"
            "QMenu::item:selected { background: #e0e0e0; color: #000000; }\n"
            "QPushButton { background: #eaeaea; color: #000000; }\n"
            "QComboBox { background: #ffffff; color: #000000; border: 1px solid #ccc; }\n"
            "QComboBox QAbstractItemView { background: #ffffff; color: #000000; "
                "selection-background-color: #e0e0e0; selection-color: #000000; }"
        ),
        "log_colors": {
            "info": "#000000",
            "success": "#2e7d32",
            "warn": "#f57c00",
            "error": "#d32f2f"
        }
    },
    "dark": {
        "stylesheet": (
            "QWidget { background: #282828; color: #eaeaea; }\n"
            "QTextEdit { background: #404040; color: #eaeaea; border: 2px solid #333; }\n"
            "QMenuBar, QMenu, QMenu::item { background: #1b1b1b; color: #eaeaea; }\n"
            "QMenuBar::item:selected { background: #333333; color: #ffffff; }\n"
            "QMenu::item:selected { background: #444444; color: #ffffff; }\n"
            "QPushButton { background: #2b2b2b; color: #eaeaea; }\n"
            "QComboBox { background: #1e1e1e; color: #eaeaea; border: 1px solid #444; }\n"
            "QComboBox QAbstractItemView { background: #1e1e1e; color: #eaeaea; "
                "selection-background-color: #333333; selection-color: #ffffff; }"
        ),
        "log_colors": {
            "info": "#e0e0e0",
            "success": "#2e7d32",
            "warn": "#f57c00",
            "error": "#d32f2f"
        }
    }
}

# ---------------------- Worker Thread ----------------------
class UploadWorker(QThread):
    log_signal = Signal(str, str)
    finished_signal = Signal()

    def __init__(self, files, album_id, api_key, site_url, mode, precheck_results):
        super().__init__()
        self.files = files
        self.album_id = album_id
        self.api_key = api_key
        self.site_url = site_url
        self.mode = mode
        self._is_running = True
        self.precheck_results = precheck_results if precheck_results else {}

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.async_upload())
        except Exception as e:
            self.log_worker_actions(f"❌ Worker crashed: {e}", "error")
        finally:
            try:
                loop.stop()
            except:
                pass
            try:
                loop.close()
            except:
                pass
            asyncio.set_event_loop(None)

    def log_worker_actions(self, msg, mode="info"):
        self.log_signal.emit(msg, mode)

    async def async_upload(self):
        self.log_worker_actions(f"⏳ Starting...", "info")
        MAX_SIZE_BYTES = 8_000_000  # maximum allowed file size in bytes
        try:
            for idx, filepath in enumerate(self.files, start=1):
                if not self._is_running:
                    self.log_worker_actions("❌ Upload cancelled by user.", "info")
                    break

                filename = Path(filepath).name
                # Safely get file size (skip if inaccessible)
                try:
                    file_size_bytes = Path(filepath).stat().st_size
                except Exception as e:
                    self.log_worker_actions(f"❌ Skipping {filename}: cannot access file ({e}).", "error")
                    continue

                if file_size_bytes > MAX_SIZE_BYTES:
                    self.log_worker_actions(
                        f"❌ Skipping {filename}: File size {file_size_bytes} bytes exceeds 8,000,000 bytes limit.",
                        "error"
                    )
                    continue

                # Guard against missing precheck entry
                precheck_val = (self.precheck_results.get(filename) or "").lower()
                if precheck_val == "skip":
                    self.log_worker_actions(f"⚠️ Skipping upload for {filename} (user chose keep).", "info")
                    continue

                self.log_worker_actions(f"({idx}/{len(self.files)}) Uploading: {filename}", "info")

                try:
                    result = await hamster_upload_single_image(
                        filepath, Path(filename).stem, self.album_id, self.api_key, self.site_url, self.mode
                    )
                except Exception as e:
                    self.log_worker_actions(f"❌ Upload failed for {filename}: {e}", "error")
                    continue

                if result and result.get("Direct_URL"):
                    self.log_worker_actions(f"✅ Uploaded: {filename}", "success")

                    try:
                        # === SINGLE MODE ===
                        if self.mode == "single":
                            txt_path = Path(filepath).with_name(f"{Path(filepath).stem}_hamster.txt")
                            with open(txt_path, "w", encoding="utf-8") as f:
                                json.dump({filename: result}, f, indent=2)
                            self.log_worker_actions(f"📝 Wrote single result file: {txt_path}", "info")

                        # === GROUP MODE ===
                        elif self.mode == "group":
                            folder = Path(filepath).parent
                            group_txt_path = folder / f"{folder.name}_hamster_results.txt"

                            # Load existing data if file exists
                            group_data = {}
                            if group_txt_path.exists():
                                try:
                                    with open(group_txt_path, "r", encoding="utf-8") as f:
                                        group_data = json.load(f)
                                except json.JSONDecodeError:
                                    self.log_worker_actions(f"⚠️ Invalid JSON in {group_txt_path}, overwriting.", "warn")

                            # Add or update entry
                            group_data[filename] = result

                            # Write back to file
                            with open(group_txt_path, "w", encoding="utf-8") as f:
                                json.dump(group_data, f, indent=2)

                            self.log_worker_actions(f"🗂️ Updated group results file: {group_txt_path}", "info")

                    except Exception as e:
                        self.log_worker_actions(f"❌ Failed to write results file for {filename}: {e}", "error")
                else:
                    self.log_worker_actions(f"❌ Failed: {filename}", "error")

        except Exception as e:
            # Top-level unexpected error — log it so UI can show the problem
            self.log_worker_actions(f"❌ Worker encountered an error: {e}", "error")
        finally:
            # Always notify the UI that the worker finished (success, cancel or error)
            self.finished_signal.emit()

    def stop(self):
        self._is_running = False


# ---------------------- Main GUI ----------------------
class HamsterUploaderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Hamster Image Uploader {__version__}")
        self.setWindowIcon(QIcon("assets/hamster_uploader.ico"))
        self.setGeometry(300, 100, 700, 500)

        # --- Add menu bar ---
        self.menu_bar = QMenuBar(self)
        self.help_menu = QMenu("Help", self)
        self.view_menu = QMenu("View", self)
        self.menu_bar.addMenu(self.view_menu)
        self.menu_bar.addMenu(self.help_menu)

        self.dark_mode_action = None
        # create action after menus are in place
        self.dark_mode_action = self.view_menu.addAction("Dark mode")  # non-checkable by default
        self.dark_mode_action.triggered.connect(self.on_toggle_dark_mode)

        about_action = self.help_menu.addAction("About")
        about_action.triggered.connect(self.show_about)

        instructions_action = self.help_menu.addAction("Instructions")
        instructions_action.triggered.connect(self.show_instructions)

        issues_action = self.help_menu.addAction("Issues")
        issues_action.triggered.connect(self.show_issues)

        # --- Layout adjustments ---
        self.layout = QVBoxLayout(self)
        self.layout.setMenuBar(self.menu_bar)  # Add menu bar to layout

        # Mode selection
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["single", "group"])
        self.mode_combo.currentTextChanged.connect(self.mode_changed)
        self.layout.addWidget(QLabel("Upload Mode:"))
        self.layout.addWidget(self.mode_combo)

        # File/folder selection
        self.path_label = QLabel("Select folder path:")
        self.path_input = QLineEdit()
        self.ignore_album_missing = None
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_path)
        hbox = QHBoxLayout()
        hbox.addWidget(self.path_input)
        hbox.addWidget(self.browse_button)
        self.layout.addWidget(self.path_label)
        self.layout.addLayout(hbox)

        # Album ID (hidden, show only indicator + optional override)
        self.album_checkbox = QCheckBox("Album ID configured")
        self.album_checkbox.setEnabled(False)
        self.album_input = QLineEdit()
        self.album_input.setPlaceholderText("Optional override")
        hbox_album = QHBoxLayout()
        hbox_album.addWidget(self.album_input)
        hbox_album.addWidget(self.album_checkbox)
        self.layout.addWidget(QLabel("Album ID:"))
        self.layout.addLayout(hbox_album)

        # API Key (hidden, show only indicator + optional override)
        self.api_checkbox = QCheckBox("API Key configured")
        self.api_checkbox.setEnabled(False)
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Optional override")
        hbox_api = QHBoxLayout()
        hbox_api.addWidget(self.api_input)
        hbox_api.addWidget(self.api_checkbox)
        self.layout.addWidget(QLabel("API Key:"))
        self.layout.addLayout(hbox_api)

        # Keep a structured in-memory log so we can fully re-render on theme change
        self.log_entries = []  # list of (mode, text) tuples

        # Console/log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_actions(f"Hamster Image Uploader Started {__version__}", "info")
        self.layout.addWidget(QLabel("Console Output:"))
        self.layout.addWidget(self.log_output)

        # Buttons
        self.button_start = QPushButton("Start")
        self.button_start.clicked.connect(self.toggle_upload)
        self.button_save = QPushButton("Save Settings")
        self.button_save.clicked.connect(self.save_settings)
        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.button_start)
        hbox2.addWidget(self.button_save)
        self.layout.addLayout(hbox2)


        # Internal
        self.upload_worker = None
        self.site_url = None
        self.album_id_hidden = None
        self.api_key_hidden = None

        self.mode_changed(self.mode_combo.currentText())
        self.load_settings()

    # --- Modify load_settings() to apply saved view_mode on startup ---
    def load_settings(self):
        # Load config.json
        view_mode = "light"
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
                self.path_input.setText(config.get("working_path", ""))
                self.ignore_album_missing = config.get("ignore_album_missing", self.ignore_album_missing)
                self.mode_combo.setCurrentText(config.get("upload_mode", "single"))
                view_mode = config.get("view_mode", view_mode)
        except FileNotFoundError:
            self.log_actions("⚠️ config.json not found, using defaults.", "error")
        except json.JSONDecodeError:
            self.log_actions("⚠️ Invalid JSON in config.json, using defaults.", "error")

        try:
            with open("themes.json", "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # Validate minimal structure (must be dict with keys)
                if isinstance(loaded, dict) and loaded:
                    self.themes = copy.deepcopy(loaded)
                else:
                    self.log_actions("⚠️ Invalid structure in themes.json, using defaults.", "warn")
                    self.themes = copy.deepcopy(DEFAULT_THEMES)
        except FileNotFoundError:
            self.log_actions("⚠️ themes.json not found, using default themes.", "warn")
            self.themes = copy.deepcopy(DEFAULT_THEMES)
        except json.JSONDecodeError:
            self.log_actions("⚠️ Invalid JSON in themes.json, using default themes.", "warn")
            self.themes = copy.deepcopy(DEFAULT_THEMES)

        # Apply theme (after view_mode resolved)
        # ensure the dark_mode_action exists
        try:
            self.apply_theme(view_mode)
        except Exception as e:
            # fall back gracefully
            self.apply_theme("light")
            self.log_actions(f"⚠️ Failed to apply theme '{view_mode}': {e}", "error")

        # Load creds.secret
        try:
            with open("creds.secret", "r", encoding="utf-8") as f:
                creds = json.load(f)
                self.album_id_hidden = creds.get("hamster_album_id")
                self.api_key_hidden = creds.get("hamster_api_key")
                self.site_url = creds.get("hamster_site_url")
                self.album_checkbox.setChecked(bool(self.album_id_hidden))
                self.api_checkbox.setChecked(bool(self.api_key_hidden))
        except FileNotFoundError:
            self.log_actions("⚠️ creds.secret not found, API key and Album ID empty.", "error")
        except json.JSONDecodeError:
            self.log_actions("⚠️ Invalid JSON in creds.secret, API key and Album ID empty.", "error")

    def apply_theme(self, theme_name: str):
        """Apply stylesheet and set current log colors based on theme_name."""
        theme = None
        try:
            theme = (getattr(self, "themes", None) or DEFAULT_THEMES).get(theme_name)
        except Exception:
            theme = None

        if not theme:
            theme = (getattr(self, "themes", None) or DEFAULT_THEMES).get("light", DEFAULT_THEMES["light"])

        stylesheet = theme.get("stylesheet", "")
        self.setStyleSheet(stylesheet)

        self.current_log_colors = theme.get("log_colors", {}).copy() if isinstance(theme.get("log_colors"), dict) else DEFAULT_THEMES["light"]["log_colors"].copy()

        # Re-render logs using the new theme colors
        try:
            self._render_logs()
        except Exception as e:
            # avoid recursion: use logger, and append a plain message
            logger.exception(f"Error while re-rendering logs: {e}")
            # fallback: if something went wrong, at least show an inline message
            from html import escape
            self.log_output.insertHtml(
                f'<div style="color:#FF0000">⚠️ Could not repaint log entries: {escape(str(e))}</div>'
            )

        # Update menu text to offer the *other* mode (no checked mark)
        if getattr(self, "dark_mode_action", None):
            try:
                # if currently light, show "Dark mode" to switch; if currently dark, show "Light mode"
                self.dark_mode_action.setText("Dark mode" if theme_name == "light" else "Light mode")
            except Exception:
                pass

        self.current_view_mode = theme_name

    def on_toggle_dark_mode(self):
        """Toggle between 'light' and 'dark' and persist to config.json."""
        current = getattr(self, "current_view_mode", "light")
        new_mode = "dark" if current == "light" else "light"

        # apply immediately
        self.apply_theme(new_mode)

        # persist to config.json (preserve other keys)
        try:
            cfg_path = Path("config.json")
            cfg = {}
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}
            cfg["view_mode"] = new_mode
            cfg.setdefault("available_view_modes", ["light", "dark"])
            cfg.setdefault("working_path", self.path_input.text())
            cfg.setdefault("upload_mode", self.mode_combo.currentText())
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            self.log_actions(f"❌ Failed to persist view mode: {e}", "error")
        else:
            self.log_actions(f"Switched to {new_mode} theme", "success")

    def show_about(self):
        about_text = f"""
        <b>About Hamster Image Uploader</b><br>
        Version: {__version__}<br><br>
        Developed by edstagdh<br><br>
        This tool allows easy batch uploads of images to Hamster.<br><br>
        """
        about_text += """
        <a href="https://github.com/edstagdh/Hamster_Image_Uploader">
            GitHub Repository
        </a>""" if self.current_view_mode == "light" else """<a style="color:white" href="https://github.com/edstagdh/Hamster_Image_Uploader">
            GitHub Repository
        </a>"""

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Hamster Image Uploader - About")
        msg_box.setTextFormat(Qt.RichText)  # Enable HTML formatting
        msg_box.setText(about_text)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def show_instructions(self):
        instructions_text = f"""
        Instructions - Version: {__version__}<br><br>
        
        1. Select upload mode: 'single' for individual files, 'group' for folder uploads.<br>
        2. Browse and select the file(s) or folder path.<br>
        3. Ensure your Hamster API Key and Hamster Album ID(Optional) are configured in creds.secret OR insert them in relevant input boxes<br>
        
        """
        instructions_text += """
        <a href="https://github.com/edstagdh/Hamster_Image_Uploader/blob/master/README.md">
            Instructions are available in README file
        </a>""" if self.current_view_mode == "light" else """<a style="color:white" href="https://github.com/edstagdh/Hamster_Image_Uploader/blob/master/README.md">
            Instructions are available in README file
        </a>"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Hamster Image Uploader - Instructions")
        msg_box.setTextFormat(Qt.RichText)  # Enable HTML formatting
        msg_box.setText(instructions_text)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def show_issues(self):
        issues_text = f"""
        Issues - Version: {__version__}<br><br>"""
        issues_text += """
        <a href="https://github.com/edstagdh/Hamster_Image_Uploader/issues">
            Please submit an issue via Github Issues page
        </a>""" if self.current_view_mode == "light" else """<a style="color:white" href="https://github.com/edstagdh/Hamster_Image_Uploader/issues">
            Please submit an issue via Github Issues page
        </a>"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Hamster Image Uploader - Issues")
        msg_box.setTextFormat(Qt.RichText)  # Enable HTML formatting
        msg_box.setText(issues_text)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def log_actions(self, msg, mode="info"):
        """
        Add a log entry to the in-memory list and re-render the QTextEdit.
        mode: one of 'info', 'success', 'warn', 'error'
        """
        # Ensure color map exists
        default_map = {
            "info": "#000000",
            "success": "#2e7d32",
            "warn": "#f57c00",
            "error": "#d32f2f"
        }
        color_map = getattr(self, "current_log_colors", None) or getattr(self, "themes", {}).get("light", {}).get("log_colors", default_map)
        color = color_map.get(mode, default_map.get(mode, "#000000"))

        from html import escape
        safe_msg = escape(msg).replace("\n", "<br>")

        # store structured entry
        self.log_entries.append((mode, safe_msg))
        if len(self.log_entries) > 5000:
            self.log_entries = self.log_entries[-5000:]

        # re-render the whole log using current theme colors
        self._render_logs()

        # Keep external logger behavior for file/console logs
        if mode == "info":
            logger.info(msg)
        elif mode == "success":
            logger.success(msg)
        elif mode == "warn":
            logger.warning(msg)
        else:
            logger.error(msg)

    def _render_logs(self):
        """
        Render the in-memory self.log_entries into the QTextEdit using
        current_log_colors. This is the single source of truth for displayed logs.
        """
        try:
            # Build HTML document body: use paragraphs for each entry.
            parts = []
            for mode, safe_msg in self.log_entries:
                color = (getattr(self, "current_log_colors", {}) or {}).get(mode)
                if not color:
                    # fallback map
                    fallback = {
                        "info": "#000000",
                        "success": "#2e7d32",
                        "warn": "#f57c00",
                        "error": "#d32f2f"
                    }
                    color = fallback.get(mode, "#000000")

                # We wrap each entry in a div with a class so the HTML structure is predictable
                parts.append(
                    f'<div class="log-entry log-{mode}" style="color:{color}; white-space: pre-wrap;">'
                    f'{safe_msg}'
                    f'</div>'
                )

            body_html = "".join(parts)

            # Use insertHtml with a minimal HTML wrapper so Qt treats it as rich text
            full_html = (
                '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" '
                '"http://www.w3.org/TR/REC-html40/strict.dtd">'
                '<html><head><meta name="qrichtext" content="1" /><meta charset="utf-8" />'
                '<style type="text/css">p, li { white-space: pre-wrap; }</style></head>'
                f'<body>{body_html}</body></html>'
            )

            # Replace document in one operation to avoid incremental escapes
            self.log_output.setHtml(full_html)
            self.log_output.ensureCursorVisible()

        except Exception as e:
            # Do not call self.log_actions here (would recurse) — use logger
            logger.exception(f"Failed to render logs: {e}")

    def pre_upload_validation(self):
        """Validate that the path input matches the selected mode (group/single)."""
        mode = self.mode_combo.currentText()
        path_text = self.path_input.text().strip()

        if not path_text:
            QMessageBox.warning(self, "Warning", "Please select a valid file or folder path.")
            return False

        if mode == "group":
            folder = Path(path_text)
            if not folder.exists() or not folder.is_dir():
                QMessageBox.warning(self, "Error", "Group mode requires a valid folder path.")
                return False
        elif mode == "single":
            paths = path_text.split(";")
            if not all(Path(p).exists() and Path(p).is_file() for p in paths):
                QMessageBox.warning(self, "Error", "Single mode requires valid file paths (separated by ';').")
                return False
        else:
            QMessageBox.warning(self, "Error", f"Unknown mode: {mode}")
            return False

        return True

    def mode_changed(self, mode):
        if mode == "single":
            self.path_label.setText("Select files:")
        else:
            self.path_label.setText("Select folder path:")

        # Reset path input when mode changes
        self.path_input.clear()
        # self.log_actions(f"🔄 Upload mode changed to '{mode}', path input reset.", "info")

    def browse_path(self):
        mode = self.mode_combo.currentText()
        if mode == "single":
            files, _ = QFileDialog.getOpenFileNames(
                self, "Select Image Files", "", "Images (*.jpg *.jpeg *.png *.gif *.webp *.JPG *.JPEG *.PNG *.GIF *.WEBP)"
            )
            if files:
                self.path_input.setText(";".join(files))
        else:
            folder = QFileDialog.getExistingDirectory(self, "Select Folder")
            if folder:
                self.path_input.setText(folder)

    # ----------------- Pre-upload logic -----------------
    def pre_upload_check(self, files, mode):
        """Return dict with files/keys marked 'skip' if user chooses to keep existing data"""
        results = {}
        if mode == "single":
            for filepath in files:
                filename = Path(filepath).name
                base_name = Path(filepath).stem
                txt_path = Path(filepath).parent / f"{base_name}_hamster.txt"
                if txt_path.exists():
                    answer = QMessageBox.question(
                        self, "File exists",
                        f"{txt_path} exists. Overwrite?",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if answer == QMessageBox.Yes:
                        results[filename] = "overwrite"
                    elif answer == QMessageBox.No:
                        results[filename] = "skip"
                    else:
                        return None
        else:  # group mode
            folder = Path(self.path_input.text())
            group_txt_path = folder / f"{folder.name}_hamster_results.txt"
            group_data = {}
            if group_txt_path.exists():
                try:
                    with open(group_txt_path, "r", encoding="utf-8") as f:
                        group_data = json.load(f)
                except Exception:
                    self.log_actions("⚠️ Invalid JSON in existing group file, will overwrite.", "error")

            for filepath in files:
                filename = Path(filepath).name
                if filename in group_data:
                    answer = QMessageBox.question(
                        self, "Existing link detected",
                        f"Data exists for {filename} in group file. Overwrite?",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if answer == QMessageBox.Yes:
                        results[filename] = "overwrite"
                    elif answer == QMessageBox.No:
                        results[filename] = "skip"
                    else:
                        return None
        return results

    # ----------------- Start / Cancel -----------------
    def toggle_upload(self):
        if self.upload_worker and self.upload_worker.isRunning():
            self.upload_worker.stop()
            self.button_start.setEnabled(False)
        else:
            if not self.pre_upload_validation():
                return
            path_text = self.path_input.text().strip()

            mode = self.mode_combo.currentText()
            # Use hidden creds if input is empty
            album_id = self.album_input.text().strip() or self.album_id_hidden
            api_key = self.api_input.text().strip() or self.api_key_hidden
            site_url = self.site_url

            if not api_key:
                QMessageBox.warning(self, "Error", "API key not configured, unable to proceed")
                return

            if not album_id and not self.ignore_album_missing:
                QMessageBox.warning(self, "Warning", "Album ID not detected, uploading to main profile.")

            # Build file list
            if mode == "single":
                files = path_text.split(";")
            else:
                folder = Path(path_text)
                valid_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
                files = [str(f) for f in folder.iterdir() if f.suffix.lower() in valid_exts]

            if not files:
                QMessageBox.warning(self, "Warning", "No valid image files found.")
                return

            # Pre-upload checks
            precheck_results = self.pre_upload_check(files, mode)
            # logger.debug(precheck_results)
            if precheck_results is None:
                self.log_actions("❌ Upload cancelled by user.", "info")
                return

            self.upload_worker = UploadWorker(files, album_id, api_key, site_url, mode, precheck_results)
            self.upload_worker.log_signal.connect(self.log_actions)
            self.upload_worker.finished_signal.connect(self.upload_finished)
            self.upload_worker.start()
            self.button_start.setText("Cancel")

    def upload_finished(self):
        self.log_actions("✅ Upload process complete.", "success")
        self.button_start.setEnabled(True)
        self.button_start.setText("Start")

    def closeEvent(self, event):
        if self.upload_worker and self.upload_worker.isRunning():
            self.upload_worker.stop()
            self.upload_worker.wait(3000)
        super().closeEvent(event)

    # ----------------- Save Settings -----------------
    def save_settings(self):
        config = {
            "working_path": self.path_input.text(),
            "upload_mode": self.mode_combo.currentText(),
            "available_upload_modes": ["group", "single"],
            "view_mode": getattr(self, "current_view_mode", "light"),
            "available_view_modes": ["light", "dark"],
            "ignore_album_missing": self.ignore_album_missing if self.ignore_album_missing is not None else False
        }

        creds = {}

        # ✅ Only save if user entered a new value
        api_key_input = self.api_input.text().strip()
        album_id_input = self.album_input.text().strip()

        if album_id_input:
            creds["hamster_album_id"] = album_id_input
            self.album_id_hidden = album_id_input  # keep internal state in sync
        else:
            creds["hamster_album_id"] = self.album_id_hidden  # preserve loaded value

        if api_key_input:
            creds["hamster_api_key"] = api_key_input
            self.api_key_hidden = api_key_input
        else:
            creds["hamster_api_key"] = self.api_key_hidden

        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            # ✅ Only write creds if we have at least one non-empty field
            if creds.get("hamster_album_id") or creds.get("hamster_api_key"):
                with open("creds.secret", "w", encoding="utf-8") as f:
                    json.dump(creds, f, indent=2)

            self.log_actions("💾 Settings saved.", "success")

        except Exception as e:
            self.log_actions(f"❌ Failed to save settings: {e}", "error")


if __name__ == "__main__":
    logger.add("App_Log_{time:YYYY.MMMM}.log", rotation="30 days", backtrace=True, enqueue=False, catch=True)

    app = QApplication(sys.argv)
    font = app.font()
    ps = font.pointSizeF()
    if ps <= 0:  # fallback when point size not available
        ps = float(font.pixelSize() or 12.0)
    font.setPointSizeF(ps * 1.2)
    app.setFont(font)
    ps = font.pointSizeF()
    gui = HamsterUploaderGUI()
    gui.show()

    try:
        exit_code = app.exec()
        if exit_code == 0:
            logger.info("Hamster Image Uploader Closed Gracefully (exit code 0)")
        else:
            logger.warning(f"Hamster Image Uploader Closed with Exit Code {exit_code}")
    except Exception as e:
        logger.exception(f"❌ Unexpected error during shutdown: {e}")
        exit_code = 1
    finally:
        sys.exit(exit_code)
