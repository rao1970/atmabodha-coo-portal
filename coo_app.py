import os
import json
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import pandas as pd
import streamlit as st

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Atma Bodha Operations Hub",
    page_icon="🕉️",
    layout="wide",
    initial_sidebar_state="expanded"
)

LEDGER_FILE = "orders_ledger.csv"

# ==========================================
# SAFE SECRETS HELPER (LOCALHOST & CLOUD)
# ==========================================
def get_secret(key: str, default: str = "") -> str:
    """Safely retrieves secrets without crashing on localhost if secrets.toml is missing."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
        return default
    except Exception:
        return default

# ==========================================
# SYNCHRONIZED PRODUCT CATALOG DATA
# (Matches Google Drive 1-to-1)
# ==========================================
CATALOG_DATA = [
    {
        "Code": "01-TD-V68",
        "Product Name": "Traditional Devotional Lyric Videos",
        "Zip_File": "01_TD-V68_Traditional_Devotional_Videos.zip",
        "Format": "Single-image lyric videos (68 MP4 files)",
        "Tracks": 68,
        "Study Guide": "Not Included",
        "Price_INR": 699,
        "Secret_Key": "LINK_01_TD_V68"
    },
    {
        "Code": "02-TD-A68",
        "Product Name": "Traditional Devotional Audio",
        "Zip_File": "02_TD-A68_Traditional_Devotional_Audio.zip",
        "Format": "Traditional devotional audio (68 MP3 files)",
        "Tracks": 68,
        "Study Guide": "Not Included",
        "Price_INR": 499,
        "Secret_Key": "LINK_02_TD_A68"
    },
    {
        "Code": "03-MD-136",
        "Product Name": "Modern Soul Audio",
        "Zip_File": "03_MD-136_Modern_Soul_Audio.zip",
        "Format": "Modern devotional audio tracks (136 MP3 files)",
        "Tracks": 136,
        "Study Guide": "Not Included",
        "Price_INR": 799,
        "Secret_Key": "LINK_03_MD_136"
    },
    {
        "Code": "04-FS-136",
        "Product Name": "World Fusion Audio",
        "Zip_File": "04_FS-136_World_Fusion_Audio.zip",
        "Format": "World fusion-style audio tracks (136 MP3 files)",
        "Tracks": 136,
        "Study Guide": "Not Included",
        "Price_INR": 799,
        "Secret_Key": "LINK_04_FS_136"
    },
    {
        "Code": "05-TCP",
        "Product Name": "Traditional Complete Pack",
        "Zip_File": "05_TCP_Traditional_Complete_Pack.zip",
        "Format": "Audio (02) + Video (01) + Study Guide PDF",
        "Tracks": 136,
        "Study Guide": "Included (PDF)",
        "Price_INR": 999,
        "Secret_Key": "LINK_05_TCP"
    },
    {
        "Code": "06-TAP",
        "Product Name": "Three Audio Styles Pack",
        "Zip_File": "06_TAP_Three_Audio_Styles_Pack.zip",
        "Format": "Traditional (02) + Modern (03) + Fusion (04) + Study Guide PDF",
        "Tracks": 340,
        "Study Guide": "Included (PDF)",
        "Price_INR": 1499,
        "Secret_Key": "LINK_06_TAP"
    },
    {
        "Code": "07-CAC",
        "Product Name": "Complete Atma Bodha Collection",
        "Zip_File": "07_CAC_Complete_Atma_Bodha_Collection.zip",
        "Format": "All Audio (340) + All Videos (68) + Study Guide PDF",
        "Tracks": 408,
        "Study Guide": "Included (PDF)",
        "Price_INR": 1999,
        "Secret_Key": "LINK_07_CAC"
    }
]

# Backward compatibility alias map for older order formats
CODE_ALIASES = {
    "TCP": "05-TCP",
    "05_TCP": "05-TCP",
    "TAP": "06-TAP",
    "06_TAP": "06-TAP",
    "CAC": "07-CAC",
    "07_CAC": "07-CAC",
    "TD-A68": "02-TD-A68",
    "TD_A68": "02-TD-A68",
    "TD-V68": "01-TD-V68",
    "TD_V68": "01-TD-V68",
    "MD-136": "03-MD-136",
    "MD_136": "03-MD-136",
    "FS-136": "04-FS-136",
    "FS_136": "04-FS-136",
}

def resolve_catalog_item(code: str):
    clean = code.strip()
    target_code = CODE_ALIASES.get(clean, clean)
    for item in CATALOG_DATA:
        if item["Code"] == target_code or item["Code"] == clean:
            return item
    return None

# ==========================================
# STORAGE & LEDGER HELPERS
# ==========================================
LEDGER_COLUMNS = [
    "Order_ID", "Timestamp", "Customer_Name", "Customer_Phone", "Customer_Email",
    "Product_Codes", "Total_Amount_INR", "Payment_Mode", "UTR_Number",
    "Status", "Delivery_Timestamp", "Notes"
]

def load_ledger() -> pd.DataFrame:
    if os.path.exists(LEDGER_FILE):
        try:
            df = pd.read_csv(LEDGER_FILE, dtype=str)
            for col in LEDGER_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            return pd.DataFrame(columns=LEDGER_COLUMNS)
    return pd.DataFrame(columns=LEDGER_COLUMNS)

def save_ledger(df: pd.DataFrame):
    df.to_csv(LEDGER_FILE, index=False)

# ==========================================
# TELEGRAM ALERT HELPER
# ==========================================
def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        st.error(f"Telegram Ping Error: {e}")
        return False

# ==========================================
# GMAIL DISPATCH HELPER
# ==========================================
def find_study_guide_pdf():
    candidates = [
        "Atma_Bodha_Study_Guide.pdf",
        r"G:\My Drive\Atma_Bodha_Master_Audio_Pack_Official\Atma_Bodha_Study_Guide.pdf",
        os.path.join(os.path.dirname(__file__), "Atma_Bodha_Study_Guide.pdf")
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def dispatch_delivery_email(sender_email, sender_password, to_email, cust_name, product_codes, download_links):
    if not sender_email or not sender_password:
        return False, "Sender email or password not configured."

    msg = MIMEMultipart()
    msg["From"] = f"Atma Bodha Operations <{sender_email}>"
    msg["To"] = to_email
    msg["Subject"] = "Your Atma Bodha Order Access & Digital Downloads"

    chosen_raw = [c.strip() for c in str(product_codes).split(",") if c.strip()]
    links_lines = []

    for raw in chosen_raw:
        item = resolve_catalog_item(raw)
        if item:
            url = download_links.get(item["Code"], "").strip()
            if not url:
                url = download_links.get(raw, "").strip()
            display_url = url if url else "Link is being provisioned. You will receive an update shortly."
            links_lines.append(f"• {item['Product Name']} ({item['Zip_File']}):\n  👉 Download Link: {display_url}")
        else:
            url = download_links.get(raw, "").strip()
            display_url = url if url else "Link is being provisioned. You will receive an update shortly."
            links_lines.append(f"• {raw}:\n  👉 Download Link: {display_url}")

    links_body = "\n\n".join(links_lines)

    body = f"""Namaste {cust_name},

