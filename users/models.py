from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q, UniqueConstraint

from post_reach_backend.models import UUIDModel, UUIDTimestampedModel
from users.enums import IndustryChoices, PlatformChoices, TeamSizeChoices
from users.managers import UserManager

# Create your models here.


class User(AbstractUser, UUIDModel):
    class RoleChoices(models.TextChoices):
        CREATOR = "creator", "Creator"
        BUSINESS_OWNER = "business_owner", "Business Owner"
        AGENCY_OWNER = "agency_owner", "Agency Owner"
        SOCIAL_MEDIA_MANAGER = "social_media_manager", "Social Media Manager"

    GENDER_CHOICES = [
        ("MALE", "Male"),
        ("FEMALE", "Female"),
    ]

    username = None
    email = models.EmailField(unique=True)
    handle = models.CharField(max_length=30, unique=True, null=True, blank=True)
    role = models.CharField(
        max_length=50,
        choices=RoleChoices.choices,
        null=True,
        blank=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()


class Brand(UUIDTimestampedModel):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="brands"
    )
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    industry = models.CharField(
        max_length=100,
        choices=IndustryChoices.choices,
        blank=True,
        null=True,
    )
    posting_frequency = models.CharField(max_length=100, blank=True, null=True)
    primary_platform = models.CharField(
        max_length=100,
        choices=PlatformChoices.choices,
        blank=True,
        null=True,
    )
    team_size = models.CharField(
        max_length=100,
        choices=TeamSizeChoices.choices,
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "name"],
                name="unique_user_brand_name",
            ),
            UniqueConstraint(
                fields=["user", "is_default"],
                name="unique_user_default_brand",
            ),
        ]
