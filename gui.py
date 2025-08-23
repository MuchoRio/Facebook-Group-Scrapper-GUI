import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import signal
import sys
import time
import csv
import re
import threading
import io
from pathlib import Path

# --- Import Selenium Modules ---
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException # Ensure WebDriverException is imported
)
from selenium.webdriver.chrome.options import Options as ChromeOptions # Ensure ChromeOptions is imported
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# --- Global Variables for WebDriver and Interruption ---
driver = None
interrupted = False
collected_group_data = {}

# --- Blacklist Definitions ---
blacklist_keywords = [
    "Terakhir aktif beberapa detik yang lalu",
    "Temukan",
    "Discover",
    "Last active a few seconds ago",
    "Last active about a minute ago",
    "View group",
    "Your feed",
    "Your groups",
    "See all",
    "Create new group",
    "Buat Grup Baru",
    "Lihat Grup",
    "Lihat semua"
]

blacklist_patterns = [
    r"Terakhir aktif\s+\d+\s+jam(?: yang lalu)?",
    r"Terakhir aktif\s+\d+\s+menit(?: yang lalu| lalu)?",
    r"Terakhir aktif\s+\d+\s+detik(?: yang lalu| lalu)?",
    r"Terakhir aktif\s+\d+\s+hari(?: yang lalu)?",
    r"Active\s+\d+\s+hours?\s+ago",
    r"Active\s+\d+\s+minutes?\s+ago",
    r"Active\s+\d+\s+seconds?\s+ago",
    r"Last\s+active\s+\d+\s+(minutes?|hours?|seconds?)\s+ago"
]

# --- Redirect stdout/stderr to a Tkinter Text widget ---
class TextRedirector(object):
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag
        self.stdout = sys.stdout # Keep original stdout

    def write(self, str_val):
        self.widget.insert(tk.END, str_val, (self.tag,))
        self.widget.see(tk.END) # Scroll to the end
        self.stdout.write(str_val) # Also write to original stdout (console)

    def flush(self):
        self.stdout.flush() # Flush original stdout

# --- Helper Functions (adapted for GUI logging) ---
def log_verbose(message, verbose_flag, log_widget):
    if verbose_flag:
        log_widget.insert(tk.END, f"[VERBOSE] {message}\n", ("verbose",))
        log_widget.see(tk.END)

def display_config_summary(args, log_widget):
    log_widget.insert(tk.END, "\n================ Configuration Summary ================\n", ("info",))
    log_widget.insert(tk.END, f"Cookies File      : {args.cookies}\n", ("info",))
    log_widget.insert(tk.END, f"Output File       : {args.output} (Format: CSV)\n", ("info",))
    log_widget.insert(tk.END, f"Headless Mode     : {'ON' if args.headless else 'OFF'}\n", ("info",))
    log_widget.insert(tk.END, f"Proxy             : {'ON' if args.proxy else 'OFF'} (Note: Proxy server not implemented in this script)\n", ("info",))
    log_widget.insert(tk.END, f"Verbose Logging   : {'ON' if args.verbose else 'OFF'}\n", ("info",))
    log_widget.insert(tk.END, f"Scroll Delay      : {args.scroll_delay}s\n", ("info",))
    log_widget.insert(tk.END, f"Max Scroll        : {args.max_scroll}\n", ("info",))
    log_widget.insert(tk.END, f"Encoding          : {args.encoding}\n", ("info",))
    log_widget.insert(tk.END, "=======================================================\n\n", ("info",))
    log_widget.see(tk.END)

