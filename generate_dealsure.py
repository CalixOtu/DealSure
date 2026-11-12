
import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime
from getpass import getpass

from dotenv import load_dotenv
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# ============================================================
# DEALSURE AI CODE GENERATOR
# Run from the main Django project directory.
# ============================================================

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__",
    "node_modules", "media", "staticfiles",
    "ai_backups", ".idea"
}

ALLOWED_SUFFIXES = {
    ".py", ".html", ".css", ".js", ".txt",
    ".md", ".json", ".toml", ".rs"
}

FORBIDDEN_NAMES = {
    ".env", "db.sqlite3", "manage.py",
    "generate_dealsure.py"
}

BACKUP_DIR = ROOT / "ai_backups" / datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# PROJECT DESCRIPTION
# ============================================================

PROJECT_BRIEF = """
PROJECT: DEALSURE

DealSure is a lightweight B2B procurement and anti-fraud
platform being built for a Stellar hackathon demonstration.

CORE PROBLEM:
Businesses can lose money through fake invoices, intercepted
supplier emails, changed payment instructions, duplicate
invoices and non-delivery of purchased goods.

CORE SOLUTION:
DealSure creates a verified procurement workflow between
buyers and suppliers. It compares invoices against purchase
orders and previously verified supplier payment details.
OpenAI explains suspicious discrepancies. Stellar provides
blockchain-based transaction evidence and the foundation for
programmable escrow.

TECH STACK:
- Django 5.2+
- Python
- SQLite for the demonstration
- Tailwind CSS for EVERY HTML template
- OpenAI API using the official Python SDK and Responses API
- Stellar testnet
- Soroban smart contract in Rust where appropriate

EXISTING PROJECT:
The Django project already exists.
The accounts app has already been created.
The custom User and BusinessProfile models have already been
created and migrated.

EXISTING USER MODEL:
User fields:
- email (login identifier)
- first_name
- last_name
- phone
- role: buyer, supplier, both
- kyc_status: not_started, pending, verified, rejected
- email_verified
- phone_verified
- terms_accepted
- is_active, is_staff, is_superuser

BusinessProfile fields:
- user (OneToOneField to User)
- business_name
- business_type
- registration_number
- description
- address
- city
- state
- country
- website
- stellar_wallet_address
- stellar_wallet_verified
- wallet_verified_at
- created_at
- updated_at

IMPORTANT:
Do not recreate or replace the existing User model.
Do not change its fields or choices unless absolutely necessary.
Do not create duplicate accounts tables.
Use get_user_model() or settings.AUTH_USER_MODEL.

PRODUCT WORKFLOW:
1. Buyer creates a procurement order.
2. Buyer invites or selects a supplier.
3. Supplier submits an invoice.
4. DealSure compares invoice information with the order.
5. DealSure checks supplier identity and previously verified
   payment address.
6. OpenAI produces a fraud-risk explanation.
7. Both parties accept the transaction agreement.
8. Buyer funds the demonstration escrow.
9. Supplier confirms dispatch/delivery.
10. Buyer confirms receipt.
11. Funds are released according to the agreed rules.
12. Disputes can pause settlement.

FRAUD EXAMPLE:
A verified supplier has a previously verified Stellar wallet.
A submitted invoice contains a different wallet address.
DealSure must flag the mismatch even if the invoice amount
and supplier name are correct.

OPENAI:
Use OPENAI_API_KEY from environment variables.
Never hardcode API keys.
AI must analyse structured invoice/order information.
Combine deterministic checks with AI explanations.
AI must never independently authorize payment or release funds.
Do not claim AI can prove an invoice is genuine.

STELLAR:
Use Stellar testnet for the demonstration.
Clearly distinguish:
- Django database transaction status
- Actual Stellar testnet transaction
- Real Soroban smart-contract escrow

A normal Stellar transfer is NOT escrow.
Do not claim that a database status or ordinary transfer
locks funds in a smart contract.

Generate a Soroban Rust escrow contract scaffold and
deployment instructions if feasible.
Clearly label anything that is not deployed or tested.

DESIGN:
- Tailwind CSS on every template.
- Professional modern B2B SaaS design.
- Responsive desktop and mobile.
- Consistent navigation and dashboard layouts.
- Use Tailwind CDN for this quick demonstration.
- No Bootstrap.
- Use custom inline messages/modals instead of JavaScript alert().
- All pages must inherit a shared base template.

DEVELOPMENT RULES:
- Generate complete files, never snippets or patches.
- Use correct Django imports and URL names.
- Use Django forms and CSRF protection.
- Use login_required and role checks.
- Validate all user input on the server.
- Restrict access to transactions to their participants
  and authorized administrators.
- Handle missing records gracefully.
- Use Decimal for financial calculations.
- Use Django messages or custom UI notifications.
- Do not expose secrets in templates or JavaScript.
- Do not use fake real-world payment confirmations.
- Do not automatically migrate or execute generated code.
- Avoid unnecessary apps and complicated architecture.
- Prefer simple, working demonstration functionality.
- Include admin registrations.
- Include URL configurations.
- Include requirements.txt dependencies when needed.
- Preserve existing project configuration and models.
"""


