# 🤖 Facebook Group Scraper

## 🌟 Key Features

  - **Graphical User Interface (GUI):** No more command-line hassle\! Simply run the script and configure all the options easily through an intuitive application window. 🖱️
  - **Full Automation:** It uses **Selenium** to mimic user interactions in a browser, scrolling through pages and extracting group data. 🚀
  - **Authentication Handling:** It logs into Facebook securely using a **cookies file**. There's no need to manually enter your credentials. 🍪
  - **Smart Extraction:** The script collects the names and URLs of all detected groups on the `facebook.com/groups/joins/` page. 🔗
  - **Flexible Data Storage:** It saves the extracted data into a **CSV file** (`.csv`) for further analysis. 📊
  - **Automatic Post-processing:** The tool automatically processes the raw CSV output, filters out irrelevant groups, and saves the filtered data into separate `.txt` files for group names and URLs. ✨
  - **Configurable Options:** You can customize the script's behavior by controlling the:
      - **Headless Mode:** Run the browser in the background without a visual window. 👻
      - **Scroll Delay:** Control the scrolling speed to avoid detection. ⏱️
      - **Max Scroll Attempts:** Limit how many times the script scrolls the page. 📜
      - **Verbose Logging:** See detailed process logs in real-time right inside the application. 📝
  - **Graceful Interruption:** You can stop the process at any time using the "Stop Scraping" button on the GUI. 🛑

-----

## ⚙️ Requirements

Before running the script, make sure you have the following dependencies installed.

### Python

You need to have **Python 3.x** installed.

### Python Libraries

You can install all the necessary libraries with a single command:

```bash
pip install -r requirements.txt
```

If you don't have a `requirements.txt` file yet, you can create one manually with the following libraries:

```
selenium
webdriver-manager
tkinter
```

> **Note:** `tkinter` is usually included with standard Python installations, but it may require a separate installation on some operating systems.

### Chrome Browser

This script is designed to work with **Google Chrome**. `webdriver-manager` will automatically download a compatible `ChromeDriver` version, so you don't need to install it manually\! 🎉

-----

## 🚀 How to Use

### Step 1: Get Your Cookies File

The script requires a `cookies.json` file from your logged-in Facebook session to avoid manual authentication.

1.  Install a browser extension like **"EditThisCookie"** (for Chrome or Firefox).
2.  Log in to Facebook in your browser.
3.  Go to `facebook.com`, click the extension icon, and export the cookies in JSON format.
4.  Save this JSON file as `www.facebook.com.cookies.json` in the same directory as your `gui.py` script.

### Step 2: Run the Application

Once all requirements are installed, you can run the GUI application:

```bash
python gui.py
```

### Step 3: Configure and Start

1.  The GUI application window will appear. Make sure the `Cookies File` and `Output File` paths are correct.
2.  Adjust other options like `Headless Mode`, `Scroll Delay`, and `Max Scroll Attempts` to fit your needs.
3.  Click the **"Start Scraping"** button to begin the process.
4.  You can view the logs and the status of the process in the application window.
5.  To stop the process at any time, click the **"Stop Scraping"** button.

### Output

After the process is complete (or interrupted), the script will generate three files in the output directory you specified:

1.  `your_filename.csv` - The raw CSV file containing all the extracted groups, including the unfiltered ones.
2.  `your_filename_names_filtered.txt` - A text file with the filtered group names.
3.  `your_filename_urls_filtered.txt` - A text file with the filtered group URLs.

-----

## ⚠️ Disclaimer

  - **Use Responsibly:** Only use this script for personal purposes and do not violate Facebook's terms of service. Excessive or improper use may lead to your account being flagged or restricted.
  - **Security:** Be sure to store your cookies file in a secure location, as it contains sensitive information for your account session.
