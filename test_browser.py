from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(
            "https://postman.com",
            wait_until="domcontentloaded",
            timeout=30000
        )

        print("Title:", page.title())
        print("URL:", page.url)

        print("\n--- TEXT PREVIEW ---")
        print(page.locator("body").inner_text()[:2000])

        browser.close()


if __name__ == "__main__":
    main()