from typing import Optional
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from content.enums import PostStatus
from content.selectors import ContentPostSelector
from utils.custom_logger import CustomLogger, log_exceptions
from utils.frontend_urls import FrontendUrls

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
    "twitter": "Twitter",
    "x": "X",
}


class NotificationService:
    """
    Centralized service for dispatching email and system notifications across PostReach.
    Stateless, reusable across content, users, social accounts, and billing.
    """

    @classmethod
    def send_email(
        cls,
        *,
        to_email: str,
        subject: str,
        template_name: str,
        context: dict,
        from_name: str | None = None,
        from_email: str | None = None,
        plain_text_message: str | None = None,
    ) -> bool:
        """
        Render an HTML template and send an email to the recipient.

        :param from_name: Optional sender display name (e.g. "Winning from PostGlee", defaults to "PostGlee").
        :param from_email: Optional sender email address (defaults to settings.DEFAULT_FROM_EMAIL).
        """
        try:
            html_message = render_to_string(template_name, context)
            if plain_text_message is None:
                plain_text_message = strip_tags(html_message).strip()

            base_email = from_email or settings.DEFAULT_FROM_EMAIL
            # Extract clean email address if already formatted like 'Name <email@domain>'
            if "<" in base_email and ">" in base_email:
                sender_addr = base_email.split("<")[1].split(">")[0].strip()
                existing_name = base_email.split("<")[0].strip()
                sender_name = from_name or existing_name or "PostGlee"
            else:
                sender_addr = base_email.strip()
                sender_name = from_name or "PostGlee"

            formatted_from = f"{sender_name} <{sender_addr}>"

            send_mail(
                subject=subject,
                message=plain_text_message,
                html_message=html_message,
                from_email=formatted_from,
                recipient_list=[to_email],
                fail_silently=False,
            )
            CustomLogger.info(
                "Email sent successfully",
                extra={
                    "recipient": to_email,
                    "subject": subject,
                    "template": template_name,
                },
            )
            return True
        except Exception as exc:
            CustomLogger.exception(
                "Failed to send email",
                extra={
                    "recipient": to_email,
                    "subject": subject,
                    "template": template_name,
                    "error": str(exc),
                },
            )
            return False

    @classmethod
    @log_exceptions()
    def send_post_status_notification(cls, *, content_post_id: str | UUID) -> bool:
        """
        Send a consolidated email notification for a ContentPost once all
        targeted platforms have finished publishing (either POSTED or FAILED).
        Guarantees idempotency via content_post.email_notified_at.
        """
        try:
            content_post = ContentPostSelector.get_content_post_by_id(content_post_id)
        except Exception:
            CustomLogger.error(
                "ContentPost not found for notification dispatch",
                extra={"content_post_id": str(content_post_id)},
            )
            return False

        # Idempotency check: Don't send multiple times
        if content_post.email_notified_at is not None:
            CustomLogger.info(
                "Notification already sent for ContentPost, skipping",
                extra={"content_post_id": str(content_post.id)},
            )
            return False

        # Check if there are still pending/processing platform entries
        if ContentPostSelector.has_pending_entries(content_post):
            CustomLogger.info(
                "ContentPost still has pending platform entries, postponing notification",
                extra={"content_post_id": str(content_post.id)},
            )
            return False

        platform_entries = list(content_post.platform_entries.all())
        if not platform_entries:
            return False

        successful_entries = []
        failed_entries = []

        for entry in platform_entries:
            platform_label = PLATFORM_LABELS.get(
                entry.platform.lower(), entry.platform.title()
            )
            if entry.status == PostStatus.POSTED:
                successful_entries.append(
                    {
                        "platform": entry.platform,
                        "platform_label": platform_label,
                        "post_url": entry.post_url,
                    }
                )
            elif entry.status == PostStatus.FAILED:
                failed_entries.append(
                    {
                        "platform": entry.platform,
                        "platform_label": platform_label,
                        "error_message": entry.error_message
                        or "An unexpected platform error occurred.",
                    }
                )

        # If somehow no entries are terminal yet, don't send
        if not successful_entries and not failed_entries:
            return False

        all_succeeded = len(successful_entries) > 0 and len(failed_entries) == 0
        all_failed = len(failed_entries) > 0 and len(successful_entries) == 0

        # Build subject line
        if all_succeeded:
            if len(successful_entries) == 1:
                subject = f"🎉 Your post on {successful_entries[0]['platform_label']} is now live!"
            else:
                plat_names = ", ".join(e["platform_label"] for e in successful_entries)
                subject = f"🎉 Your post is live on {plat_names}!"
        elif all_failed:
            if len(failed_entries) == 1:
                subject = f"⚠️ Failed to publish your post on {failed_entries[0]['platform_label']}"
            else:
                subject = "⚠️ Failed to publish your post across platforms"
        else:
            # Mixed
            succ_names = ", ".join(e["platform_label"] for e in successful_entries)
            fail_names = ", ".join(e["platform_label"] for e in failed_entries)
            subject = f"📢 Post published on {succ_names} (failed on {fail_names})"

        recipient_email = content_post.user.email
        if not recipient_email:
            CustomLogger.warning(
                "User has no email for post status notification",
                extra={
                    "content_post_id": str(content_post.id),
                    "user_id": str(content_post.user.id),
                },
            )
            return False

        user_name = content_post.user.first_name or "there"
        brand_name = content_post.brand.name if content_post.brand else "Your Brand"

        caption_snippet = content_post.caption or ""
        if len(caption_snippet) > 280:
            caption_snippet = caption_snippet[:280] + "..."

        context = {
            "email_title": subject,
            "user_name": user_name,
            "brand_name": brand_name,
            "post_caption": caption_snippet,
            "successful_entries": successful_entries,
            "failed_entries": failed_entries,
            "all_succeeded": all_succeeded,
            "all_failed": all_failed,
            "dashboard_url": FrontendUrls.dashboard(),
            "home_url": FrontendUrls.base(),
            "retry_url": (
                FrontendUrls.retry_post(content_post.id) if failed_entries else None
            ),
        }

        sent = cls.send_email(
            to_email=recipient_email,
            subject=subject,
            template_name="emails/post_status.html",
            context=context,
        )

        if sent:
            content_post.email_notified_at = timezone.now()
            content_post.save(update_fields=["email_notified_at"])

        return sent
