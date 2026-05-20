import os
import re
from datetime import datetime
from functools import wraps

import mysql.connector
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "book_exchange_secret_key")

app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads", "book_ads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
UNIVERSITY_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@nu\.edu\.sa$")
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_\-#])[A-Za-z\d@$!%*?&_\-#]{8,}$")

import os
import mysql.connector




BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "ssl_ca": os.path.join(BASE_DIR, "ca.pem")
}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def fetch_all(query, params=()):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        return cursor.fetchall()
    except mysql.connector.Error as err:
        app.logger.error("Database fetch_all error: %s", err)
        return []
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def fetch_one(query, params=()):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        return cursor.fetchone()
    except mysql.connector.Error as err:
        app.logger.error("Database fetch_one error: %s", err)
        return None
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def execute_query(query, params=(), return_lastrowid=False):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(query, params)
        connection.commit()
        if return_lastrowid:
            return cursor.lastrowid
        return True
    except mysql.connector.Error as err:
        if connection and connection.is_connected():
            connection.rollback()
        app.logger.error("Database execute_query error: %s", err)
        return None if return_lastrowid else False
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def count_rows(table_name, where_clause="", params=()):
    row = fetch_one(f"SELECT COUNT(*) AS total FROM {table_name} {where_clause}", params)
    return row["total"] if row else 0


def allowed_image(filename):
    if not filename:
        return False
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def is_valid_university_email(email_value):
    if not email_value:
        return False
    return bool(UNIVERSITY_EMAIL_PATTERN.fullmatch(email_value))


def is_valid_password(password_value):
    if not password_value:
        return False
    return bool(PASSWORD_PATTERN.fullmatch(password_value))


def student_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("student_id"):
            flash("يرجى تسجيل الدخول كطالبة أولاً.", "error")
            return redirect(url_for("student_login"))
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            flash("يرجى تسجيل الدخول كمسؤولة نظام أولاً.", "error")
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)

    return wrapper


