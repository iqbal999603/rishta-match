import streamlit as st
import sqlite3
import hashlib
import os
import html
from datetime import datetime
import pandas as pd
import base64
from io import BytesIO
from PIL import Image

# ========== PAGE CONFIG ==========
st.set_page_config(page_title="Rishta Match – Find Your Partner", page_icon="💖", layout="wide")

# ========== ROMANTIC THEME CSS ==========
st.markdown("""
<style>
    .stApp { background: #1a0a0a; }
    h1, h2, h3, h4, h5, h6, p, label, div, span { color: #f0d9d9 !important; }
    .romantic-header {
        background: linear-gradient(135deg, #b30047, #ff4d4d);
        padding: 20px;
        border-radius: 20px;
        text-align: center;
        color: white !important;
        margin-bottom: 20px;
        box-shadow: 0 0 20px rgba(255,77,77,0.5);
    }
    .profile-card {
        background: #2d1a1a;
        border: 1px solid #ff4d4d;
        border-radius: 15px;
        padding: 15px;
        margin: 10px 0;
        transition: 0.3s;
        display: flex;
        gap: 15px;
        align-items: start;
    }
    .profile-card:hover { border-color: #ff9999; box-shadow: 0 0 10px #ff4d4d; }
    .profile-img {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #ff4d4d;
    }
    .profile-info { flex: 1; }
    .stButton button {
        background: linear-gradient(45deg, #ff4d4d, #b30047);
        border: none;
        color: white;
        border-radius: 30px;
        font-weight: bold;
    }
    .stButton button:hover { transform: scale(1.05); box-shadow: 0 0 20px #ff4d4d; }
    .notification {
        background: #2d1a1a;
        border-left: 4px solid #ff4d4d;
        padding: 10px;
        margin: 5px 0;
    }
    .stTextInput input, .stSelectbox div, .stNumberInput input {
        background: #2d1a1a !important;
        color: white !important;
        border: 1px solid #ff4d4d !important;
    }
</style>
""", unsafe_allow_html=True)  # Safe: no user data inside

# ========== SECRETS (NO HARDCODED FALLBACK) ==========
def get_admin_secrets():
    try:
        admin_secret = st.secrets["ADMIN_SECRET"]
        admin_password = st.secrets["ADMIN_PASSWORD"]
        return admin_secret, admin_password
    except Exception:
        st.error("""
        ⚠️ **Admin secrets not configured!**  
        Please add `ADMIN_SECRET` and `ADMIN_PASSWORD` to your Streamlit secrets.  
        For local development, create a `.streamlit/secrets.toml` file.
        """)
        st.stop()

ADMIN_SECRET, ADMIN_PASSWORD = get_admin_secrets()

