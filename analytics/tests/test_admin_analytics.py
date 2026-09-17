from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from analytics.services import AdminAnalyticsService
from content.enums import FileTypeChoice, PostStatus
from content.models import ContentMedia, ContentPost, ContentPostPlatform, PendingUpload
from social_accounts.models import Brand, SocialAccount
from social_accounts.utils.encryption import encrypt_text
from users.models import User


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        email="superadmin@example.com",
        password="SuperPassword123!",
        first_name="Super",
        last_name="Admin",
    )


@pytest.fixture
def superadmin_client(api_client, superuser):
    api_client.force_authenticate(user=superuser)
    return api_client


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff@example.com",
        password="StaffPassword123!",
        first_name="Staff",
        last_name="User",
        is_staff=True,
        is_superuser=False,
    )


@pytest.mark.django_db
class TestAdminAnalyticsService:
    def test_overview_empty_db(self):
        data = AdminAnalyticsService.get_platform_overview()

        assert "summary" in data
        assert data["summary"]["total_users"] == 0
        assert data["summary"]["completed_onboarding"] == 0
        assert data["summary"]["onboarding_completion_rate_percentage"] == 0.0
        assert data["summary"]["total_connected_accounts"] == 0
        assert data["summary"]["live_posts_count"] == 0
        assert data["summary"]["total_posts"] == 0
        assert data["summary"]["failed_posts_count"] == 0

        assert data["users"]["total_users"] == 0
        assert data["users"]["active_users"] == 0
        assert data["users"]["completed_onboarding"] == 0
        assert data["users"]["pending_onboarding"] == 0
        assert data["users"]["onboarding_completion_rate_percentage"] == 0.0
        assert data["users"]["roles_breakdown"]["creator"] == 0
        assert data["users"]["roles_breakdown"]["unassigned"] == 0

        assert data["brands"]["total_brands"] == 0
        assert data["brands"]["brands_with_connected_accounts"] == 0

        assert data["social_accounts"]["total_connected_accounts"] == 0

        assert data["posts"]["total_posts"] == 0
        assert data["posts"]["live_posts_count"] == 0
        assert data["posts"]["platform_posts_published"] == 0
        assert data["posts"]["status_breakdown"][PostStatus.POSTED] == 0

        assert data["storage"]["total_media_items"] == 0
        assert data["storage"]["pending_uploads"]["total"] == 0

    def test_overview_user_and_onboarding_metrics(self):
        # 1. User with complete onboarding
        user1 = User.objects.create_user(
            email="completed@example.com",
            password="Password123!",
            first_name="Alice",
            last_name="Smith",
            role=User.RoleChoices.CREATOR,
        )
        brand1 = user1.brands.get(is_default=True)
        brand1.industry = "tech"
        brand1.posting_frequency = "daily"
        brand1.primary_platform = "instagram"
        brand1.team_size = "solo"
        brand1.save()

        # 2. User with pending onboarding (role set, but default brand lacks onboarding fields)
        user2 = User.objects.create_user(
            email="pending@example.com",
            password="Password123!",
            first_name="Bob",
            last_name="Jones",
            role=User.RoleChoices.BUSINESS_OWNER,
        )

        # 3. User with no role and uncompleted onboarding
        User.objects.create_user(
            email="norole@example.com",
            password="Password123!",
            first_name="Charlie",
            last_name="Brown",
        )

        data = AdminAnalyticsService.get_platform_overview()
        users = data["users"]

        assert users["total_users"] == 3
        assert users["active_users"] == 3
        assert users["completed_onboarding"] == 1
        assert users["pending_onboarding"] == 2
        assert users["onboarding_completion_rate_percentage"] == 33.33
        assert users["roles_breakdown"]["creator"] == 1
        assert users["roles_breakdown"]["business_owner"] == 1
        assert users["roles_breakdown"]["unassigned"] == 1
        assert users["growth"]["joined_today"] == 3

    def test_overview_posts_and_live_status(self, user, brand):
        # Post 1: Published on Instagram and YouTube (Live post)
        post1 = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Post 1",
            content_type="video",
        )
        ContentPostPlatform.objects.create(
            content_post=post1,
            platform="instagram",
            status=PostStatus.POSTED,
            platform_post_id="ig_1",
        )
        ContentPostPlatform.objects.create(
            content_post=post1,
            platform="youtube",
            status=PostStatus.POSTED,
            platform_post_id="yt_1",
        )

        # Post 2: Scheduled on TikTok (Not live)
        post2 = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Post 2",
            content_type="photo",
        )
        ContentPostPlatform.objects.create(
            content_post=post2,
            platform="tiktok",
            status=PostStatus.SCHEDULED,
        )

        # Post 3: Failed on Facebook
        post3 = ContentPost.objects.create(
            user=user,
            brand=brand,
            caption="Post 3",
            content_type="text",
        )
        ContentPostPlatform.objects.create(
            content_post=post3,
            platform="facebook",
            status=PostStatus.FAILED,
            error_message="Network timeout",
        )

        data = AdminAnalyticsService.get_platform_overview()
        posts = data["posts"]

        assert posts["total_posts"] == 3
        assert posts["live_posts_count"] == 1  # only post1 has went live
        assert posts["platform_posts_published"] == 2  # ig_1 + yt_1
        assert posts["status_breakdown"][PostStatus.POSTED] == 2
        assert posts["status_breakdown"][PostStatus.SCHEDULED] == 1
        assert posts["status_breakdown"][PostStatus.FAILED] == 1
        assert posts["content_types_breakdown"]["video"] == 1
        assert posts["content_types_breakdown"]["photo"] == 1
        assert posts["content_types_breakdown"]["text"] == 1
        assert posts["published_by_platform"]["instagram"] == 1
        assert posts["published_by_platform"]["youtube"] == 1
        assert posts["activity"]["posts_created_today"] == 3

    def test_overview_brands_social_and_storage(self, user, brand):
        SocialAccount.objects.create(
            brand=brand,
            platform="instagram",
            account_name="@brand_ig",
            external_id="ext_ig_1",
            _access_token=encrypt_text("token_ig"),
            token_expires_at=timezone.now() + timedelta(days=30),
        )

        # Brand 2 with no social account
        Brand.objects.create(
            user=user,
            name="Second Brand",
            industry="marketing",
            team_size="small",
        )

        # Pending uploads
        PendingUpload.objects.create(
            user=user,
            r2_key="uploads/photo1.jpg",
            content_type="image/jpeg",
            is_claimed=True,
        )
        PendingUpload.objects.create(
            user=user,
            r2_key="uploads/photo2.jpg",
            content_type="image/jpeg",
            is_claimed=False,
        )

        # Media item
        post = ContentPost.objects.create(user=user, brand=brand)
        ContentMedia.objects.create(
            content_post=post,
            r2_key="videos/vid.mp4",
            file_type=FileTypeChoice.VIDEO,
            order=0,
        )

        data = AdminAnalyticsService.get_platform_overview()

        assert data["brands"]["total_brands"] == 2
        assert data["brands"]["brands_with_connected_accounts"] == 1
        assert data["brands"]["industries_breakdown"]["marketing"] == 1

        assert data["social_accounts"]["total_connected_accounts"] == 1
        assert data["social_accounts"]["platforms_breakdown"]["instagram"] == 1

        assert data["storage"]["total_media_items"] == 1
        assert data["storage"]["pending_uploads"]["total"] == 2
        assert data["storage"]["pending_uploads"]["claimed"] == 1
        assert data["storage"]["pending_uploads"]["unclaimed"] == 1


