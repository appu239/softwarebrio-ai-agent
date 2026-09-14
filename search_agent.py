import os

from dotenv import load_dotenv
from tavily import TavilyClient


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise ValueError(
        "TAVILY_API_KEY is missing. Please check your .env file."
    )

tavily_client = TavilyClient(
    api_key=api_key
)


# ---------------------------------------------------------
# Search configuration
# ---------------------------------------------------------

MAX_RESULTS_PER_QUERY = 5
MAX_FINAL_RESULTS = 8
MAX_CONTENT_CHARS = 700


# ---------------------------------------------------------
# Result relevance
# ---------------------------------------------------------

def calculate_result_priority(
    result: dict,
) -> int:
    """
    Assign a simple relevance score to a Tavily result.

    Higher scores are given to:
    - Individual LinkedIn profiles
    - LinkedIn company pages
    - Leadership-related results

    This helps reduce unnecessary search evidence before
    sending it to the LLM.
    """

    title = result.get(
        "title",
        "",
    ).lower()

    url = result.get(
        "url",
        "",
    ).lower()

    content = result.get(
        "content",
        "",
    ).lower()

    score = 0

    # -----------------------------------------------------
    # LinkedIn profile
    # -----------------------------------------------------

    if "linkedin.com/in/" in url:
        score += 10

    # -----------------------------------------------------
    # LinkedIn company page
    # -----------------------------------------------------

    if "linkedin.com/company/" in url:
        score += 7

    # -----------------------------------------------------
    # Leadership keywords
    # -----------------------------------------------------

    leadership_keywords = [
        "ceo",
        "chief executive",
        "cto",
        "chief technology",
        "co-founder",
        "founder",
        "president",
        "vp",
        "vice president",
    ]

    for keyword in leadership_keywords:

        if keyword in title:
            score += 5

        elif keyword in content:
            score += 2

    # -----------------------------------------------------
    # Company relevance
    # -----------------------------------------------------

    if "company" in title:
        score += 2

    if "leadership" in title:
        score += 4

    if "about" in title:
        score += 2

    return score


# ---------------------------------------------------------
# Result cleanup
# ---------------------------------------------------------

def clean_search_results(
    results: list[dict],
) -> list[dict]:
    """
    Remove duplicate URLs and prioritize the most relevant
    external search results.

    Only a limited number of high-value results are returned
    to control LLM context size and token usage.
    """

    unique_results: dict[str, dict] = {}

    for result in results:

        url = result.get(
            "url",
            "",
        ).strip()

        if not url:
            continue

        # -------------------------------------------------
        # Deduplicate by URL.
        # -------------------------------------------------

        if url in unique_results:
            continue

        content = result.get(
            "content",
            "",
        )

        # Keep external evidence compact.

        result["content"] = content[
            :MAX_CONTENT_CHARS
        ]

        result["priority"] = (
            calculate_result_priority(
                result
            )
        )

        unique_results[url] = result

    # -----------------------------------------------------
    # Sort highest relevance first.
    # -----------------------------------------------------

    sorted_results = sorted(
        unique_results.values(),
        key=lambda item: item.get(
            "priority",
            0,
        ),
        reverse=True,
    )

    # -----------------------------------------------------
    # Keep only the most useful results.
    # -----------------------------------------------------

    return sorted_results[
        :MAX_FINAL_RESULTS
    ]


# ---------------------------------------------------------
# External company search
# ---------------------------------------------------------

def search_company_externally(
    company_name: str,
    domain: str,
) -> list[dict]:
    """
    Search the public web for additional company and
    leadership information.

    The search is used as supplementary evidence when
    information is not available directly from the
    company's website.

    Direct company website evidence remains the primary
    source for the lead enrichment pipeline.
    """

    queries = [
        f'"{company_name}" LinkedIn company',
        f'"{company_name}" CEO LinkedIn',
        f'"{company_name}" CTO LinkedIn',
    ]

    raw_results: list[dict] = []

    for query in queries:

        print(
            f"  Tavily search: {query}"
        )

        try:

            response = tavily_client.search(
                query=query,
                search_depth="basic",
                max_results=MAX_RESULTS_PER_QUERY,
            )

            for item in response.get(
                "results",
                [],
            ):

                raw_results.append(
                    {
                        "query": query,
                        "title": item.get(
                            "title",
                            "",
                        ),
                        "url": item.get(
                            "url",
                            "",
                        ),
                        "content": item.get(
                            "content",
                            "",
                        ),
                    }
                )

        except Exception as error:

            print(
                f"  Tavily search failed: {error}"
            )

            # Continue with the next query instead
            # of stopping the entire company pipeline.

            continue

    # -----------------------------------------------------
    # Clean, rank, deduplicate and limit results.
    # -----------------------------------------------------

    filtered_results = clean_search_results(
        raw_results
    )

    print(
        f"  Tavily raw results: "
        f"{len(raw_results)}"
    )

    print(
        f"  Tavily selected results: "
        f"{len(filtered_results)}"
    )

    return filtered_results


# ---------------------------------------------------------
# Simple standalone test
# ---------------------------------------------------------

if __name__ == "__main__":

    test_results = search_company_externally(
        company_name="Postman",
        domain="postman.com",
    )

    print(
        "\n========== TAVILY SELECTED RESULTS =========="
    )

    for result in test_results:

        print(
            f"\nQuery: {result['query']}"
        )

        print(
            f"Title: {result['title']}"
        )

        print(
            f"URL: {result['url']}"
        )

        print(
            f"Priority: {result['priority']}"
        )

        print(
            f"Content: {result['content'][:300]}"
        )