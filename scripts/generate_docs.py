"""
Knowledge Base Document Generator — Aether Wireless

Generates telecom policy knowledge-base documents using OpenRouter
and saves them as PDF (always), and optionally Markdown and/or plain text.

Usage:

    python scripts/generate_docs.py

    python scripts/generate_docs.py --limit 4

    python scripts/generate_docs.py --only roaming

    python scripts/generate_docs.py --keep-md

    python scripts/generate_docs.py --keep-txt

    python scripts/generate_docs.py --keep-md --keep-txt

Environment:

    OPENROUTER_API_KEY=your_openrouter_api_key   (in a .env file next to this script's project root)

The script is otherwise self-contained: everything else (model name,
generation settings, minimum page target, document catalog, prompts)
is a constant defined below.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    from pypdf import PdfReader

    HAVE_PDF_READER = True
except ImportError:
    HAVE_PDF_READER = False


# ============================================================================
# PATHS
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT_DIR / "data" / "raw"
ENV_PATH = ROOT_DIR / ".env"


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("generate_docs")


# ============================================================================
# OPENROUTER CONFIGURATION
# ============================================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Change this to switch models — the only place the model name is set.
MODEL = "openrouter/free"


TEMPERATURE = 0.3
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 120

MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 2


# ============================================================================
# DOCUMENT GENERATION CONFIGURATION
# ============================================================================

# Every document is generated as outline -> sections -> FAQ, to reliably
# reach the minimum page target below (a single-call "standard" generation
# cannot guarantee length).
LONG_DOC_SECTIONS = 15

OUTLINE_MAX_TOKENS = 1200
SECTION_MAX_TOKENS = 3000
FAQ_MAX_TOKENS = 2000
TABLE_SECTION_MAX_TOKENS = 1200

MAX_COMPLETION_TOKENS_TO_WARN = 4096

# Minimum pages each rendered PDF should reach. This is enforced by
# generating enough sections; if `pypdf` is installed, the actual page
# count is also checked after rendering and a warning is logged if a
# document falls short (best-effort, does not block the run).
MIN_PAGES = 5

# Name of the mandatory table section injected into every document,
# in addition to whatever the model's own outline produces.
TABLE_SECTION_NAME = "Key Rules Summary"


# ============================================================================
# ENVIRONMENT
# ============================================================================

load_dotenv(ENV_PATH)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise SystemExit(f"OPENROUTER_API_KEY is missing. Add it to {ENV_PATH}.")


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class KnowledgeMetadata:
    """Metadata associated with a knowledge-base document."""

    title: str
    doc_id: str
    version: str
    last_updated: str
    department: str
    category: str
    brief: str


@dataclass
class KnowledgeDocument:
    """Generated knowledge-base document."""

    metadata: KnowledgeMetadata
    body_md: str


# ============================================================================
# LLM CLIENT
# ============================================================================


class LLMClient:
    """Small OpenRouter client used by the document generator."""

    def __init__(self, api_key: str) -> None:
        self.model = MODEL
        self.temperature = TEMPERATURE
        self.max_tokens = MAX_TOKENS

        self.client = httpx.Client(
            timeout=TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://aether-wireless.local",
                "X-Title": "Aether Wireless Knowledge Base Generator",
            },
        )

    def generate(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int | None = None,
        retries: int = MAX_RETRIES,
    ) -> tuple[str, dict]:
        """
        Generate text using OpenRouter.

        Returns:
            tuple[str, dict]:
                Generated content and usage information.
        """

        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                response = self.client.post(
                    OPENROUTER_URL,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                choices = data.get("choices", [])

                if not choices:
                    raise RuntimeError("OpenRouter returned no choices.")

                message = choices[0].get("message", {})
                content = message.get("content")

                if not content:
                    raise RuntimeError("OpenRouter returned empty content.")

                usage = data.get("usage", {})

                return content.strip(), usage

            except httpx.HTTPStatusError as exc:
                last_error = exc

                status = exc.response.status_code
                body = exc.response.text[:1000]

                # These errors normally require changing configuration
                # rather than retrying.
                if status in {400, 401, 402, 403, 404}:
                    logger.error(
                        "OpenRouter request failed: status=%s body=%s",
                        status,
                        body,
                    )
                    raise

                logger.warning(
                    "OpenRouter request failed (attempt %d/%d, status=%s): %s",
                    attempt,
                    retries,
                    status,
                    body,
                )

            except httpx.TimeoutException as exc:
                last_error = exc

                logger.warning(
                    "OpenRouter timeout (attempt %d/%d)",
                    attempt,
                    retries,
                )

            except httpx.HTTPError as exc:
                last_error = exc

                logger.warning(
                    "OpenRouter HTTP error (attempt %d/%d): %s",
                    attempt,
                    retries,
                    exc,
                )

            except RuntimeError as exc:
                last_error = exc

                logger.warning(
                    "OpenRouter response error (attempt %d/%d): %s",
                    attempt,
                    retries,
                    exc,
                )

            if attempt < retries:
                time.sleep(RETRY_DELAY_SECONDS)

        raise RuntimeError("OpenRouter generation failed.") from last_error

    def close(self) -> None:
        """Close the HTTP client."""

        self.client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, *_args) -> None:
        self.close()


# ============================================================================
# DOCUMENT CATALOG
# ============================================================================


DOCUMENT_CATALOG: list[KnowledgeMetadata] = [
    # ------------------------------------------------------------------------
    # BILLING
    # ------------------------------------------------------------------------
    KnowledgeMetadata(
        title="Billing Dispute Policy",
        doc_id="AW-BIL-001",
        version="2.1",
        last_updated="2026-08-15",
        department="Billing",
        category="billing",
        brief=(
            "Policy for handling customer billing disputes, including "
            "eligibility, investigation, evidence, timelines, credits, "
            "adjustments, and escalation."
        ),
    ),
    KnowledgeMetadata(
        title="Refund Policy",
        doc_id="AW-BIL-002",
        version="2.0",
        last_updated="2026-08-10",
        department="Billing",
        category="billing",
        brief=(
            "Rules governing customer refunds, eligibility, approval, "
            "processing timelines, payment methods, and exceptions."
        ),
    ),
    KnowledgeMetadata(
        title="Payment Policy",
        doc_id="AW-BIL-003",
        version="1.5",
        last_updated="2026-07-22",
        department="Billing",
        category="billing",
        brief=(
            "Policy governing customer payment methods, payment processing, "
            "failed payments, retry handling, and account restrictions."
        ),
    ),
    KnowledgeMetadata(
        title="Billing Invoice Policy",
        doc_id="AW-BIL-004",
        version="1.3",
        last_updated="2026-07-18",
        department="Billing",
        category="billing",
        brief=(
            "Rules for invoice generation, invoice availability, invoice "
            "corrections, billing periods, and customer requests."
        ),
    ),
    KnowledgeMetadata(
        title="Payment Eligibility Terms",
        doc_id="AW-BIL-005",
        version="1.1",
        last_updated="2026-06-30",
        department="Billing",
        category="billing",
        brief=(
            "Eligibility requirements and restrictions for customer payment "
            "arrangements and payment services."
        ),
    ),
    KnowledgeMetadata(
        title="Returns and Refunds Policy",
        doc_id="AW-BIL-006",
        version="1.4",
        last_updated="2026-07-05",
        department="Billing",
        category="billing",
        brief=(
            "Rules governing device and service returns, refund eligibility, "
            "return windows, inspection, and refund processing."
        ),
    ),
    # ------------------------------------------------------------------------
    # MOBILE
    # ------------------------------------------------------------------------
    KnowledgeMetadata(
        title="Mobile Contract Policy",
        doc_id="AW-MOB-001",
        version="2.0",
        last_updated="2026-08-01",
        department="Mobile",
        category="mobile",
        brief=(
            "Rules governing mobile service contracts, contract terms, "
            "customer obligations, renewals, cancellations, and changes."
        ),
    ),
    KnowledgeMetadata(
        title="SIM Replacement Policy",
        doc_id="AW-MOB-002",
        version="1.8",
        last_updated="2026-07-25",
        department="Mobile",
        category="mobile",
        brief=(
            "Procedure and eligibility requirements for replacing a SIM, "
            "including customer verification and activation."
        ),
    ),
    KnowledgeMetadata(
        title="Number Portability Policy",
        doc_id="AW-MOB-003",
        version="1.7",
        last_updated="2026-07-20",
        department="Mobile",
        category="mobile",
        brief=(
            "Rules and procedures for transferring a mobile number from "
            "another provider to Aether Wireless."
        ),
    ),
    KnowledgeMetadata(
        title="Postpaid Plan Guidelines",
        doc_id="AW-MOB-004",
        version="2.2",
        last_updated="2026-08-02",
        department="Mobile",
        category="mobile",
        brief=(
            "Operational guidelines for postpaid plans, including eligibility, "
            "billing, usage, plan changes, and account requirements."
        ),
    ),
    KnowledgeMetadata(
        title="Plan Upgrade Policy",
        doc_id="AW-MOB-005",
        version="1.6",
        last_updated="2026-07-14",
        department="Mobile",
        category="mobile",
        brief=(
            "Rules governing mobile plan upgrades, eligibility, effective "
            "dates, charges, and customer communication."
        ),
    ),
    KnowledgeMetadata(
        title="Data Plan Terms and Conditions",
        doc_id="AW-MOB-006",
        version="1.5",
        last_updated="2026-06-25",
        department="Mobile",
        category="mobile",
        brief=(
            "Terms governing mobile data plans, data usage, allowances, "
            "restrictions, overage handling, and service limitations."
        ),
    ),
    KnowledgeMetadata(
        title="Device Upgrade Guidelines",
        doc_id="AW-MOB-007",
        version="1.4",
        last_updated="2026-07-01",
        department="Mobile",
        category="mobile",
        brief=(
            "Guidelines for device upgrades, customer eligibility, financing, "
            "trade-in requirements, and activation."
        ),
    ),
    KnowledgeMetadata(
        title="Device Trade-In Process",
        doc_id="AW-MOB-008",
        version="1.3",
        last_updated="2026-06-18",
        department="Mobile",
        category="mobile",
        brief=(
            "Operational process for device trade-ins, including eligibility, "
            "device inspection, valuation, acceptance, and credits."
        ),
    ),
    KnowledgeMetadata(
        title="Device Protection Policy",
        doc_id="AW-MOB-009",
        version="1.2",
        last_updated="2026-07-10",
        department="Mobile",
        category="mobile",
        brief=(
            "Policy governing device protection coverage, eligibility, "
            "claims, exclusions, replacement, and customer responsibilities."
        ),
    ),
    # ------------------------------------------------------------------------
    # ROAMING
    # ------------------------------------------------------------------------
    KnowledgeMetadata(
        title="Roaming Policy",
        doc_id="AW-ROM-001",
        version="2.0",
        last_updated="2026-08-05",
        department="Roaming",
        category="roaming",
        brief=(
            "General policy for domestic and international roaming, including "
            "eligibility, activation, charges, usage, and restrictions."
        ),
    ),
    KnowledgeMetadata(
        title="International Roaming Policy",
        doc_id="AW-ROM-002",
        version="1.2",
        last_updated="2026-08-12",
        department="Roaming",
        category="roaming",
        brief=(
            "Rules for international roaming eligibility, activation, usage, "
            "charges, supported destinations, and customer support."
        ),
    ),
    KnowledgeMetadata(
        title="International Roaming Service Policy",
        doc_id="AW-SRV-004",
        version="1.2",
        last_updated="2026-08-08",
        department="Roaming",
        category="roaming",
        brief=(
            "Operational service policy for international roaming services, "
            "including availability, restrictions, billing, and escalation."
        ),
    ),
    # ------------------------------------------------------------------------
    # CUSTOMER
    # ------------------------------------------------------------------------
    KnowledgeMetadata(
        title="Customer Verification Policy",
        doc_id="AW-CUS-001",
        version="2.0",
        last_updated="2026-07-28",
        department="Customer",
        category="customer",
        brief=(
            "Customer identity verification requirements for account access, "
            "service changes, sensitive requests, and support interactions."
        ),
    ),
    KnowledgeMetadata(
        title="Complaint Handling Policy",
        doc_id="AW-CUS-002",
        version="1.7",
        last_updated="2026-08-03",
        department="Customer",
        category="customer",
        brief=(
            "Process for receiving, categorizing, investigating, resolving, "
            "and escalating customer complaints."
        ),
    ),
    KnowledgeMetadata(
        title="New Line Activation Process",
        doc_id="AW-CUS-003",
        version="1.5",
        last_updated="2026-07-16",
        department="Customer",
        category="customer",
        brief=(
            "Operational procedure for activating a new mobile line, "
            "including eligibility, verification, setup, and exceptions."
        ),
    ),
    KnowledgeMetadata(
        title="Port-In Policy",
        doc_id="AW-CUS-004",
        version="1.4",
        last_updated="2026-07-19",
        department="Customer",
        category="customer",
        brief=(
            "Policy governing customer number port-ins, eligibility, "
            "verification, rejection reasons, and completion."
        ),
    ),
    KnowledgeMetadata(
        title="Promotions Eligibility Terms",
        doc_id="AW-CUS-005",
        version="1.3",
        last_updated="2026-07-30",
        department="Customer",
        category="customer",
        brief=(
            "Eligibility rules for customer promotions, including qualifying "
            "plans, account requirements, exclusions, and verification."
        ),
    ),
    KnowledgeMetadata(
        title="Loyalty Rewards Program",
        doc_id="AW-CUS-006",
        version="1.2",
        last_updated="2026-06-20",
        department="Customer",
        category="customer",
        brief=(
            "Rules for customer loyalty rewards, eligibility, reward earning, "
            "redemption, expiration, and account requirements."
        ),
    ),
    # ------------------------------------------------------------------------
    # COMPLIANCE
    # ------------------------------------------------------------------------
    KnowledgeMetadata(
        title="KYC Policy",
        doc_id="AW-CMP-001",
        version="2.1",
        last_updated="2026-08-04",
        department="Compliance",
        category="compliance",
        brief=(
            "Know Your Customer requirements covering identity verification, "
            "required information, validation, exceptions, and compliance "
            "escalation."
        ),
    ),
    KnowledgeMetadata(
        title="Data Privacy Policy",
        doc_id="AW-LEG-011",
        version="2.0",
        last_updated="2026-07-31",
        department="Compliance",
        category="compliance",
        brief=(
            "Policy governing customer data privacy, collection, access, "
            "processing, retention, disclosure, and protection."
        ),
    ),
    KnowledgeMetadata(
        title="Privacy and Data Protection Policy",
        doc_id="AW-LEG-001",
        version="1.9",
        last_updated="2026-07-27",
        department="Compliance",
        category="compliance",
        brief=(
            "Rules governing personal data protection, data handling, "
            "customer rights, security requirements, and privacy controls."
        ),
    ),
    KnowledgeMetadata(
        title="Network Service Level Agreement",
        doc_id="AW-CMP-004",
        version="1.4",
        last_updated="2026-07-22",
        department="Compliance",
        category="compliance",
        brief=(
            "Service-level requirements covering network availability, "
            "performance expectations, incident handling, measurement, "
            "and escalation."
        ),
    ),
]


# ============================================================================
# PROMPTS
# ============================================================================


SYSTEM_PROMPT = """
You are a senior telecom policy documentation specialist.

