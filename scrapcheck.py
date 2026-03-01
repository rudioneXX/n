import asyncio
import aiohttp
import aiofiles
import ipaddress
import os
import time
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from aiohttp_socks import ProxyConnector
print("SCRIPT STARTED", flush=True)
# ================= CONFIG =================

TIMEOUT = 8
MAX_WORKERS = 120
CONCURRENCY = 200

CHECK_URL_HTTP = "http://httpbin.org/ip"
CHECK_URL_SOCKS = "http://icanhazip.com"

# ================= SOURCES =================

SOURCES = [
    # HTTP / HTTPS
    ("http", "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/master/http.txt"),
    ("http", "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/master/https.txt"),
    ("http", "https://www.free-proxy-list.net/anonymous-proxy.txt"),
    ("http", "https://www.free-proxy-list.net/uk-proxy.txt"),
    ("http", "https://www.free-proxy-list.net/us-proxy.txt"),
    ("http", "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt"),
    ("http", "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/https.txt"),
    ("http", "https://raw.githubusercontent.com/mmpx12/proxy-list/refs/heads/master/http.txt"),
    ("http", "https://raw.githubusercontent.com/mmpx12/proxy-list/refs/heads/master/https.txt"),
    ("http", "https://www.proxyrack.com/free-proxy-list?format=txt"),
    ("http", "https://free-proxy-list.net/?page=1&uptime=100&sort=uptime&order=desc&type=http"),
    ("http", "https://geonode.com/free-proxy-list?protocol=http#list"),
    ("http", "https://proxylist.download/api/proxylist.txt?type=http",
    ("http", "https://raw.githubusercontent.com/jundymek/free-proxy/master/free-proxy.txt"),
    ("http", "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt"),
    ("http", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt"),
    ("http", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"),
    ("http", "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt"),

    # SOCKS4
    ("socks4", "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/master/socks4.txt"),
    ("socks4", "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks4.txt"),
    ("socks4", "https://proxylist.download/api/proxylist.txt?type=socks4"),
    ("socks4", "https://raw.githubusercontent.com/mmpx12/proxy-list/refs/heads/master/socks4.txt"),

    # SOCKS5
    ("socks5", "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/master/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks5.txt"),
    ("socks5", "https://proxylist.download/api/proxylist.txt?type=socks5"),
    ("socks5", "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"),
    ("socks5", "https://raw.githubusercontent.com/mmpx12/proxy-list/refs/heads/master/socks5.txt")
]

# ================= SCRAPING =================

def fetch_source(p_type, url):
    found = set()
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return p_type, found

        text = r.text.replace("\ufeff", "")

        if "<" in text and ">" in text:
            text = BeautifulSoup(text, "lxml").get_text()

        for line in text.splitlines():
            line = line.strip()
            if line and ":" in line:
                found.add(line)

    except:
        pass

    return p_type, found


def scrape_proxies():
    proxies = {"http": set(), "socks4": set(), "socks5": set()}
    print(f"[+] Scraping {len(SOURCES)} sources...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_source, p_type, url) for p_type, url in SOURCES]

        for future in concurrent.futures.as_completed(futures):
            p_type, found = future.result()
            proxies[p_type].update(found)

    print(
        f"[✓] Scraped {len(proxies['http'])} HTTP | "
        f"{len(proxies['socks4'])} SOCKS4 | "
        f"{len(proxies['socks5'])} SOCKS5"
    )

    return proxies

# ================= PROXY CHECK =================

async def check_proxy(proxy, p_type):
    for attempt in range(2):  # 1 retry
        try:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)

            if p_type == "http":
                connector = aiohttp.TCPConnector(ssl=False)
                proxy_url = f"http://{proxy}"
                target_url = CHECK_URL_HTTP
            else:
                connector = ProxyConnector.from_url(f"{p_type}://{proxy}")
                proxy_url = None
                target_url = CHECK_URL_SOCKS

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:

                async with session.get(target_url, proxy=proxy_url) as resp:
                    if resp.status != 200:
                        continue

                    if p_type == "http":
                        data = await resp.json()
                        if "origin" in data:
                            return proxy
                    else:
                        text = await resp.text()
                        try:
                            ipaddress.ip_address(text.strip())
                            return proxy
                        except ValueError:
                            continue

        except:
            if attempt == 1:
                return None

    return None

# ================= PROCESS PROXIES =================

async def process_proxies(proxy_list, output_file, p_type):
    print(f"[+] Checking {len(proxy_list)} {p_type} proxies...")

    valid = []
    semaphore = asyncio.Semaphore(CONCURRENCY)
    start = time.time()

    async def bounded(proxy):
        async with semaphore:
            return await check_proxy(proxy, p_type)

    tasks = [bounded(p) for p in proxy_list]

    for i, future in enumerate(asyncio.as_completed(tasks), 1):
        result = await future
        if result:
            valid.append(result)

        if i % 50 == 0 or i == len(proxy_list):
            elapsed = time.time() - start
            print(
                f"  Checked {i}/{len(proxy_list)} | "
                f"Live: {len(valid)} | "
                f"{elapsed:.1f}s",
                end="\r",
            )

    os.makedirs("checked", exist_ok=True)

    async with aiofiles.open(output_file, "w") as f:
        for p in sorted(valid):
            await f.write(p + "\n")

    print(f"\n[✓] {len(valid)} live {p_type} proxies saved to {output_file}")
    return len(valid)

# ================= MAIN =================

async def main():
    proxies = scrape_proxies()

    os.makedirs("scraped", exist_ok=True)

    # Save scraped proxies
    for p_type in proxies:
        with open(f"scraped/{p_type}_proxies.txt", "w") as f:
            for proxy in proxies[p_type]:
                f.write(proxy + "\n")

    print("[✓] Scraped proxies saved.\n")

    live_http = await process_proxies(proxies["http"], "checked/http_live.txt", "http")
    live_socks4 = await process_proxies(proxies["socks4"], "checked/socks4_live.txt", "socks4")
    live_socks5 = await process_proxies(proxies["socks5"], "checked/socks5_live.txt", "socks5")

    print(f"\nSummary: HTTP={live_http}, SOCKS4={live_socks4}, SOCKS5={live_socks5}")

if __name__ == "__main__":
    asyncio.run(main())
