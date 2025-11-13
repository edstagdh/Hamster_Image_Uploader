import requests
import json
import asyncio
from loguru import logger
import os


async def upload_to_hamster(hamster_api_key, data, files=None):
    """
    Upload image using multipart/form-data.
    """
    url = "https://hamster.is/api/1/upload"
    headers = {
        "X-API-Key": hamster_api_key,
        "Accept": "application/json"
    }

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
            try:
                resp_json = response.json()
            except Exception:
                logger.error(f"[Attempt {attempt}] ❌ Invalid JSON response: {response.text}")
                continue

            status_ok = resp_json.get("status_code") == 200
            success_block = resp_json.get("success", {})
            image_block = resp_json.get("image", {})

            success_message = (
                isinstance(success_block, dict)
                and success_block.get("code") == 200
                and "upload" in success_block.get("message", "").lower()
            )

            if status_ok and success_message and image_block:
                logger.success(f"[Attempt {attempt}] ✅ Upload successful.")

                result = {
                    "Uploaded_GMT": image_block.get("date_gmt"),
                    "Direct_URL": image_block.get("url"),
                    "Viewer_URL": image_block.get("url_short"),
                    "Delete_URL": image_block.get("delete_url")
                }

                missing = [k for k, v in result.items() if v is None]
                if missing:
                    logger.warning(f"Missing expected fields: {', '.join(missing)}")

                return result

            else:
                logger.error(f"[Attempt {attempt}] Upload failed validation: {resp_json}")

        except requests.exceptions.RequestException as e:
            logger.error(f"[Attempt {attempt}] Network error: {e}")

        if attempt < max_retries:
            sleep_time = 2 * attempt
            logger.warning(f"Retrying in {sleep_time} seconds...")
            await asyncio.sleep(sleep_time)

    logger.error("❌ All upload attempts failed after retries.")
    return None


async def hamster_upload_single_image(filepath, base_name, hamster_album_id, hamster_api_key, mode):
    """
    Prepare data for upload, build payload for upload_to_hamster() using multipart/form-data.
    """
    if not os.path.isfile(filepath):
        logger.error(f"File not found: {filepath}")
        return None

    data = {
        "title": f"{base_name}_{mode}",
        "format": "json",
        "nsfw": 1
    }
    if hamster_album_id:
        data["album_id"] = hamster_album_id

    with open(filepath, "rb") as f:
        files = {"source": (os.path.basename(filepath), f)}
        resp_json = await upload_to_hamster(hamster_api_key, data, files)

    return resp_json


async def load_file(mode, json_file):
    try:
        with open(json_file, 'r', encoding='utf-8') as secret_file:
            secrets = json.load(secret_file)
            if mode == 1:
                return secrets["hamster_album_id"], secrets["hamster_api_key"]
            elif mode == 2:
                return secrets["working_path"], secrets["upload_mode"]
            else:
                return None, None

    except FileNotFoundError:
        logger.error(f"{json_file} file not found.")
    except KeyError as e:
        logger.error(f"Key {e} missing in {json_file}.")
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in {json_file}.")
    return None, None


async def ask_user_keep_or_overwrite(prompt_text):
    await asyncio.sleep(0.2)
    while True:
        answer = input(f"{prompt_text} [K=Keep / O=Overwrite]: ").strip().lower()
        if answer in ("k", "keep"):
            return "keep"
        elif answer in ("o", "overwrite"):
            return "overwrite"
        elif answer in ("q", "quit", "exit"):
            return "quit"
        else:
            logger.warning("Invalid input, please enter K or O.")
            await asyncio.sleep(0.1)


