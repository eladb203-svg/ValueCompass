import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.capabilities.financial_etl_capabilities import (
    FinancialETLCapabilities,
)
from src.services.company_sync_service import CompanySyncService
from src.services.web_access_service import WebAccessService


# ---------------------------------------------------------
# 1. Environment and Skill
# ---------------------------------------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY was not found in .env")

if not model_name:
    raise RuntimeError("GEMINI_MODEL was not found in .env")


project_root = Path(__file__).resolve().parent.parent

skill_path = (
    project_root
    / ".agents"
    / "skills"
    / "financial-data-etl"
    / "SKILL.md"
)

skill_text = skill_path.read_text(encoding="utf-8")


# ---------------------------------------------------------
# 2. ValueCompass services
# ---------------------------------------------------------

sync_service = CompanySyncService()
capabilities = FinancialETLCapabilities()
web_access = WebAccessService()


# ---------------------------------------------------------
# 3. Open the real ETL sync
# ---------------------------------------------------------

sync_result = sync_service.sync_company(
    company_id=1,
    latest_expected_fiscal_year=2026,
    target_years=10,
)

etl_request = sync_result["etl_request"]
sync_log_id = etl_request["sync_log_id"]
company_id = etl_request["company_id"]


print("\n[ETL REQUEST]")
print(json.dumps(etl_request, indent=2, ensure_ascii=False))


# ---------------------------------------------------------
# 4. Runtime state for this Agent run
# ---------------------------------------------------------

run_state = {
    "records_updated": 0,
    "source_details": [],
    "metadata_result": None,
}


# ---------------------------------------------------------
# 5. Search tool available to Gemini
# ---------------------------------------------------------

def search_web(
    query: str,
    include_domains: list[str] | None = None,
    max_results: int = 5,
) -> dict:
    """Search the web for sources needed by the current ETL task.

    Args:
        query: Search query.
        include_domains: Optional domains to restrict the search to.
        max_results: Maximum number of results to return.

    Returns:
        Relevant web results with title, URL, content, and score.
    """

    print(
        f"\n[TOOL] search_web called: {query}",
        flush=True,
    )

    return web_access.search_web(
        query=query,
        include_domains=include_domains,
        max_results=max_results,
    )


# ---------------------------------------------------------
# 6. Approved metadata-write tool available to Gemini
# ---------------------------------------------------------

def submit_company_metadata(
    public_since_date: str | None = None,
    reporting_currency: str | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
) -> dict:
    """Submit researched company metadata to the ValueCompass backend.

    Args:
        public_since_date: Public trading start date in YYYY-MM-DD format.
        reporting_currency: Three-letter reporting currency when requested.
        source_name: Name of the source actually used.
        source_url: URL of the source actually used.

    Returns:
        The backend validation and persistence result.
    """

    metadata = {}

    if public_since_date is not None:
        metadata["public_since_date"] = public_since_date

    if reporting_currency is not None:
        metadata["reporting_currency"] = reporting_currency

    print(
        f"\n[TOOL] submit_company_metadata called: {metadata}",
        flush=True,
    )

    result = capabilities.update_company_metadata(
        sync_log_id=sync_log_id,
        company_id=company_id,
        metadata=metadata,
    )

    run_state["metadata_result"] = result

    if result.get("status") == "UPDATED":
        run_state["records_updated"] += 1

        if source_name or source_url:
            run_state["source_details"].append({
                "source": source_name,
                "url": source_url,
            })

    return result


# ---------------------------------------------------------
# 7. Gemini client
# ---------------------------------------------------------

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        timeout=180000,
        retry_options=types.HttpRetryOptions(
            attempts=3,
            initial_delay=2.0,
            max_delay=10.0,
            exp_base=2.0,
            jitter=1.0,
        ),
    ),
)


chat = client.chats.create(
    model=model_name,
    config=types.GenerateContentConfig(
        system_instruction=skill_text,
        temperature=0.1,
        thinking_config=types.ThinkingConfig(
            thinking_level="low",
        ),
        tools=[
            search_web,
            submit_company_metadata,
        ],
    ),
)


# ---------------------------------------------------------
# 8. Operational ETL prompt
# ---------------------------------------------------------

prompt = f"""
Execute the following ValueCompass Financial ETL request:

{json.dumps(etl_request, indent=2)}

Follow the Financial Data ETL Skill exactly.

Use only the approved tools available to you.

For required metadata:
- research the requested field using search_web;
- follow the Skill source hierarchy;
- prefer authoritative or official sources;
- do not use internal model knowledge as evidence;
- do not invent or estimate values;
- submit a value only when it is sufficiently supported;
- include the source name and exact source URL when submitting metadata.

Do not perform work that is outside this ETL request.

After the approved backend tool returns, report what was done and
whether the backend accepted the update.
"""


# ---------------------------------------------------------
# 9. Execute Agent and finalize the sync
# ---------------------------------------------------------

try:
    print("\n[AGENT] Starting ETL execution...", flush=True)

    response = chat.send_message(prompt)

    print("\n[AGENT RESPONSE]")
    print(response.text)

    metadata_result = run_state["metadata_result"]

    if (
        metadata_result
        and metadata_result.get("status") == "UPDATED"
    ):
        final_status = "success"
        error_message = None
    else:
        final_status = "failed"
        error_message = "Metadata repair was not completed successfully."

    summary = {
        "records_updated": run_state["records_updated"],
        "source_details": run_state["source_details"],
    }

    if error_message:
        summary["error_message"] = error_message

    finalize_result = capabilities.finalize_sync(
        sync_log_id=sync_log_id,
        company_id=company_id,
        status=final_status,
        summary=summary,
    )

    print("\n[FINALIZE]")
    print(finalize_result)

except Exception as error:
    print(f"\n[ERROR] {error}")

    finalize_result = capabilities.finalize_sync(
        sync_log_id=sync_log_id,
        company_id=company_id,
        status="failed",
        summary={
            "records_updated": run_state["records_updated"],
            "source_details": run_state["source_details"],
            "error_message": str(error)[:1000],
        },
    )

    print("\n[FINALIZE AFTER ERROR]")
    print(finalize_result)

    raise