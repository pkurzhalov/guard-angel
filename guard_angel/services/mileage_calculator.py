import re
import time
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from ..config import settings

# **FIX**: Using the exact, trusted URL from your gm_total_miles.py
URL = "https://www.google.es/maps/dir/Fort+Myers,+Florida,+EE.+UU./Atlanta,+Georgia,+EE.+UU./@30.1718187,-86.0865988,7z/data=!3m1!4b1!4m14!4m13!1m5!1m1!1s0x88db420189a85429:0xc62908530aba258a!2m2!1d-81.8605575!2d26.6409247!1m5!1m1!1s0x88f5045d6993098d:0x66fede2f990b630b!2m2!1d-84.3885209!2d33.7501275!3e0?hl=en&entry=ttu&g_ep=EgoyMDI1MDcwNi4wIKXMDSoASAFQAw%3D%3D"

class MileageBrowser:
    def __init__(self):
        options = Options()
        options.headless = True
        options.profile = settings.firefox_profile_path
        service = Service(settings.geckodriver_path)
        self.browser = webdriver.Firefox(service=service, options=options)
        self.browser.get(URL)
        print("🌐 Mileage calculator browser started.")

    def get_miles(self, origin: str, destination: str) -> float | None:
        """Gets total miles using your trusted Selenium logic."""
        try:
            print(f"📦 Fetching miles: {origin} → {destination}")
            # Use the exact CSS selector from your old script
            WebDriverWait(self.browser, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input.tactile-searchbox-input")))
            inputs = self.browser.find_elements(By.CSS_SELECTOR, "input.tactile-searchbox-input")
            if len(inputs) < 2: return None

            inputs[0].send_keys(Keys.CONTROL, 'a', Keys.BACKSPACE); time.sleep(0.5)
            inputs[0].send_keys(origin); time.sleep(0.5); inputs[0].send_keys(Keys.ENTER)

            inputs[1].send_keys(Keys.CONTROL, 'a', Keys.BACKSPACE); time.sleep(0.5)
            inputs[1].send_keys(destination); time.sleep(0.5); inputs[1].send_keys(Keys.ENTER)

            section = WebDriverWait(self.browser, 15).until(
                EC.visibility_of_element_located((By.ID, "section-directions-trip-0"))
            )
            time.sleep(1.5) # Wait for text to fully update
            
            text = section.text
            # Use the exact, robust regex from your old script
            match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?)\s*miles', text, re.IGNORECASE)
            if match:
                miles = float(match.group(1).replace(",", ""))
                print(f"✅ Google Maps Total Miles: {miles}")
                return round(miles, 2)
            else:
                print("❌ Could not find miles in panel.")
                return 0
        except Exception as e:
            print(f"🚨 Error in Selenium mileage calculation: {e}")
            self.browser.save_screenshot('selenium_error.png')
        return 0

    def close(self):
        self.browser.quit()

mileage_browser = MileageBrowser()
