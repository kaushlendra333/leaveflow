from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import pymysql
pymysql.install_as_MySQLdb()
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'leaveflow-secret-2024')

app.config['MYSQL_HOST']        = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER']        = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD']    = os.environ.get('MYSQL_PASSWORD', 'password')
app.config['MYSQL_DB']          = os.environ.get('MYSQL_DB', 'leaveflow')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

LEAVE_DEFAULTS = {'Annual': 15, 'Sick': 10, 'Casual': 7, 'Maternity': 90}
LEAVE_COLORS   = {'Annual': '#22c55e', 'Sick': '#ef4444', 'Casual': '#3b82f6', 'Maternity': '#a855f7'}

# ── Decorators ─────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ── Auth Routes ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (request.form['email'],))
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user['password'], request.form['password']):
            session.update({'user_id': user['id'], 'name': user['name'],
                            'role': user['role'], 'email': user['email'],
                            'department': user['department']})
            flash(f'Welcome back, {user["name"].split()[0]}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        pw   = generate_password_hash(request.form['password'])
        dept = request.form['department']
        role = request.form.get('role', 'employee')
        cur  = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cur.fetchone():
            flash('Email already registered.', 'danger')
            cur.close()
            return render_template('register.html')
        cur.execute("INSERT INTO users(name,email,password,department,role) VALUES(%s,%s,%s,%s,%s)",
                    (name, email, pw, dept, role))
        uid = cur.lastrowid
        for lt, days in LEAVE_DEFAULTS.items():
            cur.execute("INSERT INTO leave_balance(user_id,leave_type,total_days,used_days) VALUES(%s,%s,%s,0)",
                        (uid, lt, days))
        mysql.connection.commit()
        cur.close()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    cur = mysql.connection.cursor()
    uid = session['user_id']
    cur.execute("SELECT * FROM leave_balance WHERE user_id=%s", (uid,))
    balances = cur.fetchall()

    if session['role'] == 'admin':
        cur.execute("""SELECT lr.*,u.name,u.department FROM leave_requests lr
                       JOIN users u ON lr.user_id=u.id ORDER BY lr.applied_on DESC LIMIT 8""")
        recent = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE status='pending'")
        pending_count = cur.fetchone()['c']
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE role='employee'")
        emp_count = cur.fetchone()['c']
        cur.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE status='approved'")
        approved_count = cur.fetchone()['c']
    else:
        cur.execute("SELECT * FROM leave_requests WHERE user_id=%s ORDER BY applied_on DESC LIMIT 8", (uid,))
        recent = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE user_id=%s AND status='pending'", (uid,))
        pending_count = cur.fetchone()['c']
        emp_count = approved_count = None

    cur.close()
    return render_template('dashboard.html', balances=balances, recent=recent,
                           pending_count=pending_count, emp_count=emp_count,
                           approved_count=approved_count, leave_colors=LEAVE_COLORS)

# ── Employee Routes ────────────────────────────────────────────────────────────

@app.route('/apply', methods=['GET', 'POST'])
@login_required
def apply_leave():
    uid = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM leave_balance WHERE user_id=%s", (uid,))
    balances = {b['leave_type']: b for b in cur.fetchall()}

    if request.method == 'POST':
        lt     = request.form['leave_type']
        sd     = request.form['start_date']
        ed     = request.form['end_date']
        reason = request.form['reason']
        days   = (datetime.strptime(ed, '%Y-%m-%d') - datetime.strptime(sd, '%Y-%m-%d')).days + 1
        if days <= 0:
            flash('End date must be after start date.', 'danger')
        else:
            bal   = balances.get(lt)
            avail = (bal['total_days'] - bal['used_days']) if bal else 0
            if avail < days:
                flash(f'Only {avail} {lt} days remaining.', 'danger')
            else:
                cur.execute("""INSERT INTO leave_requests
                               (user_id,leave_type,start_date,end_date,days,reason,status)
                               VALUES(%s,%s,%s,%s,%s,%s,'pending')""",
                            (uid, lt, sd, ed, days, reason))
                mysql.connection.commit()
                flash('Leave application submitted!', 'success')
                cur.close()
                return redirect(url_for('my_leaves'))

    cur.close()
    return render_template('apply_leave.html', balances=balances,
                           today=date.today().isoformat(), leave_colors=LEAVE_COLORS)

@app.route('/my-leaves')
@login_required
def my_leaves():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM leave_requests WHERE user_id=%s ORDER BY applied_on DESC", (session['user_id'],))
    leaves = cur.fetchall()
    cur.close()
    return render_template('my_leaves.html', leaves=leaves, leave_colors=LEAVE_COLORS)

@app.route('/cancel/<int:lid>', methods=['POST'])
@login_required
def cancel_leave(lid):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM leave_requests WHERE id=%s AND user_id=%s", (lid, session['user_id']))
    leave = cur.fetchone()
    if leave and leave['status'] == 'pending':
        cur.execute("UPDATE leave_requests SET status='cancelled' WHERE id=%s", (lid,))
        mysql.connection.commit()
        flash('Leave request cancelled.', 'success')
    else:
        flash('Cannot cancel this request.', 'danger')
    cur.close()
    return redirect(url_for('my_leaves'))

# ── Admin Routes ───────────────────────────────────────────────────────────────

@app.route('/admin/leaves')
@admin_required
def admin_leaves():
    sf  = request.args.get('status', 'pending')
    cur = mysql.connection.cursor()
    if sf == 'all':
        cur.execute("""SELECT lr.*,u.name,u.department,u.email FROM leave_requests lr
                       JOIN users u ON lr.user_id=u.id ORDER BY lr.applied_on DESC""")
    else:
        cur.execute("""SELECT lr.*,u.name,u.department,u.email FROM leave_requests lr
                       JOIN users u ON lr.user_id=u.id
                       WHERE lr.status=%s ORDER BY lr.applied_on DESC""", (sf,))
    leaves = cur.fetchall()
    cur.close()
    return render_template('admin_leaves.html', leaves=leaves, status_filter=sf, leave_colors=LEAVE_COLORS)

@app.route('/admin/action/<int:lid>', methods=['POST'])
@admin_required
def leave_action(lid):
    action  = request.form['action']
    comment = request.form.get('comment', '')
    cur     = mysql.connection.cursor()
    cur.execute("SELECT * FROM leave_requests WHERE id=%s AND status='pending'", (lid,))
    leave   = cur.fetchone()
    if leave:
        cur.execute("UPDATE leave_requests SET status=%s, admin_comment=%s WHERE id=%s",
                    (action + 'd', comment, lid))
        if action == 'approve':
            cur.execute("""UPDATE leave_balance SET used_days=used_days+%s
                           WHERE user_id=%s AND leave_type=%s""",
                        (leave['days'], leave['user_id'], leave['leave_type']))
        mysql.connection.commit()
        flash(f'Leave {action}d successfully.', 'success')
    cur.close()
    return redirect(url_for('admin_leaves'))

@app.route('/admin/employees')
@admin_required
def admin_employees():
    cur = mysql.connection.cursor()
    cur.execute("""SELECT u.*,
        COALESCE(SUM(lb.total_days),0) AS total_days,
        COALESCE(SUM(lb.used_days),0)  AS used_days
        FROM users u LEFT JOIN leave_balance lb ON u.id=lb.user_id
        WHERE u.role='employee' GROUP BY u.id ORDER BY u.name""")
    employees = cur.fetchall()
    cur.close()
    return render_template('admin_employees.html', employees=employees)

@app.route('/admin/employee/<int:eid>')
@admin_required
def employee_detail(eid):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", (eid,))
    emp = cur.fetchone()
    cur.execute("SELECT * FROM leave_balance WHERE user_id=%s", (eid,))
    balances = cur.fetchall()
    cur.execute("SELECT * FROM leave_requests WHERE user_id=%s ORDER BY applied_on DESC", (eid,))
    leaves = cur.fetchall()
    cur.close()
    return render_template('employee_detail.html', emp=emp, balances=balances,
                           leaves=leaves, leave_colors=LEAVE_COLORS)

@app.route('/admin/update-balance', methods=['POST'])
@admin_required
def update_balance():
    cur = mysql.connection.cursor()
    cur.execute("UPDATE leave_balance SET total_days=%s WHERE user_id=%s AND leave_type=%s",
                (request.form['total_days'], request.form['user_id'], request.form['leave_type']))
    mysql.connection.commit()
    cur.close()
    flash('Balance updated.', 'success')
    return redirect(url_for('employee_detail', eid=request.form['user_id']))

if __name__ == '__main__':
    app.run(debug=True)
