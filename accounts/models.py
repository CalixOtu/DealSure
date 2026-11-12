
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager


class UserManager(BaseUserManager):
    """Custom manager using email instead of username."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            **extra_fields
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):

    class Role(models.TextChoices):
        BUYER = "buyer", "Buyer"
        SUPPLIER = "supplier", "Supplier"
        BOTH = "both", "Buyer and Supplier"

    class KYCStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        PENDING = "pending", "Pending Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    username = None

    email = models.EmailField(unique=True)

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.BUYER
    )

    kyc_status = models.CharField(
        max_length=20,
        choices=KYCStatus.choices,
        default=KYCStatus.NOT_STARTED
    )

    email_verified = models.BooleanField(default=False)

    phone_verified = models.BooleanField(default=False)

    terms_accepted = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email


class BusinessProfile(models.Model):

    class BusinessType(models.TextChoices):
        COMPANY = "company", "Registered Company"
        SME = "sme", "Small Business"
        INDIVIDUAL = "individual", "Individual Business"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="business_profile"
    )

    business_name = models.CharField(max_length=200)

    business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.OTHER
    )

    registration_number = models.CharField(
        max_length=100,
        blank=True
    )

    description = models.TextField(blank=True)

    address = models.TextField(blank=True)

    city = models.CharField(max_length=100, blank=True)

    state = models.CharField(max_length=100, blank=True)

    country = models.CharField(
        max_length=100,
        default="Nigeria"
    )

    website = models.URLField(blank=True)

    # Supplier's previously verified Stellar payout address.
    stellar_wallet_address = models.CharField(
        max_length=100,
        blank=True
    )

    stellar_wallet_verified = models.BooleanField(default=False)

    wallet_verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.business_name