# ============================================================
# DEVELOPMENT PHASES
# Each phase receives the existing project files as context.
# ============================================================

PHASES = [
    {
        "name": "01_accounts_and_dashboard",
        "instructions": """
Build the complete authentication and dashboard experience.

Requirements:
- Registration with email and password.
- Buyer, supplier or both account selection.
- Business profile registration.
- Login using email and password.
- Logout.
- Role-based dashboard redirection.
- Profile and business profile pages.
- Profile editing with appropriate restrictions.
- User dashboard.
- Supplier dashboard.
- Buyer dashboard.
- Shared Tailwind base template and navigation.
- Account URL configuration.
- Project URL integration.
- Django forms and admin improvements where needed.

Reuse the existing User and BusinessProfile models.
Do not recreate them.
Create all required templates.
Use Django authentication correctly.
"""
    },
    {
        "name": "02_procurement_and_invoices",
        "instructions": """
Build the procurement and supplier invoice module.

Create a procurement Django app.

Features:
- Create procurement orders.
- List buyer orders.
- Supplier invitations or supplier selection.
- Supplier order dashboard.
- Supplier can accept or reject an order.
- Supplier can submit an invoice.
- Invoice number, amount, description and payment address.
- Optional invoice attachment.
- Buyer can view submitted invoices.
- Procurement order detail page.
- Transaction agreement and acceptance records.
- Prevent unauthorized access.
- Admin management.

The invoice must record the payment address separately.
Compare it against the supplier's existing verified
BusinessProfile.stellar_wallet_address.

Create complete models, forms, views, URLs, templates,
admin configuration and app configuration.
"""
    },
    {
        "name": "03_openai_fraud_detection",
        "instructions": """
Build a separate ai_engine Django app.

This is a key DealSure feature.

Implement:
1. Deterministic invoice checks:
   - Supplier name mismatch.
   - Supplier business mismatch.
   - Invoice amount differs from purchase order.
   - Duplicate invoice number for the same supplier.
   - Payment wallet differs from the verified supplier wallet.
   - Supplier KYC is not verified.
   - Supplier wallet is not verified.

2. OpenAI analysis:
   - Use the official openai Python SDK.
   - Use the Responses API.
   - Read OPENAI_API_KEY from environment.
   - Model configurable through OPENAI_MODEL.
   - Send structured purchase order and invoice data.
   - Request JSON containing risk_level, risk_score,
     suspicious_findings, explanation and recommendations.
   - Handle API errors and missing API key.
   - Never expose API key.
   - Never let AI authorize payments or release funds.

3. Save analysis results in the database.
4. Add a fraud analysis page to each invoice.
5. Show clear risk badges and explanations.
6. Include deterministic findings even if OpenAI is unavailable.

Do not claim that AI can verify the truth of an invoice.
The system detects discrepancies and suspicious patterns.
Create all complete files and templates.
"""
    },
    {
        "name": "04_stellar_escrow_and_disputes",
        "instructions": """
Build the escrow and dispute demonstration.

Create an escrow Django app.

Features:
- Escrow transaction records.
- Funding status.
- Agreement acceptance requirements.
- Delivery confirmation.
- Buyer confirmation.
- Release and refund workflow.
- Dispute creation.
- Evidence upload.
- Admin dispute resolution.
- Prevent settlement while disputed.
- Transaction history and audit records.
- Role-specific transaction pages.

STELLAR:
Prepare a Stellar testnet integration module.
Use environment variables for network and secret settings.
Never put secret keys in templates.
Provide testnet transaction creation and verification
where supported by the installed Stellar SDK.

IMPORTANT:
A normal Stellar payment is not smart-contract escrow.
Do not label an ordinary transfer as locked escrow.

Also provide a minimal Soroban Rust contract scaffold
under a separate stellar_contract directory, with
Cargo.toml and clear testnet deployment instructions.
The contract should model:
- Buyer funding.
- Fixed supplier payout address.
- Release after authorized confirmation.
- Refund/dispute protection.
- Prevention of unauthorized release.

Clearly distinguish the working Django demo workflow,
testnet transactions and undeployed contract code.

Create admin controls and complete Tailwind templates.
"""
    }
]


