import sys
import asyncio
import json
from pathlib import Path
from loguru import logger
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QFileDialog, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon

from upload import hamster_upload_single_image  # your async upload function


# ---------------------- Worker Thread ----------------------
class UploadWorker(QThread):
    log_signal = Signal(str, str)
    finished_signal = Signal()

    def __init__(self, files, album_id, api_key, mode, precheck_results):
        super().__init__()
        self.files = files
        self.album_id = album_id
        self.api_key = api_key
        self.mode = mode
        self._is_running = True
        self.precheck_results = precheck_results

    def run(self):
        asyncio.run(self.async_upload())

    def log_worker_actions(self, msg, mode="info"):
        self.log_signal.emit(msg, mode)

    async def async_upload(self):
        for idx, filepath in enumerate(self.files, start=1):
            if not self._is_running:
                self.log_worker_actions("❌ Upload cancelled by user.", "info")
                break

            filename = Path(filepath).name
            if self.precheck_results.get(filename) == "skip":
                self.log_worker_actions(f"⚠️ Skipping upload for {filename} (user chose keep).", "info")
                continue

            self.log_worker_actions(f"({idx}/{len(self.files)}) Uploading: {filename}", "info")

            result = await hamster_upload_single_image(
                filepath, Path(filename).stem, self.album_id, self.api_key, self.mode
            )

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

        self.layout = QVBoxLayout(self)

        # Mode selection
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["single", "group"])
        self.mode_combo.currentTextChanged.connect(self.mode_changed)
        self.layout.addWidget(QLabel("Upload Mode:"))
        self.layout.addWidget(self.mode_combo)

        # File/folder selection
        self.path_label = QLabel("Select folder path:")
        self.path_input = QLineEdit()
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
        self.album_id_hidden = None
        self.api_key_hidden = None

        self.mode_changed(self.mode_combo.currentText())
        self.load_settings()

    def load_settings(self):
        # Load config.json
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
                self.path_input.setText(config.get("working_path", ""))
                self.mode_combo.setCurrentText(config.get("upload_mode", "single"))
        except FileNotFoundError:
            self.log_actions("⚠️ config.json not found, using defaults.", "error")
        except json.JSONDecodeError:
            self.log_actions("⚠️ Invalid JSON in config.json, using defaults.", "error")

        # Load creds.secret
        try:
            with open("creds.secret", "r", encoding="utf-8") as f:
                creds = json.load(f)
                self.album_id_hidden = creds.get("hamster_album_id")
                self.api_key_hidden = creds.get("hamster_api_key")
                self.album_checkbox.setChecked(bool(self.album_id_hidden))
                self.api_checkbox.setChecked(bool(self.api_key_hidden))
        except FileNotFoundError:
            self.log_actions("⚠️ creds.secret not found, API key and Album ID empty.", "error")
        except json.JSONDecodeError:
            self.log_actions("⚠️ Invalid JSON in creds.secret, API key and Album ID empty.", "error")

    def log_actions(self, msg, mode="info"):
        self.log_output.append(msg)
        self.log_output.ensureCursorVisible()
        if mode == "info":
            logger.info(msg)
        elif mode == "success":
            logger.success(msg)
        elif mode == "warn":
            logger.warning(msg)
        else:
            logger.error(msg)

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
                self, "Select Image Files", "", "Images (*.jpg *.jpeg *.png *.gif *.webp)"
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
                base_name = Path(filepath).stem
                txt_path = Path(filepath).parent / f"{base_name}_hamster.txt"
                if txt_path.exists():
                    answer = QMessageBox.question(
                        self, "File exists",
                        f"{txt_path} exists. Overwrite?",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    if answer == QMessageBox.Yes:
                        results[filepath] = "overwrite"
                    elif answer == QMessageBox.No:
                        results[filepath] = "skip"
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
                        results[filename] = "Overwrite"
                    elif answer == QMessageBox.No:
                        results[filename] = "Skip"
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

            if not album_id or not api_key:
                QMessageBox.warning(self, "Error", "API key or Album ID not configured.")
                return

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
            if precheck_results is None:
                self.log_actions("❌ Upload cancelled by user.", "info")
                return

            self.upload_worker = UploadWorker(files, album_id, api_key, mode, precheck_results)
            self.upload_worker.log_signal.connect(self.log_actions)
            self.upload_worker.finished_signal.connect(self.upload_finished)
            self.upload_worker.start()
            self.button_start.setText("Cancel")

    def upload_finished(self):
        self.log_actions("✅ Upload process complete.", "success")
        self.button_start.setEnabled(True)
        self.button_start.setText("Start")

    # ----------------- Save Settings -----------------
    def save_settings(self):
        config = {
            "working_path": self.path_input.text(),
            "upload_mode": self.mode_combo.currentText(),
            "available_upload_modes": ["group", "single"]
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

    VERSION_FILE = Path(__file__).parent / "VERSION"

    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            __version__ = f.read().strip()
    except Exception:
        __version__ = "unknown"

    app = QApplication(sys.argv)
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

