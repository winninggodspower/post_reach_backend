from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser

from post_reach_backend.models import UUIDModel, UUIDTimestampedModel
from users.managers import UserManager

# Create your models here.

class User(AbstractUser, UUIDModel):
    GENDER_CHOICES = [
        ("MALE", "Male"),
        ("FEMALE", "Female"),
    ]

    username = None
    email = models.EmailField(unique=True)
    handle = models.CharField(max_length=30, unique=True, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()


class OnboardingData(UUIDTimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    how_found_us = models.CharField(max_length=255, blank=True, null=True)
    usage_intent = models.TextField(blank=True, null=True)