# ============================================================
# READ EXISTING PROJECT FILES
# ============================================================

def collect_project_context():
    collected = []
    total_chars = 0
    max_chars = 85000

    for current, dirs, files in os.walk(ROOT):
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDED_DIRS
        ]

        for filename in files:
            path = Path(current) / filename

            if path.name in FORBIDDEN_NAMES:
                continue

            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue

            relative = path.relative_to(ROOT).as_posix()

            try:
                content = path.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )
            except Exception:
                continue

            # Avoid sending secrets found in configuration.
            content = re.sub(
                r"(?im)^(\s*SECRET_KEY\s*=\s*).+$",
                r"\1'[REDACTED]'",
                content
            )

            content = re.sub(
                r"(?im)^(\s*(?:OPENAI_API_KEY|API_KEY|PASSWORD)\s*=\s*).+$",
                r"\1'[REDACTED]'",
                content
            )

            block = (
                f"\n\n===== FILE: {relative} =====\n"
                f"{content}\n"
            )

            if total_chars + len(block) > max_chars:
                continue

            collected.append(block)
            total_chars += len(block)

    return "\n".join(collected)


# ============================================================
# SAFE FILE WRITING
# ============================================================

def safe_write(relative_path, content):
    relative = Path(relative_path)

    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe file path: {relative_path}")

    if relative.name in FORBIDDEN_NAMES:
        raise ValueError(f"Protected file: {relative_path}")

    if any(part in EXCLUDED_DIRS for part in relative.parts):
        raise ValueError(f"Protected directory: {relative_path}")

    if relative.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {relative_path}")

    destination = (ROOT / relative).resolve()

    if ROOT.resolve() not in destination.parents:
        raise ValueError(f"Path outside project: {relative_path}")

    # Never overwrite existing migrations.
    if "migrations" in relative.parts:
        raise ValueError("AI cannot overwrite migration files.")

    if destination.exists():
        backup_path = BACKUP_DIR / relative

        backup_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        shutil.copy2(destination, backup_path)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    destination.write_text(
        content,
        encoding="utf-8"
    )

    print(f"[SAVED] {relative_path}")


# ============================================================
# OPENAI GENERATION
# ============================================================

