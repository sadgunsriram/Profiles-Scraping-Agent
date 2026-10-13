import os
from playwright.sync_api import sync_playwright

def main():
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "browser_profile"))
    if not os.path.exists(profile_dir):
        print("="*60)
        print("ERROR: Persistent profile folder does not exist!")
        print("Please run: python skills/profile_scraper/save_linkedin_session.py first.")
        print("="*60)
        return

    print("="*60)
    print("VERIFYING AUTOMATIC LINKEDIN LOGIN")
    print("="*60)
    print("Launching Chromium headlessly with your saved profile...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile_dir,
            channel="chrome",
            headless=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            ignore_default_args=["--enable-automation"]
        )
        page = context.new_page()
        
        print("Navigating to LinkedIn Home page...")
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        
        current_url = page.url
        print(f"Current page URL: {current_url}")
        
        # Take verification screenshot
        screenshot_path = os.path.join(os.path.dirname(__file__), "login_verification.png")
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")
        
        is_blocked = "authwall" in current_url or "login" in current_url or "checkpoint" in current_url
        is_logged_in = "feed" in current_url and not is_blocked
        
        print("\n" + "="*40)
        print("LOGIN STATUS RESULT")
        print("="*40)
        if is_logged_in:
            print("STATUS: SUCCESS! You are AUTOMATICALLY LOGGED IN.")
            print("The agent will scrape successfully without any credentials.")
        elif is_blocked:
            print("STATUS: FAILED. You are redirected to a login/authwall screen.")
            print("Please rerun: python skills/profile_scraper/save_linkedin_session.py")
        else:
            print(f"STATUS: AMBIGUOUS. Navigated to {current_url}.")
            print("Check the screenshot 'login_verification.png' to see what loaded.")
        print("="*40)
        
        context.close()

if __name__ == "__main__":
    main()
