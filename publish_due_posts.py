import io
import base64
import json
import os
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai.errors import APIError
from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parent
PHOTOS_DIR = ROOT / "photos"
STATE_PATH = ROOT / "state.json"
LOCAL_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
POST_TIME = time(hour=7)
SCHEDULE_BUFFER = timedelta(minutes=15)
MAX_FACEBOOK_IMAGE_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
PHOTO_STYLES = (
        "warm editorial",
        "bright outdoor",
        "cinematic",
        "soft portrait",
        "vibrant fashion",
        "classic monochrome",
        "cool urban",
)
FREE_PHOTO_STYLES = (
        "natural",
        "warm",
        "cool",
        "vibrant",
        "soft",
        "monochrome",
        "cinematic",
)
GEMINI_IMAGE_MODEL = "gemini-nano-banana-2.1"


def load_json(path: Path, default: Any) -> Any:
        if not path.exists():
                    return default
                with path.open(encoding="utf-8") as file:
                            return json.load(file)


def save_json(path: Path, content: Any) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(content, file, indent=2, ensure_ascii=False)
                file.write("\n")
            temporary_path.replace(path)


def http_json(
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
) -> dict[str, Any]:
        request = urllib.request.Request(
            url, data=data, headers=headers or {}, method=method
)
    try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                                payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body[:500]}") from error
except urllib.error.URLError as error:
        raise RuntimeError(f"Network error: {error.reason}") from error

    try:
                result = json.loads(payload)
except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON response from API: {payload[:500]}") from error
    if not isinstance(result, dict):
                raise RuntimeError("API returned an unexpected JSON response")
            if "error" in result:
                        raise RuntimeError(f"API error: {result['error']}")
                    return result


def build_multipart(
        fields: dict[str, str],
        file_field: str,
        file_name: str,
        image: bytes,
        mime_type: str,
) -> tuple[bytes, str]:
        boundary = f"----PythonBoundary{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
                parts.extend(
                                [
                                                    f"--{boundary}\r\n".encode(),
                                                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                                                    value.encode("utf-8"),
                                                    b"\r\n",
                                ]
                )
            parts.extend(
                        [
                                        f"--{boundary}\r\n".encode(),
                                        (
                                                            f'Content-Disposition: form-data; name="{file_field}"; '
                                                            f'filename="{file_name}"\r\n'
                                        ).encode(),
                                        f"Content-Type: {mime_type}\r\n\r\n".encode(),
                                        image,
                                        b"\r\n",
                                        f"--{boundary}--\r\n".encode(),
                        ]
            )
    return b"".join(parts), boundary


def apply_tint(
        image: Image.Image, color: tuple[int, int, int], strength: float
) -> Image.Image:
        return Image.blend(image, Image.new("RGB", image.size, color), strength)


def create_free_variation(source_path: Path, style_index: int) -> bytes:
        with Image.open(source_path) as source:
                    source.seek(0)
                    image = ImageOps.exif_transpose(source)
                    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                                    rgba = image.convert("RGBA")
                                    background = Image.new("RGBA", rgba.size, "white")
                                    background.alpha_composite(rgba)
                                    image = background.convert("RGB")
else:
            image = image.convert("RGB")

    style = FREE_PHOTO_STYLES[style_index % len(FREE_PHOTO_STYLES)]
    if style == "natural":
                image = ImageOps.autocontrast(image, cutoff=0.5)
                image = ImageEnhance.Color(image).enhance(1.08)
                image = ImageEnhance.Contrast(image).enhance(1.04)
elif style == "warm":
        image = ImageEnhance.Color(image).enhance(1.05)
        image = apply_tint(image, (255, 190, 105), 0.07)
elif style == "cool":
        image = ImageEnhance.Contrast(image).enhance(1.04)
        image = apply_tint(image, (105, 175, 255), 0.06)
elif style == "vibrant":
        image = ImageOps.autocontrast(image, cutoff=0.5)
        image = ImageEnhance.Color(image).enhance(1.22)
        image = ImageEnhance.Contrast(image).enhance(1.08)
elif style == "soft":
        image = ImageEnhance.Color(image).enhance(1.04)
        image = ImageEnhance.Contrast(image).enhance(0.94)
        image = ImageEnhance.Sharpness(image).enhance(0.92)
elif style == "monochrome":
        image = ImageOps.colorize(
                        ImageOps.autocontrast(image.convert("L")),
                        black="#20252d",
                        white="#f4eee3",
        )