Your task is to create internal operational knowledge-base documents for
Aether Wireless.

The documents will be consumed by customer-service agents and an AI
retrieval system.

Requirements:

- Write only Markdown.
- Never invent unsupported company rules, policies, thresholds, prices,
  eligibility requirements, timelines, or regulatory obligations.
- When exact values are not provided by the source brief, describe the
  operational concept without inventing a number.
- Prefer concrete operational rules.
- Clearly distinguish eligibility, requirements, exceptions, procedures,
  responsibilities, escalation, and timelines.
- Include practical examples where useful.
- Make the document useful for retrieval and question answering.
- Use clear headings, bullets, numbered procedures, and tables when useful.
- Do not use marketing language.
- Do not mention AI, LLMs, prompts, or document generation.
- Do not put a document title at the beginning.
- The document must begin with `## Overview`.
- The document must end with `## FAQs`.
- Include 4 to 6 operational FAQs.
""".strip()


OUTLINE_PROMPT = """
Create a detailed Markdown outline for the telecom policy document described
below.

Rules:

- Return headings only.
- Use H2 headings (`##`).
- The first heading must be `## Overview`.
- The final heading must be `## FAQs`.
- Create approximately {section_count} sections.
- Cover scope, eligibility, requirements, rules, procedures, exceptions,
  responsibilities, timelines, escalation, and operational handling where
  applicable.
