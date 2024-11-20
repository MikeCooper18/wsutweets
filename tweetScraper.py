from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from pythonosc import udp_client
import time
import os
import requests
import random

from dotenv import load_dotenv


def send_keys_delayed(element, keys, delay=0.1):
    for key in keys:
        element.send_keys(key)

        # Offset delay randomly by a small amount +- 50% of the delay
        offset = random.uniform(-0.5 * delay, 0.5 * delay)
        time.sleep(delay + offset)


def random_sleep(min_time=0.5, max_time=1.5):
    time.sleep(random.uniform(min_time, max_time))


def random_time_offset(base_time, offset=0.5):
    return random.uniform(base_time - offset, base_time + offset)


class TweetScraper:
    def __init__(self, resolume_ip, osc_port=7070, http_port=8080, banned_words_file="banned_words.txt", twitter_tag="#warwickpop", layer_number=1, NUM_TWEETS=10, headless=True, refresh_period=300):
        if twitter_tag.startswith("#"):
            self.twitter_tag = twitter_tag[1:]
        else:
            self.twitter_tag = twitter_tag

        self.layer_number = layer_number
        self.NUM_TWEETS = NUM_TWEETS
        self.resolume_address = resolume_ip # str
        self.osc_port = osc_port # int
        self.http_port = http_port # int


        self.refresh_period = refresh_period # refresh period in seconds, default 5 minutes

        # Load login credentials from env variables
        load_dotenv()
        self.username = os.environ["TWITTER_USERNAME"]
        self.password = os.environ["TWITTER_PASSWORD"]
        self.email = os.environ["EMAIL"]
        print(f"Username: {self.username}")
        print(f"Password: {self.password}")
        print(f"Email: {self.email}")

        # Setup web driver with higher resolution settings
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new") # Run in headless mode
        options.add_argument("--window-size=2560,1440")  # Full HD
        options.add_argument("--force-device-scale-factor=2")  # 2x pixel density
        options.add_argument("--high-dpi-support=2")
        
        
        self.driver = webdriver.Chrome(options=options)
        # Set window size explicitly as well
        self.driver.set_window_size(2560, 1440)


        self.load_banned_words(banned_words_file)

        # Setup the Resolume OSC client
        self.resolume_client = udp_client.SimpleUDPClient("127.0.0.1", self.osc_port)

        # Create a screenshots directory if it does not exist
        self.screenshot_dir = "tweet_screenshots"
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)

        # Clear the screenshots directory
        self.clear_directory(self.screenshot_dir)

    
    def load_banned_words(self, banned_words_file):
        self.banned_words = []
        with open(banned_words_file, "r") as f:
            for line in f:
                self.banned_words.append(line.strip().lower())
            
        self.banned_words = set(self.banned_words)


    def is_tweet_safe(self, tweet_text):
        tweet_text = tweet_text.lower()
        tweet_words = set(tweet_text.split())

        intersection = tweet_words.intersection(self.banned_words)
        return len(intersection) == 0


    def capture_tweet(self, tweet_element, index):
        try:
            # Scroll the tweet into view using JavaScript
            self.driver.execute_script("""
                let tweet = arguments[0];
                let y = tweet.getBoundingClientRect().top + window.pageYOffset;
                window.scrollTo({
                    top: y - 150,  // Offset by 150px to avoid header
                    behavior: 'smooth'
                });
            """, tweet_element)
            
            # Wait for scroll animation
            time.sleep(2)
            
            # Take screenshot
            screenshot_path = f"{self.screenshot_dir}/tweet_{index}.png"
            tweet_element.screenshot(screenshot_path)
            
            return screenshot_path
    
        except Exception as e:
            print(f"Error capturing screenshot for tweet {index}: {e}")
            raise e
    

    def send_to_resolume(self, image_path, layer_number, clip_number):
        status_lookup = {
            204: "Ok",
            400: "Clip URL is invalid",
            404: "The requested layer or clip does not exist",
            412: "A precondition failed, the clip cannot be loaded"
        }

        # Get the URI
        full_image_path = os.path.abspath(image_path)
        full_image_path = "file:///" + full_image_path
        full_image_path = full_image_path.replace("\\", "/")
        full_image_path = full_image_path.replace(" ", "%20")

        webserver_address = f"http://{self.resolume_address}:{self.http_port}/api/v1/"
        endpoint = f"composition/layers/{layer_number}/clips/{clip_number}/open"
        try:
            # Send the POST message to the endpoint, request body is the URI
            print(f"Sending message to Resolume on {webserver_address + endpoint} with data: {full_image_path}")
            response = requests.post(webserver_address + endpoint, data=full_image_path)
            print(f"Sent message to Resolume: {response.status_code} {status_lookup.get(response.status_code, 'Unknown error')}")

            # Set duration of the clip to 10 seconds.
            self.resolume_client.send_message(f"/composition/layers/{layer_number}/clips/{clip_number}/transport/position/behaviour/duration", 10)
            print("Set clip duration to 10 seconds")
        except Exception as e:
            print(f"Error sending OSC message to Resolume: {e}")
            raise e

    def login(self):
        try:
            # Navigate to the twitter login page
            self.driver.get("https://twitter.com/login")
            wait = WebDriverWait(self.driver, 10) # timeout of 10 seconds

            # Enter username
            username_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[autocomplete='username']")))
            random_sleep()
            # username_input.send_keys(self.username)
            send_keys_delayed(username_input, self.username)
            username_input.send_keys(Keys.RETURN)

            # Wait 2 seconds
            time.sleep(2)

            # Check if the additional verification prompt appears
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, "//span[text()='Phone or email']")))
                verification_prompt = self.driver.find_element(By.CSS_SELECTOR, "input[data-testid='ocfEnterTextTextInput']")
                random_sleep()
                print("Verification prompt detected. Entering email...")

                # Enter email or phone number for verification
                # verification_prompt.send_keys(self.email)
                send_keys_delayed(verification_prompt, self.email)
                verification_prompt.send_keys(Keys.RETURN)
                print("Verified")

            except:
                # If no verification prompt, proceed normally
                print("No additional verification needed.")

            # Enter password
            password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='password']")))
            random_sleep()
            # password_input.send_keys(self.password)
            send_keys_delayed(password_input, self.password)
            password_input.send_keys(Keys.RETURN)

            # Wait for the login to complete and home page to load
            wait.until(EC.url_contains("/home"))
            random_sleep()
            print("Logged in successfully.")
            return True

        except Exception as e:
            print("Failed to login.")
            print(e)
            return


    def clear_directory(self, directory, filetypes=[".png"]):
        for file in os.listdir(directory):
            if any(file.endswith(filetype) for filetype in filetypes):
                os.remove(os.path.join(directory, file))
        print(f"Cleared directory {directory}.")
    


    def scrape_and_process(self):
        print("Starting continuous tweet scraping...")
        print(f"Refresh period set to {self.refresh_period} seconds.")
        try:
            # First login
            if not self.login():
                print("Failed to login. Exiting...")
                return
            
            # Navigate to the twitter search page with the given tag
            search_url = f"https://twitter.com/search?q=%23{self.twitter_tag}&src=typed_query&f=live"
            print(f"Navigating to: {search_url}")
            self.driver.get(search_url)
            print("Loaded search page.")

            # Continuous scraping loop
            while True:
                print("Press Ctrl+C to stop the script.")
                try:    
                    # Clear the directory of images
                    self.clear_directory(self.screenshot_dir, filetypes=[".png"])

                    # Wait for the tweets to load
                    print("Waiting for tweets to load...")
                    wait = WebDriverWait(self.driver, 15)  # Increased timeout to 15 seconds
                    tweets = wait.until(
                        EC.presence_of_all_elements_located(
                            (By.CSS_SELECTOR, 'article[data-testid="tweet"]')
                        )
                    )
                    print(f"Found {len(tweets)} tweets.")

                    # Get a list of all the tweets, they all have 'data-testid="tweet"' attribute.
                    clip_number = 1
                    for idx, tweet in enumerate(tweets[:self.NUM_TWEETS]):
                        i = idx + 1
                        # Get tweet text
                        print(f"\nProcessing tweet {i}")
                        tweet_text = tweet.find_element(By.CSS_SELECTOR, "div[lang]").text
                        print(f"Tweet {i} text: {tweet_text[:50]}...")

                        # Check if tweet is safe
                        if not self.is_tweet_safe(tweet_text):
                            print(f"[!] Tweet {i} contains banned words. Skipping...")
                            continue

                        # Capture tweet
                        print(f"Tweet {i} is safe. Capturing...")
                        screenshot_path = self.capture_tweet(tweet, i)
                        print(f"Captured tweet {i} to {screenshot_path}")

                        # Send to Resolume
                        print(f"Sending tweet {i} to Resolume...")
                        self.send_to_resolume(screenshot_path, self.layer_number, clip_number)
                        clip_number += 1
                        print(f"Sent tweet {i} to Resolume.")

                        random_sleep()

                    # Wait for the specified refresh period before next scrape
                    print(f"Waiting {self.refresh_period} seconds before next refresh...")
                    sleep_period = random_time_offset(self.refresh_period, offset=0.1 * self.refresh_period)
                    time.sleep(sleep_period)

                    # Refresh the page
                    print("Refreshing page...")
                    self.driver.refresh()
                    time.sleep(10)  # Give some time for the page to reload

                except Exception as inner_e:
                    print(f"Error in scraping loop: {inner_e}")
                    print(f"\nWaiting and retrying...")
                    # Wait a bit before trying again
                    time.sleep(10)
                    # Refresh the page to reset
                    self.driver.refresh()
                    time.sleep(10)

        except Exception as e:
            print("Critical error in scrape_and_process.")
            print(e)
        finally:
            self.driver.quit()


if __name__ == "__main__":
    # ip="172.25.47.92"
    ip="192.168.56.1" # IP will need to be changed to the IP Resolume sets for its HTTP server.
    osc_port=7000 # Shouldn't need to be changed
    http_port=8080 # Shouldn't need to be changed
    banned_words_file="banned_words.txt" # File containing banned words
    twitter_tag="#warwickpop" # Tag to search for
    layer_number=1 # Layer number in Resolume
    NUM_TWEETS=10 # Number of tweets to scrape
    headless = False # Run in headless mode, set to False to see the browser window

    refresh_period = 60 # Refresh period in seconds

    tweet_scraper = TweetScraper(resolume_ip=ip, osc_port=osc_port, http_port=http_port, banned_words_file=banned_words_file, twitter_tag=twitter_tag, layer_number=layer_number, NUM_TWEETS=NUM_TWEETS, headless=headless, refresh_period=refresh_period)
    tweet_scraper.scrape_and_process()



# Potential Improvements:
# [] Add logging
# [] Add more error handling