Thank you for your order. Your digital access details for the Atma Bodha collection are confirmed:

Requested Package(s):
{product_codes}

Direct Cloud Download Links:
{links_body}

Your comprehensive Atma Bodha Study Guide PDF is attached to this email.

Warm regards,
W. Srinivas Rao
Atma Bodha Operations Desk
"""
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF Study Guide
    pdf_path = find_study_guide_pdf()
    if pdf_path:
        try:
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment; filename=Atma_Bodha_Study_Guide.pdf")
            msg.attach(part)
        except Exception as e:
            st.warning(f"Could not attach PDF: {e}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True, "Email dispatched successfully!"
    except Exception as e:
        return False, str(e)

# ==========================================
# SIDEBAR CONFIGURATION
# ==========================================
st.sidebar.markdown("### 📱 Telegram Phone Alerts")
default_token = get_secret("TELEGRAM_BOT_TOKEN", "8836740336:AAE3xjRLK4P_oqK2Ra6dlSImYIWxxxVizLk")
default_chat_id = get_secret("TELEGRAM_CHAT_ID", "5858834506")
bot_token = st.sidebar.text_input("Telegram Bot Token", value=default_token, type="password")
chat_id = st.sidebar.text_input("Telegram Chat ID", value=default_chat_id)

if st.sidebar.button("🔔 Send Test Telegram Ping to Phone"):
    test_msg = f"🔔 <b>Atma Bodha System Ping</b>\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nStatus: System operational!"
    if send_telegram_alert(bot_token, chat_id, test_msg):
        st.sidebar.success("Ping delivered to your phone!")
    else:
        st.sidebar.error("Failed to send ping. Check Bot Token or Chat ID.")

st.sidebar.markdown("---")
st.sidebar.markdown("### ✉️ Gmail Dispatch Settings")
sender_email = st.sidebar.text_input("Sender Gmail", value=get_secret("SENDER_EMAIL", "raomurthy1@gmail.com"))
sender_password = st.sidebar.text_input("Gmail App Password", value=get_secret("SENDER_PASSWORD", "mdik stjy qjdc zres"), type="password")

st.sidebar.markdown("---")
with st.sidebar.expander("📁 Google Drive Delivery Links", expanded=False):
    st.caption("Paste shareable file links directly here or manage them in Secrets:")
    drive_links = {}
    for item in CATALOG_DATA:
        key = item["Code"]
        sec_key = item["Secret_Key"]
        clean_code_var = f"LINK_{key.replace('-', '_')}"
        default_url = get_secret(sec_key, get_secret(clean_code_var, ""))
        drive_links[key] = st.text_input(f"{item['Zip_File']}", value=default_url, key=f"drive_{key}")

st.sidebar.markdown("---")
ledger_df = load_ledger()
st.sidebar.markdown(f"💾 **Storage File:** `{LEDGER_FILE}`")
st.sidebar.markdown(f"**Total records:** {len(ledger_df)}")

# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("🕉️ Atma Bodha Digital COO Operations Hub")
st.caption("Central Operations: Product Catalogue | Enquiries | Telegram Mobile Alerts | Google Drive Delivery | Persistent Ledger")

tabs = st.tabs([
    "📚 Catalogue & Auto-Reply",
    "📝 1. Enquiry Intake",
    "💳 2. Payment Proof & Alert",
    "🛡️ 3. Bank Verification Desk",
    "📦 4. Secure Delivery Desk",
    "📊 5. Operations Ledger"
])

# ------------------------------------------
# TAB 0: CATALOGUE & AUTO-REPLY
# ------------------------------------------
with tabs[0]:
    st.subheader("Approved Product Catalogue (Synchronized with Google Drive)")
    cat_df = pd.DataFrame(CATALOG_DATA)[["Code", "Product Name", "Zip_File", "Format", "Tracks", "Study Guide", "Price_INR"]]
    st.dataframe(cat_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Quick Customer Inquiry Response Templates")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**WhatsApp Greeting & Pricing Outline:**")
        template_inquiry = """Namaste! Thank you for inquiring about the Atma Bodha digital collection.

