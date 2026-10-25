from django.db import models


class PlanTierChoices(models.TextChoices):
    FREE = "free", "Free"
    STARTER = "starter", "Starter"
    CREATOR = "creator", "Creator"
    AGENCY = "agency", "Agency"


class SubscriptionStatusChoices(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past Due"
    UNPAID = "unpaid", "Unpaid"
    CANCELED = "canceled", "Canceled"
    EXPIRED = "expired", "Expired"


class BillingIntervalChoices(models.TextChoices):
    MONTH = "month", "Month"
    YEAR = "year", "Year"


class PaymentMethodTypeChoices(models.TextChoices):
    FREE = "free", "Free"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    OTHER = "other", "Other"


class TransactionStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class PaymentTypeChoices(models.TextChoices):
    RECURRING = "recurring", "Recurring"
    ONE_TIME = "one_time", "One-Time"


class PaymentMethodChoices(models.TextChoices):
    CARD = "CARD", "Card"
    NGN_BANK_TRANSFER = "NGN_BANK_TRANSFER", "NGN Bank Transfer"
    UNKNOWN = "UNKNOWN", "Unknown"
