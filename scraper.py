from typing import Any

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

RELEVANT_KEYWORDS = [
    "about",
    "company",
    "team",
    "leadership",
    "contact",
    "pricing",
]

MAX_PAGE_CHARS = 4000
PAGE_TIMEOUT_MS = 30000
NETWORK_IDLE_TIMEOUT_MS = 10000
MAX_RETRIES = 2


# ---------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------

def clean_text(html: str) -> str:
    """
    Remove unnecessary HTML elements and return clean
    human-readable webpage text.

    Footer content is intentionally preserved because
    contact information and public email addresses are
    commonly placed there.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    for element in soup([
        "script",
        "style",
        "svg",
        "noscript",
    ]):
        element.decompose()

    return soup.get_text(
        separator=" ",
        strip=True,
    )


# ---------------------------------------------------------
# LinkedIn context extraction
# ---------------------------------------------------------

def extract_linkedin_context(
    anchor: Any,
    base_url: str,
) -> dict[str, str]:
    """
    Extract a LinkedIn URL together with nearby visible
    text from the same HTML section.

    The nearby text may contain a person's name,
    job title, or other useful context.

    The function does not invent or infer a person.
    It only preserves text that already exists in
    the webpage HTML.
    """

    href = anchor.get(
        "href",
        "",
    ).strip()

    if not href:
        return {}

    full_url = urljoin(
        base_url,
        href,
    )

    # -----------------------------------------------------
    # Get visible text directly from the LinkedIn anchor.
    # -----------------------------------------------------

    anchor_text = anchor.get_text(
        " ",
        strip=True,
    )

    context_parts: list[str] = []

    if anchor_text:
        context_parts.append(
            anchor_text
        )

    # -----------------------------------------------------
    # Look at the parent element.
    # -----------------------------------------------------

    parent = anchor.parent

    if parent:

        parent_text = parent.get_text(
            " ",
            strip=True,
        )

        if parent_text:
            context_parts.append(
                parent_text
            )

    # -----------------------------------------------------
    # Look at a small surrounding HTML section.
    #
    # This is useful for cards such as:
    #
    #   Abhijit Kane
    #   Chief ...
    #   LinkedIn
    #
    # where the name/title is not inside the <a> itself.
    # -----------------------------------------------------

    current = anchor

    for _ in range(2):

        current = current.parent

        if current is None:
            break

        surrounding_text = current.get_text(
            " ",
            strip=True,
        )

        if surrounding_text:
            context_parts.append(
                surrounding_text
            )

    # -----------------------------------------------------
    # Remove duplicate context strings.
    # -----------------------------------------------------

    unique_context: list[str] = []

    for value in context_parts:

        if value not in unique_context:
            unique_context.append(
                value
            )

    # Keep context reasonably small.
    context = " | ".join(
        unique_context
    )

    if len(context) > 500:
        context = context[:500]

    return {
        "url": full_url,
        "context": context,
    }


# ---------------------------------------------------------
# Link and contact extraction
# ---------------------------------------------------------

def extract_page_links(
    html: str,
    base_url: str,
) -> dict[str, list]:
    """
    Extract useful links and public contact information
    directly from the rendered HTML.

    This preserves information that may be lost when
    converting HTML into plain text.

    LinkedIn profile context is also preserved so the
    downstream LLM can associate names/roles with
    explicitly discovered LinkedIn URLs.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    emails: set[str] = set()

    linkedin_urls: set[str] = set()

    linkedin_profiles: list[dict[str, str]] = []

    for anchor in soup.find_all(
        "a",
        href=True,
    ):

        href = anchor.get(
            "href",
            "",
        ).strip()

        if not href:
            continue

        # -------------------------------------------------
        # Extract mailto email addresses
        # -------------------------------------------------

        if href.lower().startswith(
            "mailto:"
        ):

            email = (
                href[7:]
                .split("?", 1)[0]
                .strip()
            )

            if email:
                emails.add(
                    email
                )

        # -------------------------------------------------
        # Extract LinkedIn URLs + context
        # -------------------------------------------------

        elif "linkedin.com/" in href.lower():

            profile = extract_linkedin_context(
                anchor,
                base_url,
            )

            if not profile:
                continue

            linkedin_url = profile.get(
                "url",
                "",
            )

            if not linkedin_url:
                continue

            linkedin_urls.add(
                linkedin_url
            )

            # -------------------------------------------------
            # Avoid duplicate LinkedIn entries.
            # -------------------------------------------------

            already_exists = any(
                item["url"] == linkedin_url
                for item in linkedin_profiles
            )

            if not already_exists:

                linkedin_profiles.append(
                    profile
                )

    return {
        "emails": sorted(
            emails
        ),
        "linkedin_urls": sorted(
            linkedin_urls
        ),
        "linkedin_profiles": linkedin_profiles,
    }