- Do not invent specific policy values.
- Do not write section content.

Document:

Title: {title}
Document ID: {doc_id}
Version: {version}
Last Updated: {last_updated}
Department: {department}
Category: {category}

Brief:
{brief}
""".strip()


SECTION_PROMPT = """
Write the content for the following section of an internal telecom policy
knowledge-base document.

Document information:

Title: {title}
Document ID: {doc_id}
Version: {version}
Department: {department}
Category: {category}

Document brief:
{brief}

Section:
{section}

Rules:

- Do not repeat the section heading.
- Write only the section content.
- Use Markdown.
- Be operational and precise.
- Explain applicable rules, requirements, procedures, exceptions,
  responsibilities, and escalation.
- Do not invent exact numbers, prices, dates, thresholds, or eligibility
  criteria that are not supported by the brief.
- Do not introduce unrelated policy areas.
- Use bullets, numbered steps, or tables when useful.
""".strip()


TABLE_SECTION_PROMPT = """
Create the "{section_name}" section for the following telecom policy
document. This section MUST consist of a single Markdown table
summarizing the key operational rules of the document, and nothing else.

Document information:

Title: {title}
Document ID: {doc_id}
Department: {department}
Category: {category}

Document brief:
{brief}

Rules:

- Return a Markdown table only — a header row, a separator row, and at
  least 4 data rows. No text before or after the table.