else:
        image = ImageOps.autocontrast(image, cutoff=1)
        image = ImageEnhance.Color(image).enhance(0.92)
        image = ImageEnhance.Contrast(image).enhance(1.12)
        image = apply_tint(image, (255, 190, 130), 0.035)

    output = io.BytesIO()
    for max_side in (2048, 1600, 1200, 900, 640):
                image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                for quality in (90, 82, 74):
                                output.seek(0)
                                output.truncate()
                                image.save(output, format="JPEG", quality=quality, optimize=True)
                                if output.tell() <= MAX_FACEBOOK_IMAGE_SIZE:
                                                    return output.getvalue()

                        raise RuntimeError("Edited photo exceeds Facebook's 10 MB photo limit.")


def create_ai_variation(source_path: Path, style_index: int, api_key: str) -> bytes:
        if not api_key:
                    raise RuntimeError("Configure GEMINI_API_KEY in GitHub Secrets.")

    with Image.open(source_path) as source:
                source.seek(0)
        image = ImageOps.exif_transpose(source)
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                        rgba = image.convert("RGBA")
                        background = Image.new("RGBA", rgba.size, "white")
                        background.alpha_composite(rgba)
                        image = background.convert("RGB")
else:
            image = image.convert("RGB")
        image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        image_buffer = io.BytesIO()
        image.save(image_buffer, format="JPEG", quality=90, optimize=True)

    style = PHOTO_STYLES[style_index % len(PHOTO_STYLES)]
    prompt = (
                "Create a clearly noticeable, photorealistic creative variation of the "
                "provided photo for a social media post. Preserve the identity and "
                "recognizable facial features of the person, if present. Give the person "
                "a natural alternate pose and adapt the outfit and background tastefully "
                "to this visual direction: "
                f"{style}. Keep the main subject recognizable and anatomically natural. "
                "Do not add text, watermarks, logos, or extra people."
    )
    client = genai.Client(api_key=api_key)
    try:
                interaction = client.interactions.create(
                    model=GEMINI_IMAGE_MODEL,
                    input=[
                                        {"type": "text", "text": prompt},
                                        {
                                                                "type": "image",
                                                                "mime_type": "image/jpeg",
                                                                "data": base64.b64encode(image_buffer.getvalue()).decode("ascii"),
                                        },
                    ],
    )
except APIError as error:
        message = str(error).replace(api_key, "[redacted]")
        raise RuntimeError(f"Gemini image editing failed: {message}") from error

    output_image = getattr(interaction, "output_image", None)
    image_data = getattr(output_image, "data", None)
    if not isinstance(image_data, str) or not image_data:
                raise RuntimeError("Gemini response did not contain an edited image.")

    try:
                edited_bytes = base64.b64decode(image_data, validate=True)
        with Image.open(io.BytesIO(edited_bytes)) as edited:
                        result = ImageOps.exif_transpose(edited).convert("RGB")
                        result.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                        output = io.BytesIO()
                        for quality in (90, 82, 74):
                                            output.seek(0)
                                            output.truncate()
                                            result.save(output, format="JPEG", quality=quality, optimize=True)
                                            if output.tell() <= MAX_FACEBOOK_IMAGE_SIZE:
                                                                    return output.getvalue()
except (ValueError, OSError) as error:
        raise RuntimeError("Gemini returned an invalid or unsupported image.") from error

    raise RuntimeError("Gemini-edited photo exceeds Facebook's 10 MB photo limit.")