# ---------------------------------------------------------
# Relevant page discovery
# ---------------------------------------------------------

def discover_pages(
    page: Any,
    homepage_url: str,
) -> list[str]:
    """
    Find relevant internal pages from the company homepage.
    """

    links = page.locator(
        "a"
    ).all()

    discovered: list[str] = []

    homepage_domain = urlparse(
        homepage_url
    ).netloc.lower()

    for link in links:

        try:

            href = link.get_attribute(
                "href"
            )

            if not href:
                continue

            full_url = urljoin(
                homepage_url,
                href,
            )

            parsed_url = urlparse(
                full_url
            )

            # -------------------------------------------------
            # Only keep HTTP/HTTPS URLs.
            # -------------------------------------------------

            if parsed_url.scheme not in {
                "http",
                "https",
            }:
                continue

            # -------------------------------------------------
            # Only keep links belonging to the
            # same website.
            # -------------------------------------------------

            if (
                parsed_url.netloc.lower()
                != homepage_domain
            ):
                continue

            # -------------------------------------------------
            # Ignore fragments.
            # -------------------------------------------------

            if parsed_url.fragment:
                continue

            # -------------------------------------------------
            # Ignore duplicate trailing-slash variants.
            # -------------------------------------------------

            normalized_url = full_url.rstrip(
                "/"
            )

            url_lower = normalized_url.lower()

            # -------------------------------------------------
            # Discover relevant pages.
            # -------------------------------------------------

            if any(
                keyword in url_lower
                for keyword in RELEVANT_KEYWORDS
            ):

                if normalized_url not in discovered:

                    discovered.append(
                        normalized_url
                    )

        except Exception:
            # Ignore malformed or inaccessible links.
            continue

    return discovered


# ---------------------------------------------------------
# Single page scraping
# ---------------------------------------------------------

