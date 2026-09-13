from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


# Pages that are useful for company research
RELEVANT_KEYWORDS = [
    "about",
    "company",
    "team",
    "leadership",
    "contact",
    "pricing"
]


def clean_text(html):
    """Remove unnecessary HTML and return clean webpage text."""

    soup = BeautifulSoup(html, "html.parser")

    for element in soup([
        "script",
        "style",
        "svg",
        "noscript",
        "nav",
        "footer",
        "header"
    ]):
        element.decompose()

    return soup.get_text(separator=" ", strip=True)


def discover_pages(page, homepage_url):
    """Find relevant internal pages from the homepage."""

    links = page.locator("a").all()

    discovered = []

    homepage_domain = urlparse(homepage_url).netloc

    for link in links:
        try:
            href = link.get_attribute("href")

            if not href:
                continue

            full_url = urljoin(homepage_url, href)

            parsed_url = urlparse(full_url)

            # Only keep links belonging to the same website
            if parsed_url.netloc != homepage_domain:
                continue

            # Ignore page fragments
            if parsed_url.fragment:
                continue

            # Only HTTP/HTTPS links
            if parsed_url.scheme not in ["http", "https"]:
                continue

            url_lower = full_url.lower()

            # Check whether URL contains a relevant keyword
            for keyword in RELEVANT_KEYWORDS:
                if keyword in url_lower:
                    if full_url not in discovered:
                        discovered.append(full_url)
                    break

        except Exception:
            continue

    return discovered


def scrape_page(page, url):
    """Scrape and clean one webpage."""

    try:
        print(f"  Scraping: {url}")

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        html = page.content()

        text = clean_text(html)

        # Limit each page to avoid sending excessive content
        # to the LLM.
        MAX_PAGE_CHARS = 4000

        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + "\n[Content truncated]"

        return {
            "url": url,
            "title": page.title(),
            "text": text
        }

    except Exception as e:
        print(f"  Failed: {url}")
        print(f"  Reason: {e}")

        return {
            "url": url,
            "title": "",
            "text": "",
            "error": str(e)
        }


def scrape_company(domain):
    """Scrape homepage and discover relevant company pages."""

    if not domain.startswith("http"):
        domain = "https://" + domain

    results = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        page = browser.new_page()

        # Step 1: Scrape homepage
        print(f"\n========== {domain} ==========")

        homepage = scrape_page(page, domain)

        results.append(homepage)

        # Step 2: Discover relevant pages
        print("\nDiscovering relevant pages...")

        discovered_pages = discover_pages(page, domain)

        print(f"Found {len(discovered_pages)} relevant pages:")

        for url in discovered_pages:
            print(f"  - {url}")

        # Step 3: Scrape discovered pages
        for url in discovered_pages:

            result = scrape_page(page, url)

            results.append(result)

        browser.close()

    return results


if __name__ == "__main__":

    company_data = scrape_company("https://postman.com")

    print("\n\n========== SCRAPING COMPLETE ==========")

    for item in company_data:

        print("\nURL:", item["url"])
        print("Title:", item["title"])
        print("Text length:", len(item["text"]))

        if "error" in item:
            print("ERROR:", item["error"])