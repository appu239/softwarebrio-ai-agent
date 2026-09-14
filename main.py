import json

from urllib.parse import urlparse

from scraper import scrape_company

from llm_extractor import extract_company_intelligence

from search_agent import search_company_externally


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

TARGET_DOMAINS = [
    "https://postman.com",
    "https://supabase.com",
    "https://vapi.ai",
]

MAX_TOTAL_CHARS = 16000


# ---------------------------------------------------------
# Content preparation
# ---------------------------------------------------------

def build_company_context(
    scraped_pages: list[dict],
) -> str:
    """
    Combine cleaned webpage content and explicitly discovered
    contact information into one context for the LLM.

    The total context is capped to control token usage.

    LinkedIn profile context is also included so the LLM can
    associate explicitly discovered names and roles with
    LinkedIn URLs without inventing information.
    """

    combined_text = ""

    for page in scraped_pages:

        if not page.get("text"):
            continue

        page_content = (
            f"\n\nPAGE URL: {page['url']}\n"
            f"PAGE TITLE: {page['title']}\n"
            f"PAGE CONTENT:\n{page['text']}\n"
        )

        # -------------------------------------------------
        # Include explicitly discovered emails.
        # -------------------------------------------------

        emails = page.get(
            "emails",
            [],
        )

        if emails:
            page_content += (
                "\nPUBLIC EMAILS DISCOVERED:\n"
                + "\n".join(emails)
                + "\n"
            )

        # -------------------------------------------------
        # Include explicitly discovered LinkedIn URLs.
        # -------------------------------------------------

        linkedin_urls = page.get(
            "linkedin_urls",
            [],
        )

        if linkedin_urls:
            page_content += (
                "\nLINKEDIN URLS DISCOVERED:\n"
                + "\n".join(linkedin_urls)
                + "\n"
            )

        # -------------------------------------------------
        # Include LinkedIn profile context.
        #
        # This helps the LLM connect a person's name/role
        # with the correct LinkedIn URL.
        # -------------------------------------------------

        linkedin_profiles = page.get(
            "linkedin_profiles",
            [],
        )

        if linkedin_profiles:

            page_content += (
                "\nLINKEDIN PROFILE CONTEXT:\n"
            )

            for profile in linkedin_profiles:

                profile_url = profile.get(
                    "url",
                    "",
                )

                profile_context = profile.get(
                    "context",
                    "",
                )

                if profile_url:

                    page_content += (
                        f"URL: {profile_url}\n"
                    )

                    if profile_context:

                        page_content += (
                            f"Visible page context: "
                            f"{profile_context}\n"
                        )

        # -------------------------------------------------
        # Respect total context limit.
        # -------------------------------------------------

        remaining = (
            MAX_TOTAL_CHARS
            - len(combined_text)
        )

        if remaining <= 0:
            break

        combined_text += page_content[:remaining]

    return combined_text


# ---------------------------------------------------------
# External search context
# ---------------------------------------------------------

def build_external_search_context(
    search_results: list[dict],
) -> str:
    """
    Convert Tavily search results into a compact context
    that can be supplied to the LLM as supplementary evidence.

    External search results are treated as supporting evidence.
    The website content remains the primary source.
    """

    if not search_results:
        return ""

    context = (
        "\n\n"
        "EXTERNAL SEARCH EVIDENCE:\n"
        "The following information was discovered through "
        "public web search. Use it only as supplementary "
        "evidence when relevant. Do not treat search results "
        "as stronger than direct company website evidence.\n"
    )

    for index, result in enumerate(
        search_results,
        start=1,
    ):

        title = result.get(
            "title",
            "",
        )

        url = result.get(
            "url",
            "",
        )

        content = result.get(
            "content",
            "",
        )

        if not (
            title
            or url
            or content
        ):
            continue

        # Keep individual search results compact.
        content = content[:700]

        context += (
            f"\nSEARCH RESULT {index}\n"
            f"TITLE: {title}\n"
            f"URL: {url}\n"
            f"CONTENT: {content}\n"
        )

    return context


# ---------------------------------------------------------
# Deterministic metadata collection
# ---------------------------------------------------------

