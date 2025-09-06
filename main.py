import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import signal
import sys
import time
import csv
import re
import threading
from pathlib import Path

# --- Import Selenium Modules ---
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, WebDriverException
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
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
    "berita hari ini", "berita terkini", "berita trending hari ini", "beranda anda",
    "berita viral", "temukan", "discover", "view group", "your feed", "your groups",
    "see all", "create new group", "buat grup baru", "lihat grup", "lihat semua"
]

# --- PERBAIKAN FILTER UTAMA: Pola Regex yang Lebih Akurat ---
blacklist_patterns = [
    # Pola untuk "BERITA [NAMA NEGARA/KOTA] [TAHUN]"
    r"berita\s+([a-zA-Z\s]+)\s+\d{4}",

    # Pola Bahasa Indonesia yang Diperbaiki (lebih akurat)
    # Menangkap format: [angka] [unit waktu] atau [se-unitwaktu]
    r"(terakhir aktif|active)\s+(?:sekitar|about)?\s*(\d+\s+(?:detik|menit|jam|hari|minggu)|semenit|sejam|sehari|seminggu)\s+(?:yang )?lalu",
    
    # Pola Bahasa Inggris yang sudah diperbaiki
    r"(last active|active)\s+(?:about|a few)?\s*(\d+|a|an)\s+(second|minute|hour|day|week)s?\s+ago",
    
    # Pola umum untuk menangkap sisa-sisa yang mungkin terlewat
    r"last active a few seconds ago", r"last active about a minute ago"
]

compiled_blacklist_patterns = [re.compile(p, re.IGNORECASE) for p in blacklist_patterns]


# --- Redirect stdout/stderr to a Tkinter Text widget ---
class TextRedirector(object):
    def __init__(self, widget, tag="stdout"):
        self.widget = widget; self.tag = tag; self.stdout = sys.stdout
    def write(self, str_val):
        self.widget.insert(tk.END, str_val, (self.tag,)); self.widget.see(tk.END); self.stdout.write(str_val)
    def flush(self):
        self.stdout.flush()

# --- Helper Functions ---
def log_verbose(message, verbose_flag, log_widget):
    if verbose_flag:
        log_widget.insert(tk.END, f"[VERBOSE] {message}\n", ("verbose",)); log_widget.see(tk.END)

def display_config_summary(args, log_widget):
    log_widget.insert(tk.END, "\n================ Configuration Summary ================\n", ("info",))
    log_widget.insert(tk.END, f"Cookies File      : {args.cookies}\n", ("info",))
    log_widget.insert(tk.END, f"Output File       : {args.output} (Format: CSV)\n", ("info",))
    log_widget.insert(tk.END, f"Headless Mode     : {'ON' if args.headless else 'OFF'}\n", ("info",))
    log_widget.insert(tk.END, f"Verbose Logging   : {'ON' if args.verbose else 'OFF'}\n", ("info",))
    log_widget.insert(tk.END, f"Scroll Delay      : {args.scroll_delay}s\n", ("info",))
    log_widget.insert(tk.END, f"Max Scroll        : {args.max_scroll}\n", ("info",))
    log_widget.insert(tk.END, "=======================================================\n\n", ("info",))
    log_widget.see(tk.END)

def safe_quit(log_widget, is_gui_initiated=False):
    global interrupted, driver
    if not is_gui_initiated:
        if driver:
            log_widget.insert(tk.END, "\nCTRL+C detected. Attempting graceful exit...\n", ("warning",)); interrupted = True
    else:
        log_widget.insert(tk.END, "Stop button pressed. Attempting graceful exit...\n", ("warning",)); interrupted = True

    if driver:
        try: driver.quit()
        except WebDriverException: pass
        finally: driver = None
    # Fitur baru akan menyimpan file dengan nama profil, jadi tidak perlu save di sini.
    if not is_gui_initiated: sys.exit(0)

