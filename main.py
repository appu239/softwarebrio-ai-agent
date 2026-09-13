import json

from scraper import scrape_company
from llm_extractor import extract_company_intelligence


TARGET_DOMAINS = [
    "https://postman.com",
    "https://supabase.com",
    "https://vapi.ai"
]


def run_agent(domain):
    """
    Run the complete lead enrichment process for one company.
    """

    print("\n" + "=" * 60)
    print(f"STARTING AGENT: {domain}")
    print("=" * 60)

    try:

        # Step 1: Scrape website
        scraped_pages = scrape_company(domain)

        # Step 2: Combine scraped content
        combined_text = ""

        MAX_TOTAL_CHARS = 16000

        for page in scraped_pages:

            if not page.get("text"):
                continue

            page_content = (
                f"\n\nPAGE URL: {page['url']}\n"
                f"PAGE TITLE: {page['title']}\n"
                f"{page['text']}"
            )

            remaining = MAX_TOTAL_CHARS - len(combined_text)

            if remaining <= 0:
                break

            combined_text += page_content[:remaining]

        # Step 3: Check content
        if not combined_text.strip():

            return {
                "domain": domain,
                "error": "No usable website content found."
            }

        # Step 4: AI extraction
        print("\nSending website content to AI...")

        intelligence = extract_company_intelligence(
            combined_text
        )

        result = intelligence.model_dump()

        result["domain"] = domain

        print("AI extraction successful.")

        return result

    except Exception as e:

        print(f"Agent failed for {domain}")
        print(f"Reason: {e}")

        return {
            "domain": domain,
            "error": str(e)
        }


def main():

    all_results = []

    for domain in TARGET_DOMAINS:

        result = run_agent(domain)

        all_results.append(result)

    # Save final results
    with open("output.json", "w", encoding="utf-8") as file:

        json.dump(
            all_results,
            file,
            indent=2,
            ensure_ascii=False
        )

    print("\n" + "=" * 60)
    print("ALL COMPANIES PROCESSED")
    print("=" * 60)

    print("\nResults saved to: output.json")


if __name__ == "__main__":
    main()