def parse_datetime_local(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def to_badge_class(status_value):
    mapping = {
        "بانتظار": "badge2 badge2--pending",
        "مقبول": "badge2 badge2--accepted",
        "مرفوض": "badge2 badge2--rejected",
        "ملغي": "badge2 badge2--cancel",
    }
    return mapping.get(status_value, "badge2")


@app.context_processor
def global_template_values():
    return {"current_year": datetime.now().year, "badge_class": to_badge_class}


@app.route("/")
def home_index():
    stats = {
        "books_count": count_rows("books"),
        "ads_count": count_rows("book_ads"),
        "available_ads": count_rows("book_ads", "WHERE ad_status = %s", ("متاح",)),
        "requests_count": count_rows("exchange_requests"),
    }
    return render_template("home/index.html", page_title="الرئيسية", stats=stats, active_page="home")


@app.route("/about")
def home_about():
    return render_template("home/about.html", page_title="حول المنصة", active_page="about")


@app.route("/students/signup", methods=["GET", "POST"])
def student_signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        university_email = request.form.get("university_email", "").strip().lower()
        major = request.form.get("major", "").strip()
        level = request.form.get("level", "").strip() or None
        password = request.form.get("password", "")

        if not all([full_name, university_email, major, password]):
            flash("يرجى ملء جميع الحقول المطلوبة.", "error")
            return redirect(url_for("student_signup"))

        if not is_valid_university_email(university_email):
            flash("يرجى إدخال بريد جامعي صالح بصيغة name@nu.edu.sa", "error")
            return redirect(url_for("student_signup"))

        if not is_valid_password(password):
            flash("كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حرف كبير وحرف صغير ورقم ورمز خاص.", "error")
            return redirect(url_for("student_signup"))

        exists = fetch_one(
            "SELECT student_id FROM students WHERE university_email = %s",
            (university_email,),
        )
        if exists:
            flash("هذا البريد الإلكتروني مستخدم بالفعل.", "error")
            return redirect(url_for("student_signup"))

        ok = execute_query(
            """
            INSERT INTO students (full_name, university_email, major, level, password)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (full_name, university_email, major, level, password),
        )

        if ok:
            flash("تم إنشاء الحساب بنجاح. يمكنك الآن تسجيل الدخول.", "success")
            return redirect(url_for("student_login"))

        flash("حصل خطأ أثناء إنشاء الحساب.", "error")

    return render_template("students/signup.html", page_title="تسجيل حساب", active_page="signup")


@app.route("/students/login", methods=["GET", "POST"])

def student_login():
    if session.get("student_id"):
        return redirect(url_for("student_ads"))

    if request.method == "POST":
        university_email = request.form.get("university_email", "").strip().lower()
        password = request.form.get("password", "")

        if not is_valid_university_email(university_email):
            flash("يرجى إدخال بريد جامعي صالح.", "error")
            return redirect(url_for("student_login"))

        student = fetch_one(
            """
            SELECT student_id, full_name
            FROM students
            WHERE university_email = %s AND password = %s
            """,
            (university_email, password),
        )

        if student:
            session["student_id"] = student["student_id"]
            session["student_name"] = student["full_name"]
            flash("تم تسجيل الدخول بنجاح.", "success")
            return redirect(url_for("student_ads"))

        flash("بيانات الدخول غير صحيحة.", "error")

    return render_template("students/login.html", page_title="تسجيل دخول الطالبة", active_page="login")


@app.route("/students/logout")

def student_logout():
    session.pop("student_id", None)
    session.pop("student_name", None)
    flash("تم تسجيل الخروج.", "success")
    return redirect(url_for("home_index"))


@app.route("/book_ads")
def student_ads():
    q = request.args.get("q", "").strip()
    major = request.args.get("major", "").strip()
    ad_type = request.args.get("ad_type", "").strip()
    ad_status = request.args.get("ad_status", "").strip()

    query = """
        SELECT
            ba.ad_id,
            ba.student_id,
            ba.ad_type,
            ba.copy_condition,
            ba.book_image,
            ba.delivery_method,
            ba.ad_status,
            ba.ad_date,
            b.book_title,
            b.course_name,
            b.major,
            b.short_description,
            s.full_name AS owner_name
        FROM book_ads ba
        JOIN books b ON b.book_id = ba.book_id
        JOIN students s ON s.student_id = ba.student_id
        WHERE 1=1
    """

    params = []
    if q:
        query += " AND (b.book_title LIKE %s OR b.course_name LIKE %s OR b.major LIKE %s)"
        like_term = f"%{q}%"
        params.extend([like_term, like_term, like_term])

    if major:
        query += " AND b.major = %s"
        params.append(major)

    if ad_type:
        query += " AND ba.ad_type = %s"
        params.append(ad_type)

    if ad_status and ad_status != "الكل":
        query += " AND ba.ad_status = %s"
        params.append(ad_status)

    query += " ORDER BY ba.ad_date DESC"

    ads = fetch_all(query, tuple(params))
    majors = fetch_all("SELECT DISTINCT major FROM books ORDER BY major")

    return render_template(
        "book_ads/list.html",
        page_title="الإعلانات",
        ads=ads,
        majors=majors,
        filters={"q": q, "major": major, "ad_type": ad_type, "ad_status": ad_status},
        active_page="ads",
    )


@app.route("/book_ads/<int:ad_id>")
def ad_details(ad_id):
    ad = fetch_one(
        """
        SELECT
            ba.ad_id,
            ba.student_id,
            ba.ad_type,
            ba.copy_condition,
            ba.book_image,
            ba.delivery_method,
            ba.ad_status,
            ba.ad_date,
            b.book_title,
            b.course_name,
            b.major,
            b.short_description,
            s.full_name AS owner_name
        FROM book_ads ba
        JOIN books b ON b.book_id = ba.book_id
        JOIN students s ON s.student_id = ba.student_id
        WHERE ba.ad_id = %s
        """,
        (ad_id,),
    )

    if not ad:
        flash("الإعلان غير موجود.", "error")
        return redirect(url_for("student_ads"))

    current_student_id = session.get("student_id")
    my_request = None
    if current_student_id:
        my_request = fetch_one(
            """
            SELECT request_id, request_status
            FROM exchange_requests
            WHERE ad_id = %s AND requester_student_id = %s
            """,
            (ad_id, current_student_id),
        )

    return render_template(
        "book_ads/details.html",
        page_title="تفاصيل الإعلان",
        ad=ad,
        my_request=my_request,
        active_page="ads",
    )


@app.route("/book_ads/<int:ad_id>/request", methods=["POST"])
@student_required
def create_exchange_request(ad_id):
    current_student_id = session["student_id"]

    ad = fetch_one("SELECT ad_id, student_id, ad_status FROM book_ads WHERE ad_id = %s", (ad_id,))
    if not ad:
        flash("الإعلان غير موجود.", "error")
        return redirect(url_for("student_ads"))

    if ad["student_id"] == current_student_id:
        flash("لا يمكنك طلب إعلانك الشخصي.", "error")
        return redirect(url_for("ad_details", ad_id=ad_id))

    if ad["ad_status"] != "متاح":
        flash("هذا الإعلان غير متاح حالياً.", "error")
        return redirect(url_for("ad_details", ad_id=ad_id))

    existing = fetch_one(
        """
        SELECT request_id
        FROM exchange_requests
        WHERE ad_id = %s AND requester_student_id = %s
        """,
        (ad_id, current_student_id),
    )

    if existing:
        flash("سبق أن أرسلت طلباً لهذا الإعلان.", "error")
        return redirect(url_for("ad_details", ad_id=ad_id))

    ok = execute_query(
        """
        INSERT INTO exchange_requests (ad_id, requester_student_id)
        VALUES (%s, %s)
        """,
        (ad_id, current_student_id),
    )

    if ok:
        flash("تم إرسال الطلب بنجاح.", "success")
        return redirect(url_for("my_requests"))

    flash("تعذر إرسال الطلب.", "error")
    return redirect(url_for("ad_details", ad_id=ad_id))


@app.route("/book_ads/create", methods=["GET", "POST"])
@student_required
def create_ad():
    books = fetch_all("SELECT book_id, book_title, course_name, major FROM books ORDER BY book_title ASC")

    if request.method == "POST":
        book_id = request.form.get("book_id", "").strip()
        ad_type = request.form.get("ad_type", "").strip()
        copy_condition = request.form.get("copy_condition", "").strip()
        delivery_method = request.form.get("delivery_method", "").strip() or None

        if not all([book_id, ad_type, copy_condition]):
            flash("يرجى تعبئة الحقول المطلوبة.", "error")
            return redirect(url_for("create_ad"))

        image_filename = None
        image_file = request.files.get("book_image")
        if image_file and image_file.filename:
            if not allowed_image(image_file.filename):
                flash("صيغة الصورة غير مدعومة.", "error")
                return redirect(url_for("create_ad"))

            safe_name = secure_filename(image_file.filename)
            image_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            image_file.save(image_path)

        ok = execute_query(
            """
            INSERT INTO book_ads (
                student_id,
                book_id,
                ad_type,
                copy_condition,
                book_image,
                delivery_method
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session["student_id"], int(book_id), ad_type, copy_condition, image_filename, delivery_method),
        )

        if ok:
            flash("تم نشر الإعلان بنجاح.", "success")
            return redirect(url_for("my_ads"))

        flash("حدث خطأ أثناء نشر الإعلان.", "error")

    return render_template("book_ads/create.html", page_title="إنشاء إعلان", books=books, active_page="create_ad")


@app.route("/book_ads/my")
@student_required
def my_ads():
    student_id = session["student_id"]

    ads = fetch_all(
        """
        SELECT
            ba.ad_id,
            ba.book_id,
            ba.ad_type,
            ba.copy_condition,
            ba.book_image,
            ba.delivery_method,
            ba.ad_status,
            ba.ad_date,
            b.book_title,
            b.course_name,
            b.major
        FROM book_ads ba
        JOIN books b ON b.book_id = ba.book_id
        WHERE ba.student_id = %s
        ORDER BY ba.ad_date DESC
        """,
        (student_id,),
    )

    requests_for_my_ads = fetch_all(
        """
        SELECT
            er.request_id,
            er.ad_id,
            er.request_status,
            er.meeting_place,
            er.meeting_time,
            s.full_name AS requester_name
        FROM exchange_requests er
        JOIN book_ads ba ON ba.ad_id = er.ad_id
        JOIN students s ON s.student_id = er.requester_student_id
        WHERE ba.student_id = %s
        ORDER BY er.request_id DESC
        """,
        (student_id,),
    )

    requests_map = {}
    for one_request in requests_for_my_ads:
        requests_map.setdefault(one_request["ad_id"], []).append(one_request)

    for ad in ads:
        ad["requests"] = requests_map.get(ad["ad_id"], [])

    return render_template("book_ads/my_ads.html", page_title="إعلاناتي", ads=ads, active_page="my_ads")


@app.route("/exchange_requests/my")
@student_required
def my_requests():
    rows = fetch_all(
        """
        SELECT
            er.request_id,
            er.request_status,
            er.meeting_place,
            er.meeting_time,
            ba.ad_type,
            ba.ad_status,
            b.book_title,
            b.course_name
        FROM exchange_requests er
        JOIN book_ads ba ON ba.ad_id = er.ad_id
        JOIN books b ON b.book_id = ba.book_id
        WHERE er.requester_student_id = %s
        ORDER BY er.request_id DESC
        """,
        (session["student_id"],),
    )

    return render_template(
        "exchange_requests/my_list.html",
        page_title="طلباتي",
        requests=rows,
        active_page="my_requests",
    )


@app.route("/exchange_requests/<int:request_id>/cancel", methods=["POST"])
@student_required
def cancel_request(request_id):
    owned_request = fetch_one(
        """
        SELECT request_id, request_status
        FROM exchange_requests
        WHERE request_id = %s AND requester_student_id = %s
        """,
        (request_id, session["student_id"]),
    )

    if not owned_request:
        flash("الطلب غير موجود.", "error")
        return redirect(url_for("my_requests"))

    if owned_request["request_status"] in ("مرفوض", "ملغي"):
        flash("لا يمكن تعديل هذا الطلب.", "error")
        return redirect(url_for("my_requests"))

    ok = execute_query(
        "UPDATE exchange_requests SET request_status = %s WHERE request_id = %s",
        ("ملغي", request_id),
    )

    if ok:
        flash("تم إلغاء الطلب.", "success")
    else:
        flash("تعذر إلغاء الطلب.", "error")

    return redirect(url_for("my_requests"))


@app.route("/exchange_requests/<int:request_id>/owner_update", methods=["POST"])
@student_required
def owner_update_request(request_id):
    status_value = request.form.get("request_status", "").strip()
    meeting_place = request.form.get("meeting_place", "").strip() or None
    meeting_time = parse_datetime_local(request.form.get("meeting_time", "").strip())

    allowed_statuses = {"بانتظار", "مقبول", "مرفوض", "ملغي"}
    if status_value not in allowed_statuses:
        flash("حالة الطلب غير صالحة.", "error")
        return redirect(url_for("my_ads"))

    row = fetch_one(
        """
        SELECT er.request_id, er.ad_id
        FROM exchange_requests er
        JOIN book_ads ba ON ba.ad_id = er.ad_id
        WHERE er.request_id = %s AND ba.student_id = %s
        """,
        (request_id, session["student_id"]),
    )

    if not row:
        flash("لا تملكين صلاحية تعديل هذا الطلب.", "error")
        return redirect(url_for("my_ads"))

    if status_value == "مقبول" and (not meeting_place or not meeting_time):
        flash("عند قبول الطلب يجب تحديد مكان ووقت التسليم.", "error")
        return redirect(url_for("my_ads"))

    update_ok = execute_query(
        """
        UPDATE exchange_requests
        SET request_status = %s, meeting_place = %s, meeting_time = %s
        WHERE request_id = %s
        """,
        (status_value, meeting_place, meeting_time, request_id),
    )

    if not update_ok:
        flash("تعذر تحديث الطلب.", "error")
        return redirect(url_for("my_ads"))

    ad_id = row["ad_id"]

    if status_value == "مقبول":
        execute_query(
            """
            UPDATE exchange_requests
            SET request_status = 'مرفوض'
            WHERE ad_id = %s AND request_id <> %s AND request_status = 'بانتظار'
            """,
            (ad_id, request_id),
        )
        execute_query("UPDATE book_ads SET ad_status = 'محجوز' WHERE ad_id = %s", (ad_id,))
    else:
        accepted_row = fetch_one(
            "SELECT COUNT(*) AS total FROM exchange_requests WHERE ad_id = %s AND request_status = 'مقبول'",
            (ad_id,),
        )
        if accepted_row and accepted_row["total"] > 0:
            execute_query("UPDATE book_ads SET ad_status = 'محجوز' WHERE ad_id = %s", (ad_id,))
        else:
            execute_query("UPDATE book_ads SET ad_status = 'متاح' WHERE ad_id = %s", (ad_id,))

    flash("تم تحديث الطلب بنجاح.", "success")
    return redirect(url_for("my_ads"))


@app.route("/admins/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin = fetch_one(
            """
            SELECT admin_id, full_name
            FROM admins
            WHERE username = %s AND password = %s
            """,
            (username, password),
        )

        if admin:
            session["admin_id"] = admin["admin_id"]
            session["admin_name"] = admin["full_name"]
            flash("تم تسجيل الدخول للإدارة بنجاح.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("بيانات دخول الإدارة غير صحيحة.", "error")

    return render_template("admins/admin_login.html", page_title="دخول الإدارة", active_page="admin_login")


@app.route("/admins/logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_name", None)
    flash("تم تسجيل خروج الإدارة.", "success")
    return redirect(url_for("home_index"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    stats = {
        "students": count_rows("students"),
        "books": count_rows("books"),
        "ads": count_rows("book_ads"),
        "available_ads": count_rows("book_ads", "WHERE ad_status = %s", ("متاح",)),
        "requests": count_rows("exchange_requests"),
        "accepted_requests": count_rows("exchange_requests", "WHERE request_status = %s", ("مقبول",)),
    }
    return render_template("admins/dashboard.html", page_title="لوحة التحكم", stats=stats, active_page="dashboard")


@app.route("/admin/admins")
@admin_required
def admin_admins():
    admins = fetch_all("SELECT admin_id, full_name, username FROM admins ORDER BY admin_id DESC")
    return render_template("admins/list.html", page_title="إدارة المسؤولين", admins=admins, active_page="admins")


@app.route("/admin/admins/add", methods=["POST"])
@admin_required
def add_admin():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not all([full_name, username, password, confirm_password]):
        flash("جميع الحقول مطلوبة.", "error")
        return redirect(url_for("admin_admins"))

    if password != confirm_password:
        flash("كلمة المرور وتأكيدها غير متطابقين.", "error")
        return redirect(url_for("admin_admins"))

    exists = fetch_one("SELECT admin_id FROM admins WHERE username = %s", (username,))
    if exists:
        flash("اسم المستخدم مستخدم مسبقاً.", "error")
        return redirect(url_for("admin_admins"))

    ok = execute_query(
        "INSERT INTO admins (full_name, username, password) VALUES (%s, %s, %s)",
        (full_name, username, password),
    )

    if ok:
        flash("تمت إضافة المسؤول بنجاح.", "success")
    else:
        flash("تعذر إضافة المسؤول.", "error")

    return redirect(url_for("admin_admins"))


@app.route("/admin/admins/<int:admin_id>/delete", methods=["POST"])
@admin_required
def delete_admin(admin_id):
    if admin_id == session.get("admin_id"):
        flash("لا يمكنك حذف حسابك الحالي.", "error")
        return redirect(url_for("admin_admins"))

    ok = execute_query("DELETE FROM admins WHERE admin_id = %s", (admin_id,))
    if ok:
        flash("تم حذف المسؤول.", "success")
    else:
        flash("تعذر حذف المسؤول.", "error")

    return redirect(url_for("admin_admins"))


@app.route("/admin/students")
@admin_required
def admin_students():
    students = fetch_all(
        """
        SELECT student_id, full_name, university_email, major, level
        FROM students
        ORDER BY student_id DESC
        """
    )
    return render_template("students/admin_list.html", page_title="إدارة الطالبات", students=students, active_page="students")


@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@admin_required
def delete_student(student_id):
    ok = execute_query("DELETE FROM students WHERE student_id = %s", (student_id,))
    if ok:
        flash("تم حذف الطالبة.", "success")
    else:
        flash("تعذر حذف الطالبة.", "error")

    return redirect(url_for("admin_students"))


@app.route("/admin/books")
@admin_required
def admin_books():
    books = fetch_all(
        """
        SELECT book_id, book_title, course_name, major, short_description
        FROM books
        ORDER BY book_id DESC
        """
    )
    return render_template("books/admin_list.html", page_title="إدارة الكتب", books=books, active_page="books")


@app.route("/admin/books/add", methods=["POST"])
@admin_required
def add_book():
    book_title = request.form.get("book_title", "").strip()
    course_name = request.form.get("course_name", "").strip()
    major = request.form.get("major", "").strip()
    short_description = request.form.get("short_description", "").strip() or None

    if not all([book_title, course_name, major]):
        flash("بيانات الكتاب الأساسية مطلوبة.", "error")
        return redirect(url_for("admin_books"))

    ok = execute_query(
        """
        INSERT INTO books (book_title, course_name, major, short_description)
        VALUES (%s, %s, %s, %s)
        """,
        (book_title, course_name, major, short_description),
    )

    if ok:
        flash("تمت إضافة الكتاب.", "success")
    else:
        flash("تعذر إضافة الكتاب.", "error")

    return redirect(url_for("admin_books"))


@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
@admin_required
def delete_book(book_id):
    ok = execute_query("DELETE FROM books WHERE book_id = %s", (book_id,))
    if ok:
        flash("تم حذف الكتاب.", "success")
    else:
        flash("تعذر حذف الكتاب. قد يكون مرتبطاً بإعلانات.", "error")

    return redirect(url_for("admin_books"))


@app.route("/admin/book_ads")
@admin_required
def admin_ads():
    ads = fetch_all(
        """
        SELECT
            ba.ad_id,
            ba.ad_type,
            ba.copy_condition,
            ba.delivery_method,
            ba.ad_status,
            ba.ad_date,
            b.book_title,
            s.full_name AS owner_name
        FROM book_ads ba
        JOIN books b ON b.book_id = ba.book_id
        JOIN students s ON s.student_id = ba.student_id
        ORDER BY ba.ad_id DESC
        """
    )
    return render_template("book_ads/admin_list.html", page_title="إدارة الإعلانات", ads=ads, active_page="ads")


@app.route("/admin/book_ads/<int:ad_id>/status", methods=["POST"])
@admin_required
def admin_update_ad_status(ad_id):
    status_value = request.form.get("ad_status", "").strip()
    if status_value not in {"متاح", "محجوز", "مغلق"}:
        flash("حالة الإعلان غير صالحة.", "error")
        return redirect(url_for("admin_ads"))

    ok = execute_query("UPDATE book_ads SET ad_status = %s WHERE ad_id = %s", (status_value, ad_id))
    if ok:
        flash("تم تحديث حالة الإعلان.", "success")
    else:
        flash("تعذر تحديث حالة الإعلان.", "error")

    return redirect(url_for("admin_ads"))


@app.route("/admin/book_ads/<int:ad_id>/delete", methods=["POST"])
@admin_required
def delete_ad(ad_id):
    ok = execute_query("DELETE FROM book_ads WHERE ad_id = %s", (ad_id,))
    if ok:
        flash("تم حذف الإعلان.", "success")
    else:
        flash("تعذر حذف الإعلان.", "error")

    return redirect(url_for("admin_ads"))


@app.route("/admin/exchange_requests")
@admin_required
def admin_requests():
    rows = fetch_all(
        """
        SELECT
            er.request_id,
            er.request_status,
            er.meeting_place,
            er.meeting_time,
            b.book_title,
            requester.full_name AS requester_name,
            owner.full_name AS owner_name
        FROM exchange_requests er
        JOIN book_ads ba ON ba.ad_id = er.ad_id
        JOIN books b ON b.book_id = ba.book_id
        JOIN students requester ON requester.student_id = er.requester_student_id
        JOIN students owner ON owner.student_id = ba.student_id
        ORDER BY er.request_id DESC
        """
    )
    return render_template(
        "exchange_requests/admin_list.html",
        page_title="إدارة الطلبات",
        requests=rows,
        active_page="requests",
    )


@app.route("/admin/exchange_requests/<int:request_id>/update", methods=["POST"])
@admin_required
def admin_update_request(request_id):
    status_value = request.form.get("request_status", "").strip()
    meeting_place = request.form.get("meeting_place", "").strip() or None
    meeting_time = parse_datetime_local(request.form.get("meeting_time", "").strip())

    if status_value not in {"بانتظار", "مقبول", "مرفوض", "ملغي"}:
        flash("حالة الطلب غير صالحة.", "error")
        return redirect(url_for("admin_requests"))

    ok = execute_query(
        """
        UPDATE exchange_requests
        SET request_status = %s, meeting_place = %s, meeting_time = %s
        WHERE request_id = %s
        """,
        (status_value, meeting_place, meeting_time, request_id),
    )

    if ok:
        flash("تم تحديث الطلب.", "success")
    else:
        flash("تعذر تحديث الطلب.", "error")

    return redirect(url_for("admin_requests"))


@app.route("/admin/exchange_requests/<int:request_id>/delete", methods=["POST"])
@admin_required
def delete_request(request_id):
    ok = execute_query("DELETE FROM exchange_requests WHERE request_id = %s", (request_id,))
    if ok:
        flash("تم حذف الطلب.", "success")
    else:
        flash("تعذر حذف الطلب.", "error")

    return redirect(url_for("admin_requests"))


# if __name__ == "__main__":
#     app.run(debug=True, port=1446)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
