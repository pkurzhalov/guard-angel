import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from ..config import settings

# Using your original, reliable 3-field URL
URL = "https://www.google.com/maps/dir/Fort+Myers,+FL/Atlanta,+GA/Baltimore,+MD"

class MileageBrowser:
    def __init__(self):
        self.browser = self._init_browser()

    def _init_browser(self):
        options = Options()
        options.headless = True
        options.profile = settings.firefox_profile_path
        service = Service(settings.geckodriver_path)
        browser_instance = webdriver.Firefox(service=service, options=options)
        browser_instance.get(URL) # Go to the pre-filled URL
        return browser_instance

    def get_miles(self, *waypoints: str) -> int | None:
        try:
            input_fields = self.browser.find_elements(By.CSS_SELECTOR, "div[id^='directions-searchbox-'] input")
            
            # Input new waypoints
            for i, point in enumerate(waypoints):
                if i < len(input_fields):
                    input_field = input_fields[i]
                    input_field.clear()
                    input_field.send_keys(point)
                    if i == len(waypoints) - 1:
                        input_field.send_keys(Keys.ENTER)

            trip_element = WebDriverWait(self.browser, 20).until(
                EC.visibility_of_element_located((By.ID, "section-directions-trip-0"))
            )
            time.sleep(2)
            
            distance_div_xpath = ".//div[contains(text(), 'mi') and not(contains(text(), 'min'))]"
            distance_div = trip_element.find_element(By.XPATH, distance_div_xpath)
            miles_text = distance_div.text
            
            miles_match = re.search(r'([\d,]+)\s*mi', miles_text)
            if miles_match:
                total_miles = int(miles_match.group(1).replace(",", ""))
                print(f"Google Maps calculated miles: {total_miles}")
                return total_miles

        except Exception as e:
            print(f"Error in Selenium mileage calculation: {e}")
            self.browser.save_screenshot('selenium_error.png')
        return None

    def close(self):
        self.browser.quit()

mileage_browser = MileageBrowser()
