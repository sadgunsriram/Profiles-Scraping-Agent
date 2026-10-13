import os
import sys
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

def main():
    # Load environment variables
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    load_dotenv(dotenv_path=os.path.join(workspace_root, ".env"), override=True)
    username_val = os.getenv("LINKEDIN_USERNAME")
    password_val = os.getenv("LINKEDIN_PASSWORD")

    # Resolve profile path relative to this script directory
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "browser_profile"))
    os.makedirs(profile_dir, exist_ok=True)
    
    print("="*60)
    print("LINKEDIN INTERACTIVE PERSISTENT SESSION CAPTURE")
    print("="*60)
    print(f"Profile Directory: {profile_dir}")
    print("Launching Chromium browser with persistent profile...")
    
    # Ensure SignalHire extension is ready if enabled
    ext_enabled = os.getenv("ENABLE_SIGNALHIRE_EXTENSION", "true").lower() in ("true", "1", "yes")
    ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "extensions", "signalhire"))
    launch_args = []
    ignore_default = ["--enable-automation"]

    if ext_enabled:
        try:
            from skills.profile_scraper.setup_extension import setup_signalhire_extension
            setup_signalhire_extension()
        except Exception as ex:
            print(f"Note: setup_signalhire_extension: {ex}")
            
        if os.path.exists(os.path.join(ext_dir, "manifest.json")):
            print(f"Loading SignalHire extension from: {ext_dir}")
            launch_args.extend([
                f"--disable-extensions-except={ext_dir}",
                f"--load-extension={ext_dir}",
            ])
            ignore_default.append("--disable-extensions")

    launch_args.append("--disable-blink-features=AutomationControlled")

    with sync_playwright() as p:
        # Launch visible browser with persistent context using real Google Chrome
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 800},
            args=launch_args,
            ignore_default_args=ignore_default
        )
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver;")
        
        print("Navigating to LinkedIn...")
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        
        # Directly open the extension popup page so user can see and sign in to the extension
        if ext_enabled:
            ext_id = None
            for _ in range(10):
                if context.service_workers:
                    ext_id = context.service_workers[0].url.split("/")[2]
                    break
                page.wait_for_timeout(300)
                
            if ext_id:
                popup_url = f"chrome-extension://{ext_id}/popup.html"
                print(f"[Extension] Opening SignalHire extension popup tab: {popup_url}")
                ext_page = context.new_page()
                ext_page.goto(popup_url)
                ext_page.bring_to_front()
        
        # Check if already logged in (redirected to feed)
        curr_url = page.url
        if "feed" not in curr_url:
            # 1. Handle main homepage redirect (Click top-right "Sign in" button to open form)
            if "login" not in curr_url and "authwall" not in curr_url:
                signin_btn = page.query_selector("a.nav__button-secondary, a:has-text('Sign in'), .nav__button-secondary")
                if signin_btn:
                    print("\n[Notice] Landing homepage detected. Clicking the top-right 'Sign in' button...")
                    try:
                        signin_btn.click()
                        page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"Note: Failed to click Sign In button: {str(e)}")

            # 2. Handle signup, join, or authwall redirects (Click bottom "Already on LinkedIn? Sign in" link)
            curr_url = page.url
            if "signup" in curr_url or "join" in curr_url or "authwall" in curr_url:
                print("\n[Notice] Authwall/Join page detected. Clicking 'Sign in' link in browser...")
                for sel in [
                    "a:has-text('Sign in')",
                    "text='Sign in'",
                    ".authwall-join-form__link",
                    "[href*='login']"
                ]:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            print(f"Clicking Sign In link on authwall via: {sel}")
                            loc.last.click()
                            page.wait_for_timeout(3000)
                            break
                    except Exception:
                        continue

            # 3. Handle "Welcome back" Profile Chooser page
            page_content = page.content().lower()
            if "another account" in page_content or "welcome back" in page_content:
                print("\n[Notice] Welcome back screen detected. Clicking 'Sign in using another account' link...")
                try:
                    target = page.locator("text=another account").first
                    target.click()
                    page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"Note: Failed to click another account link: {str(e)}")

            if username_val and password_val and username_val != "your_email@example.com" and password_val != "your_password":
                print("Attempting to auto-fill credentials...")
                try:
                    # Wait dynamically up to 10 seconds for the input fields to render visible
                    page.locator("#username, #session_key").first.wait_for(state="visible", timeout=10000)
                    page.wait_for_timeout(500)
                    
                    filled = False
                    # Try standard /login selectors
                    if page.query_selector("#username"):
                        page.fill("#username", username_val)
                        page.wait_for_timeout(300)
                        page.fill("#password", password_val)
                        filled = True
                    # Try homepage login selectors
                    elif page.query_selector("#session_key"):
                        page.fill("#session_key", username_val)
                        page.wait_for_timeout(300)
                        page.fill("#session_password", password_val)
                        filled = True
                        
                    if filled:
                        page.wait_for_timeout(500)
                        # Find and click Sign In submit button
                        submit_btn = page.query_selector("button[type=submit], button[data-litms-control-urn='login-submit'], .btn__primary--large, .form__submit")
                        if submit_btn:
                            print("Clicking sign-in button...")
                            submit_btn.click()
                            page.wait_for_timeout(3000)
                        else:
                            print("Note: Could not locate the submit button. Please click sign-in manually.")
                    else:
                        print("Note: Could not find username/password inputs. Please type them manually in the browser window.")
                except Exception as e:
                    print(f"Note: Auto-login typing encountered an issue: {str(e)}")
            else:
                print("No credentials configured in your .env file yet. Please type your login details manually.")
        else:
            print("Already logged in! Redirected directly to LinkedIn home feed.")
        
        print("\n" + "*"*60)
        print("ACTION REQUIRED:")
        print("1. If prompted, solve any CAPTCHAs or 2FA checks for LinkedIn.")
        print("2. Once on LinkedIn, click the SignalHire extension sidebar/icon on the screen and SIGN IN to your SignalHire account.")
        print("3. Once both LinkedIn and SignalHire are logged in, return here.")
        print("*"*60 + "\n")
        
        input("Press ENTER here once you have successfully logged into LinkedIn and SignalHire...")
        
        print("\nSaving session and closing browser...")
        context.close()
        print("Browser profile session saved successfully!")
        print("="*60)

if __name__ == "__main__":
    main()