# ========== DATABASE HELPERS (No cache, safe threading) ==========
def get_db_connection():
    """Returns a new SQLite connection with WAL mode and row_factory."""
    conn = sqlite3.connect('rishta.db', timeout=20)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE, gender TEXT, age INTEGER, education TEXT,
                  occupation TEXT, city TEXT, religion TEXT,
                  marital_status TEXT, height TEXT, bio TEXT,
                  contact TEXT, photo_base64 TEXT, password TEXT,
                  join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS interests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  from_user INTEGER, to_user INTEGER,
                  date TEXT, is_read INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER, message TEXT, is_read INTEGER DEFAULT 0,
                  created_at TEXT)''')
    # Unique index on name to prevent duplicates
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_name ON users(name)")
    conn.commit()
    conn.close()

init_db()

# ========== PASSWORD HASHING ==========
def hash_password(pwd):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt, 100000)
    return salt.hex() + ':' + dk.hex()

def verify_password(stored, provided):
    try:
        salt_hex, dk_hex = stored.split(':')
        salt = bytes.fromhex(salt_hex)
        new_dk = hashlib.pbkdf2_hmac('sha256', provided.encode(), salt, 100000)
        return new_dk.hex() == dk_hex
    except:
        return False

# ========== NOTIFICATION HELPER ==========
def add_notification(user_id, msg):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO notifications (user_id, message, created_at) VALUES (?,?,?)",
              (user_id, msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ========== IMAGE HANDLING (with validation) ==========
def image_to_base64(image_file):
    if image_file is None:
        return None
    # Check file size (2 MB limit)
    if image_file.size > 2 * 1024 * 1024:
        st.error("Photo too large! Maximum 2 MB allowed.")
        return None
    try:
        img = Image.open(image_file)
        img.verify()  # Verify image integrity
        img = Image.open(image_file)  # Need to reopen after verify
        img = img.resize((300, 300))
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=80)
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        st.error("Invalid image file. Please upload JPG, JPEG, or PNG.")
        return None

# ========== SESSION STATE INIT ==========
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_name = None
if 'page' not in st.session_state:
    st.session_state.page = "Home"

# ========== HEADER ==========
st.markdown('<div class="romantic-header"><h1>💖 Rishta Match 💖</h1><p>🌸 Pyar bhari shadi ka pehla kadam 🌸</p></div>', unsafe_allow_html=True)

# ========== SIDEBAR (with logout) ==========
page_map = {
    "🏠 Home": "Home",
    "📝 Register": "Register",
    "🔐 Login": "Login",
    "👀 Browse Profiles": "Browse",
    "💌 My Interests": "Interests",
    "👑 Admin": "Admin"
}
with st.sidebar:
    menu = ["🏠 Home", "📝 Register", "🔐 Login", "👀 Browse Profiles", "💌 My Interests"]
    admin_input = st.text_input("Admin Secret", type="password", placeholder="Enter admin secret")
    if admin_input == ADMIN_SECRET:
        menu.append("👑 Admin")
    sel = st.selectbox("Menu", menu, label_visibility="collapsed")
    if st.session_state.page != page_map[sel]:
        st.session_state.page = page_map[sel]
        st.rerun()
    
    # Logout button
    if st.session_state.logged_in:
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.user_name = None
            st.rerun()

# ========== NOTIFICATIONS ==========
if st.session_state.logged_in:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, message FROM notifications WHERE user_id=? AND is_read=0 ORDER BY created_at DESC", (st.session_state.user_id,))
    notifs = c.fetchall()
    if notifs:
        with st.expander(f"🔔 {len(notifs)} new notification(s)"):
            for n in notifs:
                # Escape notification message to prevent XSS
                safe_msg = html.escape(n[1])
                st.markdown(f'<div class="notification">{safe_msg}</div>', unsafe_allow_html=True)
            # Mark as read – safe because ids are ints from DB
            ids = [n[0] for n in notifs]
            placeholders = ','.join('?' * len(ids))
            c.execute(f"UPDATE notifications SET is_read=1 WHERE id IN ({placeholders})", ids)
            conn.commit()
    conn.close()

# ========== PAGES ==========
if st.session_state.page == "Home":
    st.markdown("""
    ## 🌹 Welcome to Rishta Match!
    Create your profile with photo, browse matches with advanced filters, and when both like each other – contact details are revealed!
    """)
    st.markdown("[💰 Free Earning](https://mansha99.pythonanywhere.com/)")

elif st.session_state.page == "Register":
    if st.session_state.logged_in:
        st.warning("Already logged in")
        st.stop()
    with st.form("reg", clear_on_submit=True):
        st.subheader("📝 Create Your Profile")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name *")
            gender = st.selectbox("Gender *", ["Male", "Female"])
            age = st.number_input("Age *", 18, 80, 25)
            education = st.selectbox("Education", ["Matric", "Intermediate", "Bachelor", "Master", "PhD", "Other"])
            occupation = st.text_input("Occupation")
        with col2:
            city = st.text_input("City *")
            religion = st.selectbox("Religion", ["Islam", "Christianity", "Hinduism", "Other"])
            marital_status = st.selectbox("Marital Status", ["Never Married", "Divorced", "Widowed"])
            height = st.text_input("Height (e.g., 5'8\")", placeholder="5 feet 8 inches")
        bio = st.text_area("About Yourself (Bio)")
        contact = st.text_input("Contact Number (hidden until match)", help="Phone number will only be shown after mutual interest")
        photo = st.file_uploader("Upload Your Photo", type=["jpg", "jpeg", "png"])
        password = st.text_input("Password *", type="password")
        confirm = st.text_input("Confirm Password *", type="password")
        submitted = st.form_submit_button("Register 💖")
        if submitted:
            if not name or not password or not gender or not city:
                st.error("Name, password, gender, and city are required.")
            elif password != confirm:
                st.error("Passwords don't match.")
            elif len(password) < 4:
                st.error("Password must be at least 4 characters.")
            else:
                photo_b64 = None
                if photo:
                    photo_b64 = image_to_base64(photo)
                    if photo_b64 is None:
                        st.stop()
                hashed = hash_password(password)
                join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn = get_db_connection()
                c = conn.cursor()
                try:
                    c.execute("""INSERT INTO users 
                                 (name, gender, age, education, occupation, city, religion, marital_status, height, bio, contact, photo_base64, password, join_date)
                                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (name, gender, age, education, occupation, city, religion, marital_status, height, bio, contact, photo_b64, hashed, join_date))
                    conn.commit()
                    st.success("Profile created! You can now login.")
                    st.session_state.page = "Login"
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This name is already taken. Please choose a different name.")
                finally:
                    conn.close()

elif st.session_state.page == "Login":
    if st.session_state.logged_in:
        st.warning("Already logged in")
        st.stop()
    with st.form("login"):
        st.subheader("🔐 Login")
        name = st.text_input("Full Name (as registered)")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE name=?", (name,))
            user = c.fetchone()
            conn.close()
            if user and verify_password(user[13], password):
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.success("Login successful!")
                st.session_state.page = "Browse"
                st.rerun()
            else:
                st.error("Invalid credentials")

elif st.session_state.page == "Browse":
    st.subheader("👀 Browse Profiles")
    conn = get_db_connection()
    c = conn.cursor()
    with st.expander("🔍 Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            gender = st.selectbox("Gender", ["All", "Male", "Female"], key="filter_gender")
            age_min, age_max = st.slider("Age Range", 18, 80, (18, 80))
        with col2:
            education = st.selectbox("Education", ["All", "Matric", "Intermediate", "Bachelor", "Master", "PhD", "Other"], key="filter_education")
            religion = st.selectbox("Religion", ["All", "Islam", "Christianity", "Hinduism", "Other"], key="filter_religion")
        with col3:
            city = st.text_input("City (contains)")
            marital = st.selectbox("Marital Status", ["All", "Never Married", "Divorced", "Widowed"], key="filter_marital")

    query = "SELECT * FROM users WHERE age BETWEEN ? AND ?"
    params = [age_min, age_max]
    if gender != "All":
        query += " AND gender = ?"
        params.append(gender)
    if education != "All":
        query += " AND education = ?"
        params.append(education)
    if religion != "All":
        query += " AND religion = ?"
        params.append(religion)
    if city:
        query += " AND city LIKE ?"
        params.append(f"%{city}%")
    if marital != "All":
        query += " AND marital_status = ?"
        params.append(marital)
    query += " ORDER BY join_date DESC"
    c.execute(query, params)
    profiles = c.fetchall()

    # If logged in, fetch all interests sent by current user in one go
    sent_interests = set()
    if st.session_state.logged_in:
        c.execute("SELECT to_user FROM interests WHERE from_user=?", (st.session_state.user_id,))
        sent_interests = {row[0] for row in c.fetchall()}

    if profiles:
        for p in profiles:
            if st.session_state.logged_in and p[0] == st.session_state.user_id:
                continue
            # Escape all user data to prevent XSS
            safe_name = html.escape(p[1])
            safe_age = html.escape(str(p[3]))
            safe_edu = html.escape(p[4] if p[4] else 'N/A')
            safe_occ = html.escape(p[5] if p[5] else 'N/A')
            safe_city = html.escape(p[6] if p[6] else 'N/A')
            safe_rel = html.escape(p[7] if p[7] else 'N/A')
            safe_marital = html.escape(p[8] if p[8] else 'N/A')
            safe_height = html.escape(p[9] if p[9] else 'N/A')
            safe_bio = html.escape(p[10] if p[10] else '')
            photo_html = ""
            if p[12]:
                photo_html = f'<img src="data:image/jpeg;base64,{p[12]}" class="profile-img" />'
            else:
                photo_html = '<div style="width:120px;height:120px;border-radius:50%;background:#333;display:inline-block;text-align:center;line-height:120px;font-size:40px;">👤</div>'
            st.markdown(f"""
            <div class="profile-card">
                {photo_html}
                <div class="profile-info">
                    <h3>💐 {safe_name}, {safe_age}</h3>
                    <p>🎓 {safe_edu} | 💼 {safe_occ} | 📍 {safe_city}</p>
                    <p>🕌 {safe_rel} | 💍 {safe_marital} | 📏 {safe_height}</p>
                    <p>{safe_bio}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)  # Safe because we escaped user data
            
            if st.session_state.logged_in:
                if p[0] in sent_interests:
                    st.button("✅ Interest Sent", disabled=True, key=f"sent_{p[0]}")
                else:
                    if st.button("💌 Send Interest", key=f"send_{p[0]}"):
                        # Send interest
                        c.execute("INSERT INTO interests (from_user, to_user, date) VALUES (?,?,?)",
                                  (st.session_state.user_id, p[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        add_notification(p[0], f"💖 {html.escape(st.session_state.user_name)} has shown interest in you!")
                        # Check mutual interest
                        c.execute("SELECT id FROM interests WHERE from_user=? AND to_user=?", (p[0], st.session_state.user_id))
                        mutual = c.fetchone()
                        if mutual:
                            c.execute("SELECT name, contact FROM users WHERE id=?", (st.session_state.user_id,))
                            me = c.fetchone()
                            c.execute("SELECT name, contact FROM users WHERE id=?", (p[0],))
                            them = c.fetchone()
                            add_notification(st.session_state.user_id, f"🎉 It's a Match! {html.escape(them[0])} also likes you. Contact: {html.escape(them[1])}")
                            add_notification(p[0], f"🎉 It's a Match! {html.escape(me[0])} also likes you. Contact: {html.escape(me[1])}")
                            st.success("🎉 It's a Match! Contact details have been shared with both of you.")
                        else:
                            st.success("Interest sent!")
                        st.rerun()
            st.markdown("---")
    else:
        st.info("No profiles found. Try different filters.")
    conn.close()

elif st.session_state.page == "Interests":
    if not st.session_state.logged_in:
        st.warning("Login required")
        st.stop()
    st.subheader("💌 My Interests")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT i.id, u.name, i.date FROM interests i JOIN users u ON i.to_user = u.id WHERE i.from_user = ?", (st.session_state.user_id,))
    sent = c.fetchall()
    c.execute("SELECT i.id, u.name, i.date FROM interests i JOIN users u ON i.from_user = u.id WHERE i.to_user = ?", (st.session_state.user_id,))
    received = c.fetchall()
    conn.close()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Sent")
        for s in sent:
            safe_name = html.escape(s[1])
            st.write(f"➡️ {safe_name} – {s[2][:10]}")
    with col2:
        st.markdown("### Received")
        for r in received:
            safe_name = html.escape(r[1])
            st.write(f"⬅️ {safe_name} – {r[2][:10]}")

elif st.session_state.page == "Admin":
    if admin_input != ADMIN_SECRET:
        st.error("Admin secret required")
        st.stop()
    st.success("👑 Admin Panel")
    tab1, tab2 = st.tabs(["Manage Profiles", "Export Data"])
    with tab1:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, gender, age, city, contact FROM users")
        users = c.fetchall()
        for u in users:
            cols = st.columns([2,2,1,1,2,2])
            cols[0].write(html.escape(u[1]))
            cols[1].write(html.escape(u[2]))
            cols[2].write(str(u[3]))
            cols[3].write(html.escape(u[4] if u[4] else "N/A"))
            cols[4].write(html.escape(u[5] if u[5] else "N/A"))
            if cols[5].button("Delete", key=f"del_{u[0]}"):
                c.execute("DELETE FROM users WHERE id=?", (u[0],))
                c.execute("DELETE FROM interests WHERE from_user=? OR to_user=?", (u[0], u[0]))
                conn.commit()
                st.rerun()
        conn.close()
    with tab2:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT name, gender, age, education, occupation, city, religion, marital_status, contact, join_date FROM users")
        data = c.fetchall()
        conn.close()
        df = pd.DataFrame(data, columns=["Name","Gender","Age","Education","Occupation","City","Religion","Marital Status","Contact","Join Date"])
        st.download_button("Download CSV", df.to_csv(index=False).encode(), "rishta_users.csv")

# ========== FOOTER ==========
st.markdown("""
<div style="position:fixed; bottom:0; left:0; width:100%; background:#2d1a1a; text-align:center; padding:8px; font-size:12px; color:#ff9999; border-top:1px solid #ff4d4d;">
    🌸 Rishta Match – Pyar bhari shadi ka safar 🌸
</div>
""", unsafe_allow_html=True)
