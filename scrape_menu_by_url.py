"""
Script Scraping Menu GrabFood per Restoran
==========================================
Input  : URL restoran GrabFood (langsung dari argumen atau input interaktif)
Output : List semua menu beserta harga (ditampilkan di terminal & disimpan ke CSV/JSON)

Cara pakai:
  python scrape_menu_by_url.py
  python scrape_menu_by_url.py "https://food.grab.com/id/id/restaurant/xxx-delivery/RESTOID"
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import re
import json
import csv
import sys
from datetime import datetime


# ─────────────────────────────────────────────
# SETUP DRIVER
# ─────────────────────────────────────────────
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


# ─────────────────────────────────────────────
# SCROLL HALAMAN UNTUK LOAD SEMUA MENU
# ─────────────────────────────────────────────
def scroll_and_load_menus(driver, max_scrolls=10):
    """Scroll ke bawah sampai tidak ada konten baru atau mencapai batas scroll."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0
    no_change_count = 0

    while scroll_count < max_scrolls:
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(5)

        new_height = driver.execute_script("return document.body.scrollHeight")

        if new_height == last_height:
            no_change_count += 1
            if no_change_count >= 3:
                print(f"  ✓ Sudah sampai bawah setelah {scroll_count} scroll")
                break
        else:
            no_change_count = 0

        last_height = new_height
        scroll_count += 1

    # Kembali ke atas agar semua elemen ter-render
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(3)


# ─────────────────────────────────────────────
# EXTRACT HARGA DARI TEXT
# ─────────────────────────────────────────────
def extract_price(price_text):
    """Ekstrak angka harga dari string teks."""
    if not price_text:
        return None
    price_digits = re.sub(r'[^\d]', '', price_text)
    try:
        return int(price_digits) if price_digits else None
    except Exception:
        return None


# ─────────────────────────────────────────────
# MAIN SCRAPING FUNCTION
# ─────────────────────────────────────────────
def scrape_menu(driver, url):
    """
    Scrape semua menu dan harga dari URL restoran GrabFood.
    
    Returns:
        list of dict: [{'name': ..., 'price': ..., 'price_formatted': ..., 'description': ...}, ...]
    """
    print(f"\nMembuka URL: {url}")
    driver.get(url)
    time.sleep(3)

    print("  Scrolling untuk memuat semua menu...")
    scroll_and_load_menus(driver)

    # Coba selector utama
    menu_items = driver.find_elements(By.CSS_SELECTOR, 'div.ant-row[class*="menuItem"]')

    if not menu_items:
        print("  Mencoba selector alternatif...")
        menu_items = driver.find_elements(By.CSS_SELECTOR, 'div.ant-row')

    if not menu_items:
        print("  ✗ Tidak ada item menu ditemukan.")
        return []

    print(f"  Ditemukan {len(menu_items)} elemen menu, mengekstrak data...")

    hasil = []

    for item in menu_items:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
            time.sleep(0.1)

            # ── Ambil nama menu ───────────────────────
            menu_name = ''
            try:
                name_elem = item.find_element(By.CSS_SELECTOR, '[class*="itemNameTitle"]')
                menu_name = name_elem.text.strip()
            except Exception:
                try:
                    name_elem = item.find_element(By.CSS_SELECTOR, '[class*="itemNameDescription"]')
                    menu_name = name_elem.text.split('\n')[0].strip()
                except Exception:
                    full_text = item.text
                    if full_text:
                        menu_name = full_text.split('\n')[0].strip()

            if not menu_name:
                continue

            # ── Ambil deskripsi ───────────────────────
            description = ''
            try:
                desc_elem = item.find_element(By.CSS_SELECTOR, '[class*="itemNameDescription"]')
                desc_lines = desc_elem.text.split('\n')
                if len(desc_lines) > 1:
                    description = ' '.join(desc_lines[1:]).strip()
            except Exception:
                full_text = item.text
                lines = [l for l in full_text.split('\n') if l.strip()]
                if len(lines) > 1:
                    description = ' '.join(lines[1:]).strip()

            description = description[:200]

            # ── Ambil harga ───────────────────────────
            price = None
            price_text = ''

            try:
                # Cek harga diskon dulu
                discount_elem = item.find_element(By.CSS_SELECTOR, '[class*="discountedPrice"]')
                price_text = discount_elem.text.strip()
                price = extract_price(price_text)
            except Exception:
                try:
                    price_elem = item.find_element(By.CSS_SELECTOR, '[class*="itemPrice"]')
                    price_text = price_elem.text.strip()
                    price = extract_price(price_text)
                except Exception:
                    # Fallback: cari angka di teks item
                    full_text = item.text
                    for line in full_text.split('\n'):
                        if re.search(r'\d', line):
                            potential_price = extract_price(line)
                            if potential_price and potential_price > 1000:
                                price = potential_price
                                price_text = line
                                break

            menu_data = {
                'name': menu_name,
                'description': description,
                'price': price,
                'price_formatted': f"Rp {price:,}" if price else 'N/A'
            }
            hasil.append(menu_data)

        except Exception:
            continue

    return hasil