def generate_phase(client, phase, context):
    print("\n" + "=" * 65)
    print("GENERATING:", phase["name"])
    print("=" * 65)

    instructions = f"""
You are a senior Django engineer building DealSure.

{PROJECT_BRIEF}

CURRENT DEVELOPMENT PHASE:
{phase['instructions']}

EXISTING PROJECT FILES:
{context}

OUTPUT REQUIREMENT:
Return ONLY valid JSON with this exact structure:

{{
  "files": [
    {{
      "path": "relative/path/to/file.py",
      "content": "complete file contents"
    }}
  ],
  "notes": "Short setup notes and any important limitations"
}}

Rules:
- Every file must be complete.
- Never return markdown fences.
- Do not return explanations instead of code.
- Do not return patches.
- Do not omit required imports.
- Do not overwrite manage.py, .env or database files.
- Do not generate migration files.
- Do not recreate existing User or BusinessProfile models.
- Use existing field names and choices.
- Keep the code consistent with previously generated files.
- Generate only files required for this phase.
- Use valid JSON escaping for all file contents.
- If a required existing configuration needs an update,
  return the complete updated configuration file.
"""

    response = client.responses.create(
        model=MODEL,
        instructions=(
            "You generate complete, consistent Django project files. "
            "Follow the requested JSON output format exactly."
        ),
        input=instructions,
        text={
            "format": {
                "type": "json_object"
            }
        },
        max_output_tokens=14000
    )

    raw = response.output_text

    if not raw:
        raise RuntimeError(
            f"No output returned for {phase['name']}"
        )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        error_file = ROOT / f"failed_{phase['name']}.txt"
        error_file.write_text(raw, encoding="utf-8")

        raise RuntimeError(
            f"Invalid JSON. Raw response saved to {error_file}"
        ) from exc

    files = result.get("files", [])

    if not files:
        raise RuntimeError(
            f"No files generated for {phase['name']}"
        )

    for item in files:
        if not isinstance(item, dict):
            continue

        path = item.get("path")
        content = item.get("content")

        if not path or not isinstance(content, str):
            continue

        safe_write(path, content)

    print("\nPHASE NOTES:")
    print(result.get("notes", "No additional notes."))

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    if not (ROOT / "manage.py").exists():
        print("ERROR: Run this script from your Django project root.")
        return

    api_key = APIKEY

    if not api_key:
        api_key = getpass(
            "Paste your OpenAI API key (input hidden): "
        ).strip()

    if not api_key:
        print("ERROR: OpenAI API key is required.")
        return

    client = OpenAI(api_key=api_key)

    print("\nDEALSURE AI CODE GENERATOR")
    print("Model:", MODEL)
    print("Project:", ROOT)
    print("Backups:", BACKUP_DIR)

    context = collect_project_context()

    print(
        f"\nExisting project context: {len(context):,} characters"
    )

    print("\nThe generator will make four API generation calls.")
    print("Generated files will be backed up before replacement.")

    confirm = input(
        "\nType GENERATE to begin: "
    ).strip()

    if confirm != "GENERATE":
        print("Cancelled.")
        return

    for phase in PHASES:
        try:
            generate_phase(
                client,
                phase,
                collect_project_context()
            )

        except Exception as error:
            print("\nGENERATION STOPPED:", error)
            print("Your existing files have not been deleted.")
            print("Backups:", BACKUP_DIR)
            return

    print("\n" + "=" * 65)
    print("ALL FOUR GENERATION PHASES COMPLETED")
    print("=" * 65)

    print("""
NEXT ACTIONS:

1. Inspect the generated files.
2. Review requirements.txt and install missing packages.
3. Run: python manage.py check
4. Resolve any errors before migrating.
5. Run: python manage.py makemigrations
6. Run: python manage.py migrate
7. Run: python manage.py runserver

Do not assume generated Stellar contract code is deployed.
Follow its deployment instructions separately.
""")

    print("Backup directory:", BACKUP_DIR)


if __name__ == "__main__":
    main()
