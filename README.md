# 🐹 Hamster Image Uploader

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue" />
  <img src="https://img.shields.io/badge/Framework-PySide6-teal" />
  <img src="https://img.shields.io/github/license/edstagdh/Hamster_Image_Uploader" />
</p>

**Hamster Image Uploader** is a desktop application built using **PySide6** and **Python 3.10** for uploading images to **Hamster** through its API. It supports both single-image and batch-folder uploads, handles authentication, and logs detailed upload progress with graceful cancellation.

Version: See the `VERSION` file

---

## ✨ Features

* **Single Mode** — Upload one or multiple individual images.
* **Group Mode** — Upload all valid images from a folder in batch.
* **Automatic Authentication** — Loads API Key and Album ID from `creds.secret`, with optional overriding via UI.
* **Pre-upload Validations** — Warns if existing result JSON files or missing credentials are detected, with Skip/Overwrite options.
* **Comprehensive Logging**:

  * Real-time GUI console logs
  * Persistent logs using `loguru`
* **Structured JSON Output**:

  * Per-image JSON (Single Mode)
  * Per-folder JSON (Group Mode)
* **Graceful Cancellation** — Uploads can be stopped mid-process.

---

## 🛣️ Roadmap

- [ ] Drag-and-drop file selection
- [ ] Retry queue for failed uploads
- [ ] Progress bar visualisation
- [ ] Better error classification and retry logic

---

## Screenshots
<p align="center">
<img src="https://hamster.is/images/2025/11/13/image33e223df76f488e7.png"/>
</p>

---

## 🚀 Getting Started

### Prerequisites

* Python **3.10**
* **PySide6**
* **loguru**
* Additional dependencies listed in `requirements.txt`
* Valid **Hamster API Key** and **Album ID**(Optional)

### Installation

Clone the repository:

```bash
git clone https://github.com/edstagdh/Hamster_Image_Uploader.git
cd hamster_uploader
```

Install the required packages:

```bash
pip install -r requirements.txt
```

### Configuration

1. Copy and rename the example configuration:

   * `config.json_Example` → `config.json`
   * Optional:
     * Update `working_path` and `upload_mode`

2. Copy and rename credentials template:

   * `creds.secret_Example` → `creds.secret`
   * Add your `hamster_api_key` and `hamster_album_id`(Optional)

### Running the Application

```bash
python main.py
```

---

## 🧩 Usage

1. Select a **file** (Single Mode) or a **folder** (Group Mode).
2. Click **Start** to begin uploading.
3. Monitor progress in the GUI log console.
4. Review generated JSON results saved next to your source files.
5. Press **Cancel** to stop at any time.

---

## 📁 Folder Structure

```
hamster_uploader/
├── .gitignore
├── assets/
│   └── hamster_uploader.ico
├── config.json
├── config.json_Example
├── creds.secret
├── creds.secret_Example
├── README.md
├── main.py
├── upload.py
├── requirements.txt
└── VERSION
```

---

## 📜 Logging & Output

* **GUI Console** — Shows real-time upload progress.
* **Persistent Logs** — Saved in format:

  * `App_Log_{YYYY.MMMM}.log`
* **.TXT Files Output**:
  * Single Mode: One JSON formatted text file per image.
  * Group Mode: One JSON formatted text file per folder.

---

## 🛡️ Error Handling

The application handles and logs:

* API key or album ID missing
* Invalid file formats
* Failed upload attempts
* Existing output files (Skip/Overwrite prompt)
* Network/API errors

All issues are logged both in the GUI and the persistent logs.

---

## 📄 License

*MIT License*