from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from dotenv import load_dotenv
import requests
import os
from datetime import datetime, timedelta
import json
import types

load_dotenv()

mysql = types.SimpleNamespace(connector=None)
try:
    import mysql.connector as mysql_connector
    mysql.connector = mysql_connector
except Exception:
    mysql.connector = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
CORS(app)

# === CONFIG ===
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
PIN = os.environ.get("PIN", "1234")
PORT = int(os.environ.get("PORT", "5000"))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

try:
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
except ValueError:
    MYSQL_PORT = 3307

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("MYSQL_DB")

# === GLOBAL STATE ===
channels = []
azam_token = ""
last_token_refresh = None
ACCESS_CODES = {
    f"{os.environ.get('ACCESS_CODE1', '')}": {"device_id": None, "label": "MSOLID", "paid": True, "expires_at": None},
    f"{os.environ.get('ACCESS_CODE2', '')}": {"device_id": None, "label": "MPUME", "paid": True, "expires_at": None},
}

app.config["ACCESS_CODES"] = ACCESS_CODES
app.ACCESS_CODES = ACCESS_CODES


def get_mysql_connection():
    """Return a MySQL connection if credentials are configured; otherwise return None."""
    if mysql.connector is None or not MYSQL_USER or not MYSQL_DB:
        return None

    try:
        return mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            autocommit=True,
            charset="utf8mb4",
        )
    except Exception as exc:
        print(f"MySQL connection failed: {exc}")
        return None