- Columns: "Rule / Area", "Description", "Timeline or Threshold",
  "Applies To".
- Where the brief does not support a specific number or date, write a
  qualitative description (e.g. "Within standard processing window")
  instead of inventing one.
- Do not repeat the section heading.
- Do not add any explanation outside the table.
""".strip()


FAQ_PROMPT = """
Create exactly 5 operational FAQs for the following telecom policy document.

Document:

Title: {title}
Document ID: {doc_id}
Department: {department}
Category: {category}

Brief:
{brief}

Use exactly this format:

Q: question
A: answer

Requirements:

- Exactly 5 questions.
- Each answer must be concise and operational.
- Questions should reflect realistic customer-service scenarios.
- Do not invent unsupported policy values.
- Do not add headings.
""".strip()


# A Markdown table separator row, e.g. "|---|---|" or "| --- | --- |".
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$")


# ============================================================================
# DOCUMENT GENERATOR
# ============================================================================


class DocumentGenerator:
    """Generates telecom policy documents using an LLM."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def generate(self, metadata: KnowledgeMetadata) -> KnowledgeDocument:
        """
        Generate one complete knowledge-base document.

        Always uses outline + section generation + a mandatory table
        section + FAQ generation, to reliably reach MIN_PAGES once
        rendered to PDF.
        """

        logger.info(
            "Generating document: %s (%s)",
            metadata.title,
            metadata.doc_id,
        )

        body = self._generate_long_document(metadata)
        body = self._clean_markdown(body)

        return KnowledgeDocument(
            metadata=metadata,
            body_md=body,
        )

    def _generate_long_document(
        self,
        metadata: KnowledgeMetadata,
    ) -> str:
        """Generate a long document in multiple controlled calls."""

        outline = self._generate_outline(metadata)

        sections = self._extract_h2_headings(outline)

        if not sections:
            logger.warning(
                "No outline headings found for %s. "
                "Retrying outline once before falling back.",
                metadata.doc_id,
            )

            outline = self._generate_outline(metadata)
            sections = self._extract_h2_headings(outline)

        # Remove Overview and FAQs because those are generated separately.
        content_sections = [
            section
            for section in sections
            if section.lower() not in {"overview", "faqs"}
        ]

        logger.info(
            "Generating %d sections for %s",
            len(content_sections),
            metadata.doc_id,
        )

        generated_sections: list[tuple[str, str]] = []

        for index, section in enumerate(
            content_sections,
            start=1,
        ):
            logger.info(
                "Generating section %d/%d: %s",
                index,
                len(content_sections),
                section,
            )

            content = self._generate_section(
                metadata,
                section,
            )

            generated_sections.append((section, content))

        # Mandatory table section — generated deterministically rather
        # than relying on the model's own outline to include a table.
        table_content = self._generate_table_section(metadata)
        generated_sections.insert(0, (TABLE_SECTION_NAME, table_content))

        overview = self._generate_section(
            metadata,
            "Overview",
        )

        faq = self._generate_faq(metadata)

        parts: list[str] = [
            "## Overview",
            "",
            overview,
            "",
        ]

        for section, content in generated_sections:
            parts.extend(
                [
                    f"## {section}",
                    "",
                    content,
                    "",
                ]
            )

        parts.extend(
            [
                "## FAQs",
                "",
                faq,
                "",
            ]
        )

        return "\n".join(parts)

    def _generate_outline(
        self,
        metadata: KnowledgeMetadata,
    ) -> str:
        """Generate a section outline."""

        prompt = OUTLINE_PROMPT.format(
            section_count=LONG_DOC_SECTIONS,
            title=metadata.title,
            doc_id=metadata.doc_id,
            version=metadata.version,
            last_updated=metadata.last_updated,
            department=metadata.department,
            category=metadata.category,
            brief=metadata.brief,
        )

        content, usage = self.llm.generate(
            [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=OUTLINE_MAX_TOKENS,
        )

        self._log_usage(
            metadata.doc_id,
            usage,
            "outline",
        )

        return content

    def _generate_section(
        self,
        metadata: KnowledgeMetadata,
        section: str,
    ) -> str:
        """Generate one document section."""

        prompt = SECTION_PROMPT.format(
            title=metadata.title,
            doc_id=metadata.doc_id,
            version=metadata.version,
            department=metadata.department,
            category=metadata.category,
            brief=metadata.brief,
            section=section,
        )

        content, usage = self.llm.generate(
            [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=SECTION_MAX_TOKENS,
        )

        self._log_usage(
            metadata.doc_id,
            usage,
            f"section:{section}",
        )

        return content

    def _generate_table_section(
        self,
        metadata: KnowledgeMetadata,
    ) -> str:
        """Generate the mandatory table section, with one retry if the
        model fails to return an actual Markdown table."""

        prompt = TABLE_SECTION_PROMPT.format(
            section_name=TABLE_SECTION_NAME,
            title=metadata.title,
            doc_id=metadata.doc_id,
            department=metadata.department,
            category=metadata.category,
            brief=metadata.brief,
        )

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        for attempt in (1, 2):
            content, usage = self.llm.generate(
                messages,
                max_tokens=TABLE_SECTION_MAX_TOKENS,
            )

            self._log_usage(
                metadata.doc_id,
                usage,
                "table_section",
            )

            if self._contains_markdown_table(content):
                return content

            logger.warning(
                "Table section for %s did not contain a valid Markdown "
                "table (attempt %d/2).",
                metadata.doc_id,
                attempt,
            )

        logger.warning(
            "Proceeding without a validated table for %s — rendering "
            "will show whatever content was returned.",
            metadata.doc_id,
        )

        return content

    def _generate_faq(
        self,
        metadata: KnowledgeMetadata,
    ) -> str:
        """Generate the FAQ section."""

        prompt = FAQ_PROMPT.format(
            title=metadata.title,
            doc_id=metadata.doc_id,
            department=metadata.department,
            category=metadata.category,
            brief=metadata.brief,
        )

        content, usage = self.llm.generate(
            [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=FAQ_MAX_TOKENS,
        )

        self._log_usage(
            metadata.doc_id,
            usage,
            "faq",
        )

        return content

    @staticmethod
    def _contains_markdown_table(markdown: str) -> bool:
        """Check whether the given text contains a Markdown table."""

        lines = [line.strip() for line in markdown.splitlines() if line.strip()]

        for i in range(len(lines) - 1):
            if "|" in lines[i] and _TABLE_SEPARATOR_RE.match(lines[i + 1]):
                return True

        return False

    @staticmethod
    def _extract_h2_headings(markdown: str) -> list[str]:
        """Extract H2 headings from Markdown."""

        headings: list[str] = []

        pattern = re.compile(
            r"^##\s+(.+?)\s*$",
            re.MULTILINE,
        )

        for match in pattern.finditer(markdown):
            heading = match.group(1).strip()

            if heading:
                headings.append(heading)

        return headings

    @staticmethod
    def _clean_markdown(markdown: str) -> str:
        """Clean common LLM Markdown artifacts."""

        markdown = markdown.strip()

        # Remove accidental fenced Markdown wrapper.
        if markdown.startswith("```markdown"):
            markdown = markdown[len("```markdown") :].strip()

        elif markdown.startswith("```md"):
            markdown = markdown[len("```md") :].strip()

        elif markdown.startswith("```"):
            markdown = markdown[3:].strip()

        if markdown.endswith("```"):
            markdown = markdown[:-3].strip()

        return markdown

    @staticmethod
    def _log_usage(
        doc_id: str,
        usage: dict,
        operation: str,
    ) -> None:
        """Log token usage returned by OpenRouter."""

        if not usage:
            return

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        logger.info(
            "LLM usage | doc=%s | operation=%s | prompt=%s | completion=%s | total=%s",
            doc_id,
            operation,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

        if completion_tokens >= MAX_COMPLETION_TOKENS_TO_WARN:
            logger.warning(
                "Completion reached warning threshold | "
                "doc=%s | operation=%s | completion=%s",
                doc_id,
                operation,
                completion_tokens,
            )


# ============================================================================
# PLAIN TEXT CONVERSION
# ============================================================================


def markdown_to_plain_text(markdown: str) -> str:
    """Convert generated Markdown into a clean plain-text rendering.

    Headings become uppercase lines underlined with dashes, inline
    formatting markers are stripped, and Markdown tables are flattened
    into simple column-separated rows.
    """

    output: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()

        if not line:
            output.append("")
            continue

        heading_match = re.match(r"^#{2,6}\s+(.*)", line)

        if heading_match:
            text = heading_match.group(1).strip()
            output.append(text.upper())
            output.append("-" * len(text))
            continue

        # Drop Markdown table separator rows entirely.
        if _TABLE_SEPARATOR_RE.match(line):
            continue

        # Flatten table rows into plain column-separated text.
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            line = "  |  ".join(cells)

        line = re.sub(r"`(.+?)`", r"\1", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"\*(.+?)\*", r"\1", line)

        output.append(line)

    text = "\n".join(output).strip()

    return text + "\n"


# ============================================================================
# PDF RENDERER
# ============================================================================


class PDFRenderer:
    """Render generated Markdown into a simple PDF."""

    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()

        self.title_style = ParagraphStyle(
            "DocumentTitle",
            parent=self.styles["Title"],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=16,
        )

        self.h2_style = ParagraphStyle(
            "H2",
            parent=self.styles["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=12,
            spaceAfter=8,
        )

        self.h3_style = ParagraphStyle(
            "H3",
            parent=self.styles["Heading3"],
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=5,
        )

        self.body_style = ParagraphStyle(
            "Body",
            parent=self.styles["BodyText"],
            fontSize=9.5,
            leading=13,
            spaceAfter=6,
        )

        self.small_style = ParagraphStyle(
            "Small",
            parent=self.styles["BodyText"],
            fontSize=8,
            leading=10,
            spaceAfter=4,
        )

    def render(
        self,
        document: KnowledgeDocument,
        output_path: Path,
    ) -> None:
        """Render a KnowledgeDocument to PDF."""

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        pdf = SimpleDocTemplate(
            str(output_path),
            pagesize=LETTER,
            rightMargin=0.65 * inch,
            leftMargin=0.65 * inch,
            topMargin=0.65 * inch,
            bottomMargin=0.65 * inch,
            title=document.metadata.title,
            author="Aether Wireless",
        )

        story: list = []

        self._add_title(
            story,
            document.metadata,
        )

        markdown_lines = document.body_md.splitlines()

        index = 0

        while index < len(markdown_lines):
            line = markdown_lines[index].strip()

            if not line:
                index += 1
                continue

            # --------------------------------------------------------------
            # H2
            # --------------------------------------------------------------

            if line.startswith("## "):
                heading = line[3:].strip()

                story.append(
                    Paragraph(
                        self._escape(heading),
                        self.h2_style,
                    )
                )

                index += 1
                continue

            # --------------------------------------------------------------
            # H3
            # --------------------------------------------------------------

            if line.startswith("### "):
                heading = line[4:].strip()

                story.append(
                    Paragraph(
                        self._escape(heading),
                        self.h3_style,
                    )
                )

                index += 1
                continue

            # --------------------------------------------------------------
            # Table
            # --------------------------------------------------------------

            if self._is_table_start(
                markdown_lines,
                index,
            ):
                table, new_index = self._parse_table(
                    markdown_lines,
                    index,
                )

                if table:
                    story.append(table)
                    story.append(Spacer(1, 8))

                index = new_index
                continue

            # --------------------------------------------------------------
            # Numbered list
            # --------------------------------------------------------------

            numbered_match = re.match(
                r"^(\d+)\.\s+(.+)",
                line,
            )

            if numbered_match:
                number = numbered_match.group(1)
                text = numbered_match.group(2)

                story.append(
                    Paragraph(
                        f"<b>{number}.</b> {self._format_inline(text)}",
                        self.body_style,
                    )
                )

                index += 1
                continue

            # --------------------------------------------------------------
            # Bullet
            # --------------------------------------------------------------

            if line.startswith("- ") or line.startswith("* "):
                text = line[2:].strip()

                story.append(
                    Paragraph(
                        f"• {self._format_inline(text)}",
                        self.body_style,
                    )
                )

                index += 1
                continue

            # --------------------------------------------------------------
            # FAQ
            # --------------------------------------------------------------

            if line.startswith("Q:"):
                question = line[2:].strip()

                story.append(
                    Paragraph(
                        f"<b>Q:</b> {self._format_inline(question)}",
                        self.body_style,
                    )
                )

                index += 1
                continue

            if line.startswith("A:"):
                answer = line[2:].strip()

                story.append(
                    Paragraph(
                        f"<b>A:</b> {self._format_inline(answer)}",
                        self.body_style,
                    )
                )

                index += 1
                continue

            # --------------------------------------------------------------
            # Regular paragraph
            # --------------------------------------------------------------

            paragraph_lines = [line]

            next_index = index + 1

            while next_index < len(markdown_lines):
                next_line = markdown_lines[next_index].strip()

                if not next_line:
                    break

                if (
                    next_line.startswith("## ")
                    or next_line.startswith("### ")
                    or next_line.startswith("- ")
                    or next_line.startswith("* ")
                    or next_line.startswith("Q:")
                    or next_line.startswith("A:")
                    or re.match(r"^\d+\.\s+", next_line)
                    or self._is_table_start(
                        markdown_lines,
                        next_index,
                    )
                ):
                    break

                paragraph_lines.append(next_line)
                next_index += 1

            paragraph = " ".join(paragraph_lines)

            story.append(
                Paragraph(
                    self._format_inline(paragraph),
                    self.body_style,
                )
            )

            index = next_index

        pdf.build(story)

    def _add_title(
        self,
        story: list,
        metadata: KnowledgeMetadata,
    ) -> None:
        """Add document title and metadata."""

        story.append(
            Paragraph(
                self._escape(metadata.title),
                self.title_style,
            )
        )

        metadata_table = Table(
            [
                [
                    "<b>Document ID</b>",
                    self._escape(metadata.doc_id),
                    "<b>Version</b>",
                    self._escape(metadata.version),
                ],
                [
                    "<b>Department</b>",
                    self._escape(metadata.department),
                    "<b>Category</b>",
                    self._escape(metadata.category),
                ],
                [
                    "<b>Last Updated</b>",
                    self._escape(metadata.last_updated),
                    "<b>Status</b>",
                    "Active",
                ],
            ],
            colWidths=[
                1.0 * inch,
                1.55 * inch,
                1.0 * inch,
                1.55 * inch,
            ],
        )

        metadata_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, -1),
                        colors.whitesmoke,
                    ),
                    (
                        "BACKGROUND",
                        (2, 0),
                        (2, -1),
                        colors.whitesmoke,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, -1),
                        "Helvetica",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        8,
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        story.append(metadata_table)
        story.append(Spacer(1, 16))

    @staticmethod
    def _is_table_start(
        lines: list[str],
        index: int,
    ) -> bool:
        """Check whether the current line starts a Markdown table."""

        if index + 1 >= len(lines):
            return False

        current = lines[index].strip()
        separator = lines[index + 1].strip()

        if "|" not in current:
            return False

        return bool(_TABLE_SEPARATOR_RE.match(separator))

    def _parse_table(
        self,
        lines: list[str],
        index: int,
    ) -> tuple[Table | None, int]:
        """Parse a basic Markdown table."""

        rows: list[list[str]] = []

        while index < len(lines):
            line = lines[index].strip()

            if not line or "|" not in line:
                break

            if len(rows) == 1 and _TABLE_SEPARATOR_RE.match(line):
                index += 1
                continue

            cells = [cell.strip() for cell in line.strip("|").split("|")]

            rows.append([self._format_inline(cell) for cell in cells])

            index += 1

        if not rows:
            return None, index

        table = Table(
            rows,
            repeatRows=1,
            hAlign="LEFT",
        )

        table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.whitesmoke,
                    ),
                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        7.5,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        4,
                    ),
                ]
            )
        )

        return table, index

    @staticmethod
    def _escape(text: str) -> str:
        """Escape text for ReportLab Paragraph."""

        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _format_inline(self, text: str) -> str:
        """Convert basic Markdown inline formatting to ReportLab HTML."""

        text = self._escape(text)

        # Inline code.
        text = re.sub(
            r"`(.+?)`",
            r"<font name='Courier'>\1</font>",
            text,
        )

        # Bold.
        text = re.sub(
            r"\*\*(.+?)\*\*",
            r"<b>\1</b>",
            text,
        )

        # Italic.
        text = re.sub(
            r"\*(.+?)\*",
            r"<i>\1</i>",
            text,
        )

        return text


