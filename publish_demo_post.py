import os
import sys
import urllib.parse

from publish_due_posts import (
    PHOTO_STYLES,
    ROOT,
    STATE_PATH,
    create_ai_variation,
    get_unprocessed_photos,
    http_json,
    load_json,
    save_json,
    upload_unpublished_photo,
)


def publish_demo_post() -> int:
    page_id = os.environ.get("FB_PAGE_ID", "").strip()
    access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "").strip()
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    api_version = os.environ.get("FB_GRAPH_API_VERSION", "v26.0").strip()
    caption = os.environ.get(
        "FB_DEMO_CAPTION", "AI-edited demo photo. Generated for preview."
    ).strip()
    if not page_id or not access_token:
        raise RuntimeError("Configure FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN in GitHub Secrets.")
    if not gemini_api_key:
        raise RuntimeError("Configure GEMINI_API_KEY in GitHub Secrets.")
    if not api_version or not caption:
        raise RuntimeError("FB_GRAPH_API_VERSION and FB_DEMO_CAPTION cannot be empty.")

    state = load_json(
        STATE_PATH,
        {"processed_images": [], "scheduled_dates": {}, "run_dates": []},
    )
    if not isinstance(state, dict):
        raise ValueError("state.json must contain a JSON object.")
    photos = get_unprocessed_photos(state)
    if not photos:
        raise RuntimeError("No unprocessed photos found for a demo post.")

    photo_path = photos[0]
    relative_path = photo_path.relative_to(ROOT).as_posix()
    processed_images = state["processed_images"]
    style_index = len(processed_images) % len(PHOTO_STYLES)
    image = create_ai_variation(photo_path, style_index, gemini_api_key)
    photo_id = upload_unpublished_photo(
        page_id, access_token, api_version, image, caption
    )
    form = urllib.parse.urlencode(
        {
            "access_token": access_token,
            "message": caption,
            "attached_media[0][media_fbid]": photo_id,
            "published": "true",
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
        raise RuntimeError("Facebook demo post response did not contain an ID.")

    processed_images.append(relative_path)
    save_json(STATE_PATH, state)
    print(
        f"Published Gemini-edited demo for {relative_path} as Facebook post {post_id}."
    )
    return 0


def main() -> int:
    try:
        return publish_demo_post()
    except (FileNotFoundError, OSError, RuntimeError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
