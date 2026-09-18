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

    def test_downscale_for_tiktok_portrait(self):
        # 1920x2560 exceeds TikTok 1080p limit
        img = Image.new("RGB", (1920, 2560), (0, 128, 255))
        resized, was_resized = ImageService.downscale_if_needed(img, ["tiktok"])
        assert was_resized is True
        assert resized.size == (1080, 1440)

    def test_downscale_for_tiktok_landscape(self):
        # 2560x1920 landscape
        img = Image.new("RGB", (2560, 1920), (0, 128, 255))
        resized, was_resized = ImageService.downscale_if_needed(img, ["tiktok"])
        assert was_resized is True
        assert resized.size == (1440, 1080)

    def test_does_not_downscale_for_other_platforms(self):
        # 1920x2560 for Facebook should remain 1920x2560
        img = Image.new("RGB", (1920, 2560), (0, 128, 255))
        resized, was_resized = ImageService.downscale_if_needed(
            img, ["facebook", "linkedin"]
        )
        assert was_resized is False
        assert resized.size == (1920, 2560)

    def test_process_image_for_platforms_downscales_tiktok_jpg(self):
        # Large JPEG for TikTok gets downscaled
        raw_bytes = self._create_image_bytes(size=(1920, 2560), format="JPEG")
        output_bytes, new_key, was_modified = ImageService.process_image_for_platforms(
            raw_bytes, "photos/big.jpg", ["tiktok"]
        )
        assert was_modified is True
        assert new_key == "photos/big.jpg"
        with Image.open(io.BytesIO(output_bytes)) as out_img:
            assert out_img.size == (1080, 1440)
            assert out_img.format == "JPEG"

    def test_process_image_for_platforms_noop_when_within_limits(self):
        # Small JPEG within limits is not modified
        raw_bytes = self._create_image_bytes(size=(800, 600), format="JPEG")
        output_bytes, new_key, was_modified = ImageService.process_image_for_platforms(
            raw_bytes, "photos/small.jpg", ["tiktok"]
        )
        assert was_modified is False
        assert output_bytes == raw_bytes