# ─────────────────────────────────────────────
# HAPUS DUPLIKAT
# ─────────────────────────────────────────────
def remove_duplicates(menu_list):
    """Hapus item menu yang memiliki nama sama (case-insensitive), pertahankan yang pertama."""
    seen = set()
    unique = []
    for item in menu_list:
        key = item['name'].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    removed = len(menu_list) - len(unique)
    if removed:
        print(f"  ✓ Duplikat dihapus: {removed} item (dari {len(menu_list)} → {len(unique)} item unik)")
    return unique


# ─────────────────────────────────────────────
# TAMPILKAN HASIL
# ─────────────────────────────────────────────
def print_results(menu_list):
    """Cetak hasil scraping ke terminal dalam format tabel."""
    if not menu_list:
        print("\n  Tidak ada menu yang berhasil di-scrape.")
        return

    print(f"\n{'='*70}")
    print(f"  DAFTAR MENU ({len(menu_list)} item)")
    print(f"{'='*70}")
    print(f"{'No.':<5} {'Nama Menu':<45} {'Harga':>12}")
    print(f"{'-'*70}")

    for idx, menu in enumerate(menu_list, 1):
        name = menu['name'][:43]
        price_str = menu['price_formatted']
        print(f"{idx:<5} {name:<45} {price_str:>12}")

    print(f"{'='*70}")

    prices = [m['price'] for m in menu_list if m['price']]
    if prices:
        avg = sum(prices) // len(prices)
        print(f"  Total item dengan harga : {len(prices)}")
        print(f"  Rata-rata harga         : Rp {avg:,}")
        print(f"  Harga terendah          : Rp {min(prices):,}")
        print(f"  Harga tertinggi         : Rp {max(prices):,}")
    print(f"{'='*70}\n")


# ─────────────────────────────────────────────
# SIMPAN KE FILE
# ─────────────────────────────────────────────
def save_results(menu_list, url):
    """Simpan hasil ke file JSON dan CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"menu_result_{timestamp}"

    # JSON
    json_path = f"{base_name}.json"
    output = {
        'url': url,
        'scraped_at': datetime.now().isoformat(),
        'total_items': len(menu_list),
        'menus': menu_list
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Disimpan ke: {json_path}")

    # CSV
    '''
    csv_path = f"{base_name}.csv"
    if menu_list:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'price', 'price_formatted', 'description'])
            writer.writeheader()
            writer.writerows(menu_list)
        print(f"  ✓ Disimpan ke: {csv_path}")
    '''
    return json_path


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    # Ambil URL dari argumen command line atau input interaktif
    if len(sys.argv) > 1:
        url = sys.argv[1].strip()
    else:
        print("=" * 60)
        print("  GrabFood Menu Scraper")
        print("=" * 60)
        url = input("  Masukkan URL restoran GrabFood:\n  > ").strip()

    if not url:
        print("ERROR: URL tidak boleh kosong.")
        sys.exit(1)

    if "grab.com" not in url:
        print("WARNING: URL tidak seperti URL GrabFood. Lanjutkan saja? (y/n)")
        if input("  > ").strip().lower() != 'y':
            sys.exit(0)

    driver = setup_driver()
    try:
        menu_list = scrape_menu(driver, url)
        menu_list = remove_duplicates(menu_list)
        print_results(menu_list)

        if menu_list:
            save = input("Simpan hasil ke file? (y/n): ").strip().lower()
            if save == 'y':
                save_results(menu_list, url)
        else:
            print("Tidak ada data yang disimpan.")

    finally:
        print("\nMenutup browser...")
        driver.quit()


if __name__ == '__main__':
    main()
