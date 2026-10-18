import base64
import json
import mimetypes
import os
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PHOTOS_DIR = ROOT / "photos"
STATE_PATH = ROOT / "state.json"
LOCAL_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
POST_TIME = time(hour=7)
SCHEDULE_BUFFER = timedelta(minutes=15)
MAX_FACEBOOK_IMAGE_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
STYLE_PROMPTS = (
    "Create a polished fashion-editorial variation. Give the subject a confident new pose, dramatic studio lighting, and a premium magazine color grade.",
    "Create a warm golden-hour lifestyle variation. Use a natural, relaxed pose, soft sunlight, and a beautiful outdoor background.",
    "Create a bold cinematic variation. Use a dynamic pose, rich colors, atmospheric lighting, and a clean background.",
    "Create an elegant minimal studio variation. Use a refined pose, soft neutral colors, and professional softbox lighting.",
    "Create a vibrant street-style variation. Use an energetic pose, colorful urban background, and crisp editorial lighting.",
    "Create a dreamy artistic variation. Use a graceful pose, soft pastel tones, and subtle cinematic light.",
    "Create a premium travel-editorial variation. Use a candid pose, an attractive scenic background, and natural light.",
)


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
    fields: dict[str, str], file_field: str, file_name: str, image: bytes, mime_type: str
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


def generate_with_openai(source_path: Path, prompt: str, api_key: str) -> bytes:
    source_bytes = source_path.read_bytes()
    source_mime = mimetypes.guess_type(source_path.name)[0] or "image/jpeg"
    body, boundary = build_multipart(
        {"model": "gpt-image-2.5-sunburst", "prompt": prompt, "quality": "high"},
        "image",
        source_path.name,
        source_bytes,
        source_mime,
    )
    result = http_json(
        "POST",
        "https://api.openai.com/v1/images/edits",
        body,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    images = result.get("data")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict):
        raise RuntimeError("OpenAI did not return an image")
    encoded_image = images[0].get("b64_json")
    if not isinstance(encoded_image, str):
        raise RuntimeError("OpenAI response did not contain base64 image data")
    try:
        return base64.b64decode(encoded_image, validate=True)
    except ValueError as error:
        raise RuntimeError("OpenAI returned invalid base64 image data") from error


def generate_with_gemini(source_path: Path, prompt: str, api_key: str) -> bytes:
    source_mime = mimetypes.guess_type(source_path.name)[0] or "image/jpeg"
    image_data = base64.b64encode(source_path.read_bytes()).decode("ascii")
    payload = {
        "model": "gemini-nano-banana-2.1",
        "input": [
            {"type": "text", "text": prompt},
            {"type": "image", "mime_type": source_mime, "data": image_data},
        ],
    }
    result = http_json(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    output_image = result.get("output_image")
    if not isinstance(output_image, dict):
        raise RuntimeError("Gemini did not return an output image")
    encoded_image = output_image.get("data")
    if not isinstance(encoded_image, str):
        raise RuntimeError("Gemini response did not contain base64 image data")
    try:
        return base64.b64decode(encoded_image, validate=True)
    except ValueError as error:
        raise RuntimeError("Gemini returned invalid base64 image data") from error


def generate_image(source_path: Path, prompt: str) -> bytes:
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        try:
            return generate_with_openai(source_path, prompt, openai_key)
        except RuntimeError as error:
            if not os.environ.get("GEMINI_API_KEY", "").strip():
                raise
            print(f"OpenAI failed; trying Gemini fallback: {error}", file=sys.stderr)

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            return generate_with_gemini(source_path, prompt, gemini_key)
        except RuntimeError as error:
            if openai_key:
                raise RuntimeError(
                    f"Both image providers failed; Gemini error: {error}"
                ) from error
            raise

    raise RuntimeError("Configure OPENAI_API_KEY and/or GEMINI_API_KEY in GitHub Secrets.")


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
        "ai-variation.png",
        image,
        "image/png",
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
    style = STYLE_PROMPTS[len(processed_images) % len(STYLE_PROMPTS)]
    prompt = (
        f"{style} Use the supplied photo as visual reference. Make a tasteful, "
        "high-quality creative variation; do not add text, logos, or watermarks."
    )
    image = generate_image(photo_path, prompt)
    if not image:
        raise RuntimeError("The image provider returned an empty image.")
    if len(image) > MAX_FACEBOOK_IMAGE_SIZE:
        raise RuntimeError("Generated image exceeds Facebook's 10 MB photo limit.")

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
        f"Scheduled {relative_path} as Facebook post {post_id} "
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