def safe_quit(log_widget, is_gui_initiated=False):
    global interrupted, driver, collected_group_data
    if not is_gui_initiated: # If called by signal handler (CTRL+C)
        if driver:
            log_widget.insert(tk.END, "\nCTRL+C detected. Attempting graceful exit...\n", ("warning",))
            interrupted = True
    else: # If called by GUI (Stop button)
        log_widget.insert(tk.END, "Stop button pressed. Attempting graceful exit...\n", ("warning",))
        interrupted = True

    if driver:
        log_verbose("Attempting to close WebDriver...", True, log_widget)
        try:
            driver.quit()
            log_verbose("WebDriver closed successfully.", True, log_widget)
        except WebDriverException as e:
            log_widget.insert(tk.END, f"[WARNING] Error closing WebDriver: {e}\n", ("warning",))
        finally:
            driver = None

    if collected_group_data: # Save collected data if available, even on interrupt
        save_groups_to_file(app_instance.output_path_var.get(), collected_group_data,
                            app_instance.encoding_var.get(), app_instance.verbose_var.get(),
                            is_final=not interrupted, log_widget=log_widget)
        # Perform post-processing if not interrupted and data was saved
        # Only perform post-processing if the process was NOT interrupted at the final saving stage
        if not interrupted:
            post_process_csv(app_instance.output_path_var.get(), log_widget, app_instance.encoding_var.get(), app_instance.verbose_var.get())


    if not is_gui_initiated: # Only exit sys if not GUI initiated
        sys.exit(0)

def load_cookies(driver, cookies_path, verbose, log_widget):
    log_verbose(f"Attempting to load cookies from: {cookies_path}", verbose, log_widget)
    try:
        with open(cookies_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        log_verbose(f"Loaded {len(cookies)} cookies from file.", verbose, log_widget)

        driver.get("https://www.facebook.com")
        log_verbose("Navigated to facebook.com to set cookies.", verbose, log_widget)
        time.sleep(2)

        for cookie in cookies:
            if 'sameSite' not in cookie:
                 cookie['sameSite'] = 'Lax'
            if 'expiry' in cookie and (cookie['expiry'] is None or cookie['expiry'] == -1):
                 del cookie['expiry']
            elif 'expires' in cookie and isinstance(cookie['expires'], float):
                 cookie['expires'] = int(cookie['expires'])
            if 'expires' in cookie and 'expiry' not in cookie:
                cookie['expiry'] = cookie.pop('expires')

            try:
                driver.add_cookie(cookie)
            except Exception as e:
                cookie_name = cookie.get('name', 'N/A')
                log_widget.insert(tk.END, f"[WARNING] Could not add cookie: {cookie_name}. Error: {e}\n", ("warning",))
                log_verbose(f"Problematic cookie data for '{cookie_name}': {cookie}", verbose, log_widget)

        log_verbose("Finished adding cookies.", verbose, log_widget)
        driver.refresh()
        log_verbose("Page refreshed after adding cookies.", verbose, log_widget)
        time.sleep(3)
        return True

    except FileNotFoundError:
        log_widget.insert(tk.END, f"[ERROR] Cookies file not found: {cookies_path}\n", ("error",))
        return False
    except json.JSONDecodeError:
        log_widget.insert(tk.END, f"[ERROR] Could not decode JSON from cookies file: {cookies_path}\n", ("error",))
        return False
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] An unexpected error occurred while loading cookies: {e}\n", ("error",))
        import traceback
        log_verbose(f"Traceback:\n{traceback.format_exc()}", verbose, log_widget)
        return False

