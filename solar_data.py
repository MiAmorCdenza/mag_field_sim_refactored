import requests
import time
import threading

class SolarDataManager:
    def __init__(self):
        self.kp_index = 0.0
        self.running = True
        self.thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self.thread.start()

    def _fetch_loop(self):
        # Fetch data every 5 minutes
        while self.running:
            try:
                # NOAA SWPC 3-day Kp index JSON
                url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    # data is a list of dicts: {"time_tag": "...", "Kp": 2.33, ...}
                    latest = data[-1]
                    self.kp_index = float(latest['Kp'])
                    print(f"[SolarData] Updated Kp index: {self.kp_index} (Time: {latest['time_tag']})")
                else:
                    print(f"[SolarData] Failed to fetch data. Status code: {response.status_code}")
            except Exception as e:
                print(f"[SolarData] Error fetching solar data: {e}")
            
            # Sleep for 5 minutes (300 seconds)
            time.sleep(300)

    def get_kp_index(self):
        return self.kp_index
