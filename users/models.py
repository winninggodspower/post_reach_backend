from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser

from post_reach_backend.models import UUIDModel, UUIDTimestampedModel
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

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()
