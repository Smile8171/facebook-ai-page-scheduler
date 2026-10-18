import base64
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from publish_due_posts import (
    GEMINI_IMAGE_MODEL,
    MAX_FACEBOOK_IMAGE_SIZE,
    create_ai_variation,
    create_free_variation,
)


class FreePhotoVariationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_path = Path(self.temp_dir.name) / "source.png"
        image = Image.new("RGB", (64, 48))
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                pixels[x, y] = (x * 4, y * 5, (x + y) * 2)
        image.save(self.source_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_variation_is_valid_jpeg_without_cropping(self) -> None:
        result = create_free_variation(self.source_path, 0)
        with Image.open(io.BytesIO(result)) as edited:
            self.assertEqual(edited.format, "JPEG")
            self.assertEqual(edited.size, (64, 48))
        self.assertLessEqual(len(result), MAX_FACEBOOK_IMAGE_SIZE)

    def test_styles_produce_distinct_basic_treatments(self) -> None:
        variations = {
            create_free_variation(self.source_path, style_index)
            for style_index in range(7)
        }
        self.assertEqual(len(variations), 7)

    @staticmethod
    def make_image_response() -> SimpleNamespace:
        image = Image.new("RGB", (32, 24), color="purple")
        image_buffer = io.BytesIO()
        image.save(image_buffer, format="PNG")
        return SimpleNamespace(
            output_image=SimpleNamespace(
                data=base64.b64encode(image_buffer.getvalue()).decode("ascii")
            )
        )

    @patch("publish_due_posts.genai.Client")
    def test_ai_variation_sends_image_and_returns_jpeg(self, client_factory) -> None:
        client = client_factory.return_value
        client.interactions.create.return_value = self.make_image_response()

        result = create_ai_variation(self.source_path, 0, "test-api-key")

        client_factory.assert_called_once_with(api_key="test-api-key")
        client.interactions.create.assert_called_once()
        request = client.interactions.create.call_args.kwargs
        self.assertEqual(request["model"], GEMINI_IMAGE_MODEL)
        self.assertIn("warm editorial", request["input"][0]["text"])
        self.assertEqual(request["input"][1]["type"], "image")
        self.assertEqual(request["input"][1]["mime_type"], "image/jpeg")
        with Image.open(io.BytesIO(result)) as edited:
            self.assertEqual(edited.format, "JPEG")
            self.assertEqual(edited.size, (32, 24))
        self.assertLessEqual(len(result), MAX_FACEBOOK_IMAGE_SIZE)

    def test_ai_variation_requires_api_key(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
            create_ai_variation(self.source_path, 0, "")

    @patch("publish_due_posts.genai.Client")
    def test_ai_variation_rejects_missing_image(self, client_factory) -> None:
        client_factory.return_value.interactions.create.return_value = SimpleNamespace(
            output_image=None
        )

        with self.assertRaisesRegex(RuntimeError, "did not contain an edited image"):
            create_ai_variation(self.source_path, 0, "test-api-key")


if __name__ == "__main__":
    unittest.main()
