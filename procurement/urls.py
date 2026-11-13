from django.urls import path
from . import views

app_name = "procurement"

urlpatterns = [
    # Buyer
    path("orders/", views.order_list, name="order_list"),
    path("orders/create/", views.order_create, name="order_create"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    # Supplier
    path("supplier/orders/", views.supplier_orders, name="supplier_orders"),
    path(
        "supplier/orders/<int:order_id>/decision/",
        views.supplier_order_decision,
        name="supplier_order_decision",
    ),
    path(
        "orders/<int:order_id>/invoice/",
        views.supplier_invoice_submit,
        name="supplier_invoice_submit",
    ),
    # Agreements
    path(
        "orders/<int:order_id>/agreement/accept/",
        views.agreement_accept,
        name="agreement_accept",
    ),
    path(
        "orders/<int:order_id>/escrow/start/",
        views.escrow_start,
        name="escrow_start",
    ),
]