def collect_scraped_metadata(
    scraped_pages: list[dict],
) -> tuple[list[str], list[str], list[dict]]:
    """
    Collect emails, LinkedIn URLs, and LinkedIn profile
    context directly from scraper results.

    These values are deterministic because they were
    discovered directly from webpage HTML.
    """

    emails: set[str] = set()

    linkedin_urls: set[str] = set()

    linkedin_profiles: list[dict] = []

    for page in scraped_pages:

        # -------------------------------------------------
        # Collect emails.
        # -------------------------------------------------

        for email in page.get(
            "emails",
            [],
        ):

            if email:
                emails.add(email)

        # -------------------------------------------------
        # Collect LinkedIn URLs.
        # -------------------------------------------------

        for linkedin_url in page.get(
            "linkedin_urls",
            [],
        ):

            if linkedin_url:
                linkedin_urls.add(
                    linkedin_url
                )

        # -------------------------------------------------
        # Collect LinkedIn profile context.
        # -------------------------------------------------

        for profile in page.get(
            "linkedin_profiles",
            [],
        ):

            if not isinstance(
                profile,
                dict,
            ):
                continue

            profile_url = profile.get(
                "url",
                "",
            )

            if not profile_url:
                continue

            # Avoid duplicate profile entries.
            already_exists = any(
                item.get("url") == profile_url
                for item in linkedin_profiles
            )

            if not already_exists:

                linkedin_profiles.append(
                    {
                        "url": profile_url,
                        "context": profile.get(
                            "context",
                            "",
                        ),
                    }
                )

    return (
        sorted(emails),
        sorted(linkedin_urls),
        linkedin_profiles,
    )


# ---------------------------------------------------------
# Leadership evidence validation
# ---------------------------------------------------------

def validate_leadership_against_evidence(
    leadership: list[dict],
    evidence: str,
) -> list[dict]:
    """
    Keep only leadership records that have reasonable
    evidence in the research context.

    Validation rules:

    - Ignore invalid/non-dictionary records.
    - Require a non-empty name and role.
    - Require a reasonably complete person name.
    - Require the person's name to appear in the evidence.
    - Require the role/title to appear in the evidence.
    - Reject company LinkedIn pages.
    - Keep an individual LinkedIn URL only when it is
      explicitly present in the evidence.

    This prevents incomplete or weakly supported leadership
    records from appearing in the final output.
    """

    evidence_lower = evidence.lower()

    # Normalize whitespace so evidence matching is more reliable.
    normalized_evidence = " ".join(
        evidence_lower.split()
    )

    validated = []

    for member in leadership:

        if not isinstance(member, dict):
            continue

        name = str(
            member.get(
                "name",
                "",
            )
        ).strip()

        role = str(
            member.get(
                "role",
                "",
            )
        ).strip()

        linkedin_url = str(
            member.get(
                "linkedin_url",
                "",
            )
        ).strip()

        # -------------------------------------------------
        # Basic validation
        # -------------------------------------------------

        if not name or not role:
            continue

        # -------------------------------------------------
        # Require a reasonably complete person's name.
        #
        # This prevents incomplete values such as:
        # "Seth"
        # "John"
        # "CEO"
        #
        # from becoming leadership records.
        # -------------------------------------------------

        name_parts = name.split()

        if len(name_parts) < 2:

            print(
                f"  Removing incomplete leadership name: "
                f"{name}"
            )

            continue

        # -------------------------------------------------
        # Person's name must appear in the evidence.
        # -------------------------------------------------

        normalized_name = " ".join(
            name_parts
        ).lower()

        name_supported = (
            normalized_name
            in normalized_evidence
        )

        if not name_supported:

            print(
                f"  Removing unsupported leadership member: "
                f"{name}"
            )

            continue

        # -------------------------------------------------
        # Role must also be supported by the evidence.
        #
        # This makes validation stricter than simply
        # checking whether the person's name exists.
        # -------------------------------------------------

        normalized_role = " ".join(
            role.lower().split()
        )

        role_supported = (
            normalized_role
            in normalized_evidence
        )

        if not role_supported:

            print(
                f"  Removing unsupported role for: "
                f"{name}"
            )

            continue

        # -------------------------------------------------
        # Never allow a company LinkedIn page to represent
        # an individual leadership member.
        # -------------------------------------------------

        if "/company/" in linkedin_url.lower():

            print(
                f"  Removing company LinkedIn URL for: "
                f"{name}"
            )

            linkedin_url = ""

        # -------------------------------------------------
        # LinkedIn URL must be explicitly present in the
        # evidence supplied to the LLM.
        # -------------------------------------------------

        if linkedin_url:

            if linkedin_url.lower() not in evidence_lower:

                print(
                    f"  Removing unsupported LinkedIn URL "
                    f"for: {name}"
                )

                linkedin_url = ""

        validated.append(
            {
                "name": name,
                "role": role,
                "linkedin_url": linkedin_url,
            }
        )

    return validated