def init_database():
    """Create the tables needed for persistent code storage."""
    conn = get_mysql_connection()
    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS access_codes (
                    code VARCHAR(20) PRIMARY KEY,
                    label VARCHAR(200) NOT NULL,
                    device_id VARCHAR(255) NULL,
                    paid BOOLEAN NOT NULL DEFAULT TRUE,
                    expires_at DATETIME NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        return True
    except Exception as exc:
        print(f"MySQL init error: {exc}")
        return False
    finally:
        conn.close()


def load_access_codes_from_mysql():
    """Load access codes from MySQL if available."""
    conn = get_mysql_connection()
    if conn is None:
        return {}

    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM access_codes ORDER BY created_at DESC")
            rows = cursor.fetchall()

        result = {}
        for row in rows:
            expires_at = row.get("expires_at")
            if hasattr(expires_at, "isoformat"):
                expires_at_value = expires_at.isoformat()
            else:
                expires_at_value = expires_at

            result[str(row["code"])] = {
                "device_id": row.get("device_id"),
                "label": row.get("label", "Customer"),
                "paid": bool(row.get("paid", True)),
                "expires_at": expires_at_value,
            }
        return result
    except Exception as exc:
        print(f"MySQL load error: {exc}")
        return {}
    finally:
        conn.close()


def save_access_code_to_mysql(code, details):
    """Store a single access code in MySQL."""
    conn = get_mysql_connection()
    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO access_codes (code, label, device_id, paid, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    label = VALUES(label),
                    device_id = VALUES(device_id),
                    paid = VALUES(paid),
                    expires_at = VALUES(expires_at)
                """,
                (code, details.get("label", "Customer"), details.get("device_id"), bool(details.get("paid", True)), details.get("expires_at"))
            )
        return True
    except Exception as exc:
        print(f"MySQL save error: {exc}")
        return False
    finally:
        conn.close()


def refresh_access_codes_state():
    """Refresh global access codes from MySQL if configured."""
    mysql_codes = load_access_codes_from_mysql()
    if mysql_codes:
        global ACCESS_CODES
        ACCESS_CODES = mysql_codes
        app.config["ACCESS_CODES"] = ACCESS_CODES
        app.ACCESS_CODES = ACCESS_CODES
        return True
    return False


init_database()
refresh_access_codes_state()

# === SUPABASE QUERY ===
def supabase_query(table):
    """Fetch data from Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&order=sort_order.asc"
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Supabase error: {e}")
        return []

# === TOKEN REFRESH ===
def refresh_token():
    """Refresh Azam token from Supabase function"""
    global azam_token, last_token_refresh
    
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/functions/v1/cdn-token"
        data = {"t": int(datetime.now().timestamp() * 1000)}
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if isinstance(result, dict) and "token" in result:
            azam_token = result["token"]
            last_token_refresh = datetime.now()
            return True
    except Exception as e:
        print(f"Token refresh error: {e}")
    
    return False

# === LOAD CHANNELS ===
def load_channels():
    """Load all channels from Supabase"""
    global channels
    channels = supabase_query("channels")
    refresh_token()
    return channels

# === ROUTES ===

@app.route('/')
def index():
    """Serve main page"""
    return render_template('index.html')

@app.route('/api/verify-pin', methods=['POST'])
def verify_pin():
    """Verify admin PIN or a unique access code bound to one device."""
    data = request.json or {}
    pin = str(data.get('pin', '')).strip()
    device_id = str(data.get('device_id', '')).strip() or request.headers.get('X-Device-Id', '').strip()

    if not device_id:
        return jsonify({"success": False, "error": "Device ID is required"}), 400

    if pin == PIN:
        return jsonify({"success": True, "mode": "admin"})

    code = ACCESS_CODES.get(pin)
    if not code:
        return jsonify({"success": False, "error": "Wrong access code"}), 401

    if not code.get("paid", True):
        return jsonify({"success": False, "error": "This code has not been paid for yet"}), 401

    expires_at = code.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                return jsonify({"success": False, "error": "This code has expired"}), 401
        except ValueError:
            pass

    current_device = code.get("device_id")
    if current_device in (None, device_id):
        ACCESS_CODES[pin]["device_id"] = device_id
        save_access_code_to_mysql(pin, ACCESS_CODES[pin])
        return jsonify({"success": True, "mode": "member", "label": code.get("label", "Customer")})

    return jsonify({"success": False, "error": "This code is already in use on another device"}), 401

@app.route('/api/access-codes', methods=['GET', 'POST'])
def manage_access_codes():
    """List or create access codes for customers."""
    if request.method == 'GET':
        return jsonify(ACCESS_CODES)

    data = request.json or {}
    custom_code = str(data.get('code', '')).strip()
    label = str(data.get('label', 'Customer')).strip() or 'Customer'
    paid = bool(data.get('paid', True))
    expires_days = int(data.get('expires_days', 30) or 30)

    if custom_code:
        code = custom_code
    else:
        import random
        code = str(random.randint(1000, 9999))
        while code in ACCESS_CODES:
            code = str(random.randint(1000, 9999))

    expiry = (datetime.now() + timedelta(days=expires_days)).isoformat()
    ACCESS_CODES[code] = {
        "device_id": None,
        "label": label,
        "paid": paid,
        "expires_at": expiry if paid else None,
    }
    save_access_code_to_mysql(code, ACCESS_CODES[code])
    return jsonify({"success": True, "code": code, "label": label, "paid": paid, "expires_at": expiry if paid else None})

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page to protect access-code management."""
    if request.method == 'POST':
        entered_pin = str(request.form.get('pin', '')).strip()
        if entered_pin == PIN:
            session['admin_logged_in'] = True
            return redirect(url_for('access_code_admin'))
        return render_template('admin_login.html', error='Wrong admin PIN')

    if session.get('admin_logged_in'):
        return redirect(url_for('access_code_admin'))

    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/access-codes')
def access_code_admin():
    """Admin page to generate unique access codes."""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('access_codes.html', access_codes=ACCESS_CODES)

@app.route('/api/channels', methods=['GET'])
def get_channels():
    """Get all channels"""
    if not channels:
        load_channels()
    
    # Filter active channels
    active = [c for c in channels if c.get('active', True)]
    return jsonify(active)

@app.route('/api/channels/filter', methods=['POST'])
def filter_channels():
    """Filter channels by category and search"""
    data = request.json
    category = data.get('category', 'all')
    search = data.get('search', '').lower()
    
    if not channels:
        load_channels()
    
    # Filter active channels
    filtered = [c for c in channels if c.get('active', True)]
    
    # Category filtering
    category_keys = {
        'sports': ["sport","premier","tnt","uefa","ufc","champion","bein","redbull","barca","real madrid","wwe","dazan","football"],
        'movies': ["movie","sinema","horizon","axn","amc","drama","perry","kix","series","a3"],
        'entertainment': ["music","canal","vctv","crown","cheka","utv","wasafi","zamaradi","tbc","zbc","abood","ruken","nat_geo","baby","cartoon","cbeebies","bbc"]
    }
    
    if category == 'free':
        filtered = [c for c in filtered if c.get('is_free', False)]
    elif category in category_keys:
        filtered = [c for c in filtered if any(k in c.get('name', '').lower() for k in category_keys[category])]
    
    # Search filtering
    if search:
        filtered = [c for c in filtered if search in c.get('name', '').lower()]
    
    return jsonify(filtered)

@app.route('/api/token', methods=['GET'])
def get_token():
    """Get current Azam token"""
    global azam_token, last_token_refresh
    
    # Refresh if needed (every 30 seconds)
    if last_token_refresh is None or datetime.now() - last_token_refresh > timedelta(seconds=30):
        refresh_token()
    
    return jsonify({"token": azam_token})

@app.route('/api/channel/<channel_id>', methods=['GET'])
def get_channel(channel_id):
    """Get specific channel details"""
    if not channels:
        load_channels()
    
    channel = next((c for c in channels if c.get('id') == channel_id), None)
    
    if channel:
        # Ensure we have fresh token
        refresh_token()
        return jsonify(channel)
    else:
        return jsonify({"error": "Channel not found"}), 404

@app.route('/api/direct-url', methods=['POST'])
def direct_url():
    """Convert DB channel URL to direct Azam URL with fresh token"""
    data = request.json
    url = data.get('url', '')
    
    global azam_token
    
    if not url:
        return jsonify({"url": ""})
    
    # Refresh token if needed
    if not azam_token or (last_token_refresh and datetime.now() - last_token_refresh > timedelta(seconds=25)):
        refresh_token()
    
    processed_url = url
    
    # Decode azam-resolve wrapper if present
    if "azam-resolve" in processed_url or "?u=" in processed_url:
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            parsed = urlparse(processed_url)
            query = parse_qs(parsed.query)
            if 'u' in query:
                processed_url = unquote(query['u'][0])
        except:
            pass
    
    # Inject fresh token if present
    if azam_token and '/tok_' in processed_url:
        import re
        processed_url = re.sub(r'/tok_[^/]+/', f'/tok_{azam_token}/', processed_url)
    
    return jsonify({"url": processed_url})

# === BACKGROUND TASKS ===
def init_app():
    """Initialize app on startup"""
    load_channels()
    
    # Schedule periodic token refresh
    import threading
    def refresh_loop():
        while True:
            import time
            time.sleep(30)
            refresh_token()
    
    refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
    refresh_thread.start()

# === ERROR HANDLERS ===
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Server error"}), 500

# === MAIN ===
if __name__ == '__main__':
    init_app()
    app.run(debug=FLASK_DEBUG, host='0.0.0.0', port=PORT)
