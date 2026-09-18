import io

import pytest
from PIL import Image

from content.services.image_service import ImageService


class TestImageService:
    def _create_image_bytes(
        self, mode="RGB", size=(100, 100), color=(255, 0, 0), format="PNG"
    ):
        img = Image.new(mode, size, color)
        buf = io.BytesIO()
        img.save(buf, format=format)
        return buf.getvalue()

    def test_is_transcode_needed_jpeg(self):
        # Already JPEG should never need transcode
        assert not ImageService.is_transcode_needed("photos/pic.jpg", ["tiktok"])
        assert not ImageService.is_transcode_needed("photos/pic.jpeg", ["instagram"])
        assert not ImageService.is_transcode_needed("photos/pic.JPG", ["facebook"])

    def test_is_transcode_needed_tiktok(self):
        # TikTok accepts WebP and JPEG, rejects PNG
        assert not ImageService.is_transcode_needed("photos/pic.webp", ["tiktok"])
        assert ImageService.is_transcode_needed("photos/pic.png", ["tiktok"])

    def test_is_transcode_needed_instagram(self):
        # Instagram rejects PNG and WebP
        assert ImageService.is_transcode_needed("photos/pic.png", ["instagram"])
        assert ImageService.is_transcode_needed("photos/pic.webp", ["instagram"])

    def test_is_transcode_needed_other_platforms(self):
        # Facebook and LinkedIn accept PNG and WebP
        assert not ImageService.is_transcode_needed("photos/pic.png", ["facebook"])
        assert not ImageService.is_transcode_needed("photos/pic.webp", ["linkedin"])

    def test_is_transcode_needed_multi_platform(self):
        # Transcode needed if any platform in the list requires it
        assert ImageService.is_transcode_needed(
            "photos/pic.png", ["facebook", "tiktok"]
        )
        assert not ImageService.is_transcode_needed(
            "photos/pic.png", ["facebook", "linkedin"]
        )

    def test_transcode_rgb_png_to_jpeg(self):
        png_bytes = self._create_image_bytes(mode="RGB", format="PNG")
        jpeg_bytes = ImageService.transcode_to_jpeg(png_bytes)

        # Inspect resulting bytes
        with Image.open(io.BytesIO(jpeg_bytes)) as img:
            assert img.format == "JPEG"
            assert img.mode == "RGB"
            assert img.size == (100, 100)

    def test_transcode_rgba_png_to_jpeg(self):
        # Transparent red pixel
        png_bytes = self._create_image_bytes(
            mode="RGBA", color=(255, 0, 0, 128), format="PNG"
        )
        jpeg_bytes = ImageService.transcode_to_jpeg(png_bytes)

        with Image.open(io.BytesIO(jpeg_bytes)) as img:
            assert img.format == "JPEG"
            assert img.mode == "RGB"

    def test_transcode_webp_to_jpeg(self):
        webp_bytes = self._create_image_bytes(mode="RGB", format="WEBP")
        jpeg_bytes = ImageService.transcode_to_jpeg(webp_bytes)

        with Image.open(io.BytesIO(jpeg_bytes)) as img:
            assert img.format == "JPEG"
            assert img.mode == "RGB"