def scroll_page(driver, scroll_delay, max_scroll, verbose, log_widget):
    log_verbose("Starting page scroll...", verbose, log_widget)
    scroll_count = 0
    last_height = driver.execute_script("return document.body.scrollHeight")

    while scroll_count < max_scroll:
        if interrupted:
            log_verbose("Scroll interrupted by user.", verbose, log_widget)
            break

        log_verbose(f"Scroll attempt {scroll_count + 1}/{max_scroll}...", verbose, log_widget)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_delay)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            time.sleep(scroll_delay / 2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                log_verbose("Reached bottom of the page or no new content loaded.", verbose, log_widget)
                break

        last_height = new_height
        scroll_count += 1

    if scroll_count == max_scroll:
        log_verbose(f"Reached maximum scroll limit ({max_scroll}).", verbose, log_widget)
    else:
        log_verbose(f"Scrolling finished after {scroll_count + 1} attempts.", verbose, log_widget)

def contains_blacklist(text):
    lower_text = text.lower()
    if any(kw.lower() in lower_text for kw in blacklist_keywords):
        return True
    for pattern in blacklist_patterns:
        if re.search(pattern, lower_text):
            return True
    return False

def extract_group_names_and_urls(driver, verbose, log_widget):
    global collected_group_data
    log_verbose("Extracting group names and URLs...", verbose, log_widget)
    extracted_count_in_pass = 0
    try:
        group_links_xpath = "//a[contains(@href, '/groups/') and @role='link' and normalize-space(.)]"

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, group_links_xpath))
        )

        group_link_elements = driver.find_elements(By.XPATH, group_links_xpath)
        log_verbose(f"Found {len(group_link_elements)} potential group link elements.", verbose, log_widget)

        initial_dict_size = len(collected_group_data)

        for element in group_link_elements:
            if interrupted:
                log_verbose("Extraction interrupted by user.", verbose, log_widget)
                break
            try:
                group_name = element.text.strip()
                group_url = element.get_attribute('href')

                # No filtering here, store all for post-processing
                if group_name and group_url and '/groups/' in group_url:
                    if not group_url.startswith(('http://', 'https://')):
                         base_url = "https://www.facebook.com"
                         group_url = f"{base_url}{group_url}" if group_url.startswith('/') else f"{base_url}/{group_url}"

                    if group_name not in collected_group_data:
                       log_verbose(f"  -> Found: '{group_name}' - {group_url}", verbose, log_widget)
                       collected_group_data[group_name] = group_url
                       extracted_count_in_pass += 1
                # Removed the blacklist check during extraction
            except Exception as e:
                log_widget.insert(tk.END, f"[WARNING] Could not extract details from an element: {e}\n", ("warning",))

        newly_added = len(collected_group_data) - initial_dict_size
        log_verbose(f"Extracted {newly_added} new unique groups in this pass (filtering to be applied later).\n", verbose, log_widget)
        log_verbose(f"Total unique groups collected so far: {len(collected_group_data)}\n", verbose, log_widget)

    except TimeoutException:
        log_verbose("No group link elements found within the timeout period or page structure changed.", verbose, log_widget)
    except NoSuchElementException:
        log_verbose("Group link elements not found using the specified XPath.", verbose, log_widget)
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] An unexpected error occurred during group data extraction: {e}\n", ("error",))

    return extracted_count_in_pass > 0

def save_groups_to_file(output_path, group_data, encoding, verbose, is_final=True, log_widget=None):
    if not group_data:
        log_verbose("No group data collected to save.", verbose, log_widget)
        return

    action = "Saving final" if is_final else "Saving intermediate progress for"
    log_msg = f"{action} {len(group_data)} unique groups to {output_path}..."
    if log_widget:
        log_widget.insert(tk.END, f"[INFO] {log_msg}\n", ("info",))
        log_widget.see(tk.END)
    else:
        print(f"[INFO] {log_msg}")

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding=encoding) as f:
            writer = csv.writer(f)
            writer.writerow(['GroupName', 'GroupURL'])

            sorted_names = sorted(group_data.keys())
            for name in sorted_names:
                writer.writerow([name, group_data[name]])

        log_msg = "Successfully saved group data to CSV."
        if log_widget:
            log_widget.insert(tk.END, f"[INFO] {log_msg}\n", ("info",))
            log_widget.see(tk.END)
        else:
            print(f"[INFO] {log_msg}")
    except IOError as e:
        log_msg = f"[ERROR] Could not write to output file {output_path}: {e}"
        if log_widget:
            log_widget.insert(tk.END, f"{log_msg}\n", ("error",))
            log_widget.see(tk.END)
        else:
            print(log_msg, file=sys.stderr)
    except Exception as e:
        log_msg = f"[ERROR] An unexpected error occurred while saving the file: {e}"
        if log_widget:
            log_widget.insert(tk.END, f"{log_msg}\n", ("error",))
            log_widget.see(tk.END)
        else:
            print(log_msg, file=sys.stderr)

