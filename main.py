from bs4 import BeautifulSoup as bs
from selenium import webdriver
from datetime import datetime as dt
from datetime import time
from pytz import timezone
import requests
import telebot
import time as t
import firebase_admin
from firebase_admin import credentials, firestore
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os

# Initialize Firebase
cred = credentials.Certificate("firebase_credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

tz = timezone("Asia/Kolkata")

tick = "✔️"
cross = "❌"

Admin = os.getenv("ADMIN_ID")

bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))

zlink = os.getenv("ZOMATO_LINK")
slink = os.getenv("SWIGGY_LINK")

# Chrome options
chrome_options = webdriver.ChromeOptions()
# chrome_options.add_argument("--headless")
# chrome_options.add_argument("--disable-dev-shm-usage")
# chrome_options.add_argument("--no-sandbox")

driver = webdriver.Chrome(service=Service(
    ChromeDriverManager().install()), options=chrome_options)


def is_time_between(begin_time, end_time, check_time=None):
    check_time = check_time or dt.now(tz).time()
    if begin_time < end_time:
        return begin_time <= check_time <= end_time
    else:
        return check_time >= begin_time or check_time <= end_time


def get_date():
    now = dt.now(tz)
    current_time = now.strftime("%I:%M %p")
    return str(current_time)


def getList(dict):
    return dict.keys()


def Get_USERS():
    doc_users = db.collection("Users").document("users")
    users_db = doc_users.get().to_dict()
    USERS = list(getList(users_db))
    return USERS


def swiggy_check():
    driver.get(slink)
    source = driver.page_source
    soup = bs(source, "html.parser")
    pageHeader = soup.find("div", attrs={"class": "sc-kRRyDe thiEb"})
    pageStatusLine = pageHeader.find(
        "div", attrs={"class": "sc-kMribo bnHjVl"}) if pageHeader else None
    print(pageStatusLine)
    if pageStatusLine:
        status_text = pageStatusLine.text if isinstance(
            pageStatusLine, list) else pageStatusLine.text
        if "Outlet is not accepting orders" in status_text or "Opens today in" in status_text:
            return ["Offline", get_date(), "Outlet is not accepting orders"]
        else:
            return ["Online", get_date(), "Online"]
    return ["Error", get_date(), "Unable to determine status"]


def zomato_check():
    try:
        driver.get(zlink)
        source = driver.page_source
        soup = bs(source, "html.parser")
        pageHeader = soup.find("div", attrs={"class": "sc-fOICqy fPpMAv"})
        pageStatusLine = pageHeader.find_all(
            "section")[-1].text if pageHeader else None
        print(pageStatusLine)
        if not pageStatusLine:
            raise Exception("Page status line not found")

        status_map = {
            "Opens in": "Offline",
            "Opens tomorrow": "Offline",
            "Opens at": "Offline",
            "closes in": "Online",
            "Currently closed": "Offline",
            "Open now": "Online",
            "Closes in": "Online"
        }

        for key in status_map:
            if key in pageStatusLine:
                status = status_map[key]
                return [status, get_date(), status]

        bot.send_message(
            Admin, f"<b>Error in Zomato Status Check Function</b>\n\nUnrecognized status line:\n{pageStatusLine}", parse_mode="HTML")
        return ["Error", get_date(), "Unrecognized status line"]

    except Exception as e:
        error_message = (
            f"<b>Error in Zomato Status Check Function</b>\n\n"
            f"Exception: {str(e)}\n"
            f"Status Line: {pageStatusLine if 'pageStatusLine' in locals() else 'N/A'}"
        )
        bot.send_message(Admin, error_message, parse_mode="HTML")
        return ["Error", get_date(), str(e)]


def check_and_update_status(platform, current_status, db_status, db_doc, link, tick, cross):
    status, timestamp, reason = current_status
    if status != db_status:
        current_status = zomato_check() if platform == "Zomato" else swiggy_check()
        if current_status[0] == status:
            update_firestore_and_notify_users(
                platform, current_status, db_doc, link, tick, cross)


def update_firestore_and_notify_users(platform, current_status, db_doc, link, tick, cross):
    status, timestamp, reason = current_status
    text = (
        f"{tick}<b><a href='{link}'>{platform}</a></b>\nYour store is currently Online ({timestamp})\n"
        if status == "Online" else
        f"{cross}<b><a href='{link}'>{platform}</a></b>\nYour store is currently Offline ({timestamp})"
    )

    USERS = Get_USERS()
    for user in USERS:
        bot.send_message(
            user, text, disable_web_page_preview=True, parse_mode="HTML")

    data = {"Status": status, "Time": timestamp, "Reason": reason}
    db_doc.set(data)


def main():
    if is_time_between(time(9, 0), time(23, 10), dt.now(tz).time()):
        zomato_current = zomato_check()
        swiggy_current = swiggy_check()

        doc_zomato = db.collection("Zomato").document("Status")
        doc_swiggy = db.collection("Swiggy").document("Status")

        zomato_db = doc_zomato.get().to_dict().get("Status")
        swiggy_db = doc_swiggy.get().to_dict().get("Status")

        check_and_update_status("Zomato", zomato_current,
                                zomato_db, doc_zomato, zlink, tick, cross)
        check_and_update_status("Swiggy", swiggy_current,
                                swiggy_db, doc_swiggy, slink, tick, cross)


while True:
    try:
        main()
        t.sleep(15)
    except Exception as e:
        print(f"Error: {e}")
    t.sleep(5)