# (Fungsi load_cookies, scroll_page, contains_blacklist, dll. tetap sama, tidak perlu diubah)
def load_cookies(driver, cookies_path, verbose, log_widget):
    log_verbose(f"Attempting to load cookies from: {cookies_path}", verbose, log_widget)
    try:
        with open(cookies_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        log_verbose(f"Loaded {len(cookies)} cookies from file.", verbose, log_widget)
        driver.get("https://www.facebook.com")
        time.sleep(2)
        for cookie in cookies:
            if 'sameSite' not in cookie: cookie['sameSite'] = 'Lax'
            if 'expiry' in cookie and (cookie['expiry'] is None or cookie['expiry'] == -1): del cookie['expiry']
            elif 'expires' in cookie and isinstance(cookie['expires'], float): cookie['expires'] = int(cookie['expires'])
            if 'expires' in cookie and 'expiry' not in cookie: cookie['expiry'] = cookie.pop('expires')
            try: driver.add_cookie(cookie)
            except Exception: pass
        log_verbose("Finished adding cookies.", verbose, log_widget)
        driver.refresh()
        log_verbose("Page refreshed after adding cookies.", verbose, log_widget)
        time.sleep(3)
        return True
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] Failed during cookie load: {e}\n", ("error",))
        return False

def scroll_page(driver, scroll_delay, max_scroll, verbose, log_widget):
    log_verbose("Starting page scroll...", verbose, log_widget)
    scroll_count = 0
    last_height = driver.execute_script("return document.body.scrollHeight")
    while scroll_count < max_scroll:
        if interrupted: log_verbose("Scroll interrupted.", verbose, log_widget); break
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_delay)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            log_verbose("Reached bottom of the page.", verbose, log_widget); break
        last_height = new_height
        scroll_count += 1
    log_verbose(f"Scrolling finished after {scroll_count + 1} attempts.", verbose, log_widget)

def contains_blacklist(text):
    lower_text = text.lower()
    if any(kw in lower_text for kw in blacklist_keywords): return True
    for pattern in compiled_blacklist_patterns:
        if pattern.search(lower_text): return True
    return False

def extract_group_names_and_urls(driver, verbose, log_widget):
    global collected_group_data
    log_verbose("Extracting group names and URLs...", verbose, log_widget)
    try:
        group_links_xpath = "//a[contains(@href, '/groups/') and @role='link' and normalize-space(.)]"
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, group_links_xpath)))
        group_link_elements = driver.find_elements(By.XPATH, group_links_xpath)
        initial_dict_size = len(collected_group_data)
        for element in group_link_elements:
            if interrupted: break
            try:
                group_name = element.text.strip()
                group_url = element.get_attribute('href')
                if group_name and group_url and '/groups/' in group_url:
                    if not group_url.startswith(('http:', 'https:')):
                         group_url = f"https://www.facebook.com{group_url}"
                    if group_name not in collected_group_data:
                       collected_group_data[group_name] = group_url
            except Exception: pass
        newly_added = len(collected_group_data) - initial_dict_size
        log_verbose(f"Extracted {newly_added} new unique groups.\n", verbose, log_widget)
    except Exception:
        log_verbose("No group link elements found.", verbose, log_widget)

def save_groups_to_file(output_path, group_data, encoding, verbose, log_widget=None):
    if not group_data: return
    log_msg = f"Saving {len(group_data)} unique groups to {output_path}..."
    if log_widget: log_widget.insert(tk.END, f"[INFO] {log_msg}\n", ("info",))
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', newline='', encoding=encoding) as f:
            writer = csv.writer(f)
            writer.writerow(['GroupName', 'GroupURL'])
            for name, url in sorted(group_data.items()): writer.writerow([name, url])
        if log_widget: log_widget.insert(tk.END, "[INFO] Successfully saved group data to CSV.\n", ("info",))
    except Exception as e:
        if log_widget: log_widget.insert(tk.END, f"[ERROR] Could not write to CSV file: {e}\n", ("error",))


# --- FUNGSI BARU: Untuk mengambil nama profil ---
def get_profile_name(driver, log_widget):
    """Navigates to the user's profile page and extracts their name."""
    log_widget.insert(tk.END, "[INFO] Navigating to profile page to get user name...\n", ("info",))
    try:
        driver.get("https://www.facebook.com/me/")
        # Menggunakan XPath yang lebih stabil untuk menemukan H1 di dalam area utama halaman
        h1_xpath = "//div[@role='main']//h1"
        wait_time = 20
        h1_element = WebDriverWait(driver, wait_time).until(
            EC.presence_of_element_located((By.XPATH, h1_xpath))
        )
        
        # Menggunakan JavaScript untuk mendapatkan teks utama dari H1, tanpa teks tambahan di dalam <span>
        full_name = driver.execute_script("return arguments[0].firstChild.textContent.trim();", h1_element)
        
        if full_name:
            log_widget.insert(tk.END, f"[INFO] Profile name found: {full_name}\n", ("info",))
            # Membersihkan nama dari karakter yang tidak valid untuk nama file
            sanitized_name = re.sub(r'[\s\W]+', '', full_name)
            return sanitized_name
        else:
            log_widget.insert(tk.END, "[WARNING] Could not extract profile name text.\n", ("warning",))
            return "user"
            
    except (TimeoutException, WebDriverException):
        log_widget.insert(tk.END, "[WARNING] Could not find profile name element. Using default 'user'.\n", ("warning",))
        return "user" # Default name jika gagal
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] An unexpected error occurred while getting profile name: {e}\n", ("error",))
        return "user"