# --- NEW: Post-processing function to filter CSV and create separate files ---
def post_process_csv(csv_input_path, log_widget, encoding, verbose):
    log_widget.insert(tk.END, "[INFO] Starting post-processing to filter and separate group data...\n", ("info",))
    log_widget.see(tk.END)

    filtered_names = []
    filtered_urls = []
    
    output_dir = Path(csv_input_path).parent # Get directory of the CSV file
    # Use the base name of the CSV file to name the TXT files, without the .csv extension
    base_name = Path(csv_input_path).stem 
    output_name_file = output_dir / f"{base_name}_names_filtered.txt" # New name for clarity
    output_url_file = output_dir / f"{base_name}_urls_filtered.txt"   # New name for clarity

    try:
        # Check if the input CSV file exists
        if not Path(csv_input_path).exists():
            log_widget.insert(tk.END, f"[ERROR] CSV input file not found for post-processing: {csv_input_path}\n", ("error",))
            return # Exit if file doesn't exist

        with open(csv_input_path, mode='r', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                name = row.get('GroupName', '').strip() # Use .get() for safer access
                url = row.get('GroupURL', '').strip()   # Use .get() for safer access

                if name and url and not contains_blacklist(name): # Ensure name and url are not empty
                    filtered_names.append(name)
                    filtered_urls.append(url)
        
        # Save filtered names
        with open(output_name_file, mode='w', encoding=encoding) as f:
            for name in filtered_names:
                f.write(name + '\n')
        log_widget.insert(tk.END, f"[INFO] Filtered group names saved to: {output_name_file}\n", ("info",))

        # Save filtered URLs
        with open(output_url_file, mode='w', encoding=encoding) as f:
            for url in filtered_urls:
                f.write(url + '\n')
        log_widget.insert(tk.END, f"[INFO] Filtered group URLs saved to: {output_url_file}\n", ("info",))

        log_widget.insert(tk.END, "[INFO] Post-processing completed.\n", ("info",))
        log_widget.see(tk.END)

    except FileNotFoundError: # This catch might be redundant if the initial check passes
        log_widget.insert(tk.END, f"[ERROR] CSV input file not found for post-processing (during open): {csv_input_path}\n", ("error",))
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] An error occurred during post-processing: {e}\n", ("error",))
        import traceback
        log_widget.insert(tk.END, f"Traceback:\n{traceback.format_exc()}\n", ("error",))
    