Here are our top packages:
• 05-TCP - Traditional Complete Pack: 136 tracks (Audio + Video + Study Guide) - ₹999
• 06-TAP - Three Audio Styles Pack: 340 tracks (Devotional, Modern & Fusion) - ₹1,499
• 07-CAC - Complete Atma Bodha Collection: 408 tracks (All Audio, Videos & Study Guide) - ₹1,999

Please let us know your preferred choice, and we will share the UPI payment details immediately."""
        st.text_area("Copy Inquiry Reply", template_inquiry, height=180)

    with c2:
        st.markdown("**Payment Instructions Template:**")
        template_pay = """To confirm your order, please complete the transfer via UPI:

UPI ID: raomurthy1@gmail.com
Amount: ₹[ENTER AMOUNT]

After completing the payment, please share the 12-digit UTR reference number or payment screenshot here. Your download links and Study Guide PDF will be dispatched to your email immediately."""
        st.text_area("Copy Payment Instructions", template_pay, height=180)

# ------------------------------------------
# TAB 1: ENQUIRY INTAKE
# ------------------------------------------
with tabs[1]:
    st.subheader("Customer Enquiry Intake")
    st.caption("Log a new enquiry with customer phone number and multiple requested product codes.")

    with st.form("enquiry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cust_name = st.text_input("Customer Full Name *", placeholder="e.g. Ramesh Kumar")
            cust_phone = st.text_input("Customer Phone / WhatsApp Number *", placeholder="e.g. +91 98765 43210")
        with col2:
            cust_email = st.text_input("Customer Email Address *", placeholder="e.g. customer@gmail.com")

            product_labels = [f"{item['Code']} - {item['Product Name']} (₹{item['Price_INR']})" for item in CATALOG_DATA]
            label_to_code = {f"{item['Code']} - {item['Product Name']} (₹{item['Price_INR']})": item["Code"] for item in CATALOG_DATA}

            selected_labels = st.multiselect(
                "Requested Product Codes (Choose 1, 2, or more) *",
                options=product_labels,
                default=[product_labels[4]]  # Defaults to 05-TCP
            )

        notes = st.text_area("Customer Notes / Referral Source", placeholder="Optional special notes or requests...")
        submit_enquiry = st.form_submit_button("Log Enquiry / Create Order")

    if submit_enquiry:
        if not cust_name.strip() or not cust_email.strip() or not cust_phone.strip() or not selected_labels:
            st.error("Please fill all required fields: Name, Phone, Email, and at least one Product Code.")
        else:
            chosen_codes = [label_to_code[lbl] for lbl in selected_labels]
            chosen_codes_str = ", ".join(chosen_codes)

            est_total = sum(resolve_catalog_item(c)["Price_INR"] for c in chosen_codes if resolve_catalog_item(c))
            order_id = f"AB-{datetime.now().strftime('%y%m%d')}-{len(ledger_df) + 1:03d}"

            new_record = {
                "Order_ID": order_id,
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Customer_Name": cust_name.strip(),
                "Customer_Phone": cust_phone.strip(),
                "Customer_Email": cust_email.strip(),
                "Product_Codes": chosen_codes_str,
                "Total_Amount_INR": str(est_total),
                "Payment_Mode": "Pending",
                "UTR_Number": "",
                "Status": "Pending Payment Proof",
                "Delivery_Timestamp": "",
                "Notes": notes.strip()
            }

            ledger_df = pd.concat([ledger_df, pd.DataFrame([new_record])], ignore_index=True)
            save_ledger(ledger_df)
            st.success(f"Order **{order_id}** created for **{cust_name}** with package(s): **{chosen_codes_str}**!")
            st.info("Switch to Tab 2 to submit payment proof and trigger your mobile Telegram alert.")

# ------------------------------------------
# TAB 2: PAYMENT PROOF & ALERT
# ------------------------------------------
with tabs[2]:
    st.subheader("Payment Proof Submission & Mobile Alert")
    ledger_df = load_ledger()
    pending_payment = ledger_df[ledger_df["Status"] == "Pending Payment Proof"]

    if pending_payment.empty:
        st.info("No orders currently waiting for payment submission. Log an enquiry first in Tab 1.")
    else:
        order_options = [
            f"{row['Order_ID']} | {row['Customer_Name']} | 📞 {row['Customer_Phone']} | 📦 {row['Product_Codes']}"
            for _, row in pending_payment.iterrows()
        ]
        selected_order_option = st.selectbox("Select Pending Order", options=order_options)
        selected_order_id = selected_order_option.split(" | ")[0]
        curr_row = pending_payment[pending_payment["Order_ID"] == selected_order_id].iloc[0]

        with st.form("payment_proof_form"):
            col1, col2 = st.columns(2)
            with col1:
                utr = st.text_input("Transaction UTR / Bank Reference Number *", placeholder="12-digit UPI / IMPS UTR")
                amount = st.text_input("Amount Paid (INR)", value=str(curr_row["Total_Amount_INR"]))
            with col2:
                payment_mode = st.selectbox("Payment Channel", ["UPI / QR Code", "GPay / PhonePe", "Bank NEFT / IMPS", "Other"])
                payment_notes = st.text_input("Payment Remarks", placeholder="e.g. Received on GPay")

            submit_proof = st.form_submit_button("Submit Payment Proof & Ping Telegram")

        if submit_proof:
            if not utr.strip():
                st.error("Please enter a valid Transaction UTR / Reference number.")
            else:
                idx = ledger_df[ledger_df["Order_ID"] == selected_order_id].index[0]
                ledger_df.at[idx, "UTR_Number"] = utr.strip()
                ledger_df.at[idx, "Total_Amount_INR"] = amount.strip()
                ledger_df.at[idx, "Payment_Mode"] = payment_mode
                ledger_df.at[idx, "Status"] = "Pending Bank Verification"
                save_ledger(ledger_df)

                # Send Telegram Alert to Mobile
                alert_text = f"""💰 <b>NEW PAYMENT PROOF RECEIVED</b>
