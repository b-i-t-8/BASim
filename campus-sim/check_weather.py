import urllib.request
import urllib.parse
import json
import http.cookiejar

BASE_URL = "http://localhost:8080"

def check_status(opener, label):
    status_url = f"{BASE_URL}/api/status"
    with opener.open(status_url) as response:
        if response.getcode() == 200:
            data = json.loads(response.read().decode('utf-8'))
            print(f"[{label}] Date: {data['simulation_date']}, OAT: {data['oat']}, Season: {data['season']}")
        else:
            print(f"[{label}] Failed to get status: {response.getcode()}")

def set_date(opener, date_str):
    url = f"{BASE_URL}/api/admin/date"
    data = json.dumps({"date": date_str}).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    
    try:
        with opener.open(req) as response:
            if response.getcode() == 200:
                print(f"Set date to {date_str}")
            else:
                print(f"Failed to set date: {response.getcode()}")
    except urllib.error.HTTPError as e:
        print(f"Failed to set date: {e.code} {e.read().decode('utf-8')}")

def main():
    # Setup cookie jar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    # Login
    login_url = f"{BASE_URL}/login"
    login_data = urllib.parse.urlencode({
        "username": "admin",
        "password": "admin123"
    }).encode('utf-8')
    
    req = urllib.request.Request(login_url, data=login_data, method='POST')
    with opener.open(req) as response:
        if response.getcode() != 200:
            print("Login failed")
            return

    # Check Initial
    check_status(opener, "Initial")
    
    # Set to Summer (July 15, 2pm)
    set_date(opener, "2024-07-15T14:00:00")
    
    # Check Summer
    check_status(opener, "Summer")

    # Set to Winter (Jan 15, 4am - coldest)
    set_date(opener, "2024-01-15T04:00:00")
    
    # Check Winter Night
    check_status(opener, "Winter Night")

if __name__ == "__main__":
    main()