def count_pdf_pages(pdf_path: Path) -> int | None:
    """Return the page count of a rendered PDF, or None if pypdf is
    not installed (page-count verification is then skipped)."""

    if not HAVE_PDF_READER:
        return None

    try:
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        logger.warning("Could not read back page count for %s.", pdf_path)
        return None


# ============================================================================
# FILE OUTPUT
# ============================================================================


def document_output_dir(
    metadata: KnowledgeMetadata,
) -> Path:
    """Return the category directory for a document."""

    return RAW_DIR / metadata.category


def document_filename(
    metadata: KnowledgeMetadata,
) -> str:
    """Create a filesystem-safe filename."""

    filename = metadata.title.lower()

    filename = re.sub(
        r"[^a-z0-9]+",
        "_",
        filename,
    )

    filename = filename.strip("_")

    return f"{metadata.doc_id}_{filename}"


def save_document(
    document: KnowledgeDocument,
    renderer: PDFRenderer,
    *,
    keep_md: bool,
    keep_txt: bool,
) -> dict[str, Path]:
    """Save PDF (always), and optionally Markdown and/or plain text.

    Returns a dict mapping format name ("pdf", "md", "txt") to the
    path written, for whichever formats were produced.
    """

    output_dir = document_output_dir(document.metadata)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    base_name = document_filename(document.metadata)

    paths: dict[str, Path] = {}

    if keep_md:
        md_path = output_dir / f"{base_name}.md"

        md_path.write_text(
            document.body_md,
            encoding="utf-8",
        )

        paths["md"] = md_path

    if keep_txt:
        txt_path = output_dir / f"{base_name}.txt"

        txt_path.write_text(
            markdown_to_plain_text(document.body_md),
            encoding="utf-8",
        )

        paths["txt"] = txt_path

    pdf_path = output_dir / f"{base_name}.pdf"

    renderer.render(
        document,
        pdf_path,
    )

    paths["pdf"] = pdf_path

    return paths


