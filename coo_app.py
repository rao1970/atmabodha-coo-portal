"""
Atma Bodha Digital Education & Devotional Media
Digital Chief Operating Officer (COO) Operations Portal
File: coo_app.py
Run command: streamlit run coo_app.py
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
from typing import Dict, List, Optional
import urllib.parse
import uuid

import pandas as pd
import requests
import streamlit as st

# =========================================================================
# 1. IMMUTABLE PRODUCT CATALOGUE
# =========================================================================
@dataclass(frozen=True)
class Product:
    code: str
    name: str
    format_type: str
    track_count: int
    includes_guide: bool
    price_inr: int
    included_codes: List[str] = field(default_factory=list)


CATALOGUE: Dict[str, Product] = {
    "TD-A68": Product(
        code="TD-A68",
        name="Traditional Devotional Audio",
        format_type="Devotional Audio",
        track_count=68,
        includes_guide=False,
        price_inr=149,
    ),
    "TD-V68": Product(
        code="TD-V68",
        name="Traditional Devotional Lyric Videos",
        format_type="Single-image lyric videos",
        track_count=68,
        includes_guide=False,
        price_inr=249,
    ),
    "MD-136": Product(
        code="MD-136",
        name="Modern Soul Audio",
        format_type="Modern devotional audio tracks",
        track_count=136,
        includes_guide=False,
        price_inr=299,
    ),
    "FS-136": Product(
        code="FS-136",
        name="World Fusion Audio",
        format_type="Fusion-style audio tracks",
        track_count=136,
        includes_guide=False,
        price_inr=299,
    ),
    "TCP": Product(
        code="TCP",
        name="Traditional Complete Pack",
        format_type="TD-A68 + TD-V68 + Atma Bodha Study Guide PDF",
        track_count=136,
        includes_guide=True,
        price_inr=349,
        included_codes=["TD-A68", "TD-V68"],
    ),
    "TAP": Product(
        code="TAP",
        name="Three Audio Styles Pack",
        format_type="TD-A68 + MD-136 + FS-136 + Atma Bodha Study Guide PDF",
        track_count=340,
        includes_guide=True,
        price_inr=599,
        included_codes=["TD-A68", "MD-136", "FS-136"],
    ),
    "CAC": Product(
        code="CAC",
        name="Complete Atma Bodha Collection",
        format_type="TD-A68 + TD-V68 + MD-136 + FS-136 + Atma Bodha Study Guide PDF",
        track_count=408,
        includes_guide=True,
        price_inr=899,
        included_codes=["TD-A68", "TD-V68", "MD-136", "FS-136"],
    ),
}

DRIVE_PRODUCT_FOLDERS: Dict[str, str] = {
    "TD-A68": "DRIVE_SECURE_TD_A68_AUDIO",
    "TD-V68": "DRIVE_SECURE_TD_V68_VIDEOS",
    "MD-136": "DRIVE_SECURE_MD_136_SOUL",
    "FS-136": "DRIVE_SECURE_FS_136_FUSION",
    "TCP":    "DRIVE_SECURE_TCP_COMPLETE_PACK",
    "TAP":    "DRIVE_SECURE_TAP_THREE_AUDIO_PACK",
    "CAC":    "DRIVE_SECURE_CAC_FULL_COLLECTION",
}

CSV_LEDGER_FILE = "orders_ledger.csv"


# =========================================================================
# 2. STATUS ENUM & ORDER SCHEMA
# =========================================================================
class OrderStatus(Enum):
    ENQUIRY = "Enquiry"
    PAYMENT_PENDING = "Payment pending"
    PAYMENT_RECEIVED = "Payment received"
    VERIFICATION_REQUIRED = "Verification required"
    APPROVED = "Approved"
    DELIVERED = "Delivered"
    DELIVERY_PROBLEM = "Delivery problem"
    REFUND_REQUESTED = "Refund requested"
    CLOSED = "Closed"


@dataclass
class OrderRecord:
    order_id: str
    created_at: str
    customer_phone: str
    product_code: str
    amount_inr: int
    customer_gmail: str = ""
    utr_number: str = ""
    status: OrderStatus = OrderStatus.PAYMENT_PENDING
    verified_by: str = ""
    delivered_at: str = ""
    delivery_folder: str = ""
    delivery_message: str = ""
    audit_notes: List[str] = field(default_factory=list)


# =========================================================================
# 3. CSV PERSISTENT STORAGE HANDLERS
# =========================================================================
def save_orders_to_disk(orders: Dict[str, OrderRecord]):
    """Persists entire order state to CSV file on disk."""
    rows = []
    for o in orders.values():
        rows.append({
            "order_id": o.order_id,
            "created_at": o.created_at,
            "customer_phone": o.customer_phone,
            "product_code": o.product_code,
            "amount_inr": o.amount_inr,
            "customer_gmail": o.customer_gmail,
            "utr_number": o.utr_number,
            "status": o.status.value,
            "verified_by": o.verified_by,
            "delivered_at": o.delivered_at,
            "delivery_folder": o.delivery_folder,
            "delivery_message": o.delivery_message,
            "audit_notes": " || ".join(o.audit_notes)
        })
    df = pd.DataFrame(rows)
    df.to_csv(CSV_LEDGER_FILE, index=False)


def load_orders_from_disk() -> Dict[str, OrderRecord]:
    """Loads saved orders from CSV file on disk."""
    if not os.path.exists(CSV_LEDGER_FILE):
        return {}
    try:
        df = pd.read_csv(CSV_LEDGER_FILE, dtype=str).fillna("")
        orders = {}
        for _, row in df.iterrows():
            try:
                st_val = OrderStatus(row["status"])
            except Exception:
                st_val = OrderStatus.PAYMENT_PENDING

            amt = int(row["amount_inr"]) if row["amount_inr"].isdigit() else 0
            notes_raw = row["audit_notes"]
            notes = notes_raw.split(" || ") if notes_raw else []

            record = OrderRecord(
                order_id=row["order_id"],
                created_at=row["created_at"],
                customer_phone=row["customer_phone"],
                product_code=row["product_code"],
                amount_inr=amt,
                customer_gmail=row["customer_gmail"],
                utr_number=row["utr_number"],
                status=st_val,
                verified_by=row["verified_by"],
                delivered_at=row["delivered_at"],
                delivery_folder=row["delivery_folder"],
                delivery_message=row["delivery_message"],
                audit_notes=notes
            )
            orders[record.order_id] = record
        return orders
    except Exception as e:
        st.error(f"Error loading {CSV_LEDGER_FILE}: {e}")
        return {}


# =========================================================================
# 4. DISPATCH & NOTIFICATION ENGINES
# =========================================================================
def safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def send_telegram_notification(bot_token: str, chat_id: str, html_message: str) -> Dict[str, any]:
    """Sends background instant alert to Telegram phone app."""
    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
    payload = {
        "chat_id": chat_id.strip(),
        "text": html_message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=12)
        res_data = response.json()
        if res_data.get("ok"):
            return {"status": True, "message": "Notification successfully sent to your Telegram!"}
        else:
            return {"status": False, "message": f"Telegram Error: {res_data.get('description', 'Failed')}"}
    except Exception as e:
        return {"status": False, "message": f"Connection Error: {str(e)}"}


def generate_whatsapp_enquiry_reply(product_code: str) -> str:
    clean = product_code.strip().upper()
    if clean not in CATALOGUE:
        return "Invalid Product Code."
    p = CATALOGUE[clean]
    guide_note = "• Includes: Complete Atma Bodha Study Guide (PDF)\n" if p.includes_guide else ""
    return (
        f"Hari Om! Thank you for inquiring about {p.name} ({p.code}).\n\n"
        f"Product Details:\n"
        f"• Code: {p.code}\n"
        f"• Format: {p.format_type}\n"
        f"• Tracks: {p.track_count}\n"
        f"{guide_note}"
        f"• Official Price: ₹{p.price_inr}\n\n"
        f"How to Complete Your Order:\n"
        f"1. Make UPI payment of ₹{p.price_inr} to our official VPA: [atmadbodha.official@upi]\n"
        f"2. Reply to this chat with:\n"
        f"   - Product Code: {p.code}\n"
        f"   - UTR / Transaction Reference Number\n"
        f"   - Payment screenshot\n"
        f"   - Your Gmail address (for secure Google Drive access)\n\n"
        f"Access is provisioned privately upon payment verification."
    )


def generate_delivery_message(order: OrderRecord) -> str:
    p = CATALOGUE[order.product_code]
    upgrade_prompt = ""
    if order.product_code in ["TD-A68", "TD-V68"]:
        upgrade_prompt = (
            "\n\n*Optional Study Upgrade:*\n"
            "If you later wish to add the lyric videos and the Study Guide PDF, you can upgrade to the "
            "Traditional Complete Pack (TCP — ₹349) anytime by paying the difference. Simply message 'UPGRADE TCP'."
        )
    elif order.product_code in ["MD-136", "FS-136"]:
        upgrade_prompt = (
            "\n\n*Complete Library Upgrade:*\n"
            "To explore all 408 tracks across all 3 musical styles with the Study Guide, "
            "you can upgrade to the Complete Atma Bodha Collection (CAC — ₹899) anytime. Simply message 'UPGRADE CAC'."
        )

    return (
        f"Hari Om! Your access for {p.name} ({p.code}) is now active.\n\n"
        f"Order Details:\n"
        f"• Order Reference: {order.order_id}\n"
        f"• Registered Gmail: {order.customer_gmail}\n"
        f"• Access Method: Restricted Private Google Drive (Read Only)\n\n"
        f"How to Access Your Files:\n"
        f"1. Open Google Drive (drive.google.com) using {order.customer_gmail}.\n"
        f"2. Navigate to the 'Shared with me' tab.\n"
        f"3. Open the folder: '{p.name}'.\n\n"
        f"Customer Support:\n"
        f"If you experience any access issues, please reply directly to this message."
        f"{upgrade_prompt}"
    )


# =========================================================================
# 5. INITIALIZE SESSION STATE & LOAD DISK STORAGE
# =========================================================================
if "orders" not in st.session_state:
    loaded_orders = load_orders_from_disk()
    if loaded_orders:
        st.session_state.orders = loaded_orders
    else:
        st.session_state.orders = {}
        # Seed default demonstration order if fresh file
        demo_id = f"AB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-DEMO1"
        st.session_state.orders[demo_id] = OrderRecord(
            order_id=demo_id,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            customer_phone="+919876543210",
            product_code="TD-A68",
            amount_inr=149,
            customer_gmail="seeker.sample@gmail.com",
            utr_number="UTR428901234567",
            status=OrderStatus.VERIFICATION_REQUIRED,
            audit_notes=["Enquiry created.", "Payment proof with UTR submitted."]
        )
        save_orders_to_disk(st.session_state.orders)


# =========================================================================
# 6. UI CONFIGURATION & SIDEBAR
# =========================================================================
st.set_page_config(page_title="Atma Bodha Operations Desk", layout="wide", page_icon="🕉️")

st.title("🕉️ Atma Bodha Digital COO Operations Hub")
st.caption("Central Operations: Product Catalogue | Enquiries | Telegram Mobile Alerts | Google Drive Delivery | Disk Persistence Active")

# Sidebar Configuration (Your Pre-Configured Credentials)
st.sidebar.header("📱 Telegram Phone Alerts Configuration")
st.sidebar.markdown("Instant background notifications to your mobile Telegram app.")

telegram_token = st.sidebar.text_input(
    "Telegram Bot Token",
    value="8836740336:AAE3xjRLK4P_oqK2Ra6dlSImYIWxxxVizLk",
    help="Bot token from @BotFather"
)
telegram_chat_id = st.sidebar.text_input(
    "Telegram Chat ID",
    value="5858834506",
    help="Your personal chat ID"
)

if st.sidebar.button("🔔 Send Test Telegram Ping to Phone"):
    if not telegram_token or not telegram_chat_id:
        st.sidebar.error("Bot Token and Chat ID must be set.")
    else:
        test_msg = (
            "🔔 <b>[COO SYSTEM ALERT]</b>\n\n"
            "Atma Bodha Operations Portal is live and linked to your phone!\n"
            "Persistent disk storage is ACTIVE."
        )
        res = send_telegram_notification(telegram_token, telegram_chat_id, test_msg)
        if res.get("status") is True:
            st.sidebar.success("✅ Delivered! Check your Telegram phone notification.")
        else:
            st.sidebar.error(res.get("message"))

st.sidebar.divider()
st.sidebar.info(f"💾 **Storage File:** `{CSV_LEDGER_FILE}`\n\nTotal records saved: {len(st.session_state.orders)}")


# =========================================================================
# 7. APPLICATION WORKFLOW TABS
# =========================================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📚 Catalogue & Auto-Reply",
    "📝 1. Enquiry Intake",
    "💳 2. Payment Proof & Alert",
    "🛡️ 3. Bank Verification Desk",
    "📦 4. Secure Delivery Desk",
    "📊 5. Operations Ledger & Reports"
])

# -------------------------------------------------------------------------
# TAB 1: PRODUCT CATALOGUE & AUTO-REPLY
# -------------------------------------------------------------------------
with tab1:
    st.subheader("Approved Product Catalogue")
    cat_rows = []
    for k, v in CATALOGUE.items():
        cat_rows.append({
            "Code": v.code,
            "Product Name": v.name,
            "Format": v.format_type,
            "Tracks": v.track_count,
            "Study Guide": "Included (PDF)" if v.includes_guide else "Not Included",
            "Price": f"₹{v.price_inr}"
        })
    st.dataframe(pd.DataFrame(cat_rows), use_container_width=True)

    st.divider()
    st.subheader("Generate WhatsApp Enquiry Response")
    col_code, _ = st.columns([2, 1])
    with col_code:
        picked_code = st.selectbox("Select Product to generate customer message:", list(CATALOGUE.keys()))
    
    reply_msg = generate_whatsapp_enquiry_reply(picked_code)
    st.text_area("WhatsApp Auto-Reply Template (Copy & send to customer):", value=reply_msg, height=220)

# -------------------------------------------------------------------------
# TAB 2: ENQUIRY INTAKE
# -------------------------------------------------------------------------
with tab2:
    st.subheader("Create New Customer Enquiry")
    with st.form("create_enquiry_form"):
        cust_phone_in = st.text_input("Customer Phone Number", value="+91 ")
        item_code_in = st.selectbox("Requested Product Code", list(CATALOGUE.keys()))
        btn_create = st.form_submit_button("Create Enquiry Order")

        if btn_create:
            if len(cust_phone_in.strip()) < 10:
                st.error("Please enter a valid customer phone number.")
            else:
                p_item = CATALOGUE[item_code_in]
                new_id = f"AB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
                st.session_state.orders[new_id] = OrderRecord(
                    order_id=new_id,
                    created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    customer_phone=cust_phone_in.strip(),
                    product_code=p_item.code,
                    amount_inr=p_item.price_inr,
                    status=OrderStatus.PAYMENT_PENDING,
                    audit_notes=[f"Enquiry created for {p_item.name} (₹{p_item.price_inr})."]
                )
                save_orders_to_disk(st.session_state.orders)
                st.success(f"Enquiry created and saved to disk! Order ID: **{new_id}** | Amount: ₹{p_item.price_inr}")
                safe_rerun()

# -------------------------------------------------------------------------
# TAB 3: PAYMENT PROOF & INSTANT TELEGRAM ALERT
# -------------------------------------------------------------------------
with tab3:
    st.subheader("Submit Payment Proof & Dispatch Mobile Alert")
    unpaid_orders = [o for o in st.session_state.orders.values() if o.status == OrderStatus.PAYMENT_PENDING]

    if not unpaid_orders:
        st.info("No orders currently waiting for payment submission.")
    else:
        order_options = {
            f"{o.order_id} | {o.product_code} (₹{o.amount_inr}) | Phone: {o.customer_phone}": o.order_id
            for o in unpaid_orders
        }
        chosen_label = st.selectbox("Select Pending Order:", list(order_options.keys()))
        target_order_id = order_options[chosen_label]
        target_rec = st.session_state.orders[target_order_id]

        with st.form("proof_submit_form"):
            entered_utr = st.text_input("UTR / Transaction Reference Number (from screenshot)", placeholder="e.g. 428901234567")
            entered_gmail = st.text_input("Customer Gmail Address (for Google Drive delivery)", placeholder="e.g. devotee@gmail.com")
            btn_submit_proof = st.form_submit_button("Submit Payment Proof & Buzz COO Phone via Telegram")

            if btn_submit_proof:
                if not entered_utr or len(entered_utr.strip()) < 6:
                    st.error("Please provide a valid UTR number (at least 6 digits).")
                elif not entered_gmail or "@gmail.com" not in entered_gmail.lower():
                    st.error("A valid @gmail.com address is required for secure Google Drive delivery.")
                else:
                    target_rec.utr_number = entered_utr.strip()
                    target_rec.customer_gmail = entered_gmail.strip().lower()
                    target_rec.status = OrderStatus.VERIFICATION_REQUIRED
                    target_rec.audit_notes.append(f"UTR {entered_utr} submitted. Status set to Verification Required.")
                    
                    save_orders_to_disk(st.session_state.orders)

                    # Formulate Telegram Alert
                    tg_alert = (
                        "🚨 <b>NEW PAYMENT SUBMITTED — VERIFICATION REQUIRED</b>\n\n"
                        f"• <b>Order Reference:</b> <code>{target_rec.order_id}</code>\n"
                        f"• <b>Product SKU:</b> {target_rec.product_code} ({CATALOGUE[target_rec.product_code].name})\n"
                        f"• <b>Expected Amount:</b> <b>₹{target_rec.amount_inr}</b>\n"
                        f"• <b>Submitted UTR:</b> <code>{target_rec.utr_number}</code>\n"
                        f"• <b>Customer Gmail:</b> {target_rec.customer_gmail}\n\n"
                        "👉 <i>Action Required: Verify credit in bank account statement before approving.</i>"
                    )

                    st.success(f"Proof submitted for Order **{target_rec.order_id}**! Saved to disk.")

                    # Auto-send to your phone
                    if telegram_token and telegram_chat_id:
                        res = send_telegram_notification(telegram_token, telegram_chat_id, tg_alert)
                        if res.get("status") is True:
                            st.success("✅ Instant notification buzz sent directly to your phone via Telegram!")
                        else:
                            st.warning(f"Telegram dispatch notice: {res.get('message')}")

# -------------------------------------------------------------------------
# TAB 4: HUMAN BANK VERIFICATION GATEWAY
# -------------------------------------------------------------------------
with tab4:
    st.subheader("Human Bank Verification Desk (Mandatory Human Sign-off)")
    st.markdown("⚠️ **Security Rule:** *Never deliver files without human verification against the actual bank ledger.*")

    awaiting_list = [o for o in st.session_state.orders.values() if o.status == OrderStatus.VERIFICATION_REQUIRED]

    if not awaiting_list:
        st.info("No orders currently awaiting bank credit verification.")
    else:
        for ord_item in awaiting_list:
            with st.container(border=True):
                st.markdown(f"### Order: `{ord_item.order_id}`")
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Product:** {ord_item.product_code} ({CATALOGUE[ord_item.product_code].name})")
                c1.write(f"**Amount:** ₹{ord_item.amount_inr}")
                c2.write(f"**UTR Reference:** `{ord_item.utr_number}`")
                c2.write(f"**Customer Phone:** `{ord_item.customer_phone}`")
                c3.write(f"**Customer Gmail:** `{ord_item.customer_gmail}`")
                c3.write(f"**Submitted At:** `{ord_item.created_at}`")

                st.divider()
                verified_check = st.checkbox(
                    f"I have verified bank credit of ₹{ord_item.amount_inr} with UTR {ord_item.utr_number} in our official account.",
                    key=f"check_{ord_item.order_id}"
                )
                verifier_name_in = st.text_input(
                    "Verifier Name / Staff ID",
                    value="Operations Lead",
                    key=f"name_{ord_item.order_id}"
                )

                col_a, col_b = st.columns([1, 1])
                with col_a:
                    if st.button("✅ Approve Order", key=f"btn_app_{ord_item.order_id}"):
                        if not verified_check:
                            st.error("You must check the bank confirmation box before approving.")
                        else:
                            ord_item.status = OrderStatus.APPROVED
                            ord_item.verified_by = verifier_name_in
                            ord_item.audit_notes.append(f"Approved by {verifier_name_in} after bank verification.")
                            
                            save_orders_to_disk(st.session_state.orders)

                            # Confirmation notice to your phone
                            if telegram_token and telegram_chat_id:
                                send_telegram_notification(
                                    telegram_token,
                                    telegram_chat_id,
                                    f"✅ <b>ORDER APPROVED</b>: <code>{ord_item.order_id}</code> (₹{ord_item.amount_inr}) verified by {verifier_name_in}."
                                )
                                
                            st.success(f"Order {ord_item.order_id} APPROVED & Saved! Ready for secure delivery.")
                            safe_rerun()

                with col_b:
                    if st.button("❌ Reject (UTR Not Found)", key=f"btn_rej_{ord_item.order_id}"):
                        ord_item.status = OrderStatus.DELIVERY_PROBLEM
                        ord_item.audit_notes.append(f"Payment rejected by {verifier_name_in}: UTR mismatch.")
                        save_orders_to_disk(st.session_state.orders)
                        st.warning(f"Order {ord_item.order_id} flagged as Delivery Problem.")
                        safe_rerun()

# -------------------------------------------------------------------------
# TAB 5: SECURE CLOUD DELIVERY DESK
# -------------------------------------------------------------------------
with tab5:
    st.subheader("Secure Private Cloud Delivery Desk")
    approved_list = [o for o in st.session_state.orders.values() if o.status == OrderStatus.APPROVED]
    delivered_list = [o for o in st.session_state.orders.values() if o.status == OrderStatus.DELIVERED]

    if not approved_list and not delivered_list:
        st.info("No approved orders pending delivery.")
    
    if approved_list:
        st.markdown("#### ⏳ Approved Orders Awaiting Delivery:")
        for a_ord in approved_list:
            with st.container(border=True):
                st.markdown(f"**Order ID:** `{a_ord.order_id}` | **Item:** {a_ord.product_code} (₹{a_ord.amount_inr})")
                st.write(f"• **Target Gmail:** `{a_ord.customer_gmail}`")
                st.write(f"• **Private Cloud Folder:** `{DRIVE_PRODUCT_FOLDERS.get(a_ord.product_code)}`")
                st.write(f"• **Verified By:** `{a_ord.verified_by}`")

                if st.button("🚀 Grant Private Google Drive Access & Finalize Delivery", key=f"dlv_{a_ord.order_id}"):
                    a_ord.status = OrderStatus.DELIVERED
                    a_ord.delivered_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    a_ord.delivery_folder = DRIVE_PRODUCT_FOLDERS.get(a_ord.product_code, "RESTRICTED_FOLDER")
                    a_ord.delivery_message = generate_delivery_message(a_ord)
                    a_ord.audit_notes.append(f"Restricted access provisioned to {a_ord.customer_gmail}.")
                    
                    save_orders_to_disk(st.session_state.orders)
                    st.success(f"Order {a_ord.order_id} marked as DELIVERED & Saved to Disk!")
                    safe_rerun()

    if delivered_list:
        st.divider()
        st.markdown("#### ✅ Completed Deliveries (Copy Customer Access Message):")
        for d_ord in delivered_list:
            with st.expander(f"📦 Order {d_ord.order_id} — {d_ord.product_code} to {d_ord.customer_gmail} (Delivered)", expanded=True):
                st.write(f"**Delivered At:** {d_ord.delivered_at}")
                st.write(f"**Private Folder Provisioned:** `{d_ord.delivery_folder}`")
                st.text_area(
                    "WhatsApp Customer Message (Sent to Customer):",
                    value=d_ord.delivery_message or generate_delivery_message(d_ord),
                    height=200,
                    key=f"txt_{d_ord.order_id}"
                )

# -------------------------------------------------------------------------
# TAB 6: OPERATIONS LEDGER & REPORTS
# -------------------------------------------------------------------------
with tab6:
    st.subheader("Master Order Operations Ledger (Persistent on Disk)")
    
    ledger_records = []
    for o in st.session_state.orders.values():
        ledger_records.append({
            "Order ID": o.order_id,
            "Created": o.created_at,
            "Customer Phone": o.customer_phone,
            "Product": o.product_code,
            "Amount": f"₹{o.amount_inr}",
            "UTR Number": o.utr_number,
            "Customer Gmail": o.customer_gmail,
            "Status": o.status.value,
            "Verified By": o.verified_by,
            "Delivered At": o.delivered_at
        })
    
    df_ledger = pd.DataFrame(ledger_records)
    st.dataframe(df_ledger, use_container_width=True)

    csv_bytes = df_ledger.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Master Orders CSV",
        data=csv_bytes,
        file_name="atma_bodha_orders_ledger.csv",
        mime="text/csv"
    )

    st.divider()
    st.subheader("COO Executive Metrics Summary")
    total_enquiries = len(st.session_state.orders)
    paid_count = [o for o in st.session_state.orders.values() if o.status in [OrderStatus.APPROVED, OrderStatus.DELIVERED, OrderStatus.CLOSED]]
    revenue_sum = sum(o.amount_inr for o in paid_count)
    conv_pct = (len(paid_count) / total_enquiries * 100) if total_enquiries > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Inquiries", total_enquiries)
    m2.metric("Verified Paid Orders", len(paid_count))
    m3.metric("Gross Revenue", f"₹{revenue_sum}")
    m4.metric("Conversion Rate", f"{conv_pct:.1f}%")