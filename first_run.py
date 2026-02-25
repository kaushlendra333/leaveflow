"""
Run this ONCE before starting the app.
Usage: python first_run.py
"""
import os, sys

print("\n🌿 LeaveFlow — First-Time Setup")
print("=" * 40)

# Step 1: Read .env
if not os.path.exists('.env'):
    print("\n❌ .env file not found!")
    print("   Create it first, then run this script again.")
    sys.exit(1)

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

host = env.get('MYSQL_HOST', 'localhost')
user = env.get('MYSQL_USER', 'root')
pw   = env.get('MYSQL_PASSWORD', 'password')
db   = env.get('MYSQL_DB', 'leaveflow')

print(f"\n🗄️  Connecting to MySQL at {host} as '{user}'...")

try:
    import mysql.connector
except ImportError:
    print("   ❌ mysql-connector-python not installed.")
    print("      Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    conn = mysql.connector.connect(host=host, user=user, password=pw)
    print("   ✅ Connected to MySQL!")
except Exception as e:
    print(f"   ❌ Could not connect: {e}")
    print("\n   Check your MYSQL_PASSWORD in .env file.")
    sys.exit(1)

from werkzeug.security import generate_password_hash

cur = conn.cursor()
print(f"\n🏗️  Creating database '{db}' and tables...")
cur.execute(f"CREATE DATABASE IF NOT EXISTS {db}")
cur.execute(f"USE {db}")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(120) NOT NULL,
    email      VARCHAR(160) UNIQUE NOT NULL,
    password   VARCHAR(260) NOT NULL,
    department VARCHAR(100) DEFAULT 'General',
    role       ENUM('admin','employee') DEFAULT 'employee',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS leave_balance (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    leave_type ENUM('Annual','Sick','Casual','Maternity') NOT NULL,
    total_days INT DEFAULT 0,
    used_days  INT DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_bal(user_id, leave_type)
)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS leave_requests (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    leave_type    ENUM('Annual','Sick','Casual','Maternity') NOT NULL,
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    days          INT NOT NULL,
    reason        TEXT,
    status        ENUM('pending','approved','rejected','cancelled') DEFAULT 'pending',
    admin_comment TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
)""")

print("   ✅ Tables created!")

DEFAULTS = [('Annual',15),('Sick',10),('Casual',7),('Maternity',90)]

def add_user(name, email, pw_plain, dept, role):
    try:
        cur.execute(
            "INSERT INTO users(name,email,password,department,role) VALUES(%s,%s,%s,%s,%s)",
            (name, email, generate_password_hash(pw_plain), dept, role))
        uid = cur.lastrowid
        for lt, days in DEFAULTS:
            cur.execute(
                "INSERT INTO leave_balance(user_id,leave_type,total_days,used_days) VALUES(%s,%s,%s,0)",
                (uid, lt, days))
        conn.commit()
        return True
    except:
        return False

print("\n👤 Creating demo accounts...")
accounts = [
    ('Admin User', 'admin@company.com', 'admin123', 'HR',          'admin'),
    ('John Doe',   'john@company.com',  'emp123',   'Engineering', 'employee'),
    ('Sara Lee',   'sara@company.com',  'emp123',   'Marketing',   'employee'),
]
for args in accounts:
    ok = add_user(*args)
    print(f"   {'✅' if ok else '⏭️  Already exists —'} {args[1]}  /  {args[2]}")

cur.close()
conn.close()

print("\n" + "=" * 40)
print("🎉 Setup complete! Now run:\n")
print("   python app.py")
print("\n   Then open: http://localhost:5000")
print("=" * 40 + "\n")
