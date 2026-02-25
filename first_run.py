import os
import sys

print("\n🌿 LeaveFlow — First-Time Setup")
print("=" * 40)

host = os.environ.get('MYSQL_HOST', 'localhost')
user = os.environ.get('MYSQL_USER', 'root')
pw = os.environ.get('MYSQL_PASSWORD', '')
db = os.environ.get('MYSQL_DB', 'leaveflow')

print(f"Connecting to MySQL at {host}...")

try:
    import pymysql
    conn = pymysql.connect(host=host, user=user, password=pw, charset='utf8mb4')
    cursor = conn.cursor()
    print("✅ Connected!")

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db}`")
    cursor.execute(f"USE `{db}`")

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(200) NOT NULL,
        department VARCHAR(100),
        role VARCHAR(20) DEFAULT 'employee'
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS leave_balance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        leave_type VARCHAR(50),
        total_days INT DEFAULT 0,
        used_days INT DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS leave_requests (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        leave_type VARCHAR(50),
        start_date DATE,
        end_date DATE,
        days INT,
        reason TEXT,
        status VARCHAR(20) DEFAULT 'pending',
        admin_comment TEXT,
        applied_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    print("✅ Tables created!")

    from werkzeug.security import generate_password_hash

    # Admin account
    cursor.execute("SELECT * FROM users WHERE email='admin@company.com'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (name, email, password, department, role) VALUES (%s,%s,%s,%s,%s)",
            ('Admin', 'admin@company.com', generate_password_hash('admin123'), 'Management', 'admin'))
        conn.commit()
        admin_id = cursor.lastrowid
        for lt, days in [('Annual',15),('Sick',10),('Casual',7),('Maternity',90)]:
            cursor.execute("INSERT INTO leave_balance (user_id,leave_type,total_days,used_days) VALUES (%s,%s,%s,0)",
                (admin_id, lt, days))
        print("✅ Admin created: admin@company.com / admin123")

    # Employee accounts
    for name, email in [('John Doe','john@company.com'),('Sara Smith','sara@company.com')]:
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (name, email, password, department, role) VALUES (%s,%s,%s,%s,%s)",
                (name, email, generate_password_hash('emp123'), 'Engineering', 'employee'))
            conn.commit()
            emp_id = cursor.lastrowid
            for lt, days in [('Annual',15),('Sick',10),('Casual',7),('Maternity',90)]:
                cursor.execute("INSERT INTO leave_balance (user_id,leave_type,total_days,used_days) VALUES (%s,%s,%s,0)",
                    (emp_id, lt, days))
        print(f"✅ Employee created: {email} / emp123")

    conn.commit()
    conn.close()
    print("=" * 40)
    print("✅ Setup complete!")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)