━━━━━━━━━━━━━━━━━━━━
<b>Order ID:</b> {selected_order_id}
<b>Customer:</b> {curr_row['Customer_Name']}
<b>Phone:</b> {curr_row['Customer_Phone']}
<b>Email:</b> {curr_row['Customer_Email']}
<b>Packages:</b> {curr_row['Product_Codes']}
<b>Amount:</b> ₹{amount.strip()}
<b>UTR / Ref:</b> <code>{utr.strip()}</code>
<b>Channel:</b> {payment_mode}
━━━━━━━━━━━━━━━━━━━━
👉 Open Tab 3 (Bank Verification Desk) to authorize delivery!"""

                ping_ok = send_telegram_alert(bot_token, chat_id, alert_text)
                if ping_ok:
                    st.success("Payment proof saved and instant alert sent to your Telegram phone app!")
                else:
                    st.warning("Payment proof saved, but Telegram ping failed. Check Bot Token or Chat ID.")
                st.rerun()

# ------------------------------------------
# TAB 3: BANK VERIFICATION DESK
# ------------------------------------------
with tabs[3]:
    st.subheader("Bank Verification & Authorization Desk")
    ledger_df = load_ledger()
    pending_verify = ledger_df[ledger_df["Status"] == "Pending Bank Verification"]

    if pending_verify.empty:
        st.info("No orders currently waiting for bank verification.")
    else:
        st.write(f"**{len(pending_verify)} order(s) awaiting verification:**")
        for _, row in pending_verify.iterrows():
            with st.expander(f"Order: {row['Order_ID']} — {row['Customer_Name']} (₹{row['Total_Amount_INR']})", expanded=True):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Customer:** {row['Customer_Name']}")
                c1.write(f"**Phone:** {row['Customer_Phone']}")
                c2.write(f"**Packages:** {row['Product_Codes']}")
                c2.write(f"**Email:** {row['Customer_Email']}")
                c3.write(f"**UTR:** `{row['UTR_Number']}`")
                c3.write(f"**Channel:** {row['Payment_Mode']}")

                if st.button(f"✅ Authorize Delivery for {row['Order_ID']}", key=f"verify_{row['Order_ID']}"):
                    idx = ledger_df[ledger_df["Order_ID"] == row["Order_ID"]].index[0]
                    ledger_df.at[idx, "Status"] = "Approved - Ready for Delivery"
                    save_ledger(ledger_df)
                    st.success(f"Order {row['Order_ID']} authorized! Switch to Tab 4 for dispatch.")
                    st.rerun()

# ------------------------------------------
# TAB 4: SECURE DELIVERY DESK
# ------------------------------------------
with tabs[4]:
    st.subheader("Secure Digital Delivery Desk")
    ledger_df = load_ledger()
    ready_delivery = ledger_df[ledger_df["Status"] == "Approved - Ready for Delivery"]

    if ready_delivery.empty:
        st.info("No authorized orders currently pending digital dispatch.")
    else:
        for _, row in ready_delivery.iterrows():
            with st.expander(f"Dispatch Order: {row['Order_ID']} — {row['Customer_Name']}", expanded=True):
                st.write(f"**Customer:** {row['Customer_Name']} | 📞 {row['Customer_Phone']} | ✉️ {row['Customer_Email']}")
                st.write(f"**Selected Packages:** {row['Product_Codes']}")

                # Prepare delivery links
                active_links = {}
                raw_codes = [c.strip() for c in str(row["Product_Codes"]).split(",") if c.strip()]
                for raw in raw_codes:
                    cat_item = resolve_catalog_item(raw)
                    code_key = cat_item["Code"] if cat_item else raw
                    # Check sidebar inputs first, then fallback to secrets
                    url = drive_links.get(code_key, "").strip() or get_secret(f"LINK_{code_key.replace('-', '_')}", "").strip()
                    active_links[code_key] = url

                if st.button(f"🚀 Send Digital Delivery Email to {row['Customer_Name']}", key=f"del_{row['Order_ID']}"):
                    with st.spinner("Dispatching secure access email with PDF attachment..."):
                        ok, msg_res = dispatch_delivery_email(
                            sender_email,
                            sender_password,
                            row["Customer_Email"],
                            row["Customer_Name"],
                            row["Product_Codes"],
                            active_links
                        )
                        if ok:
                            idx = ledger_df[ledger_df["Order_ID"] == row["Order_ID"]].index[0]
                            ledger_df.at[idx, "Status"] = "Delivered"
                            ledger_df.at[idx, "Delivery_Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            save_ledger(ledger_df)
                            st.success(f"Delivery email sent to {row['Customer_Email']}!")
                            st.rerun()
                        else:
                            st.error(f"Email failed to send: {msg_res}")

# ------------------------------------------
# TAB 5: OPERATIONS LEDGER & AUDIT
# ------------------------------------------
with tabs[5]:
    st.subheader("Central Operations Ledger")
    ledger_df = load_ledger()
    st.dataframe(ledger_df, use_container_width=True)

    csv_data = ledger_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Ledger as CSV",
        data=csv_data,
        file_name=f"atma_bodha_ledger_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )