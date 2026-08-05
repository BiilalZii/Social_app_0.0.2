# -*- coding: utf-8 -*-
"""
تطبيق إدارة قسم الخدمات الاجتماعية للموظفين - النسخة المحسّنة
Employee Social Services Management System - Enhanced
"""

from flask import Flask, render_template, request, redirect, url_for, flash, g, make_response
import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "social_services_secret_key_2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.environ.get("DB_DIR", BASE_DIR)
try:
    test_path = os.path.join(DB_DIR, ".write_test")
    with open(test_path, "w") as f:
        f.write("ok")
    os.remove(test_path)
except Exception:
    DB_DIR = "/tmp"

DATABASE = os.path.join(DB_DIR, "social_services.db")


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS Employee (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Name TEXT NOT NULL,
            Sex TEXT CHECK(Sex IN ('ذكر', 'أنثى')),
            RIP TEXT,
            Name_AR TEXT,
            Department TEXT,
            Phone TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS AIDE_TYPE (
            Type_AIDE TEXT PRIMARY KEY,
            Value REAL DEFAULT 0,
            Description TEXT
        );

        CREATE TABLE IF NOT EXISTS Credit (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Employee_ID INTEGER NOT NULL,
            Type_Credit TEXT NOT NULL,
            Montant REAL NOT NULL,
            N_check TEXT,
            D_check TEXT,
            Months INTEGER DEFAULT 10,
            Status TEXT DEFAULT 'نشط',
            Notes TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (Employee_ID) REFERENCES Employee(ID) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS AIDE (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Employee_ID INTEGER NOT NULL,
            Type_AIDE TEXT NOT NULL,
            Type_Doc TEXT,
            N_Doc TEXT,
            Date_Doc TEXT,
            Montant REAL,
            Status TEXT DEFAULT 'مقبول',
            Notes TEXT,
            Created_At TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (Employee_ID) REFERENCES Employee(ID) ON DELETE CASCADE,
            FOREIGN KEY (Type_AIDE) REFERENCES AIDE_TYPE(Type_AIDE)
        );

        CREATE TABLE IF NOT EXISTS Settings (
            Key TEXT PRIMARY KEY,
            Value TEXT
        );
    """)

    types = [
        ("ولادة طفل", 15000, "منحة ولادة"),
        ("ختان طفل", 8000, "منحة ختان"),
        ("زواج الموظف", 25000, "منحة زواج"),
        ("وفاة والد أو والدة", 20000, "منحة وفاة والد/والدة"),
        ("وفاة أحد الأبناء", 20000, "منحة وفاة ابن/ابنة"),
        ("عمرة", 50000, "منحة عمرة"),
        ("حج", 100000, "منحة حج"),
    ]
    for t, v, d in types:
        conn.execute(
            "INSERT OR IGNORE INTO AIDE_TYPE (Type_AIDE, Value, Description) VALUES (?, ?, ?)",
            (t, v, d)
        )

    # الميزانية الافتراضية
    conn.execute("INSERT OR IGNORE INTO Settings (Key, Value) VALUES ('budget_total', '5000000')")
    conn.execute("INSERT OR IGNORE INTO Settings (Key, Value) VALUES ('budget_year', ?)", (str(datetime.now().year),))
    conn.execute("INSERT OR IGNORE INTO Settings (Key, Value) VALUES ('office_name', 'مكتب الخدمات الاجتماعية')")
    conn.commit()
    conn.close()


try:
    init_db()
except Exception as e:
    print(f"Warning: Could not init DB: {e}")


def get_setting(key, default=""):
    db = get_db()
    row = db.execute("SELECT Value FROM Settings WHERE Key=?", (key,)).fetchone()
    return row["Value"] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO Settings (Key, Value) VALUES (?, ?)", (key, str(value)))
    db.commit()


def get_budget_stats():
    db = get_db()
    total_budget = float(get_setting("budget_total", "5000000"))
    spent_aides = db.execute("SELECT COALESCE(SUM(Montant),0) FROM AIDE WHERE Status='مقبول'").fetchone()[0]
    spent_credits = db.execute("SELECT COALESCE(SUM(Montant),0) FROM Credit WHERE Status='نشط'").fetchone()[0]
    total_spent = spent_aides + spent_credits
    remaining = total_budget - total_spent
    return {
        "total": total_budget,
        "spent_aides": spent_aides,
        "spent_credits": spent_credits,
        "total_spent": total_spent,
        "remaining": remaining,
        "percent_used": round((total_spent / total_budget * 100) if total_budget else 0, 1)
    }


# ==================== الرئيسية ====================
@app.route("/")
def index():
    db = get_db()
    try:
        stats = {
            "employees": db.execute("SELECT COUNT(*) FROM Employee").fetchone()[0],
            "credits_active": db.execute("SELECT COUNT(*) FROM Credit WHERE Status='نشط'").fetchone()[0],
            "credits_total": db.execute("SELECT COUNT(*) FROM Credit").fetchone()[0],
            "aides": db.execute("SELECT COUNT(*) FROM AIDE").fetchone()[0],
            "aides_accepted": db.execute("SELECT COUNT(*) FROM AIDE WHERE Status='مقبول'").fetchone()[0],
            "total_credit": db.execute("SELECT COALESCE(SUM(Montant),0) FROM Credit WHERE Status='نشط'").fetchone()[0],
            "total_aide": db.execute("SELECT COALESCE(SUM(Montant),0) FROM AIDE WHERE Status='مقبول'").fetchone()[0],
        }
        # آخر 5 عمليات
        recent_aides = db.execute("""
            SELECT a.*, e.Name_AR, e.Name FROM AIDE a
            JOIN Employee e ON a.Employee_ID = e.ID
            ORDER BY a.ID DESC LIMIT 5
        """).fetchall()
        recent_credits = db.execute("""
            SELECT c.*, e.Name_AR, e.Name FROM Credit c
            JOIN Employee e ON c.Employee_ID = e.ID
            ORDER BY c.ID DESC LIMIT 5
        """).fetchall()
        # إحصائيات حسب نوع المنحة
        aide_by_type = db.execute("""
            SELECT Type_AIDE, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
            FROM AIDE WHERE Status='مقبول' GROUP BY Type_AIDE ORDER BY total DESC
        """).fetchall()
    except Exception:
        init_db()
        stats = {k: 0 for k in ["employees","credits_active","credits_total","aides","aides_accepted","total_credit","total_aide"]}
        recent_aides, recent_credits, aide_by_type = [], [], []

    budget = get_budget_stats()
    office_name = get_setting("office_name", "مكتب الخدمات الاجتماعية")
    return render_template("index.html", stats=stats, budget=budget, recent_aides=recent_aides,
                           recent_credits=recent_credits, aide_by_type=aide_by_type, office_name=office_name)


# ==================== البحث ====================
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = {"employees": [], "credits": [], "aides": []}
    if q:
        db = get_db()
        like = f"%{q}%"
        results["employees"] = db.execute("""
            SELECT * FROM Employee
            WHERE Name LIKE ? OR Name_AR LIKE ? OR RIP LIKE ? OR Phone LIKE ? OR Department LIKE ?
            ORDER BY ID DESC LIMIT 50
        """, (like, like, like, like, like)).fetchall()
        results["credits"] = db.execute("""
            SELECT c.*, e.Name, e.Name_AR FROM Credit c
            JOIN Employee e ON c.Employee_ID = e.ID
            WHERE e.Name LIKE ? OR e.Name_AR LIKE ? OR c.Type_Credit LIKE ? OR c.N_check LIKE ? OR c.Status LIKE ?
            ORDER BY c.ID DESC LIMIT 50
        """, (like, like, like, like, like)).fetchall()
        results["aides"] = db.execute("""
            SELECT a.*, e.Name, e.Name_AR FROM AIDE a
            JOIN Employee e ON a.Employee_ID = e.ID
            WHERE e.Name LIKE ? OR e.Name_AR LIKE ? OR a.Type_AIDE LIKE ? OR a.N_Doc LIKE ? OR a.Status LIKE ?
            ORDER BY a.ID DESC LIMIT 50
        """, (like, like, like, like, like)).fetchall()
    return render_template("search.html", q=q, results=results)


# ==================== الميزانية والإعدادات ====================
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        set_setting("budget_total", request.form.get("budget_total", "0"))
        set_setting("budget_year", request.form.get("budget_year", str(datetime.now().year)))
        set_setting("office_name", request.form.get("office_name", "مكتب الخدمات الاجتماعية"))
        flash("تم حفظ الإعدادات بنجاح", "success")
        return redirect(url_for("settings"))
    budget = get_budget_stats()
    return render_template("settings.html",
                           budget_total=get_setting("budget_total"),
                           budget_year=get_setting("budget_year"),
                           office_name=get_setting("office_name"),
                           budget=budget)


# ==================== التقارير ====================
@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/reports/summary")
def report_summary():
    db = get_db()
    year = request.args.get("year", str(datetime.now().year))
    budget = get_budget_stats()

    employees_count = db.execute("SELECT COUNT(*) FROM Employee").fetchone()[0]
    credits = db.execute("""
        SELECT Status, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
        FROM Credit GROUP BY Status
    """).fetchall()
    aides = db.execute("""
        SELECT Status, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
        FROM AIDE GROUP BY Status
    """).fetchall()
    aides_by_type = db.execute("""
        SELECT Type_AIDE, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
        FROM AIDE WHERE Status='مقبول' GROUP BY Type_AIDE ORDER BY total DESC
    """).fetchall()
    credits_by_type = db.execute("""
        SELECT Type_Credit, COUNT(*) as cnt, COALESCE(SUM(Montant),0) as total
        FROM Credit GROUP BY Type_Credit
    """).fetchall()

    office_name = get_setting("office_name")
    return render_template("report_summary.html",
                           year=year, budget=budget, employees_count=employees_count,
                           credits=credits, aides=aides, aides_by_type=aides_by_type,
                           credits_by_type=credits_by_type, office_name=office_name,
                           now=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/reports/aides")
def report_aides():
    db = get_db()
    status = request.args.get("status", "")
    type_aide = request.args.get("type", "")
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    query = """
        SELECT a.*, e.Name, e.Name_AR, e.RIP, e.Department
        FROM AIDE a JOIN Employee e ON a.Employee_ID = e.ID WHERE 1=1
    """
    params = []
    if status:
        query += " AND a.Status=?"
        params.append(status)
    if type_aide:
        query += " AND a.Type_AIDE=?"
        params.append(type_aide)
    if from_date:
        query += " AND date(a.Created_At) >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date(a.Created_At) <= ?"
        params.append(to_date)
    query += " ORDER BY a.ID DESC"

    rows = db.execute(query, params).fetchall()
    total = sum(r["Montant"] or 0 for r in rows)
    types = db.execute("SELECT Type_AIDE FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    office_name = get_setting("office_name")
    return render_template("report_aides.html", rows=rows, total=total, types=types,
                           status=status, type_aide=type_aide, from_date=from_date, to_date=to_date,
                           office_name=office_name, now=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/reports/credits")
def report_credits():
    db = get_db()
    status = request.args.get("status", "")
    type_credit = request.args.get("type", "")

    query = """
        SELECT c.*, e.Name, e.Name_AR, e.RIP, e.Department
        FROM Credit c JOIN Employee e ON c.Employee_ID = e.ID WHERE 1=1
    """
    params = []
    if status:
        query += " AND c.Status=?"
        params.append(status)
    if type_credit:
        query += " AND c.Type_Credit=?"
        params.append(type_credit)
    query += " ORDER BY c.ID DESC"

    rows = db.execute(query, params).fetchall()
    total = sum(r["Montant"] or 0 for r in rows)
    office_name = get_setting("office_name")
    return render_template("report_credits.html", rows=rows, total=total,
                           status=status, type_credit=type_credit,
                           office_name=office_name, now=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/reports/employee/<int:id>")
def report_employee(id):
    db = get_db()
    emp = db.execute("SELECT * FROM Employee WHERE ID=?", (id,)).fetchone()
    if not emp:
        flash("الموظف غير موجود", "danger")
        return redirect(url_for("employees"))
    credits = db.execute("SELECT * FROM Credit WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    aides = db.execute("SELECT * FROM AIDE WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    total_credits = sum(c["Montant"] or 0 for c in credits)
    total_aides = sum(a["Montant"] or 0 for a in aides if a["Status"] == "مقبول")
    office_name = get_setting("office_name")
    return render_template("report_employee.html", emp=emp, credits=credits, aides=aides,
                           total_credits=total_credits, total_aides=total_aides,
                           office_name=office_name, now=datetime.now().strftime("%Y-%m-%d %H:%M"))


# ==================== الموظفين ====================
@app.route("/employees")
def employees():
    db = get_db()
    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        rows = db.execute("""
            SELECT * FROM Employee
            WHERE Name LIKE ? OR Name_AR LIKE ? OR RIP LIKE ? OR Phone LIKE ? OR Department LIKE ?
            ORDER BY ID DESC
        """, (like, like, like, like, like)).fetchall()
    else:
        rows = db.execute("SELECT * FROM Employee ORDER BY ID DESC").fetchall()
    return render_template("employees.html", employees=rows, q=q)


@app.route("/employees/add", methods=["GET", "POST"])
def add_employee():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("الاسم مطلوب", "danger")
            return redirect(url_for("add_employee"))
        db = get_db()
        db.execute("""
            INSERT INTO Employee (Name, Sex, RIP, Name_AR, Department, Phone)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, request.form.get("sex"), request.form.get("rip", "").strip(),
              request.form.get("name_ar", "").strip(), request.form.get("department", "").strip(),
              request.form.get("phone", "").strip()))
        db.commit()
        flash("تم إضافة الموظف بنجاح", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=None)