def scrape_page(
    page: Any,
    url: str,
) -> dict[str, Any]:
    """
    Scrape one webpage with retry handling.

    Returns cleaned text together with public emails,
    LinkedIn URLs, and LinkedIn profile context.
    """

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            print(
                f"  Scraping: {url} "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            # -------------------------------------------------
            # HTTP error handling
            # -------------------------------------------------

            if (
                response
                and response.status >= 400
            ):

                return {
                    "url": url,
                    "title": "",
                    "text": "",
                    "emails": [],
                    "linkedin_urls": [],
                    "linkedin_profiles": [],
                    "error": (
                        f"HTTP {response.status}"
                    ),
                }

            # -------------------------------------------------
            # Allow client-side JavaScript to finish rendering.
            # -------------------------------------------------

            try:

                page.wait_for_load_state(
                    "networkidle",
                    timeout=NETWORK_IDLE_TIMEOUT_MS,
                )

            except Exception:

                # Some modern websites keep network
                # connections open continuously.
                # The DOM content is still usable,
                # so continue instead of failing.
                pass

            # -------------------------------------------------
            # Read rendered HTML
            # -------------------------------------------------

            html = page.content()

            text = clean_text(
                html
            )

            extracted_links = extract_page_links(
                html,
                url,
            )

            # -------------------------------------------------
            # Empty content handling
            # -------------------------------------------------

            if not text.strip():

                return {
                    "url": url,
                    "title": page.title(),
                    "text": "",
                    "emails": extracted_links[
                        "emails"
                    ],
                    "linkedin_urls": extracted_links[
                        "linkedin_urls"
                    ],
                    "linkedin_profiles": extracted_links[
                        "linkedin_profiles"
                    ],
                    "error": (
                        "No usable text content found."
                    ),
                }

            # -------------------------------------------------
            # Token optimization
            # -------------------------------------------------

            if len(text) > MAX_PAGE_CHARS:

                text = (
                    text[:MAX_PAGE_CHARS]
                    + "\n[Content truncated]"
                )

            # -------------------------------------------------
            # Successful result
            # -------------------------------------------------

            return {
                "url": url,
                "title": page.title(),
                "text": text,
                "emails": extracted_links[
                    "emails"
                ],
                "linkedin_urls": extracted_links[
                    "linkedin_urls"
                ],
                "linkedin_profiles": extracted_links[
                    "linkedin_profiles"
                ],
            }

        except Exception as error:

            print(
                f"  Attempt {attempt} failed: {url}"
            )

            print(
                f"  Reason: {error}"
            )

            if attempt < MAX_RETRIES:

                print(
                    "  Retrying..."
                )

    # ---------------------------------------------------------
    # All retry attempts failed
    # ---------------------------------------------------------

    return {
        "url": url,
        "title": "",
        "text": "",
        "emails": [],
        "linkedin_urls": [],
        "linkedin_profiles": [],
        "error": (
            f"Failed after {MAX_RETRIES} attempts."
        ),
    }


# ---------------------------------------------------------
# Company scraping
# ---------------------------------------------------------

def scrape_company(
    domain: str,
) -> list[dict[str, Any]]:
    """
    Scrape the homepage and relevant internal company pages.

    A failed page is recorded as an error and does not stop
    the remaining pages from being processed.
    """

    if not domain.startswith(
        (
            "http://",
            "https://",
        )
    ):

        domain = "https://" + domain

    results: list[dict[str, Any]] = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        try:

            # -------------------------------------------------
            # Step 1: Homepage
            # -------------------------------------------------

            print(
                f"\n========== {domain} =========="
            )

            homepage = scrape_page(
                page,
                domain,
            )

            results.append(
                homepage
            )

            # -------------------------------------------------
            # Step 2: Page discovery
            # -------------------------------------------------

            if homepage.get(
                "error"
            ):

                print(
                    "\nHomepage could not be processed: "
                    f"{homepage['error']}"
                )

                print(
                    "Skipping page discovery."
                )

                return results

            print(
                "\nDiscovering relevant pages..."
            )

            discovered_pages = discover_pages(
                page,
                domain,
            )

            print(
                f"Found {len(discovered_pages)} "
                "relevant pages:"
            )

            for url in discovered_pages:

                print(
                    f"  - {url}"
                )

            # -------------------------------------------------
            # Step 3: Scrape discovered pages
            # -------------------------------------------------

            for url in discovered_pages:

                result = scrape_page(
                    page,
                    url,
                )

                results.append(
                    result
                )

                if result.get(
                    "error"
                ):

                    print(
                        "  Continuing after page failure: "
                        f"{result['error']}"
                    )

        finally:

            browser.close()

    return results


# ---------------------------------------------------------
# Independent scraper test
# ---------------------------------------------------------

if __name__ == "__main__":

    company_data = scrape_company(
        "https://postman.com"
    )

    print(
        "\n\n========== SCRAPING COMPLETE =========="
    )

    for item in company_data:

        print(
            "\nURL:",
            item["url"],
        )

        print(
            "Title:",
            item["title"],
        )

        print(
            "Text length:",
            len(item["text"]),
        )

        print(
            "Emails:",
            item.get(
                "emails",
                [],
            ),
        )

        print(
            "LinkedIn URLs:",
            item.get(
                "linkedin_urls",
                [],
            ),
        )

        print(
            "LinkedIn Profiles:",
            item.get(
                "linkedin_profiles",
                [],
            ),
        )

        if "error" in item:

            print(
                "ERROR:",
                item["error"],
            )