# async def main():
#     try:
#         # Load config and credentials
#         working_path, upload_mode = await load_file(2, "config.json")
#         if not working_path or not upload_mode:
#             logger.error("Missing working_path or upload_mode in config.json.")
#             exit(99)
#
#         hamster_album_id, hamster_api_key = await load_file(1, "creds.secret")
#         if not hamster_api_key or not hamster_album_id:
#             logger.error("Missing 'hamster_api_key' or 'hamster_album_id' in creds.secret.")
#             exit(99)
#
#         logger.info(f"Starting upload from: {working_path}")
#         logger.info(f"Upload mode: {upload_mode}")
#
#         valid_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
#         files = [
#             os.path.join(working_path, f)
#             for f in os.listdir(working_path)
#             if os.path.splitext(f.lower())[1] in valid_exts
#         ]
#
#         if not files:
#             logger.warning(f"No supported image files found in {working_path}")
#             exit(98)
#
#         uploaded_results = []
#
#         # Preload group data if in group mode
#         group_data = {}
#         if upload_mode == "group":
#             folder_name = os.path.basename(os.path.normpath(working_path))
#             group_txt_path = os.path.join(working_path, f"{folder_name}_hamster_results.txt")
#             if os.path.isfile(group_txt_path):
#                 with open(group_txt_path, "r", encoding="utf-8") as f:
#                     try:
#                         group_data = json.load(f)
#                     except json.JSONDecodeError:
#                         logger.warning(f"Invalid JSON in {group_txt_path}, will overwrite.")
#
#         for idx, filepath in enumerate(files, start=1):
#             filename = os.path.basename(filepath)
#             base_name, _ = os.path.splitext(filename)
#
#             # === Pre-upload check for single mode ===
#             if upload_mode == "single":
#                 txt_path = os.path.join(working_path, f"{base_name}_hamster.txt")
#                 if os.path.isfile(txt_path):
#                     action = await ask_user_keep_or_overwrite(f"File {txt_path} exists")
#                     if action == "keep":
#                         logger.info(f"Skipping upload for {filename}, keeping existing file.")
#                         continue
#                     elif action == "quit":
#                         exit(97)
#
#             # === Pre-upload check for group mode ===
#             elif upload_mode == "group":
#                 if filename in group_data:
#                     action = await ask_user_keep_or_overwrite(f"Key exists for {filename} in group file")
#                     if action == "keep":
#                         logger.info(f"Skipping upload for {filename}, keeping existing key.")
#                         continue
#                     elif action == "quit":
#                         exit(97)
#
#             logger.info(f"({idx}/{len(files)}) Uploading: {filename}")
#             result = await hamster_upload_single_image(filepath, base_name, hamster_album_id, hamster_api_key, upload_mode)
#
#             if result and result.get("Direct_URL"):
#                 uploaded_results.append({filename: result})
#                 logger.success(f"✅ Uploaded: {filename}")
#
#                 # Write single mode file
#                 if upload_mode == "single":
#                     txt_path = os.path.join(working_path, f"{base_name}_hamster.txt")
#                     with open(txt_path, "w", encoding="utf-8") as f:
#                         json.dump({filename: result}, f, indent=2)
#                     logger.debug(f"Wrote {txt_path}")
#
#                 # Update group data in memory
#                 if upload_mode == "group":
#                     group_data[filename] = result
#
#             else:
#                 logger.error(f"Upload failed for {filename}")
#
#         # Write group mode file after all uploads
#         if upload_mode == "group" and group_data:
#             folder_name = os.path.basename(os.path.normpath(working_path))
#             group_txt_path = os.path.join(working_path, f"{folder_name}_hamster_results.txt")
#             with open(group_txt_path, "w", encoding="utf-8") as f:
#                 json.dump(group_data, f, indent=2)
#             logger.success(f"All results saved to {group_txt_path}")
#
#         logger.info("✅ Upload process complete.")
#
#     except Exception as e:
#         logger.exception(f"Fatal error in main(): {e}")


# if __name__ == "__main__":
#     logger.add("App_Log_{time:YYYY.MMMM}.log", rotation="30 days", backtrace=True, enqueue=False, catch=True)
#     asyncio.run(main())