# --- Main Scraper Function (adapted for GUI) ---
def run_scraper(args, log_widget):
    global driver, collected_group_data, interrupted
    interrupted = False # Reset interrupted flag for a new run
    collected_group_data = {} # Clear previous data

    # Redirect stdout and stderr to the text widget
    # Store original stdout/stderr first
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = TextRedirector(log_widget, "stdout")
    sys.stderr = TextRedirector(log_widget, "error")

    log_widget.delete("1.0", tk.END) # Clear previous logs
    log_widget.insert(tk.END, "[INFO] Scraping process started...\n", ("info",))
    display_config_summary(args, log_widget)

    try:
        log_verbose("Initializing WebDriver...", args.verbose, log_widget)
        options = ChromeOptions() # This should now be defined

        if args.headless:
            options.add_argument("--headless")
            log_verbose("Headless mode enabled.", args.verbose, log_widget)

        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
        options.add_argument("--lang=en-US,en")
        options.add_experimental_option('prefs', {'intl.accept_languages': 'en-US,en'})

        if args.proxy:
            log_widget.insert(tk.END, "[WARNING] Proxy ON requested, but proxy server details need to be added to the script.\n", ("warning",))

        try:
            service = webdriver.chrome.service.Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            log_verbose("WebDriver initialized successfully.", args.verbose, log_widget)
        except Exception as e:
             log_widget.insert(tk.END, f"[ERROR] Failed to initialize WebDriver: {e}\n", ("error",))
             log_widget.insert(tk.END, "Please ensure Chrome and the corresponding WebDriver are installed correctly.\n", ("error",))
             log_widget.insert(tk.END, "Or check network connection if webdriver-manager is downloading.\n", ("error",))
             app_instance.set_status("Error", "red")
             return

        if interrupted: return # Check for interruption before proceeding

        if not load_cookies(driver, args.cookies, args.verbose, log_widget):
            log_widget.insert(tk.END, "[ERROR] Failed to login using cookies. Exiting.\n", ("error",))
            app_instance.set_status("Error", "red")
            return

        if interrupted: return

        try:
            WebDriverWait(driver, 15).until(
                 EC.presence_of_element_located((By.XPATH, "//input[contains(@aria-label, 'Search')] | //div[@role='search']"))
            )
            log_verbose("Login appears successful (found search element).", args.verbose, log_widget)
        except TimeoutException:
            log_widget.insert(tk.END, "[WARNING] Could not confirm successful login after loading cookies. Page might not be as expected.\n", ("warning",))

        if interrupted: return

        groups_join_url = "https://www.facebook.com/groups/joins/"
        log_verbose(f"Navigating to Your Groups page: {groups_join_url}", args.verbose, log_widget)
        driver.get(groups_join_url)

        if interrupted: return

        try:
            WebDriverWait(driver, 20).until(
                 EC.presence_of_element_located((By.XPATH, "//div[contains(@aria-label, 'group') or contains(@aria-label, 'Group')]"))
            )
            log_verbose("'/groups/joins/' page likely loaded.", args.verbose, log_widget)
        except TimeoutException:
            log_widget.insert(tk.END, f"[WARNING] Timed out waiting for '{groups_join_url}' page elements. Scraping might fail or be incomplete.\n", ("warning",))
        except WebDriverException as e: # This should now be defined
             log_widget.insert(tk.END, f"[ERROR] WebDriver error during navigation or wait on /groups/joins/: {e}\n", ("error",))
             app_instance.set_status("Error", "red")
             return

        if interrupted: return

        scroll_page(driver, args.scroll_delay, args.max_scroll, args.verbose, log_widget)

        if interrupted: return

        log_verbose("Waiting briefly after scrolling before final extraction...", args.verbose, log_widget)
        time.sleep(3)

        extract_group_names_and_urls(driver, args.verbose, log_widget)

        # Save to CSV first
        save_groups_to_file(args.output, collected_group_data, args.encoding, args.verbose, is_final=True, log_widget=log_widget)

        # Then perform post-processing if not interrupted
        if not interrupted:
            post_process_csv(args.output, log_widget, args.encoding, args.verbose)
            log_widget.insert(tk.END, "[INFO] Scraping and post-processing completed successfully.\n", ("info",))
            app_instance.set_status("Completed", "green")
        else:
            log_widget.insert(tk.END, "[INFO] Scraping process interrupted.\n", ("info",))
            app_instance.set_status("Interrupted", "orange")

    except WebDriverException as e: # This should now be defined
        log_widget.insert(tk.END, f"[ERROR] WebDriver encountered an error: {e}\n", ("error",))
        app_instance.set_status("Error", "red")
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] An unexpected error occurred: {e}\n", ("error",))
        import traceback
        log_widget.insert(tk.END, f"Traceback:\n{traceback.format_exc()}\n", ("error",))
        app_instance.set_status("Error", "red")
    finally:
        # Restore stdout/stderr to original
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        safe_quit(log_widget, is_gui_initiated=True) # Ensure driver is closed and data saved


