import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import RegistrationForm, UserLoginForm, UserProfileForm, BusinessProfileForm
from .models import BusinessProfile

User = get_user_model()


def register(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create empty business profile (prompt next)
            BusinessProfile.objects.create(user=user, business_name="", business_type="other")
            messages.success(request, "Registration successful. Please complete your business profile.")
            login(request, user)
            return redirect('accounts:business_profile_edit')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    if request.method == "POST":
        form = UserLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            password = form.cleaned_data["password"]
            user = authenticate(request, email=email, password=password)
            if user and user.is_active:
                login(request, user)
                return redirect('accounts:dashboard')
            else:
                messages.error(request, "Invalid email or password.")
    else:
        form = UserLoginForm()
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('accounts:login')


@login_required
def dashboard_redirect(request):
    # Redirect based on primary role
    if request.user.role == User.Role.BUYER:
        return redirect('accounts:buyer_dashboard')
    elif request.user.role == User.Role.SUPPLIER:
        return redirect('accounts:supplier_dashboard')
    elif request.user.role == User.Role.BOTH:
        # Show a chooser or default to buyer
        return render(request, "accounts/dashboard_chooser.html")
    # Fallback
    return redirect('accounts:profile')


@login_required
def buyer_dashboard(request):
    if request.user.role not in [User.Role.BUYER, User.Role.BOTH]:
        messages.error(request, "Access denied: not a buyer.")
        return redirect('accounts:dashboard')
    return render(request, "accounts/buyer_dashboard.html")


@login_required
def supplier_dashboard(request):
    if request.user.role not in [User.Role.SUPPLIER, User.Role.BOTH]:
        messages.error(request, "Access denied: not a supplier.")
        return redirect('accounts:dashboard')
    return render(request, "accounts/supplier_dashboard.html")


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html")


@login_required
def profile_edit(request):
    user = request.user
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('accounts:profile')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=user)
    return render(request, "accounts/profile_edit.html", {"form": form})


@login_required
def business_profile_view(request):
    try:
        business_profile = request.user.business_profile
    except BusinessProfile.DoesNotExist:
        messages.error(request, "Business profile not found.")
        return redirect('accounts:dashboard')
    return render(request, "accounts/business_profile.html", {
        "business_profile": business_profile,
        "stellar_network": settings.STELLAR_NETWORK,
    })


@login_required
def business_profile_edit(request):
    try:
        business_profile = request.user.business_profile
    except BusinessProfile.DoesNotExist:
        # Should not happen, autocreated at registration
        business_profile = BusinessProfile.objects.create(user=request.user, business_name="", business_type="other")
    if request.method == "POST":
        previous_wallet = business_profile.stellar_wallet_address
        form = BusinessProfileForm(request.POST, instance=business_profile)
        if form.is_valid():
            business_profile = form.save()
            if business_profile.stellar_wallet_address != previous_wallet:
                business_profile.stellar_wallet_verified = False
                business_profile.wallet_verified_at = None
                business_profile.save(update_fields=[
                    'stellar_wallet_verified',
                    'wallet_verified_at',
                ])
            messages.success(request, "Business profile updated.")
            return redirect('accounts:business_profile')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BusinessProfileForm(instance=business_profile)
    return render(request, "accounts/business_profile_edit.html", {"form": form, "business_profile": business_profile})


@login_required
@require_POST
def stellar_wallet_challenge(request):
    from escrow.stellar import create_wallet_challenge

    return JsonResponse({
        'message': create_wallet_challenge(request),
        'network': settings.STELLAR_NETWORK,
        'network_passphrase': settings.STELLAR_NETWORK_PASSPHRASE,
    })


@login_required
@require_POST
def stellar_wallet_verify(request):
    from escrow.stellar import verify_wallet_challenge

    try:
        payload = json.loads(request.body or b'{}')
        address = verify_wallet_challenge(
            request,
            payload.get('address'),
            payload.get('signature'),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    profile, _ = BusinessProfile.objects.get_or_create(
        user=request.user,
        defaults={
            'business_name': request.user.get_full_name() or request.user.email,
            'business_type': BusinessProfile.BusinessType.OTHER,
        },
    )
    profile.stellar_wallet_address = address
    profile.stellar_wallet_verified = True
    profile.wallet_verified_at = timezone.now()
    profile.save(update_fields=[
        'stellar_wallet_address',
        'stellar_wallet_verified',
        'wallet_verified_at',
        'updated_at',
    ])
    return JsonResponse({
        'ok': True,
        'address': address,
        'network': settings.STELLAR_NETWORK,
    })