# ---------------------------------------------------------
# Leadership + LinkedIn merging
# ---------------------------------------------------------

def merge_leadership_linkedin(
    leadership: list[dict],
    linkedin_urls: list[str],
) -> list[dict]:
    """
    Preserve valid leadership information extracted by the LLM.

    Company LinkedIn pages (/company/) are excluded because
    they do not represent individual leadership members.

    Unmatched LinkedIn profile URLs are not converted into
    artificial "Unknown" people because the system should
    never invent a person's name or role.
    """

    merged = []

    for member in leadership:

        member_copy = dict(
            member
        )

        linkedin_url = member_copy.get(
            "linkedin_url",
            "",
        )

        # -------------------------------------------------
        # Exclude company LinkedIn pages from leadership.
        # -------------------------------------------------

        if "/company/" in linkedin_url.lower():

            member_copy[
                "linkedin_url"
            ] = ""

        merged.append(
            member_copy
        )

    return merged


# ---------------------------------------------------------
# Cost summary
# ---------------------------------------------------------

def create_cost_summary(
    results: list[dict],
) -> dict:
    """
    Calculate total token usage and estimated cost
    across successfully processed companies.
    """

    total_input_tokens = 0

    total_output_tokens = 0

    total_tokens = 0

    total_cost = 0.0

    successful_companies = 0

    for result in results:

        usage = result.get(
            "usage"
        )

        if not usage:
            continue

        successful_companies += 1

        total_input_tokens += usage.get(
            "input_tokens",
            0,
        )

        total_output_tokens += usage.get(
            "output_tokens",
            0,
        )

        total_tokens += usage.get(
            "total_tokens",
            0,
        )

        total_cost += usage.get(
            "estimated_cost_usd",
            0.0,
        )

    return {
        "successful_companies": successful_companies,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "estimated_total_cost_usd": round(
            total_cost,
            8,
        ),
    }


# ---------------------------------------------------------
# Agent execution
# ---------------------------------------------------------

