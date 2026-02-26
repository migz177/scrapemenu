"""
GrabFood Menu Scraper — Streamlit App
======================================
UI sederhana: user input satu atau banyak URL GrabFood → scrape → download Excel
Fitur:
  - Batch multi-URL (satu URL per baris)
  - Nama restoran diambil otomatis dari halaman
  - Output Excel: 1 sheet per restoran + sheet SUMMARY
"""

import io
import time
import re

import streamlit as st
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.utils import get_column_letter

from selenium import webdriver
from selenium.webdriver.common.by import By


# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="GrabFood Menu Scraper",
    page_icon="🍔",
    layout="centered",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-title {
        text-align: center; font-size: 2.2rem; font-weight: 700;
        color: #00b14f; margin-bottom: 0.2rem;
    }
    .sub-title {
        text-align: center; font-size: 1rem;
        color: #555; margin-bottom: 2rem;
    }
    .info-box {
        background: #f0fdf4; border-left: 4px solid #00b14f;
        border-radius: 6px; padding: 0.8rem 1.2rem;
        margin-bottom: 1.5rem; font-size: 0.9rem; color: #166534;
    }
    .resto-header {
        background: #f8f9fa; border-radius: 8px;
        padding: 0.6rem 1rem; margin: 1rem 0 0.4rem 0;
        font-weight: 600; font-size: 1rem; color: #111;
        border-left: 4px solid #00b14f;
    }
    .stat-card {
        background: #f8f9fa; border-radius: 10px;
        padding: 1rem 1.2rem; text-align: center;
        border: 1px solid #e9ecef;
    }
    .stat-card .label {
        font-size: 0.75rem; color: #888; font-weight: 500;
        text-transform: uppercase; letter-spacing: 0.05em;
    }
    .stat-card .value {
        font-size: 1.3rem; font-weight: 700;
        color: #00b14f; margin-top: 0.2rem;
    }

    div[data-testid="stButton"] > button {
        background: #00b14f; color: white; border: none;
        border-radius: 8px; padding: 0.6rem 2rem;
        font-size: 1rem; font-weight: 600; width: 100%;
    }
    div[data-testid="stButton"] > button:hover { background: #009942; }

    div[data-testid="stDownloadButton"] > button {
        background: #1d4ed8; color: white; border: none;
        border-radius: 8px; padding: 0.6rem 2rem;
        font-size: 1rem; font-weight: 600; width: 100%;
    }
    div[data-testid="stDownloadButton"] > button:hover { background: #1e40af; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SELENIUM: DRIVER
# ─────────────────────────────────────────────
def setup_driver():
    import os
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # ── Cari binary Chrome/Chromium (Linux untuk Streamlit Cloud) ────────────
    CHROME_BINS = [
        "/usr/bin/chromium-browser",       # Ubuntu (Streamlit Cloud)
        "/usr/bin/chromium",               # beberapa distro Linux
        "/usr/bin/google-chrome",          # Chrome di Linux
        "/usr/bin/google-chrome-stable",
    ]
    for path in CHROME_BINS:
        if os.path.exists(path):
            options.binary_location = path
            break

    # ── Cari chromedriver (Linux untuk Streamlit Cloud) ──────────────────────
    CHROMEDRIVER_BINS = [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
        "/usr/lib/chromium/chromedriver",
    ]
    service = None
    for path in CHROMEDRIVER_BINS:
        if os.path.exists(path):
            service = Service(executable_path=path)
            break

    if service:
        return webdriver.Chrome(service=service, options=options)
    # Fallback: biarkan Selenium cari chromedriver sendiri (mode lokal)
    return webdriver.Chrome(options=options)


# ─────────────────────────────────────────────
# SELENIUM: AMBIL NAMA RESTORAN
# ─────────────────────────────────────────────
def get_restaurant_name(driver):
    """
    Coba ambil nama restoran dari elemen heading,
    fallback ke <title> halaman.
    """
    selectors = [
        '[class*="restaurantName"]',
        '[class*="headerName"]',
        '[class*="restaurant-name"]',
        'h1',
    ]
    for sel in selectors:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, sel)
            name = elem.text.strip()
            if name:
                return name
        except Exception:
            continue

    # Fallback: title tag  →  "Nama Restoran | GrabFood"
    try:
        title = driver.title
        if "|" in title:
            name = title.split("|")[0].strip()
        elif "-" in title:
            name = title.split("-")[0].strip()
        else:
            name = title.strip()
        if name:
            return name
    except Exception:
        pass

    return "Restoran"


# ─────────────────────────────────────────────
# SELENIUM: SCROLL
# ─────────────────────────────────────────────
def scroll_and_load_menus(driver, max_scrolls=12, progress_cb=None):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0
    no_change_count = 0

    while scroll_count < max_scrolls:
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(4)
        new_height = driver.execute_script("return document.body.scrollHeight")

        if new_height == last_height:
            no_change_count += 1
            if no_change_count >= 3:
                break
        else:
            no_change_count = 0

        last_height = new_height
        scroll_count += 1
        if progress_cb:
            progress_cb(scroll_count, max_scrolls)

    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(2)


# ─────────────────────────────────────────────
# SELENIUM: EXTRACT HARGA
# ─────────────────────────────────────────────
def extract_price(price_text):
    if not price_text:
        return None
    digits = re.sub(r'[^\d]', '', price_text)
    try:
        return int(digits) if digits else None
    except Exception:
        return None


# ─────────────────────────────────────────────
# SELENIUM: SCRAPE MENU
# ─────────────────────────────────────────────
def scrape_menu(driver, url, progress_cb=None):
    """
    Returns (resto_name, menu_list)
    menu_list: list of dict {'Nama Menu', 'Deskripsi', 'Harga (Rp)', 'Harga'}
    """
    driver.get(url)
    time.sleep(8)

    # Ambil nama restoran setelah halaman pertama load
    resto_name = get_restaurant_name(driver)

    scroll_and_load_menus(driver, max_scrolls=12, progress_cb=progress_cb)

    # Coba selector utama, fallback ke ant-row
    menu_items = driver.find_elements(By.CSS_SELECTOR, 'div.ant-row[class*="menuItem"]')
    if not menu_items:
        menu_items = driver.find_elements(By.CSS_SELECTOR, 'div.ant-row')

    if not menu_items:
        return resto_name, []

    hasil = []
    for item in menu_items:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
            time.sleep(0.05)

            # ── Nama menu ──────────────────────────────
            menu_name = ''
            try:
                elem = item.find_element(By.CSS_SELECTOR, '[class*="itemNameTitle"]')
                menu_name = elem.text.strip()
            except Exception:
                try:
                    elem = item.find_element(By.CSS_SELECTOR, '[class*="itemNameDescription"]')
                    menu_name = elem.text.split('\n')[0].strip()
                except Exception:
                    ft = item.text
                    if ft:
                        menu_name = ft.split('\n')[0].strip()
            if not menu_name:
                continue

            # ── Deskripsi ──────────────────────────────
            description = ''
            try:
                elem = item.find_element(By.CSS_SELECTOR, '[class*="itemNameDescription"]')
                lines = elem.text.split('\n')
                if len(lines) > 1:
                    description = ' '.join(lines[1:]).strip()
            except Exception:
                ft = item.text
                lines = [l for l in ft.split('\n') if l.strip()]
                if len(lines) > 1:
                    description = ' '.join(lines[1:]).strip()
            description = description[:200]

            # ── Harga ──────────────────────────────────
            price = None
            try:
                elem = item.find_element(By.CSS_SELECTOR, '[class*="discountedPrice"]')
                price = extract_price(elem.text.strip())
            except Exception:
                try:
                    elem = item.find_element(By.CSS_SELECTOR, '[class*="itemPrice"]')
                    price = extract_price(elem.text.strip())
                except Exception:
                    for line in item.text.split('\n'):
                        if re.search(r'\d', line):
                            p = extract_price(line)
                            if p and p > 1000:
                                price = p
                                break

            hasil.append({
                'Nama Menu': menu_name,
                'Deskripsi': description,
                'Harga (Rp)': price,
                'Harga': f"Rp {price:,}" if price else 'N/A',
            })
        except Exception:
            continue

    return resto_name, hasil


# ─────────────────────────────────────────────
# HAPUS DUPLIKAT
# ─────────────────────────────────────────────
def remove_duplicates(menu_list):
    seen = set()
    unique = []
    for item in menu_list:
        key = item['Nama Menu'].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ─────────────────────────────────────────────
# EXCEL BUILDER (multi-sheet)
# ─────────────────────────────────────────────
THIN = Side(style="thin", color="000000")
BLACK_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GREEN_FILL = PatternFill("solid", fgColor="00b14f")
GRAY_FILL = PatternFill("solid", fgColor="D9D9D9")


def auto_fit_columns(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                cell_len = len(str(cell.value)) if cell.value is not None else 0
                max_len = max(max_len, cell_len)
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 70)


def apply_borders(ws):
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            cell.border = BLACK_BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def style_header(ws, header_row=1, fill=GREEN_FILL):
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill


def safe_sheet_name(name, existing_names):
    """Buat nama sheet yang valid (<= 31 karakter, tidak duplikat)."""
    name = re.sub(r'[\\/*?:\[\]]', '', name)[:31]
    if not name:
        name = "Sheet"
    base = name
    counter = 1
    while name in existing_names:
        suffix = f"_{counter}"
        name = base[:31 - len(suffix)] + suffix
        counter += 1
    return name


def build_excel(results):
    """
    results: list of (resto_name, url, menu_list)
    Returns bytes dari file Excel.
    """
    output = io.BytesIO()

    summary_rows = []
    sheet_names = []

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for resto_name, url, menu_list in results:
            df = pd.DataFrame(menu_list)[['Nama Menu', 'Deskripsi', 'Harga']]
            sheet_name = safe_sheet_name(resto_name, sheet_names)
            sheet_names.append(sheet_name)
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)

            prices = [m['Harga (Rp)'] for m in menu_list if m['Harga (Rp)']]
            summary_rows.append({
                'Restoran': resto_name,
                'URL': url,
                'Total Menu': len(menu_list),
                'Rata-rata Harga': f"Rp {sum(prices)//len(prices):,}" if prices else 'N/A',
                'Harga Terendah': f"Rp {min(prices):,}" if prices else 'N/A',
                'Harga Tertinggi': f"Rp {max(prices):,}" if prices else 'N/A',
            })

        # Sheet SUMMARY
        df_summary = pd.DataFrame(summary_rows)
        df_summary.to_excel(writer, sheet_name="SUMMARY", index=False)

    output.seek(0)
    wb = load_workbook(output)

    # ── Styling per sheet restoran ────────────────────────────────────────────
    for i, (resto_name, url, menu_list) in enumerate(results):
        sheet_name = sheet_names[i]
        ws = wb[sheet_name]

        ws["A1"] = "URL"
        ws["B1"] = url
        ws["A1"].font = Font(bold=True)

        apply_borders(ws)
        style_header(ws, header_row=3)            # baris 3 = header df (startrow=2)
        auto_fit_columns(ws)
        ws.freeze_panes = "A4"

    # ── Styling SUMMARY ───────────────────────────────────────────────────────
    ws_sum = wb["SUMMARY"]
    apply_borders(ws_sum)
    style_header(ws_sum, header_row=1, fill=GRAY_FILL)
    # Override font color ke hitam untuk header abu-abu
    for cell in ws_sum[1]:
        cell.font = Font(bold=True, color="000000")
    auto_fit_columns(ws_sum)
    ws_sum.freeze_panes = "A2"

    # Pindahkan SUMMARY ke posisi pertama
    wb.move_sheet("SUMMARY", offset=-len(wb.sheetnames) + 1)

    final = io.BytesIO()
    wb.save(final)
    final.seek(0)
    return final.getvalue()


