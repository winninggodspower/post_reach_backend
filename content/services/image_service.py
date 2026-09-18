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
    def transcode_to_jpeg(cls, image_bytes: bytes, quality: int = 92) -> bytes:
        """
        Transcodes raw image bytes into JPEG format.
        - Respects EXIF orientation so phone captures aren't rotated.
        - Properly renders transparent / alpha channels on a clean white background.
        - Outputs optimized JPEG bytes.
        """
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                # Transpose image based on EXIF orientation if available
                img = ImageOps.exif_transpose(img)

                # Handle transparency (RGBA, LA, or paletted with transparency)
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
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                return buffer.getvalue()
        except Exception:
            CustomLogger.exception("Failed to transcode image to JPEG")
            raise
