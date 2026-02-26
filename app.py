"""
GrabFood Menu Scraper — Streamlit App
======================================
UI sederhana: user input URL GrabFood → scrape → download Excel
"""

import io
import time
import re
import threading

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
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main-title {
        text-align: center;
        font-size: 2.2rem;
        font-weight: 700;
        color: #00b14f;
        margin-bottom: 0.2rem;
    }

    .sub-title {
        text-align: center;
        font-size: 1rem;
        color: #555;
        margin-bottom: 2rem;
    }

    .info-box {
        background: #f0fdf4;
        border-left: 4px solid #00b14f;
        border-radius: 6px;
        padding: 0.8rem 1.2rem;
        margin-bottom: 1.5rem;
        font-size: 0.9rem;
        color: #166534;
    }

    .stat-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
        border: 1px solid #e9ecef;
    }

    .stat-card .label {
        font-size: 0.78rem;
        color: #888;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .stat-card .value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #00b14f;
        margin-top: 0.2rem;
    }

    div[data-testid="stButton"] > button {
        background: #00b14f;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 2rem;
        font-size: 1rem;
        font-weight: 600;
        width: 100%;
        transition: background 0.2s;
    }

    div[data-testid="stButton"] > button:hover {
        background: #009942;
    }

    div[data-testid="stDownloadButton"] > button {
        background: #1d4ed8;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 2rem;
        font-size: 1rem;
        font-weight: 600;
        width: 100%;
    }

    div[data-testid="stDownloadButton"] > button:hover {
        background: #1e40af;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SELENIUM HELPERS
# ─────────────────────────────────────────────
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


def scroll_and_load_menus(driver, max_scrolls=10, progress_cb=None):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0
    no_change_count = 0

    while scroll_count < max_scrolls:
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(3)

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


def extract_price(price_text):
    if not price_text:
        return None
    price_digits = re.sub(r'[^\d]', '', price_text)
    try:
        return int(price_digits) if price_digits else None
    except Exception:
        return None


def scrape_menu(driver, url, progress_cb=None):
    driver.get(url)
    time.sleep(4)

    scroll_and_load_menus(driver, max_scrolls=12, progress_cb=progress_cb)

    menu_items = driver.find_elements(By.CSS_SELECTOR, 'div.ant-row[class*="menuItem"]')
    if not menu_items:
        menu_items = driver.find_elements(By.CSS_SELECTOR, 'div.ant-row')

    if not menu_items:
        return []

    hasil = []
    for item in menu_items:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
            time.sleep(0.05)

            # Nama menu
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

            # Deskripsi
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

            # Harga
            price = None
            price_text = ''
            try:
                discount_elem = item.find_element(By.CSS_SELECTOR, '[class*="discountedPrice"]')
                price_text = discount_elem.text.strip()
                price = extract_price(price_text)
            except Exception:
                try:
                    price_elem = item.find_element(By.CSS_SELECTOR, '[class*="itemPrice"]')
                    price_text = price_elem.text.strip()
                    price = extract_price(price_text)
                except Exception:
                    full_text = item.text
                    for line in full_text.split('\n'):
                        if re.search(r'\d', line):
                            potential_price = extract_price(line)
                            if potential_price and potential_price > 1000:
                                price = potential_price
                                price_text = line
                                break

            hasil.append({
                'Nama Menu': menu_name,
                'Deskripsi': description,
                'Harga (Rp)': price,
                'Harga': f"Rp {price:,}" if price else 'N/A',
            })

        except Exception:
            continue

    return hasil


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
# EXCEL BUILDER
# ─────────────────────────────────────────────
THIN = Side(style="thin", color="000000")
BLACK_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GREEN_FILL = PatternFill("solid", fgColor="00b14f")


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


def style_header(ws, header_row=1):
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = GREEN_FILL


def build_excel(menu_list, url):
    """Build in-memory Excel file and return bytes."""
    df = pd.DataFrame(menu_list)
    df = df[['Nama Menu', 'Deskripsi', 'Harga']]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Menu", index=False, startrow=2)

    output.seek(0)
    wb = load_workbook(output)
    ws = wb["Menu"]

    # URL info di baris 1
    ws["A1"] = "URL"
    ws["B1"] = url
    ws["A1"].font = Font(bold=True)

    apply_borders(ws)
    style_header(ws, header_row=3)
    auto_fit_columns(ws)
    ws.freeze_panes = "A4"

    final = io.BytesIO()
    wb.save(final)
    final.seek(0)
    return final.getvalue()


# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
def main():
    st.markdown('<div class="main-title">GrabFood Menu Scraper</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Masukkan link restoran GrabFood dan dapatkan daftar menu dalam format Excel</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="info-box">
        <strong>Cara pakai:</strong> Tempel link restoran GrabFood (contoh: <code>https://food.grab.com/id/id/restaurant/...</code>),
        lalu klik <strong>Mulai Scraping</strong>. Proses biasanya memakan waktu 1–3 menit tergantung jumlah menu.
    </div>
    """, unsafe_allow_html=True)

    url_input = st.text_input(
        "🔗 Link Restoran GrabFood",
        placeholder="https://food.grab.com/id/id/restaurant/...",
        label_visibility="visible",
    )

    col_btn, _ = st.columns([1, 2])
    with col_btn:
        run_btn = st.button("🚀 Mulai Scraping")

    if run_btn:
        url = url_input.strip()

        if not url:
            st.error("⚠️ URL tidak boleh kosong.")
            return

        if "grab.com" not in url:
            st.warning("⚠️ URL yang dimasukkan bukan URL GrabFood. Pastikan URL sudah benar.")

        # Status placeholders
        status_text = st.empty()
        progress_bar = st.progress(0)

        def scroll_progress(current, total):
            pct = int((current / total) * 60) + 20   # 20–80%
            progress_bar.progress(min(pct, 80))
            status_text.info(f"⏳ Memuat halaman... (scroll {current}/{total})")

        status_text.info("🌐 Membuka halaman GrabFood...")
        progress_bar.progress(5)

        driver = None
        try:
            driver = setup_driver()

            progress_bar.progress(10)
            status_text.info("🔄 Sedang scroll dan memuat semua menu...")

            menu_list = scrape_menu(driver, url, progress_cb=scroll_progress)

            progress_bar.progress(85)
            status_text.info("🧹 Menghapus duplikat...")

            menu_list = remove_duplicates(menu_list)

            progress_bar.progress(90)

            if not menu_list:
                st.error("❌ Tidak ada menu yang berhasil di-scrape. Coba periksa URL atau coba lagi.")
                return

            # Build Excel
            status_text.info("📊 Membuat file Excel...")
            excel_bytes = build_excel(menu_list, url)
            progress_bar.progress(100)

            status_text.success(f"✅ Berhasil! Ditemukan **{len(menu_list)} item menu**.")

            # ── Statistics ───────────────────────────────
            st.markdown("---")
            prices = [m['Harga (Rp)'] for m in menu_list if m['Harga (Rp)']]

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="label">Total Menu</div>
                    <div class="value">{len(menu_list)}</div>
                </div>""", unsafe_allow_html=True)
            with col2:
                avg = f"Rp {sum(prices)//len(prices):,}" if prices else "N/A"
                st.markdown(f"""
                <div class="stat-card">
                    <div class="label">Rata-rata Harga</div>
                    <div class="value" style="font-size:1rem">{avg}</div>
                </div>""", unsafe_allow_html=True)
            with col3:
                low = f"Rp {min(prices):,}" if prices else "N/A"
                st.markdown(f"""
                <div class="stat-card">
                    <div class="label">Harga Terendah</div>
                    <div class="value" style="font-size:1rem">{low}</div>
                </div>""", unsafe_allow_html=True)
            with col4:
                high = f"Rp {max(prices):,}" if prices else "N/A"
                st.markdown(f"""
                <div class="stat-card">
                    <div class="label">Harga Tertinggi</div>
                    <div class="value" style="font-size:1rem">{high}</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")

            # ── Preview table ────────────────────────────
            st.subheader("📋 Preview Menu")
            df_preview = pd.DataFrame(menu_list)[['Nama Menu', 'Deskripsi', 'Harga']]
            st.dataframe(df_preview, use_container_width=True, height=300)

            # ── Download button ───────────────────────────
            st.markdown("")
            st.download_button(
                label="⬇️ Download Excel",
                data=excel_bytes,
                file_name="grabfood_menu.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        except Exception as e:
            st.error(f"❌ Terjadi error: {e}")
        finally:
            if driver:
                driver.quit()


if __name__ == "__main__":
    main()
