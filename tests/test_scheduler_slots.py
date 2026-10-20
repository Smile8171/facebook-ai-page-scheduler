import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from publish_due_posts import (
    LOCAL_TIMEZONE,
    get_next_photo,
    next_publish_slot,
    process_next_photo,
)


class PublishSlotTests(unittest.TestCase):
    def test_selects_all_three_daily_slots_independently(self) -> None:
        now = datetime(2026, 10, 20, 0, 30, tzinfo=timezone.utc)

        morning, morning_name = next_publish_slot(now, {})
        afternoon, afternoon_name = next_publish_slot(
            now,
            {f"{morning.date().isoformat()}:{morning_name}": {}},
        )
        evening, evening_name = next_publish_slot(
            now,
            {
                f"{morning.date().isoformat()}:{morning_name}": {},
                f"{afternoon.date().isoformat()}:{afternoon_name}": {},
            },
        )

        self.assertEqual((morning.hour, morning_name), (7, "morning"))
        self.assertEqual((afternoon.hour, afternoon.minute, afternoon_name), (13, 10, "afternoon"))
        self.assertEqual((evening.hour, evening_name), (17, "evening"))
        self.assertEqual(morning.date(), afternoon.date())
        self.assertEqual(afternoon.date(), evening.date())

    def test_skips_slots_that_are_too_close_or_already_reserved(self) -> None:
        now = datetime(2026, 10, 20, 1, 50, tzinfo=timezone.utc)
        scheduled = {
            "2026-10-20:morning": {},
            "2026-10-20:afternoon": {},
            "2026-10-20:evening": {},
        }

        publish_at, slot_name = next_publish_slot(now, scheduled)

        self.assertEqual(publish_at.date().isoformat(), "2026-10-21")
        self.assertEqual((publish_at.hour, slot_name), (7, "morning"))

    def test_legacy_date_entry_reserves_its_morning_slot(self) -> None:
        now = datetime(2026, 10, 20, 0, 30, tzinfo=timezone.utc)

        publish_at, slot_name = next_publish_slot(now, {"2026-10-20": {}})

        self.assertEqual((publish_at.hour, publish_at.minute, slot_name), (13, 10, "afternoon"))

    def test_photo_cycle_reuses_sources_after_finishing_the_list(self) -> None:
        photos = [Path("first.jpg"), Path("second.jpg")]

        first, first_index = get_next_photo(
            {"processed_images": ["first.jpg"]}, photos
        )
        second, second_index = get_next_photo(
            {"processed_images": ["first.jpg", "second.jpg"], "photo_cycle_index": 0},
            photos,
        )

        self.assertEqual((first, first_index), (photos[1], 1))
        self.assertEqual((second, second_index), (photos[0], 0))

    def test_scheduler_records_all_three_slots_for_same_day(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "photos" / "source.jpg"
            source_path.parent.mkdir()
            source_path.touch()
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps(
                    {"processed_images": [], "scheduled_dates": {}, "run_dates": []}
                ),
                encoding="utf-8",
            )
            morning = datetime(2026, 10, 20, 6, 0, tzinfo=LOCAL_TIMEZONE)
            afternoon = datetime(2026, 10, 20, 12, 10, tzinfo=LOCAL_TIMEZONE)
            evening = datetime(2026, 10, 20, 16, 0, tzinfo=LOCAL_TIMEZONE)

            with (
                patch.dict(
                    "os.environ",
                    {
                        "FB_PAGE_ID": "page-id",
                        "FB_PAGE_ACCESS_TOKEN": "page-token",
                        "GEMINI_API_KEY": "gemini-key",
                    },
                ),
                patch("publish_due_posts.ROOT", root),
                patch("publish_due_posts.STATE_PATH", state_path),
                patch("publish_due_posts.get_source_photos", return_value=[source_path]),
                patch("publish_due_posts.create_ai_variation", return_value=b"edited"),
                patch("publish_due_posts.upload_unpublished_photo", return_value="photo-id"),
                patch(
                    "publish_due_posts.schedule_page_post",
                    side_effect=["morning-post", "afternoon-post", "evening-post"],
                ),
            ):
                self.assertEqual(process_next_photo(morning), 0)
                self.assertEqual(process_next_photo(afternoon), 0)
                self.assertEqual(process_next_photo(evening), 0)

            saved_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(saved_state["scheduled_dates"]),
                {
                    "2026-10-20:morning",
                    "2026-10-20:afternoon",
                    "2026-10-20:evening",
                },
            )
            self.assertEqual(saved_state["processed_images"], ["photos/source.jpg"] * 3)
            self.assertEqual(saved_state["photo_cycle_index"], 0)

    def test_scheduler_uses_local_edit_when_gemini_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "photos" / "source.jpg"
            source_path.parent.mkdir()
            source_path.touch()
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps(
                    {"processed_images": [], "scheduled_dates": {}, "run_dates": []}
                ),
                encoding="utf-8",
            )
            publish_time = datetime(2026, 10, 20, 6, 0, tzinfo=LOCAL_TIMEZONE)

            with (
                patch.dict(
                    "os.environ",
                    {
                        "FB_PAGE_ID": "page-id",
                        "FB_PAGE_ACCESS_TOKEN": "page-token",
                        "GEMINI_API_KEY": "gemini-key",
                    },
                ),
                patch("publish_due_posts.ROOT", root),
                patch("publish_due_posts.STATE_PATH", state_path),
                patch("publish_due_posts.get_source_photos", return_value=[source_path]),
                patch(
                    "publish_due_posts.create_ai_variation",
                    side_effect=RuntimeError("Gemini timed out"),
                ),
                patch(
                    "publish_due_posts.create_free_variation",
                    return_value=b"local-edit",
                ) as local_edit,
                patch(
                    "publish_due_posts.upload_unpublished_photo",
                    return_value="photo-id",
                ) as upload,
                patch("publish_due_posts.schedule_page_post", return_value="post-id"),
            ):
                self.assertEqual(process_next_photo(publish_time), 0)

            local_edit.assert_called_once_with(source_path, 0)
            self.assertEqual(upload.call_args.args[3], b"local-edit")
            saved_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("2026-10-20:morning", saved_state["scheduled_dates"])


if __name__ == "__main__":
    unittest.main()