# --- FUNGSI DIMODIFIKASI: post_process_csv sekarang menerima profile_name ---
def post_process_csv(csv_input_path, log_widget, encoding, verbose, profile_name="user"):
    log_widget.insert(tk.END, "[INFO] Starting post-processing to filter and separate data...\n", ("info",))
    
    filtered_groups = {}
    input_path = Path(csv_input_path)
    if not input_path.exists():
        log_widget.insert(tk.END, f"[ERROR] CSV input file not found for post-processing.\n", ("error",))
        return

    output_dir, base_name = input_path.parent, input_path.stem 
    # Membuat nama file dinamis menggunakan nama profil
    output_name_file = output_dir / f"{base_name}_names_filtered_{profile_name}.txt"
    output_url_file = output_dir / f"{base_name}_urls_filtered_{profile_name}.txt"

    try:
        with open(csv_input_path, mode='r', encoding=encoding, errors='ignore') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                name, url = row.get('GroupName', '').strip(), row.get('GroupURL', '').strip()
                if name and url and not contains_blacklist(name):
                    filtered_groups[name] = url
        
        log_widget.insert(tk.END, f"[INFO] Found {len(filtered_groups)} groups after filtering.\n", ("info",))

        with open(output_name_file, mode='w', encoding=encoding) as f:
            for name in sorted(filtered_groups.keys()): f.write(name + '\n')
        log_widget.insert(tk.END, f"[INFO] Filtered names saved to: {output_name_file.name}\n", ("info",))

        with open(output_url_file, mode='w', encoding=encoding) as f:
            for name in sorted(filtered_groups.keys()): f.write(filtered_groups[name] + '\n')
        log_widget.insert(tk.END, f"[INFO] Filtered URLs saved to: {output_url_file.name}\n", ("info",))
        log_widget.insert(tk.END, "[INFO] Post-processing completed.\n", ("info",))
    except Exception as e:
        log_widget.insert(tk.END, f"[ERROR] An error occurred during post-processing: {e}\n", ("error",))