@pytest.mark.django_db
class TestAdminAnalyticsEndpoint:
    def test_unauthenticated_request_returns_401(self, api_client):
        url = reverse("admin-analytics-root")
        response = api_client.get(url)
        assert response.status_code == 401

    def test_regular_user_returns_403(self, authenticated_client):
        url = reverse("admin-analytics-root")
        response = authenticated_client.get(url)
        assert response.status_code == 403

    def test_staff_user_without_superuser_returns_403(self, api_client, staff_user):
        api_client.force_authenticate(user=staff_user)
        url = reverse("admin-analytics-root")
        response = api_client.get(url)
        assert response.status_code == 403

    def test_superadmin_user_returns_200_with_expected_structure(
        self, superadmin_client
    ):
        url = reverse("admin-analytics-root")
        response = superadmin_client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["message"] == "Admin analytics retrieved successfully."

        analytics_data = data["data"]
        assert "users" in analytics_data
        assert "brands" in analytics_data
        assert "social_accounts" in analytics_data
        assert "posts" in analytics_data
        assert "storage" in analytics_data

        assert "total_users" in analytics_data["users"]
        assert "completed_onboarding" in analytics_data["users"]
        assert "live_posts_count" in analytics_data["posts"]

    def test_alias_overview_url_returns_200_for_superadmin(self, superadmin_client):
        url = reverse("admin-analytics-overview")
        response = superadmin_client.get(url)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_summary_endpoint_returns_200_for_superadmin(self, superadmin_client):
        url = reverse("admin-analytics-summary")
        response = superadmin_client.get(url)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        summary = data["data"]
        assert "total_users" in summary
        assert "completed_onboarding" in summary
        assert "onboarding_completion_rate_percentage" in summary
        assert "total_connected_accounts" in summary
        assert "live_posts_count" in summary
        assert "total_posts" in summary
        assert "failed_posts_count" in summary