def upload_unpublished_photo(
        page_id: str, access_token: str, api_version: str, image: bytes, caption: str
) -> str:
        body, boundary = build_multipart(
                    {
                                    "access_token": access_token,
                                    "published": "false",
                                    "temporary": "true",
                                    "caption": caption,
                    },
                    "source",
                    "photo-variation.jpg",
                    image,
                    "image/jpeg",
        )
    result = http_json(
                "POST",
                f"https://graph.facebook.com/{api_version}/{page_id}/photos",
                body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    photo_id = result.get("id")
    if not isinstance(photo_id, str) or not photo_id:
                raise RuntimeError("Facebook photo upload response did not contain an ID")
    return photo_id


def schedule_page_post(
        page_id: str,
        access_token: str,
        api_version: str,
        photo_id: str,
        caption: str,
        publish_at: datetime,
) -> str:
        form = urllib.parse.urlencode(
                    {
                                    "access_token": access_token,
                                    "message": caption,
                                    "attached_media[0][media_fbid]": photo_id,
                                    "published": "false",
                                    "scheduled_publish_time": str(int(publish_at.timestamp())),
                                    "unpublished_content_type": "SCHEDULED",
                    }
        ).encode("utf-8")
    result = http_json(
                "POST",
                f"https://graph.facebook.com/{api_version}/{page_id}/feed",
                form,
                {"Content-Type": "application/x-www-form-urlencoded"},
    )
    post_id = result.get("id")
    if not isinstance(post_id, str) or not post_id:
                raise RuntimeError("Facebook scheduling response did not contain a post ID")
    return post_id


def next_publish_time(now: datetime, reserved_dates: dict[str, Any]) -> datetime:
        local_now = now.astimezone(LOCAL_TIMEZONE)
    publish_at = datetime.combine(
                local_now.date(), POST_TIME, tzinfo=LOCAL_TIMEZONE
    )
    if publish_at < local_now + SCHEDULE_BUFFER:
                publish_at += timedelta(days=1)
    while publish_at.date().isoformat() in reserved_dates:
                publish_at += timedelta(days=1)
    return publish_at


def get_unprocessed_photos(state: dict[str, Any]) -> list[Path]:
        processed = state.get("processed_images")
    if not isinstance(processed, list) or not all(
                isinstance(item, str) for item in processed
    ):
                raise ValueError("state.json processed_images must be a list of paths")
    processed_paths = set(processed)
    if not PHOTOS_DIR.is_dir():
                raise FileNotFoundError("Create the photos/ folder and add source photos.")
    return sorted(
                (
                                path
                                for path in PHOTOS_DIR.rglob("*")
                                if path.is_file()
                                and path.suffix.lower() in IMAGE_EXTENSIONS
                                and path.relative_to(ROOT).as_posix() not in processed_paths
                ),
                key=lambda path: path.relative_to(ROOT).as_posix().lower(),
    )


def process_next_photo(now: datetime | None = None) -> int:
        page_id = os.environ.get("FB_PAGE_ID", "").strip()
    access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "").strip()
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    api_version = os.environ.get("FB_GRAPH_API_VERSION", "v26.0").strip()
    caption = os.environ.get("FB_POST_CAPTION", "Aaj ki nayi vibe!").strip()
    if not page_id or not access_token:
                raise RuntimeError("Configure FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN in GitHub Secrets.")
    if not api_version:
                raise RuntimeError("FB_GRAPH_API_VERSION cannot be empty.")
    if not caption:
                raise RuntimeError("FB_POST_CAPTION cannot be empty.")

    state = load_json(
                STATE_PATH,
                {"processed_images": [], "scheduled_dates": {}, "run_dates": []},
    )
    if not isinstance(state, dict):
                raise ValueError("state.json must contain a JSON object.")
    processed_images = state.setdefault("processed_images", [])
    if not isinstance(processed_images, list) or not all(
                isinstance(item, str) for item in processed_images
    ):
                raise ValueError("state.json processed_images must be a list of paths.")
    if not isinstance(state.get("scheduled_dates", {}), dict):
                raise ValueError("state.json scheduled_dates must be an object.")
    run_dates = state.setdefault("run_dates", [])
    if not isinstance(run_dates, list) or not all(
                isinstance(item, str) for item in run_dates
    ):
                raise ValueError("state.json run_dates must be a list of dates.")

    current_time = now or datetime.now(timezone.utc)
    local_date = current_time.astimezone(LOCAL_TIMEZONE).date().isoformat()
    scheduled_dates = state.setdefault("scheduled_dates", {})
    if local_date in run_dates:
                print(f"The automation already ran on {local_date} India time.")
        return 0

    photos = get_unprocessed_photos(state)
    if not photos:
                print("No new photos found in photos/; add one or more photos to continue.")
        return 0

    photo_path = photos[0]
    relative_path = photo_path.relative_to(ROOT).as_posix()
    style_index = len(processed_images) % len(PHOTO_STYLES)
    style = PHOTO_STYLES[style_index]
    image = create_ai_variation(photo_path, style_index, gemini_api_key)

    publish_at = next_publish_time(current_time, scheduled_dates)
    photo_id = upload_unpublished_photo(
                page_id, access_token, api_version, image, caption
    )
    post_id = schedule_page_post(
                page_id, access_token, api_version, photo_id, caption, publish_at
    )

    state.setdefault("processed_images", []).append(relative_path)
    run_dates.append(local_date)
    scheduled_dates[publish_at.date().isoformat()] = {
                "source_image": relative_path,
                "facebook_post_id": post_id,
                "facebook_photo_id": photo_id,
                "scheduled_for": publish_at.isoformat(),
    }
    save_json(STATE_PATH, state)
    print(
                f"Scheduled {relative_path} ({style} AI edit) as Facebook post {post_id} "
                f"for {publish_at.isoformat()}."
    )
    return 0


def main() -> int:
        try:
                    return process_next_photo()
        except (FileNotFoundError, OSError, RuntimeError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
        raise SystemExit(main())
