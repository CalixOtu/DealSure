import os
from decimal import Decimal
from django.conf import settings
from procurement.models import SupplierInvoice, ProcurementOrder
from accounts.models import BusinessProfile
from ai_engine.models import InvoiceFraudAnalysis
from django.contrib.auth import get_user_model
import openai
import logging
User = get_user_model()

DEFAULT_OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# Deterministic checks
def deterministic_checks(invoice: SupplierInvoice):
    findings = {
        'supplier_name_mismatch': False,
        'business_name_mismatch': False,
        'amount_mismatch': False,
        'duplicate_invoice_number': False,
        'payment_wallet_mismatch': False,
        'kyc_not_verified': False,
        'wallet_not_verified': False
    }
    order = invoice.order
    supplier_profile = getattr(order.supplier, 'business_profile', None)
    # Supplier name mismatch: (order.supplier.business_profile.business_name vs invoice.order.supplier.business_profile.business_name)
    if supplier_profile:
        if supplier_profile.business_name.strip().lower() != order.supplier.business_profile.business_name.strip().lower():
            findings['supplier_name_mismatch'] = True
        # Business name from profile vs invoice (assuming invoice includes supplier business in supplier_profile)
        # In demo, use supplier's name as in profile, as invoices don't have explicit business_name field.
        # Could be expanded for real-world PDF OCR, etc.
    else:
        findings['supplier_name_mismatch'] = True
        findings['business_name_mismatch'] = True
    # Amount differs
    if invoice.amount != order.amount:
        findings['amount_mismatch'] = True
    # Duplicate invoice number for the same supplier
    from procurement.models import SupplierInvoice as SupplierInvoiceModel
    existing = SupplierInvoiceModel.objects.filter(
        invoice_number=invoice.invoice_number,
        submitted_by=invoice.submitted_by
    ).exclude(pk=invoice.pk)
    if existing.exists():
        findings['duplicate_invoice_number'] = True
    # Payment wallet differs from verified supplier wallet
    if supplier_profile and supplier_profile.stellar_wallet_verified and supplier_profile.stellar_wallet_address:
        if (invoice.payment_address or '').strip() != supplier_profile.stellar_wallet_address.strip():
            findings['payment_wallet_mismatch'] = True
    # Supplier KYC is not verified
    if order.supplier and getattr(order.supplier, 'kyc_status', None) != User.KYCStatus.VERIFIED:
        findings['kyc_not_verified'] = True
    # Supplier wallet is not verified
    if supplier_profile and not supplier_profile.stellar_wallet_verified:
        findings['wallet_not_verified'] = True
    return findings

def openai_analyze_invoice(order: ProcurementOrder, invoice: SupplierInvoice, supplier_profile: BusinessProfile = None):
    """
    Calls OpenAI to analyze the given invoice and order context.
    Returns: dict (may contain keys: risk_level, risk_score, suspicious_findings, explanation, recommendations)
    """
    if not OPENAI_API_KEY:
        return {'error': 'OpenAI API key not set.'}
    openai.api_key = OPENAI_API_KEY
    model = os.environ.get('OPENAI_MODEL', DEFAULT_OPENAI_MODEL)
    try:
        po_data = {
            "order_title": order.title or '',
            "order_description": order.description or '',
            "order_amount": str(order.amount),
            "order_currency": order.currency,
        }
        supplier_data = {
            "business_name": supplier_profile.business_name if supplier_profile else '',
            "kyc_status": getattr(order.supplier, 'kyc_status', ''),
            "stellar_wallet_address": supplier_profile.stellar_wallet_address if supplier_profile else '',
            "stellar_wallet_verified": supplier_profile.stellar_wallet_verified if supplier_profile else False,
        }
        invoice_data = {
            "invoice_number": invoice.invoice_number,
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "payment_address": invoice.payment_address,
        }
        messages = [
            {"role": "system", "content": "You are a B2B fraud risk explainer. Input: structured PO, invoice data, and supplier business profile. Compare all details and highlight any discrepancies or fraud risk. Respond ONLY in JSON with keys: risk_level (low, moderate, high), risk_score (0-100), suspicious_findings (short summary), explanation (1-3 sentences), recommendations (list of actions). NEVER claim an invoice is genuine. Never authorize payment or release of funds."},
            {"role": "user", "content": f"Purchase Order:\n{po_data}\nSupplier Profile:\n{supplier_data}\nSupplier Invoice:\n{invoice_data}\nFraud check analysis:"}
        ]
        response = openai.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=256,
            response_format={"type": "json_object"}
        )
        ai_json = response.choices[0].message.function_call or None
        if not ai_json:
            import json
            return json.loads(response.choices[0].message.content)
        return ai_json
    except Exception as e:
        logging.exception("OpenAI API invoice analysis failed")
        return {"error": str(e)}

def perform_fraud_analysis(invoice: SupplierInvoice):
    order = invoice.order
    supplier_profile = getattr(order.supplier, 'business_profile', None)
    deterministic = deterministic_checks(invoice)
    ai_result = {}
    openai_err = ''
    if OPENAI_API_KEY:
        ai_result = openai_analyze_invoice(order, invoice, supplier_profile)
        openai_err = ai_result.get('error', '') if isinstance(ai_result, dict) else ''
    analysis = InvoiceFraudAnalysis.objects.create(
        invoice=invoice,
        supplier_name_mismatch=deterministic['supplier_name_mismatch'],
        business_name_mismatch=deterministic['business_name_mismatch'],
        amount_mismatch=deterministic['amount_mismatch'],
        duplicate_invoice_number=deterministic['duplicate_invoice_number'],
        payment_wallet_mismatch=deterministic['payment_wallet_mismatch'],
        kyc_not_verified=deterministic['kyc_not_verified'],
        wallet_not_verified=deterministic['wallet_not_verified'],
        openai_error=openai_err,
    )
    # Map AI result
    if ai_result and isinstance(ai_result, dict):
        for k in ['risk_level', 'risk_score', 'suspicious_findings', 'explanation', 'recommendations']:
            if k in ai_result:
                field = f'openai_{k}'
                if hasattr(analysis, field):
                    setattr(analysis, field, ai_result[k])
        analysis.openai_model_used = os.environ.get('OPENAI_MODEL', DEFAULT_OPENAI_MODEL)
        try:
            if analysis.openai_risk_score:
                analysis.openai_risk_score = Decimal(str(analysis.openai_risk_score))
        except Exception:
            analysis.openai_risk_score = None
        analysis.save()
    return analysis