# --- FUNGSI DIMODIFIKASI: run_scraper sekarang memanggil get_profile_name ---
def run_scraper(args, log_widget):
    global driver, collected_group_data, interrupted
    interrupted = False
    collected_group_data = {}
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = TextRedirector(log_widget, "stdout"); sys.stderr = TextRedirector(log_widget, "error")
    log_widget.delete("1.0", tk.END)
    log_widget.insert(tk.END, "[INFO] Scraping process started...\n", ("info",)); display_config_summary(args, log_widget)

    try:
        log_verbose("Initializing WebDriver...", args.verbose, log_widget)
        options = ChromeOptions()
        if args.headless: options.add_argument("--headless")
        options.add_argument("--disable-gpu"); options.add_argument("--window-size=1920,1080"); options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage"); options.add_argument("--disable-notifications"); options.add_argument("--lang=en-US,id;q=0.9")
        try:
            service = webdriver.chrome.service.Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            log_verbose("WebDriver initialized.", args.verbose, log_widget)
        except Exception as e:
             log_widget.insert(tk.END, f"[ERROR] Failed to initialize WebDriver: {e}\n", ("error",)); app_instance.set_status("Error", "red"); return
        if interrupted: return
        if not load_cookies(driver, args.cookies, args.verbose, log_widget):
            log_widget.insert(tk.END, "[ERROR] Failed to login using cookies. Exiting.\n", ("error",)); app_instance.set_status("Error", "red"); return
        if interrupted: return
        driver.get("https://www.facebook.com/groups/joins/")
        if interrupted: return
        try:
            wait_time = 30 
            log_verbose(f"Waiting up to {wait_time}s for groups page...", args.verbose, log_widget)
            WebDriverWait(driver, wait_time).until(EC.presence_of_element_located((By.XPATH, "//h1[contains(., 'Grup')] | //h1[contains(., 'Groups')]")))
            log_verbose("Groups page loaded.", args.verbose, log_widget)
        except Exception as e:
             log_widget.insert(tk.END, f"[ERROR] Timed out waiting for groups page: {e}\n", ("error",)); app_instance.set_status("Error", "red"); return
        if interrupted: return
        scroll_page(driver, args.scroll_delay, args.max_scroll, args.verbose, log_widget)
        if interrupted: return
        extract_group_names_and_urls(driver, args.verbose, log_widget)
        
        # --- PENAMBAHAN FITUR BARU ---
        # Panggil fungsi untuk mendapatkan nama profil SEBELUM menyimpan file
        profile_name = "user" # Default
        if not interrupted:
            profile_name = get_profile_name(driver, log_widget)
        # ---------------------------

        save_groups_to_file(args.output, collected_group_data, args.encoding, args.verbose, log_widget=log_widget)
        if not interrupted:
            # Berikan nama profil ke fungsi post-processing
            post_process_csv(args.output, log_widget, args.encoding, args.verbose, profile_name)
            log_widget.insert(tk.END, "\n[INFO] Scraping and post-processing completed.\n", ("info",))
            app_instance.set_status("Completed", "green")
        else:
            log_widget.insert(tk.END, "\n[INFO] Scraping process interrupted.\n", ("info",))
            app_instance.set_status("Interrupted", "orange")
    except Exception as e:
        log_widget.insert(tk.END, f"\n[FATAL ERROR] An unexpected error occurred: {e}\n", ("error",))
        app_instance.set_status("Fatal Error", "red")
    finally:
        sys.stdout = original_stdout; sys.stderr = original_stderr
        safe_quit(log_widget, is_gui_initiated=True)