@app.route("/employees/edit/<int:id>", methods=["GET", "POST"])
def edit_employee(id):
    db = get_db()
    employee = db.execute("SELECT * FROM Employee WHERE ID=?", (id,)).fetchone()
    if not employee:
        flash("الموظف غير موجود", "danger")
        return redirect(url_for("employees"))
    if request.method == "POST":
        db.execute("""
            UPDATE Employee SET Name=?, Sex=?, RIP=?, Name_AR=?, Department=?, Phone=? WHERE ID=?
        """, (request.form.get("name", "").strip(), request.form.get("sex"),
              request.form.get("rip", "").strip(), request.form.get("name_ar", "").strip(),
              request.form.get("department", "").strip(), request.form.get("phone", "").strip(), id))
        db.commit()
        flash("تم تعديل بيانات الموظف", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=employee)


@app.route("/employees/delete/<int:id>")
def delete_employee(id):
    db = get_db()
    db.execute("DELETE FROM Employee WHERE ID=?", (id,))
    db.commit()
    flash("تم حذف الموظف", "success")
    return redirect(url_for("employees"))


@app.route("/employees/view/<int:id>")
def view_employee(id):
    db = get_db()
    emp = db.execute("SELECT * FROM Employee WHERE ID=?", (id,)).fetchone()
    if not emp:
        flash("الموظف غير موجود", "danger")
        return redirect(url_for("employees"))
    credits = db.execute("SELECT * FROM Credit WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    aides = db.execute("SELECT * FROM AIDE WHERE Employee_ID=? ORDER BY ID DESC", (id,)).fetchall()
    return render_template("employee_view.html", emp=emp, credits=credits, aides=aides)


# ==================== القروض ====================
@app.route("/credits")
def credits():
    db = get_db()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = """
        SELECT c.*, e.Name, e.Name_AR FROM Credit c
        JOIN Employee e ON c.Employee_ID = e.ID WHERE 1=1
    """
    params = []
    if q:
        like = f"%{q}%"
        query += " AND (e.Name LIKE ? OR e.Name_AR LIKE ? OR c.Type_Credit LIKE ? OR c.N_check LIKE ?)"
        params.extend([like, like, like, like])
    if status:
        query += " AND c.Status=?"
        params.append(status)
    query += " ORDER BY c.ID DESC"
    rows = db.execute(query, params).fetchall()
    total = sum(r["Montant"] or 0 for r in rows if r["Status"] == "نشط")
    return render_template("credits.html", credits=rows, q=q, status=status, total=total)


@app.route("/credits/add", methods=["GET", "POST"])
def add_credit():
    db = get_db()
    employees = db.execute("SELECT ID, Name, Name_AR FROM Employee ORDER BY Name").fetchall()
    if request.method == "POST":
        emp_id = request.form.get("employee_id")
        type_credit = request.form.get("type_credit")
        montant = request.form.get("montant")
        if not emp_id or not type_credit or not montant:
            flash("يرجى ملء جميع الحقول المطلوبة", "danger")
            return redirect(url_for("add_credit"))
        db.execute("""
            INSERT INTO Credit (Employee_ID, Type_Credit, Montant, N_check, D_check, Months, Notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (emp_id, type_credit, float(montant), request.form.get("n_check", "").strip(),
              request.form.get("d_check", "").strip(), int(request.form.get("months", 10)),
              request.form.get("notes", "").strip()))
        db.commit()
        flash("تم تسجيل القرض بنجاح", "success")
        return redirect(url_for("credits"))
    return render_template("credit_form.html", employees=employees, credit=None)


@app.route("/credits/edit/<int:id>", methods=["GET", "POST"])
def edit_credit(id):
    db = get_db()
    credit = db.execute("SELECT * FROM Credit WHERE ID=?", (id,)).fetchone()
    if not credit:
        flash("القرض غير موجود", "danger")
        return redirect(url_for("credits"))
    employees = db.execute("SELECT ID, Name, Name_AR FROM Employee ORDER BY Name").fetchall()
    if request.method == "POST":
        db.execute("""
            UPDATE Credit SET Employee_ID=?, Type_Credit=?, Montant=?, N_check=?, D_check=?, Months=?, Status=?, Notes=?
            WHERE ID=?
        """, (request.form.get("employee_id"), request.form.get("type_credit"), float(request.form.get("montant")),
              request.form.get("n_check", "").strip(), request.form.get("d_check", "").strip(),
              int(request.form.get("months", 10)), request.form.get("status"),
              request.form.get("notes", "").strip(), id))
        db.commit()
        flash("تم تعديل القرض", "success")
        return redirect(url_for("credits"))
    return render_template("credit_form.html", employees=employees, credit=credit)


@app.route("/credits/delete/<int:id>")
def delete_credit(id):
    db = get_db()
    db.execute("DELETE FROM Credit WHERE ID=?", (id,))
    db.commit()
    flash("تم حذف القرض", "success")
    return redirect(url_for("credits"))


# ==================== المنح ====================
@app.route("/aides")
def aides():
    db = get_db()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    type_aide = request.args.get("type", "")
    query = """
        SELECT a.*, e.Name, e.Name_AR FROM AIDE a
        JOIN Employee e ON a.Employee_ID = e.ID WHERE 1=1
    """
    params = []
    if q:
        like = f"%{q}%"
        query += " AND (e.Name LIKE ? OR e.Name_AR LIKE ? OR a.Type_AIDE LIKE ? OR a.N_Doc LIKE ?)"
        params.extend([like, like, like, like])
    if status:
        query += " AND a.Status=?"
        params.append(status)
    if type_aide:
        query += " AND a.Type_AIDE=?"
        params.append(type_aide)
    query += " ORDER BY a.ID DESC"
    rows = db.execute(query, params).fetchall()
    total = sum(r["Montant"] or 0 for r in rows if r["Status"] == "مقبول")
    types = db.execute("SELECT Type_AIDE FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    return render_template("aides.html", aides=rows, q=q, status=status, type_aide=type_aide, total=total, types=types)


@app.route("/aides/add", methods=["GET", "POST"])
def add_aide():
    db = get_db()
    employees = db.execute("SELECT ID, Name, Name_AR FROM Employee ORDER BY Name").fetchall()
    aide_types = db.execute("SELECT * FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    if request.method == "POST":
        emp_id = request.form.get("employee_id")
        type_aide = request.form.get("type_aide")
        if not emp_id or not type_aide:
            flash("يرجى ملء الحقول المطلوبة", "danger")
            return redirect(url_for("add_aide"))
        montant = request.form.get("montant")
        if not montant:
            # استخدم القيمة الافتراضية من نوع المنحة
            t = db.execute("SELECT Value FROM AIDE_TYPE WHERE Type_AIDE=?", (type_aide,)).fetchone()
            montant = t["Value"] if t else 0
        db.execute("""
            INSERT INTO AIDE (Employee_ID, Type_AIDE, Type_Doc, N_Doc, Date_Doc, Montant, Notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (emp_id, type_aide, request.form.get("type_doc", "").strip(),
              request.form.get("n_doc", "").strip(), request.form.get("date_doc", "").strip(),
              float(montant), request.form.get("notes", "").strip()))
        db.commit()
        flash("تم تسجيل المنحة بنجاح", "success")
        return redirect(url_for("aides"))
    return render_template("aide_form.html", employees=employees, aide_types=aide_types, aide=None)


@app.route("/aides/edit/<int:id>", methods=["GET", "POST"])
def edit_aide(id):
    db = get_db()
    aide = db.execute("SELECT * FROM AIDE WHERE ID=?", (id,)).fetchone()
    if not aide:
        flash("المنحة غير موجودة", "danger")
        return redirect(url_for("aides"))
    employees = db.execute("SELECT ID, Name, Name_AR FROM Employee ORDER BY Name").fetchall()
    aide_types = db.execute("SELECT * FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    if request.method == "POST":
        db.execute("""
            UPDATE AIDE SET Employee_ID=?, Type_AIDE=?, Type_Doc=?, N_Doc=?, Date_Doc=?, Montant=?, Status=?, Notes=?
            WHERE ID=?
        """, (request.form.get("employee_id"), request.form.get("type_aide"),
              request.form.get("type_doc", "").strip(), request.form.get("n_doc", "").strip(),
              request.form.get("date_doc", "").strip(), float(request.form.get("montant") or 0),
              request.form.get("status"), request.form.get("notes", "").strip(), id))
        db.commit()
        flash("تم تعديل المنحة", "success")
        return redirect(url_for("aides"))
    return render_template("aide_form.html", employees=employees, aide_types=aide_types, aide=aide)


@app.route("/aides/delete/<int:id>")
def delete_aide(id):
    db = get_db()
    db.execute("DELETE FROM AIDE WHERE ID=?", (id,))
    db.commit()
    flash("تم حذف المنحة", "success")
    return redirect(url_for("aides"))


# ==================== أنواع المنح ====================
@app.route("/aide-types")
def aide_types():
    db = get_db()
    rows = db.execute("SELECT * FROM AIDE_TYPE ORDER BY Type_AIDE").fetchall()
    return render_template("aide_types.html", types=rows)


@app.route("/aide-types/edit/<path:type_aide>", methods=["GET", "POST"])
def edit_aide_type(type_aide):
    db = get_db()
    t = db.execute("SELECT * FROM AIDE_TYPE WHERE Type_AIDE=?", (type_aide,)).fetchone()
    if not t:
        flash("النوع غير موجود", "danger")
        return redirect(url_for("aide_types"))
    if request.method == "POST":
        db.execute("UPDATE AIDE_TYPE SET Value=?, Description=? WHERE Type_AIDE=?",
                   (float(request.form.get("value") or 0), request.form.get("description", "").strip(), type_aide))
        db.commit()
        flash("تم تحديث نوع المنحة", "success")
        return redirect(url_for("aide_types"))
    return render_template("aide_type_form.html", t=t)


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  تطبيق إدارة الخدمات الاجتماعية - النسخة المحسّنة")
    print(f"  Database: {DATABASE}")
    print(f"  http://127.0.0.1:{port}")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=port)