# ============================================================================
# CATALOG FILTERING
# ============================================================================


def select_documents(
    *,
    limit: int | None,
    category: str | None,
) -> list[KnowledgeMetadata]:
    """Select documents from the catalog."""

    documents = DOCUMENT_CATALOG

    if category:
        category = category.lower()

        documents = [
            document for document in documents if document.category.lower() == category
        ]

    if limit is not None:
        documents = documents[:limit]

    return documents


# ============================================================================
# CLI
# ============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate Aether Wireless telecom policy knowledge-base documents."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to generate.",
    )

    parser.add_argument(
        "--only",
        dest="category",
        choices=[
            "billing",
            "mobile",
            "roaming",
            "customer",
            "compliance",
        ],
        help="Generate only documents from one category.",
    )

    parser.add_argument(
        "--keep-md",
        action="store_true",
        help="Also save the generated Markdown source file.",
    )

    parser.add_argument(
        "--keep-txt",
        action="store_true",
        help="Also save a plain-text rendering of the document.",
    )

    return parser.parse_args()


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    """Application entry point."""

    args = parse_args()

    documents = select_documents(
        limit=args.limit,
        category=args.category,
    )

    if not documents:
        logger.warning("No documents selected.")
        return 0

    logger.info(
        "Selected %d document(s).",
        len(documents),
    )

    logger.info(
        "Model: %s",
        MODEL,
    )

    logger.info(
        "Output directory: %s",
        RAW_DIR,
    )

    if not HAVE_PDF_READER:
        logger.info(
            "pypdf is not installed — page-count verification (target: "
            "%d pages) will be skipped.",
            MIN_PAGES,
        )

    renderer = PDFRenderer()

    successful = 0
    failed = 0
    short_pages = 0

    start_time = time.perf_counter()

    with LLMClient(OPENROUTER_API_KEY) as llm:
        generator = DocumentGenerator(llm)

        for index, metadata in enumerate(
            documents,
            start=1,
        ):
            logger.info(
                "Processing document %d/%d: %s",
                index,
                len(documents),
                metadata.title,
            )

            try:
                document = generator.generate(metadata)

                paths = save_document(
                    document,
                    renderer,
                    keep_md=args.keep_md,
                    keep_txt=args.keep_txt,
                )

                for fmt, path in paths.items():
                    logger.info(
                        "Generated %s: %s",
                        fmt.upper(),
                        path,
                    )

                page_count = count_pdf_pages(paths["pdf"])

                if page_count is not None:
                    if page_count < MIN_PAGES:
                        short_pages += 1

                        logger.warning(
                            "%s has only %d page(s), below the %d-page "
                            "target.",
                            metadata.doc_id,
                            page_count,
                            MIN_PAGES,
                        )
                    else:
                        logger.info(
                            "%s rendered with %d page(s).",
                            metadata.doc_id,
                            page_count,
                        )

                successful += 1

            except Exception:
                failed += 1

                logger.exception(
                    "Failed to generate %s (%s)",
                    metadata.title,
                    metadata.doc_id,
                )

    elapsed = time.perf_counter() - start_time

    logger.info(
        "Generation completed | successful=%d | failed=%d | "
        "below_page_target=%d | elapsed=%.2fs",
        successful,
        failed,
        short_pages,
        elapsed,
    )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())