# --- Kelas GUI FacebookScraperApp tetap sama, tidak ada perubahan di sini ---
class FacebookScraperApp:
    def __init__(self, master):
        self.master = master
        master.title("Facebook Group Scraper")
        master.geometry("800x700")
        self.style = ttk.Style()
        self.style.configure("TFrame", padding=10)
        self.style.configure("TLabel", font=('Arial', 10))
        self.style.configure("TButton", font=('Arial', 10, 'bold'))
        self.cookies_path_var = tk.StringVar(value='www.facebook.com.cookies.json')
        self.output_path_var = tk.StringVar(value='groups_data.csv')
        self.headless_var = tk.BooleanVar(value=True)
        self.verbose_var = tk.BooleanVar(value=True)
        self.scroll_delay_var = tk.DoubleVar(value=2.0)
        self.max_scroll_var = tk.IntVar(value=50)
        self.encoding_var = tk.StringVar(value='utf-8')
        self.input_widgets = []
        self.create_widgets()
        global app_instance
        app_instance = self
        signal.signal(signal.SIGINT, lambda s, f: safe_quit(self.log_text, False))

    def create_widgets(self):
        input_frame = ttk.LabelFrame(self.master, text="Configuration", padding="10")
        input_frame.pack(padx=10, pady=10, fill="x")
        ttk.Label(input_frame, text="Cookies File:").grid(row=0, column=0, sticky="w", pady=2)
        cookies_entry = ttk.Entry(input_frame, textvariable=self.cookies_path_var, width=50)
        cookies_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        cookies_btn = ttk.Button(input_frame, text="Browse", command=self.browse_cookies)
        cookies_btn.grid(row=0, column=2, pady=2)
        ttk.Label(input_frame, text="Output File (CSV):").grid(row=1, column=0, sticky="w", pady=2)
        output_entry = ttk.Entry(input_frame, textvariable=self.output_path_var, width=50)
        output_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        output_btn = ttk.Button(input_frame, text="Browse", command=self.browse_output)
        output_btn.grid(row=1, column=2, pady=2)
        headless_cb = ttk.Checkbutton(input_frame, text="Headless Mode", variable=self.headless_var)
        headless_cb.grid(row=2, column=0, sticky="w", pady=2)
        verbose_cb = ttk.Checkbutton(input_frame, text="Verbose Logging", variable=self.verbose_var)
        verbose_cb.grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(input_frame, text="Scroll Delay (s):").grid(row=3, column=0, sticky="w", pady=2)
        scroll_delay_spinbox = ttk.Spinbox(input_frame, from_=0.1, to_=10.0, increment=0.1, textvariable=self.scroll_delay_var, width=10, format="%.1f")
        scroll_delay_spinbox.grid(row=3, column=1, padx=5, pady=2, sticky="w")
        ttk.Label(input_frame, text="Max Scroll:").grid(row=4, column=0, sticky="w", pady=2)
        max_scroll_spinbox = ttk.Spinbox(input_frame, from_=1, to_=1000, increment=1, textvariable=self.max_scroll_var, width=10)
        max_scroll_spinbox.grid(row=4, column=1, padx=5, pady=2, sticky="w")
        input_frame.columnconfigure(1, weight=1)
        self.input_widgets.extend([cookies_entry, cookies_btn, output_entry, output_btn, headless_cb, verbose_cb, scroll_delay_spinbox, max_scroll_spinbox])
        button_frame = ttk.Frame(self.master)
        button_frame.pack(padx=10, pady=5, fill="x")
        self.start_button = ttk.Button(button_frame, text="Start Scraping", command=self.start_scraping)
        self.start_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(button_frame, text="Stop Scraping", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_button.pack(side="left", padx=5)
        self.status_label = ttk.Label(button_frame, text="Status: Ready", font=('Arial', 10, 'bold'))
        self.status_label.pack(side="right", padx=5)
        log_frame = ttk.LabelFrame(self.master, text="Logs", padding="10")
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_text = tk.Text(log_frame, wrap="word", height=20, bg="#212121", fg="#ffffff", font=('Consolas', 9), insertbackground="#ffffff")
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        self.log_text.tag_config("info", foreground="#00e676"); self.log_text.tag_config("verbose", foreground="#81d4fa"); self.log_text.tag_config("warning", foreground="#ffea00"); self.log_text.tag_config("error", foreground="#ff1744"); self.log_text.tag_config("stdout", foreground="#ffffff")
    def browse_cookies(self):
        filename = filedialog.askopenfilename(title="Select Cookies File", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if filename: self.cookies_path_var.set(filename)
    def browse_output(self):
        filename = filedialog.asksaveasfilename(title="Save Output As", defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if filename: self.output_path_var.set(filename)
    def set_status(self, message, color="black"):
        self.status_label.config(text=f"Status: {message}", foreground=color); self.master.update_idletasks()
    def toggle_input_widgets(self, state=tk.NORMAL):
        for widget in self.input_widgets: widget.config(state=state)
    def start_scraping(self):
        from types import SimpleNamespace
        args = SimpleNamespace(cookies=self.cookies_path_var.get(), output=self.output_path_var.get(), headless=self.headless_var.get(), verbose=self.verbose_var.get(), scroll_delay=self.scroll_delay_var.get(), max_scroll=self.max_scroll_var.get(), encoding=self.encoding_var.get())
        if not all([args.cookies, args.output]): messagebox.showerror("Input Error", "Cookies and Output file paths cannot be empty."); return
        self.set_status("Starting...", "blue"); self.start_button.config(state=tk.DISABLED); self.stop_button.config(state=tk.NORMAL); self.toggle_input_widgets(tk.DISABLED)
        self.scraper_thread = threading.Thread(target=run_scraper, args=(args, self.log_text)); self.scraper_thread.daemon = True; self.scraper_thread.start(); self.check_scraper_thread()
    def stop_scraping(self):
        global interrupted
        if messagebox.askyesno("Stop Scraping", "Are you sure? Data collected so far will be processed."):
            self.set_status("Stopping...", "orange"); interrupted = True; self.stop_button.config(state=tk.DISABLED)
    def reset_gui_state(self):
        self.start_button.config(state=tk.NORMAL); self.stop_button.config(state=tk.DISABLED); self.toggle_input_widgets(tk.NORMAL)
    def check_scraper_thread(self):
        if self.scraper_thread.is_alive(): self.master.after(100, self.check_scraper_thread)
        else: self.reset_gui_state()

if __name__ == "__main__":
    root = tk.Tk()
    app = FacebookScraperApp(root)
    root.mainloop()