def run_agent(
    domain: str,
) -> dict:
    """
    Run the complete lead enrichment pipeline for one company.

    Pipeline:

        Website
            ↓
        Playwright
            ↓
        Clean content
            ↓
        Contact / LinkedIn extraction
            ↓
        External web search
            ↓
        Combined evidence
            ↓
        LLM extraction
            ↓
        Pydantic validation
            ↓
        Evidence validation
            ↓
        Deterministic metadata
            ↓
        Structured result
    """

    print(
        "\n" + "=" * 60
    )

    print(
        f"STARTING AGENT: {domain}"
    )

    print(
        "=" * 60
    )

    try:

        # -------------------------------------------------
        # Step 1: Scrape website
        # -------------------------------------------------

        scraped_pages = scrape_company(
            domain
        )

        # -------------------------------------------------
        # Step 2: Collect deterministic metadata
        # -------------------------------------------------

        (
            scraped_emails,
            scraped_linkedin_urls,
            scraped_linkedin_profiles,
        ) = collect_scraped_metadata(
            scraped_pages
        )

        print(
            f"\nScraper discovered "
            f"{len(scraped_emails)} public email(s)."
        )

        print(
            f"Scraper discovered "
            f"{len(scraped_linkedin_urls)} LinkedIn URL(s)."
        )

        print(
            f"Scraper discovered "
            f"{len(scraped_linkedin_profiles)} "
            f"LinkedIn profile context item(s)."
        )

        # -------------------------------------------------
        # Step 3: Build website context
        # -------------------------------------------------

        combined_text = build_company_context(
            scraped_pages
        )

        # -------------------------------------------------
        # Step 4: External web search
        # -------------------------------------------------

        parsed_domain = urlparse(
            domain
        ).netloc

        company_name = (
            parsed_domain
            .replace(
                "www.",
                "",
            )
            .split(".")[0]
            .replace(
                "-",
                " ",
            )
            .title()
        )

        print(
            f"\nRunning external web search for: "
            f"{company_name}"
        )

        external_search_results = (
            search_company_externally(
                company_name=company_name,
                domain=domain,
            )
        )

        print(
            f"Tavily returned "
            f"{len(external_search_results)} "
            f"search result(s)."
        )

        external_search_context = (
            build_external_search_context(
                external_search_results
            )
        )

        # -------------------------------------------------
        # Step 5: Combine website + external evidence
        #
        # Keep the final context within the token budget.
        # -------------------------------------------------

        if external_search_context:

            remaining_chars = (
                MAX_TOTAL_CHARS
                - len(combined_text)
            )

            if remaining_chars > 0:

                combined_text += (
                    external_search_context[
                        :remaining_chars
                    ]
                )

        # -------------------------------------------------
        # Step 6: Validate content
        # -------------------------------------------------

        if not combined_text.strip():

            return {
                "domain": domain,
                "error": (
                    "No usable website or external "
                    "search content found."
                ),
            }

        print(
            f"\nFinal LLM context size: "
            f"{len(combined_text)} characters."
        )

        # -------------------------------------------------
        # Step 7: LLM extraction
        # -------------------------------------------------

        print(
            "\nSending combined evidence to AI..."
        )

        intelligence, usage = (
            extract_company_intelligence(
                combined_text
            )
        )

        # -------------------------------------------------
        # Step 8: Build structured result
        # -------------------------------------------------

        result = intelligence.model_dump()

        # -------------------------------------------------
        # Preserve deterministic scraper metadata.
        # -------------------------------------------------

        result["contact_points"] = (
            scraped_emails
            if scraped_emails
            else result.get(
                "contact_points",
                [],
            )
        )

        # -------------------------------------------------
        # Validate LLM leadership against the actual
        # evidence supplied to the LLM.
        # -------------------------------------------------

        result["leadership"] = (
            validate_leadership_against_evidence(
                result.get(
                    "leadership",
                    [],
                ),
                combined_text,
            )
        )

        result["domain"] = domain

        result["usage"] = usage

        # -------------------------------------------------
        # Terminal output
        # -------------------------------------------------

        print(
            "\nAI extraction successful."
        )

        print(
            f"Final contact points: "
            f"{len(result['contact_points'])}"
        )

        print(
            f"Final leadership/LinkedIn entries: "
            f"{len(result['leadership'])}"
        )

        print(
            f"Tokens used: "
            f"{usage['total_tokens']} "
            f"(input: "
            f"{usage['input_tokens']}, "
            f"output: "
            f"{usage['output_tokens']})"
        )

        print(
            f"Estimated cost: "
            f"${usage['estimated_cost_usd']:.8f}"
        )

        return result

    except Exception as error:

        # -------------------------------------------------
        # Company-level resilience
        # -------------------------------------------------

        print(
            f"Agent failed for {domain}"
        )

        print(
            f"Reason: {error}"
        )

        return {
            "domain": domain,
            "error": str(error),
        }


# ---------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------

def main():

    all_results = []

    for domain in TARGET_DOMAINS:

        result = run_agent(
            domain
        )

        all_results.append(
            result
        )

    # -----------------------------------------------------
    # Step 9: Cost summary
    # -----------------------------------------------------

    cost_summary = create_cost_summary(
        all_results
    )

    # -----------------------------------------------------
    # Step 10: Final output
    # -----------------------------------------------------

    final_output = {
        "results": all_results,
        "cost_summary": cost_summary,
    }

    with open(
        "output.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # -----------------------------------------------------
    # Final terminal summary
    # -----------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "ALL COMPANIES PROCESSED"
    )

    print(
        "=" * 60
    )

    print(
        "\nToken Usage Summary:"
    )

    print(
        f"  Input tokens: "
        f"{cost_summary['total_input_tokens']}"
    )

    print(
        f"  Output tokens: "
        f"{cost_summary['total_output_tokens']}"
    )

    print(
        f"  Total tokens: "
        f"{cost_summary['total_tokens']}"
    )

    print(
        f"  Estimated total cost: "
        f"${cost_summary['estimated_total_cost_usd']:.8f}"
    )

    print(
        "\nResults saved to: output.json"
    )


if __name__ == "__main__":
    main()