import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publish_demo_post import publish_demo_post


class PublishDemoPostTests(unittest.TestCase):
    def test_publishes_edited_photo_and_marks_it_processed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "photos" / "demo.jpg"
            source_path.parent.mkdir()
            source_path.touch()
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps({"processed_images": [], "scheduled_dates": {}, "run_dates": []}),
                encoding="utf-8",
            )

            with (
                patch.dict(
                    "os.environ",
                    {
                        "FB_PAGE_ID": "page-id",
                        "FB_PAGE_ACCESS_TOKEN": "page-token",
                        "GEMINI_API_KEY": "gemini-key",
                    },
                ),
                patch("publish_demo_post.ROOT", root),
                patch("publish_demo_post.STATE_PATH", state_path),
                patch("publish_demo_post.get_source_photos", return_value=[source_path]),
                patch("publish_demo_post.get_next_photo", return_value=(source_path, 0)),
                patch("publish_demo_post.create_ai_variation", return_value=b"edited"),
                patch("publish_demo_post.upload_unpublished_photo", return_value="photo-id"),
                patch("publish_demo_post.http_json", return_value={"id": "post-id"}) as http_json,
            ):
                self.assertEqual(publish_demo_post(), 0)

            http_json.assert_called_once()
            self.assertIn("/page-id/feed", http_json.call_args.args[1])
            self.assertIn(b"published=true", http_json.call_args.args[2])
            saved_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_state["processed_images"], ["photos/demo.jpg"])
            self.assertEqual(saved_state["photo_cycle_index"], 0)


if __name__ == "__main__":
    unittest.main()
