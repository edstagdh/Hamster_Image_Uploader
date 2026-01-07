import requests
import asyncio
from loguru import logger
import os


async def upload_to_hamster(hamster_api_key, site_url, data, files=None):
    """
    Upload image using multipart/form-data.
    """
    url = f"{site_url}/api/1/upload"
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
                thumb_block = resp_json.get("image", {}).get("thumb", {})
                logger.success(f"[Attempt {attempt}] ✅ Upload successful.")

                result = {
                    "Uploaded_GMT": image_block.get("date_gmt"),
                    "Direct_URL": image_block.get("url"),
                    "Thumb_URL": thumb_block.get("url"),
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


async def hamster_upload_single_image(filepath, base_name, hamster_album_id, hamster_api_key, site_url, mode):
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
        resp_json = await upload_to_hamster(hamster_api_key, site_url, data, files)

    return resp_json