# ─────────────────────────────────────────────
# STAT CARD HTML
# ─────────────────────────────────────────────
def stat_card(label, value, small=False):
    font_size = "0.95rem" if small else "1.3rem"
    return f"""
    <div class="stat-card">
        <div class="label">{label}</div>
        <div class="value" style="font-size:{font_size}">{value}</div>
    </div>"""


# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
def main():
    st.markdown('<div class="main-title">GrabFood Menu Scraper</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Masukkan satu atau beberapa link restoran GrabFood '
        'dan dapatkan daftar menu dalam format Excel</div>',
        unsafe_allow_html=True
    )

    st.markdown("""
    <div class="info-box">
        📌 <strong>Cara pakai:</strong> Tempel satu atau beberapa URL GrabFood (satu URL per baris),
        lalu klik <strong>Mulai Scraping</strong>.<br>
        ⏱️ Setiap restoran membutuhkan sekitar 1–3 menit tergantung jumlah menu.
    </div>
    """, unsafe_allow_html=True)

    urls_input = st.text_area(
        "🔗 Link Restoran GrabFood (satu URL per baris)",
        placeholder="https://food.grab.com/id/id/restaurant/...\nhttps://food.grab.com/id/id/restaurant/...",
        height=130,
    )

    col_btn, _ = st.columns([1, 2])
    with col_btn:
        run_btn = st.button("🚀 Mulai Scraping")

    if not run_btn:
        return

    # ── Validasi input ────────────────────────────────────────────────────────
    raw_urls = [u.strip() for u in urls_input.strip().splitlines() if u.strip()]
    if not raw_urls:
        st.error("⚠️ Masukkan minimal satu URL.")
        return

    invalid = [u for u in raw_urls if "grab.com" not in u]
    if invalid:
        st.warning(f"⚠️ URL berikut mungkin bukan URL GrabFood: {', '.join(invalid)}")

    # ── Progress containers ───────────────────────────────────────────────────
    overall_text = st.empty()
    overall_bar = st.progress(0)
    detail_text = st.empty()

    results = []          # list of (resto_name, url, menu_list)
    failed_urls = []

    driver = None
    try:
        overall_text.info("🌐 Membuka browser...")
        driver = setup_driver()
        total = len(raw_urls)

        for idx, url in enumerate(raw_urls):
            overall_text.info(f"🔄 Scraping restoran **{idx + 1} / {total}**...")
            overall_bar.progress(int(idx / total * 100))

            def scroll_progress(cur, mx, _idx=idx, _total=total):
                inner_pct = int((cur / mx) * 80)
                outer_pct = int((_idx / _total * 100) + (inner_pct / _total))
                overall_bar.progress(min(outer_pct, 99))
                detail_text.caption(f"  ↳ Scroll {cur}/{mx} untuk memuat semua menu...")

            try:
                detail_text.caption("  ↳ Membuka halaman...")
                resto_name, menu_list = scrape_menu(driver, url, progress_cb=scroll_progress)
                menu_list = remove_duplicates(menu_list)
                results.append((resto_name, url, menu_list))
                detail_text.caption(f"  ✅ {resto_name} — {len(menu_list)} item berhasil di-scrape")
            except Exception as e:
                failed_urls.append(url)
                detail_text.caption(f"  ❌ Gagal: {e}")

        overall_bar.progress(100)
        overall_text.success(f"✅ Selesai! {len(results)}/{total} restoran berhasil di-scrape.")

    except Exception as e:
        st.error(f"❌ Error saat membuka browser: {e}")
        return
    finally:
        if driver:
            driver.quit()

    if failed_urls:
        st.warning("⚠️ URL berikut gagal di-scrape:\n" + "\n".join(f"- {u}" for u in failed_urls))

    if not results:
        st.error("❌ Tidak ada data yang berhasil di-scrape.")
        return

    # ── Ringkasan per restoran ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Hasil Scraping")

    for resto_name, url, menu_list in results:
        st.markdown(f'<div class="resto-header">🏪 {resto_name}</div>', unsafe_allow_html=True)

        prices = [m['Harga (Rp)'] for m in menu_list if m['Harga (Rp)']]
        avg = f"Rp {sum(prices)//len(prices):,}" if prices else "N/A"
        low = f"Rp {min(prices):,}" if prices else "N/A"
        high = f"Rp {max(prices):,}" if prices else "N/A"

        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(stat_card("Total Menu", len(menu_list)), unsafe_allow_html=True)
        with c2: st.markdown(stat_card("Rata-rata", avg, small=True), unsafe_allow_html=True)
        with c3: st.markdown(stat_card("Terendah", low, small=True), unsafe_allow_html=True)
        with c4: st.markdown(stat_card("Tertinggi", high, small=True), unsafe_allow_html=True)

        with st.expander(f"📋 Preview menu {resto_name}"):
            df = pd.DataFrame(menu_list)[['Nama Menu', 'Deskripsi', 'Harga']]
            st.dataframe(df, use_container_width=True, height=250)

    # ── Build & download Excel ────────────────────────────────────────────────
    st.markdown("---")
    with st.spinner("📊 Membuat file Excel..."):
        excel_bytes = build_excel(results)

    n = len(results)
    filename = "grabfood_menu.xlsx" if n == 1 else f"grabfood_menu_{n}_resto.xlsx"

    st.download_button(
        label=f"⬇️ Download Excel ({n} restoran)",
        data=excel_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