# --- Tkinter GUI Application ---
class FacebookScraperApp:
    def __init__(self, master):
        self.master = master
        master.title("Facebook Group Scraper")
        master.geometry("800x700")

        self.style = ttk.Style()
        self.style.configure("TFrame", padding=10)
        self.style.configure("TLabel", font=('Arial', 10))
        self.style.configure("TButton", font=('Arial', 10, 'bold'))
        self.style.configure("TCheckbutton", font=('Arial', 10))

        # Variables for inputs
        self.cookies_path_var = tk.StringVar(value='www.facebook.com.cookies.json')
        self.output_path_var = tk.StringVar(value='groups_data.csv')
        self.headless_var = tk.BooleanVar(value=True)
        self.proxy_var = tk.BooleanVar(value=False)
        self.verbose_var = tk.BooleanVar(value=True)
        self.scroll_delay_var = tk.DoubleVar(value=2.0)
        self.max_scroll_var = tk.IntVar(value=50)
        self.encoding_var = tk.StringVar(value='utf-8')

        self.create_widgets()

        # Global instance for safe_quit to access
        global app_instance
        app_instance = self

        # Setup signal handler for console Ctrl+C
        signal.signal(signal.SIGINT, lambda s, f: safe_quit(self.log_text, False))


    def create_widgets(self):
        # Input Frame
        input_frame = ttk.LabelFrame(self.master, text="Configuration", padding="10 10 10 10")
        input_frame.pack(padx=10, pady=10, fill="x")

        # Row 1: Cookies File
        ttk.Label(input_frame, text="Cookies File:").grid(row=0, column=0, sticky="w", pady=2)
        self.cookies_entry = ttk.Entry(input_frame, textvariable=self.cookies_path_var, width=50)
        self.cookies_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        ttk.Button(input_frame, text="Browse", command=self.browse_cookies).grid(row=0, column=2, pady=2)

        # Row 2: Output File
        ttk.Label(input_frame, text="Output File (CSV):").grid(row=1, column=0, sticky="w", pady=2)
        self.output_entry = ttk.Entry(input_frame, textvariable=self.output_path_var, width=50)
        self.output_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        ttk.Button(input_frame, text="Browse", command=self.browse_output).grid(row=1, column=2, pady=2)

        # Row 3: Headless, Proxy, Verbose Checkboxes
        ttk.Checkbutton(input_frame, text="Headless Mode", variable=self.headless_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Checkbutton(input_frame, text="Use Proxy (Not Implemented)", variable=self.proxy_var).grid(row=2, column=1, sticky="w", pady=2)
        ttk.Checkbutton(input_frame, text="Verbose Logging", variable=self.verbose_var).grid(row=2, column=2, sticky="w", pady=2)

        # Row 4: Scroll Delay
        ttk.Label(input_frame, text="Scroll Delay (seconds):").grid(row=3, column=0, sticky="w", pady=2)
        self.scroll_delay_spinbox = ttk.Spinbox(input_frame, from_=0.1, to_=10.0, increment=0.1,
                                                textvariable=self.scroll_delay_var, width=10, format="%.1f")
        self.scroll_delay_spinbox.grid(row=3, column=1, padx=5, pady=2, sticky="w")

        # Row 5: Max Scroll
        ttk.Label(input_frame, text="Max Scroll Attempts:").grid(row=4, column=0, sticky="w", pady=2)
        self.max_scroll_spinbox = ttk.Spinbox(input_frame, from_=1, to_=1000, increment=1,
                                              textvariable=self.max_scroll_var, width=10)
        self.max_scroll_spinbox.grid(row=4, column=1, padx=5, pady=2, sticky="w")

        # Row 6: Encoding
        ttk.Label(input_frame, text="Encoding:").grid(row=5, column=0, sticky="w", pady=2)
        self.encoding_entry = ttk.Entry(input_frame, textvariable=self.encoding_var, width=15)
        self.encoding_entry.grid(row=5, column=1, padx=5, pady=2, sticky="w")


        input_frame.columnconfigure(1, weight=1) # Make entry fields expand

        # Buttons Frame
        button_frame = ttk.Frame(self.master, padding="10 0 10 10")
        button_frame.pack(padx=10, pady=5, fill="x")

        self.start_button = ttk.Button(button_frame, text="Start Scraping", command=self.start_scraping)
        self.start_button.pack(side="left", padx=5)

        self.stop_button = ttk.Button(button_frame, text="Stop Scraping", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_button.pack(side="left", padx=5)

        # Status Label
        self.status_label = ttk.Label(button_frame, text="Status: Ready", font=('Arial', 10, 'bold'))
        self.status_label.pack(side="right", padx=5)

        # Log Frame
        log_frame = ttk.LabelFrame(self.master, text="Logs", padding="10 10 10 10")
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, wrap="word", height=20, bg="#212121", fg="#ffffff",
                                font=('Consolas', 9), insertbackground="#ffffff")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=self.log_scrollbar.set)

        # Configure tags for colored logging
        self.log_text.tag_config("info", foreground="#00e676") # Green for INFO
        self.log_text.tag_config("verbose", foreground="#81d4fa") # Light blue for VERBOSE
        self.log_text.tag_config("warning", foreground="#ffea00") # Yellow for WARNING
        self.log_text.tag_config("error", foreground="#ff1744") # Red for ERROR
        self.log_text.tag_config("stdout", foreground="#ffffff") # White for normal output

    def browse_cookies(self):
        filename = filedialog.askopenfilename(
            title="Select Cookies File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.cookies_path_var.set(filename)

    def browse_output(self):
        filename = filedialog.asksaveasfilename(
            title="Save Output As",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.output_path_var.set(filename)

    def set_status(self, message, color="black"):
        self.status_label.config(text=f"Status: {message}", foreground=color)
        self.master.update_idletasks() # Update GUI immediately

    def start_scraping(self):
        self.set_status("Starting...", "blue")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # Create a dummy args object from GUI inputs
        class Args:
            def __init__(self, cookies_path, output_path, headless, proxy, verbose, scroll_delay, max_scroll, encoding):
                self.cookies = cookies_path
                self.output = output_path
                self.headless = headless
                self.proxy = proxy
                self.verbose = verbose
                self.scroll_delay = scroll_delay
                self.max_scroll = max_scroll
                self.encoding = encoding

        # Inisialisasi objek Args dengan nilai-nilai dari variabel Tkinter
        args = Args(
            cookies_path=self.cookies_path_var.get(),
            output_path=self.output_path_var.get(),
            headless=self.headless_var.get(),
            proxy=self.proxy_var.get(),
            verbose=self.verbose_var.get(),
            scroll_delay=self.scroll_delay_var.get(),
            max_scroll=self.max_scroll_var.get(),
            encoding=self.encoding_var.get()
        )

        # Validate inputs
        if not args.cookies:
            messagebox.showerror("Input Error", "Cookies file path cannot be empty.")
            self.reset_buttons()
            self.set_status("Ready", "black")
            return
        if not args.output:
            messagebox.showerror("Input Error", "Output file path cannot be empty.")
            self.reset_buttons()
            self.set_status("Ready", "black")
            return
        if args.scroll_delay <= 0:
            messagebox.showerror("Input Error", "Scroll delay must be positive.")
            self.reset_buttons()
            self.set_status("Ready", "black")
            return
        if args.max_scroll <= 0:
            messagebox.showerror("Input Error", "Max scroll must be positive.")
            self.reset_buttons()
            self.set_status("Ready", "black")
            return

        # Run the scraper in a separate thread
        self.scraper_thread = threading.Thread(target=run_scraper, args=(args, self.log_text))
        self.scraper_thread.daemon = True # Allow the thread to exit with the main program
        self.scraper_thread.start()

        self.check_scraper_thread() # Start checking thread status

    def stop_scraping(self):
        global interrupted
        if messagebox.askyesno("Stop Scraping", "Are you sure you want to stop the scraping process?"):
            self.set_status("Stopping...", "orange")
            interrupted = True # Signal the scraper to stop
            # safe_quit will be called by the thread's finally block
            self.stop_button.config(state=tk.DISABLED) # Disable stop button immediately

    def reset_buttons(self):
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def check_scraper_thread(self):
        if self.scraper_thread.is_alive():
            self.master.after(100, self.check_scraper_thread) # Check again after 100ms
        else:
            self.reset_buttons()
            if not interrupted: # If not interrupted by user, assume completion or error handled by run_scraper
                current_status_text = self.status_label.cget("text")
                if "Starting" in current_status_text and "Error" not in current_status_text and "Completed" not in current_status_text:
                    # If it started and ended without specific status, it's likely an error or early exit
                    self.set_status("Finished (with possible errors/early exit)", "red")
            # Else, status is already set to Interrupted, Completed, or Error by run_scraper

if __name__ == "__main__":
    root = tk.Tk()
    app = FacebookScraperApp(root)
    root.mainloop()