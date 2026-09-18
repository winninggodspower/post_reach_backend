import io

from PIL import Image, ImageOps

from utils.custom_logger import CustomLogger


class ImageService:
    """
    Utility service for inspecting, transforming, and transcoding image assets
    to meet social media platform format requirements.
    """

    SUPPORTED_JPEG_EXTS = {".jpg", ".jpeg"}
    TIKTOK_SUPPORTED_EXTS = {".jpg", ".jpeg", ".webp"}
    INSTAGRAM_SUPPORTED_EXTS = {".jpg", ".jpeg"}

    # TikTok Direct Post hard limits: max 1080p
    TIKTOK_MAX_PORTRAIT = (1080, 1920)  # max width 1080, max height 1920
    TIKTOK_MAX_LANDSCAPE = (1920, 1080)  # max width 1920, max height 1080

    @classmethod
    def is_transcode_needed(cls, filename_or_key: str, platforms: list[str]) -> bool:
        """
        Determine if an image needs to be converted to JPEG for the target platforms.

        - If already JPEG (.jpg, .jpeg): never needs transcoding.
        - If PNG: needs transcode if TikTok or Instagram is in platforms.
        - If WebP: needs transcode if Instagram is in platforms (Instagram rejects WebP).
        - Other platforms (Facebook, LinkedIn) accept PNG, WebP, and JPEG.
        """
        lower = filename_or_key.lower()
        ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""

        if ext in cls.SUPPORTED_JPEG_EXTS:
            return False

        # Instagram strictly requires JPEG
        if "instagram" in platforms and ext not in cls.INSTAGRAM_SUPPORTED_EXTS:
            return True

        # TikTok requires JPEG or WebP (rejects PNG and other formats)
        if "tiktok" in platforms and ext not in cls.TIKTOK_SUPPORTED_EXTS:
            return True

        return False

    @classmethod
    def downscale_if_needed(
        cls, img: Image.Image, platforms: list[str]
    ) -> tuple[Image.Image, bool]:
        """
        Downscales an image ONLY if target platform restrictions require it.
        - TikTok Direct Post enforces a maximum of 1080p resolution (max 1080px width
          for portrait/square, max 1080px height for landscape). Images exceeding this
          trigger picture_size_check_failed.
        - Uses Image.Resampling.LANCZOS for maximum sharpness and fidelity.
        - Other platforms (Facebook, LinkedIn) are NEVER downscaled, preserving original resolution.
        """
        if "tiktok" not in platforms:
            return img, False

        # Select bounding box based on orientation
        if img.width > img.height:
            max_bound = cls.TIKTOK_MAX_LANDSCAPE
        else:
            max_bound = cls.TIKTOK_MAX_PORTRAIT

        if img.width > max_bound[0] or img.height > max_bound[1]:
            resized = img.copy()
            resized.thumbnail(max_bound, Image.Resampling.LANCZOS)
            return resized, True

        return img, False

    @classmethod
    def process_image_for_platforms(
        cls, raw_bytes: bytes, filename_or_key: str, platforms: list[str]
    ) -> tuple[bytes, str, bool]:
        """
        Inspects raw image bytes and processes them for target platforms:
        - Downscales with Lanczos if 'tiktok' in platforms and dimensions exceed 1080p.
        - Transcodes PNG/WebP to JPEG if target platforms require it.
        - Flattens transparency onto a clean white background.
        - Saves with quality=95 and subsampling=0 (lossless chroma) to preserve full quality.

        Returns:
            (output_bytes, new_filename_or_key, was_modified)
        """
        format_transcode = cls.is_transcode_needed(filename_or_key, platforms)
        tiktok_check = "tiktok" in platforms

        if not format_transcode and not tiktok_check:
            return raw_bytes, filename_or_key, False

        with Image.open(io.BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            img, was_resized = cls.downscale_if_needed(img, platforms)

            if not format_transcode and not was_resized:
                return raw_bytes, filename_or_key, False

            # Convert to RGB (flattening transparency onto white background)
            if img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            ):
                background = Image.new("RGB", img.size, (255, 255, 255))
                rgba_img = img.convert("RGBA")
                background.paste(rgba_img, mask=rgba_img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buffer = io.BytesIO()
            img.save(
                buffer,
                format="JPEG",
                quality=95,
                subsampling=0,
                optimize=True,
            )
            new_key = filename_or_key.rsplit(".", 1)[0] + ".jpg"
            return buffer.getvalue(), new_key, True

    @classmethod
    def transcode_to_jpeg(cls, image_bytes: bytes, quality: int = 95) -> bytes:
        """
        Transcodes raw image bytes into JPEG format.
        - Respects EXIF orientation so phone captures aren't rotated.
        - Properly renders transparent / alpha channels on a clean white background.
        - Outputs high-fidelity JPEG bytes (quality=95, subsampling=0).
        """
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img = ImageOps.exif_transpose(img)

                if img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                ):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    rgba_img = img.convert("RGBA")
                    background.paste(rgba_img, mask=rgba_img.split()[3])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                buffer = io.BytesIO()
                img.save(
                    buffer,
                    format="JPEG",
                    quality=quality,
                    subsampling=0,
                    optimize=True,
                )
                return buffer.getvalue()
        except Exception:
            CustomLogger.exception("Failed to transcode image to JPEG")
            raise
