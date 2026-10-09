import os
import io
import traceback
from datetime import date, datetime, timedelta
import calendar
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, send_from_directory
import pymysql
import pymysql.cursors
import openpyxl

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Folder la kuhifadhia picha, mafaili ya assignment, na PDF
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
PDF_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'pdf')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_UPLOAD_FOLDER, exist_ok=True)

def get_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='student_management3',
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )

def calculate_age(born):
    if not born:
        return ""
    try:
        if isinstance(born, str):
            born = date.fromisoformat(born)
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return ""

def get_fee_for_class(darasa):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT fee_required FROM class_fees WHERE darasa = %s", (darasa,))
        res = cursor.fetchone()
    db.close()
    return float(res.get("fee_required", 0)) if res else 0.0

def calculate_permissions(ada_iliyolipwa, fee_required):
    try:
        paid = float(ada_iliyolipwa or 0)
        required = float(fee_required or 0)
    except (ValueError, TypeError):
        paid = 0.0
        required = 0.0

    if required > 0:
        percentage = (paid / required) * 100
    else:
        percentage = 0.0

    return {
        'percentage': round(percentage, 1),
        'can_attend': percentage >= 25.0,
        'can_take_exams': percentage >= 100.0
    }

# ==================== MAHUDHURIO NA MSHAHARA WA WAFANYAKAZI (JUMATATU HADI IJUMAA - MWEZI MZIMA) ====================
def calculate_staff_attendance_percentage(username):
    db = get_db()
    today = datetime.today()
    yil = today.year
    mwezi = today.month
    
    siku_ya_kwanza = date(yil, mwezi, 1)
    mwisho_wa_mwezi_siku = calendar.monthrange(yil, mwezi)[1]
    siku_ya_mwisho = date(yil, mwezi, mwisho_wa_mwezi_siku)
    
    jumla_siku_za_kazi = 0
    current_date = siku_ya_kwanza
    while current_date <= siku_ya_mwisho and current_date <= today.date():
        if current_date.weekday() < 5:  # 0 = Jumatatu hadi 4 = Ijumaa
            jumla_siku_za_kazi += 1
        current_date += timedelta(days=1)
        
    if jumla_siku_za_kazi == 0:
        return 100.0  
        
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) as present FROM staff_attendance 
            WHERE username = %s AND hali = 'Yupo' 
            AND tarehe BETWEEN %s AND %s
            AND DAYOFWEEK(tarehe) BETWEEN 2 AND 6
        """, (username, siku_ya_kwanza, siku_ya_mwisho))
        present_days = cursor.fetchone().get("present", 0)
    db.close()
    
    return round((present_days / jumla_siku_za_kazi) * 100, 1)

def has_approved_excuse(username):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM staff_excuses WHERE username = %s AND hali_ya_ombi = 'Imekubaliwa'", (username,))
        excuse = cursor.fetchone()
    db.close()
    return excuse is not None

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        selected_role = request.form.get("role", "Admin")
        
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s AND role = %s", (username, password, selected_role))
            user = cursor.fetchone()
        db.close()
        
        if user:
            if user["role"] == "Student":
                db = get_db()
                with db.cursor() as cursor:
                    cursor.execute("SELECT is_approved FROM students WHERE username = %s", (username,))
                    std_record = cursor.fetchone()
                db.close()
                
                if std_record and std_record.get("is_approved") == 0:
                    flash("Akaunti yako bado haijathibitishwa na Admin. Subiri idhini!", "warning")
                    return redirect(url_for("login"))

            session["username"] = user["username"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            
            if user["role"] == "Admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "Teacher":
                return redirect(url_for("teacher_dashboard"))
            elif user["role"] == "Student":
                return redirect(url_for("student_dashboard"))
        else:
            flash("Username, Password au Session uliyochagua si sahihi!", "danger")
            
    return render_template("login.html")

@app.route("/register-student", methods=["POST"])
def register_student():
    full_name = request.form.get("full_name")
    email = request.form.get("email")
    darasa = request.form.get("darasa")
    namba_ya_simu = request.form.get("namba_ya_simu")
    jinsia = request.form.get("jinsia")
    tarehe_ya_kuzaliwa = request.form.get("tarehe_ya_kuzaliwa")
    mahali_anapoishi = request.form.get("mahali_anapoishi")
    jina_la_mzazi = request.form.get("jina_la_mzazi")
    password = request.form.get("reg_password")
    
    if not email or not full_name or not password or not darasa:
        flash("Tafadhali jaza taarifa zote muhimu zinazohitajika!", "danger")
        return redirect(url_for("login"))

    username = email.split('@')[0].strip()
    fee_req = get_fee_for_class(darasa)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password, role, name) VALUES (%s, %s, 'Student', %s)", 
                (username, password, full_name)
            )
            cursor.execute("""
                INSERT INTO students (
                    username, darasa, namba_ya_simu, jinsia, 
                    tarehe_ya_kuzaliwa, mahali_anapoishi, jina_la_mzazi, 
                    fee_required, is_approved, uhakiki_wa_ada, profile_pic
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 'Inasubiri Uhakiki', 'default.png')
            """, (username, darasa, namba_ya_simu, jinsia, tarehe_ya_kuzaliwa, mahali_anapoishi, jina_la_mzazi, fee_req))
            
        flash("Ombi lako la usajili limetumwa kwa mafanikio! Subiri Admin alithibitishe.", "success")
    except Exception as e:
        flash(f"Usajili umeshindwa: {str(e)}", "danger")
    finally:
        db.close()
        
    return redirect(url_for("login"))

# ==================== ADMIN DASHBOARD ====================
@app.route("/admin")
def admin_dashboard():
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT users.name, users.username, users.password, teachers.* 
            FROM teachers 
            JOIN users ON teachers.username = users.username
        """)
        walimu_raw = cursor.fetchall()
        walimu = []
        for t in walimu_raw:
            t['age'] = calculate_age(t.get('tarehe_ya_kuzaliwa') or t.get('dob'))
            t['attendance_percentage'] = calculate_staff_attendance_percentage(t['username'])
            t['has_excuse'] = has_approved_excuse(t['username'])
            walimu.append(t)
        
        cursor.execute("""
            SELECT users.name, users.username, users.password, students.* 
            FROM students 
            JOIN users ON students.username = users.username
        """)
        wanafunzi_raw = cursor.fetchall()
        
        cursor.execute("""
            SELECT users.name, users.username, users.password, students.* 
            FROM students 
            JOIN users ON students.username = users.username
            WHERE students.is_approved = 0 OR students.is_approved IS NULL
        """)
        pending_students = cursor.fetchall()
        
        try:
            cursor.execute("SELECT * FROM staff_excuses WHERE hali_ya_ombi = 'Inasubiri'")
            pending_excuses = cursor.fetchall()
        except Exception:
            pending_excuses = []
        
        students_by_form = {f"Form {i}": [] for i in range(1, 7)}
        
        for std in wanafunzi_raw:
            fee_paid = std.get('ada_iliyolipwa', 0)
            fee_req = std.get('fee_required', 0)
            perms = calculate_permissions(fee_paid, fee_req)
            
            std['percentage'] = perms['percentage']
            std['can_attend'] = perms['can_attend']
            std['can_take_exams'] = perms['can_take_exams']
            std['age'] = calculate_age(std.get('tarehe_ya_kuzaliwa'))
            
            darasa = std.get('darasa', '').strip()
            if darasa in students_by_form:
                students_by_form[darasa].append(std)
            else:
                for i in range(1, 7):
                    if str(i) in darasa:
                        students_by_form[f"Form {i}"].append(std)
                        break

        try:
            cursor.execute("SELECT * FROM exam_results_pdf ORDER BY upload_date DESC")
            matokeo_pdf = cursor.fetchall()
        except Exception:
            matokeo_pdf = []

    db.close()
    
    admin_attendance = calculate_staff_attendance_percentage(session["username"])
    admin_excuse = has_approved_excuse(session["username"])

    return render_template(
        "admin_dashboard.html", 
        walimu=walimu, 
        wanafunzi=wanafunzi_raw, 
        pending_students=pending_students, 
        students_by_form=students_by_form, 
        matokeo_pdf=matokeo_pdf,
        pending_excuses=pending_excuses,
        admin_attendance=admin_attendance,
        admin_excuse=admin_excuse
    )

@app.route("/admin/pay_salary/<role>/<username>", methods=["POST"])
def pay_salary(role, username):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    attendance_percentage = calculate_staff_attendance_percentage(username)
    excuse_approved = has_approved_excuse(username)
    
    if attendance_percentage >= 90.0 or excuse_approved:
        db = get_db()
        try:
            with db.cursor() as cursor:
                if role == "Teacher":
                    cursor.execute("UPDATE teachers SET mshahara_umetolewa = 1 WHERE username = %s", (username,))
                elif role == "Admin":
                    cursor.execute("UPDATE admins SET mshahara_umetolewa = 1 WHERE username = %s", (username,))
            flash(f"Mshahara umelipwa kwa mafanikio kwa {username}! (Mahudhurio ya Mwezi: {attendance_percentage}%)", "success")
        except Exception as e:
            flash("Imeshindikana kulipa mshahara: " + str(e), "danger")
        finally:
            db.close()
    else:
        flash(f"Imeshindikana! Mahudhurio ya {username} kwa mwezi huu ni {attendance_percentage}% (Chini ya 90%). Lazima afikishe zaidi ya 90% au awe na udhuru uliokubaliwa.", "danger")
        
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/approve_excuse/<int:excuse_id>/<action>")
def approve_excuse(excuse_id, action):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    hali_mpya = "Imekubaliwa" if action == "accept" else "Imekataliwa"
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("UPDATE staff_excuses SET hali_ya_ombi = %s WHERE id = %s", (hali_mpya, excuse_id))
    db.close()
    
    flash(f"Ombi la udhuru limesasishwa kuwa: {hali_mpya}", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/add_teacher", methods=["POST"])
def add_teacher():
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    name = request.form["name"]
    username = request.form["username"]
    password = request.form["password"]
    somo = request.form["somo"]
    darasa = request.form["darasa"]
    mshahara = request.form["mshahara"]
    kiwango_elimu = request.form.get("kiwango_elimu", "")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO users (username, password, role, name) VALUES (%s, %s, 'Teacher', %s)", (username, password, name))
            cursor.execute("INSERT INTO teachers (username, somo, darasa_la_kufundisha, mshahara, kiwango_elimu, profile_pic) VALUES (%s, %s, %s, %s, %s, 'default.png')", (username, somo, darasa, mshahara, kiwango_elimu))
        flash("Mwalimu amesajiliwa kikamilifu!", "success")
    except Exception as e:
        flash("Username tayari imetumika au kuna kosa!", "danger")
    finally:
        db.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/approve_student/<username>")
def approve_student(username):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("UPDATE students SET is_approved = 1 WHERE username = %s", (username,))
    db.close()
    flash("Mwanafunzi amethibitishwa kikamilifu!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/remove_student/<username>")
def remove_student(username):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE username = %s AND role = 'Student'", (username,))
        flash("Mwanafunzi ameondolewa!", "warning")
    except Exception as e:
        flash("Imeshindikana kumuondoa mwanafunzi!", "danger")
    finally:
        db.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/remove_teacher/<username>")
def remove_teacher(username):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE username = %s AND role = 'Teacher'", (username,))
        flash("Mwalimu ameondolewa!", "warning")
    except Exception as e:
        flash("Imeshindikana kumuondoa mwalimu!", "danger")
    finally:
        db.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/update_fee/<username>", methods=["POST"])
def update_fee(username):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    try:
        kiasi_kipya = float(request.form.get("ada_iliyolipwa", 0))
    except ValueError:
        kiasi_kipya = 0.0
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT ada_iliyolipwa FROM students WHERE username = %s", (username,))
            std = cursor.fetchone()
            
            if std:
                ada_ya_zamani = float(std.get("ada_iliyolipwa", 0) or 0)
                jumla_iliyolipwa = ada_ya_zamani + kiasi_kipya
                
                cursor.execute("""
                    UPDATE students 
                    SET ada_iliyolipwa = %s, uhakiki_wa_ada = 'Imethibitishwa' 
                    WHERE username = %s
                """, (jumla_iliyolipwa, username))
                
        flash("Malipo ya ada yameongezwa na kuhifadhiwa kikamilifu!", "success")
    except Exception as e:
        flash("Imeshindikana kuhifadhi kiasi cha ada!", "danger")
    finally:
        db.close()
        
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/toggle_exam/<username>")
def toggle_exam(username):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT can_take_exams FROM students WHERE username = %s", (username,))
        std = cursor.fetchone()
        if std:
            new_status = 0 if std.get("can_take_exams") == 1 else 1
            cursor.execute("UPDATE students SET can_take_exams = %s WHERE username = %s", (new_status, username))
            flash("Ruhusa ya mtihani imebadilishwa kikamilifu!", "success")
    db.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/download_excel/<darasa>")
def download_class_excel(darasa):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
        
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT users.name, students.username, students.darasa 
            FROM students 
            JOIN users ON students.username = users.username 
            WHERE students.darasa = %s AND students.is_approved = 1
        """, (darasa,))
        wanafunzi = cursor.fetchall()
    db.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Matokeo {darasa}"
    ws.append(["Namba", "Username", "Jina la Mwanafunzi", "Darasa", "Somo", "Alama (Marks)", "Daraja (Grade)"])
    
    for idx, std in enumerate(wanafunzi, 1):
        ws.append([idx, std["username"], std["name"], std["darasa"], "", "", ""])
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Sheet_ya_Matokeo_{darasa}.xlsx"
    )

@app.route("/admin/download_pdf/<path:filename>")
def download_results_pdf(filename):
    if "username" not in session or session["role"] != "Admin":
        return redirect(url_for("login"))
    
    clean_filename = filename.strip().replace('\n', '').replace('\r', '')
    return send_from_directory(PDF_UPLOAD_FOLDER, clean_filename, as_attachment=True)

# ==================== TEACHER DASHBOARD ====================
@app.route("/teacher")
def teacher_dashboard():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    username = session["username"]
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM teachers WHERE username = %s", (username,))
        teacher_info = cursor.fetchone()
        
        darasa_lako = teacher_info.get("darasa_la_kufundisha") if teacher_info else ""
        somo_lako = teacher_info.get("somo") if teacher_info else ""
        
        cursor.execute("""
            SELECT users.name, students.* 
            FROM students 
            JOIN users ON students.username = users.username 
            WHERE students.darasa = %s
        """, (darasa_lako,))
        wanafunzi = cursor.fetchall()

        for std in wanafunzi:
            perms = calculate_permissions(std.get('ada_iliyolipwa'), std.get('fee_required'))
            std['percentage'] = perms['percentage']
            std['can_attend'] = perms['can_attend']

        try:
            cursor.execute("SELECT * FROM assignments WHERE teacher_username = %s ORDER BY id DESC", (username,))
            assignments = cursor.fetchall()
        except Exception:
            assignments = []

        try:
            cursor.execute("SELECT * FROM student_marks WHERE somo = %s ORDER BY id DESC", (somo_lako,))
            teacher_marks_list = cursor.fetchall()
        except Exception:
            teacher_marks_list = []

        try:
            cursor.execute("SELECT * FROM submitted_assignments WHERE teacher_username = %s ORDER BY id DESC", (username,))
            received_assignments = cursor.fetchall()
        except Exception:
            received_assignments = []

    db.close()
    
    attendance_percentage = calculate_staff_attendance_percentage(username)

    return render_template(
        "teacher_dashboard.html", 
        wanafunzi=wanafunzi, 
        teacher_info=teacher_info, 
        assignments=assignments, 
        teacher_marks_list=teacher_marks_list,
        received_assignments=received_assignments,
        attendance_percentage=attendance_percentage
    )

@app.route("/teacher/update_profile", methods=["POST"])
def teacher_update_profile():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    old_username = session["username"]
    new_username = request.form.get("username").strip()
    new_password = request.form.get("password").strip()
    
    file = request.files.get("profile_pic")
    pic_filename = None
    if file and file.filename != '':
        pic_filename = f"teacher_{new_username}_{file.filename}"
        file.save(os.path.join(UPLOAD_FOLDER, pic_filename))

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("UPDATE users SET username = %s, password = %s WHERE username = %s", (new_username, new_password, old_username))
            if pic_filename:
                cursor.execute("UPDATE teachers SET username = %s, profile_pic = %s WHERE username = %s", (new_username, pic_filename, old_username))
            else:
                cursor.execute("UPDATE teachers SET username = %s WHERE username = %s", (new_username, old_username))
            
        session["username"] = new_username
        flash("Taarifa za wasifu wa mwalimu zimesasishwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kusasisha profile!", "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/update_marks", methods=["POST"])
def update_marks():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    teacher_username = session["username"]
    std_username = request.form.get("username")
    alama = request.form.get("alama")
    aina_ya_tathmini = request.form.get("aina_ya_tathmini")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT somo FROM teachers WHERE username = %s", (teacher_username,))
            t_info = cursor.fetchone()
            somo_lako = t_info.get("somo") if t_info else ""
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM student_marks 
                WHERE username = %s AND somo = %s AND aina_ya_tathmini = %s
            """, (std_username, somo_lako, aina_ya_tathmini))
            count_res = cursor.fetchone()
            namba_mpya = (count_res.get("total", 0) if count_res else 0) + 1
            
            cursor.execute("""
                INSERT INTO student_marks (username, somo, aina_ya_tathmini, namba_ya_tathmini, alama) 
                VALUES (%s, %s, %s, %s, %s)
            """, (std_username, somo_lako, aina_ya_tathmini, namba_mpya, alama))
            
        flash(f"Alama zimehifadhiwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kuhifadhi alama: " + str(e), "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/edit_mark/<int:mark_id>", methods=["POST"])
def edit_mark(mark_id):
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    mpya_alama = request.form.get("alama")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("UPDATE student_marks SET alama = %s WHERE id = %s", (mpya_alama, mark_id))
        flash("Alama zimesasishwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kuhariri alama: " + str(e), "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/download_submission/<filename>")
def download_submitted_assignment(filename):
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/teacher/take_attendance", methods=["POST"])
def take_attendance():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    username = request.form.get("username")
    hali = request.form.get("hali")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO attendance (username, hali, tarehe) VALUES (%s, %s, CURDATE())", (username, hali))
        flash("Mahudhurio yamerekodiwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kurekodi mahudhurio: " + str(e), "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/add_assignment", methods=["POST"])
def add_assignment():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    username = session["username"]
    title = request.form.get("title")
    darasa = request.form.get("darasa")
    deadline = request.form.get("deadline")
    description = request.form.get("description")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assignments (teacher_username, title, darasa, deadline, description) VALUES (%s, %s, %s, %s, %s)",
                (username, title, darasa, deadline, description)
            )
        flash("Assignment imetumwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kutuma assignment: " + str(e), "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

@app.route("/teacher/add_student", methods=["POST"])
def add_student():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    name = request.form.get("name")
    email = request.form.get("email")
    darasa = request.form.get("darasa")
    namba_ya_simu = request.form.get("namba_ya_simu")
    jinsia = request.form.get("jinsia")
    tarehe_ya_kuzaliwa = request.form.get("tarehe_ya_kuzaliwa")
    mahali_anapoishi = request.form.get("mahali_anapoishi")
    jina_la_mzazi = request.form.get("jina_la_mzazi")
    password = request.form.get("password")
    ada_iliyolipwa = request.form.get("ada_iliyolipwa", 0)
    
    if not email or not name or not password or not darasa:
        flash("Tafadhali jaza taarifa zote muhimu za mwanafunzi!", "danger")
        return redirect(url_for("teacher_dashboard"))

    username = email.split('@')[0].strip()
    fee_req = get_fee_for_class(darasa)
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password, role, name) VALUES (%s, %s, 'Student', %s)", 
                (username, password, name)
            )
            cursor.execute("""
                INSERT INTO students (
                    username, darasa, namba_ya_simu, jinsia, 
                    tarehe_ya_kuzaliwa, mahali_anapoishi, jina_la_mzazi, 
                    fee_required, ada_iliyolipwa, is_approved, uhakiki_wa_ada, profile_pic
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'Imethibitishwa', 'default.png')
            """, (username, darasa, namba_ya_simu, jinsia, tarehe_ya_kuzaliwa, mahali_anapoishi, jina_la_mzazi, fee_req, ada_iliyolipwa))
            
        flash("Mwanafunzi amesajiliwa kikamilifu!", "success")
    except Exception as e:
        flash(f"Usajili umeshindwa: {str(e)}", "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

# ==================== KUTENGENEZA NA KUTUMA PDF YA MATOKEO (KILA MWANAFUNZI NA SAFU ZA TATHMINI) ====================
@app.route("/teacher/generate_results_pdf", methods=["POST"])
def teacher_generate_results_pdf():
    if "username" not in session or session["role"] != "Teacher":
        return redirect(url_for("login"))
        
    username = session["username"]
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM teachers WHERE username = %s", (username,))
        teacher_info = cursor.fetchone()
        
        darasa_lako = teacher_info.get("darasa_la_kufundisha") if teacher_info else ""
        somo_lako = teacher_info.get("somo") if teacher_info else ""
        
        # Pata orodha ya wanafunzi wote wa darasa hili
        cursor.execute("""
            SELECT users.name, students.username 
            FROM students 
            JOIN users ON students.username = users.username 
            WHERE students.darasa = %s AND students.is_approved = 1
        """, (darasa_lako,))
        wanafunzi_list = cursor.fetchall()
        
        # Pata aina zote za tathmini zilizowahi kujazwa (mfano: Assignment, Test, Final Exam)
        cursor.execute("""
            SELECT DISTINCT aina_ya_tathmini FROM student_marks WHERE somo = %s
        """, (somo_lako,))
        tathmini_types_res = cursor.fetchall()
        tathmini_types = [t['aina_ya_tathmini'] for t in tathmini_types_res]
        
        # Pata alama zote za somo hili
        cursor.execute("""
            SELECT * FROM student_marks WHERE somo = %s
        """, (somo_lako,))
        all_marks = cursor.fetchall()
    db.close()
    
    if not wanafunzi_list:
        flash("Hakuna wanafunzi waliopatikana kwenye darasa hili!", "danger")
        return redirect(url_for("teacher_dashboard"))

    # Panga alama za kila mwanafunzi kulingana na aina ya tathmini
    student_results_map = {}
    for std in wanafunzi_list:
        student_results_map[std['username']] = {
            'name': std['name'],
            'marks': {t: "-" for t in tathmini_types}
        }

    for m in all_marks:
        std_user = m['username']
        tathmini = m['aina_ya_tathmini']
        alama = m['alama']
        if std_user in student_results_map:
            student_results_map[std_user]['marks'][tathmini] = str(alama)

    clean_somo = somo_lako.strip().replace(" ", "_").replace("\n", "").replace("\r", "")
    clean_darasa = darasa_lako.strip().replace(" ", "_").replace("\n", "").replace("\r", "")
    
    filename = f"Matokeo_{clean_somo}_{clean_darasa}_{username}.pdf"
    filepath = os.path.join(PDF_UPLOAD_FOLDER, filename)
    
    try:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter

        doc = SimpleDocTemplate(filepath, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#1e293b'), alignment=1)
        elements.append(Paragraph(f"<b>MATOKEO YA SOMO LA {somo_lako.upper()}</b>", title_style))
        elements.append(Paragraph(f"Darasa: {darasa_lako} | Mwalimu: {username}", styles['Normal']))
        elements.append(Spacer(1, 15))
        
        # Jenga vichwa vya jedwali (Headers) kulingana na aina za tathmini
        header_row = ["Namba", "Jina la Mwanafunzi"] + tathmini_types
        table_data = [header_row]
        
        idx = 1
        for std_user, data in student_results_map.items():
            row = [str(idx), data['name']]
            for t in tathmini_types:
                row.append(data['marks'].get(t, "-"))
            table_data.append(row)
            idx += 1
            
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(t)
        doc.build(elements)
    except Exception as e:
        with open(filepath, "w") as f:
            f.write(f"Matokeo ya Somo: {somo_lako} - Darasa: {darasa_lako}")

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM exam_results_pdf WHERE teacher_username = %s", (username,))
            cursor.execute("""
                INSERT INTO exam_results_pdf (teacher_username, filename) 
                VALUES (%s, %s)
            """, (username, filename))
        flash("PDF ya matokeo imetengenezwa vizuri na safu (columns) za kila tathmini!", "success")
    except Exception as e:
        flash("Imeshindikana kuhifadhi kumbukumbu ya PDF: " + str(e), "danger")
    finally:
        db.close()
        
    return redirect(url_for("teacher_dashboard"))

# ==================== KUSAINI MAHUDHURIO NA UDHURU WA WAFANYAKAZI ====================
@app.route("/staff/take_my_attendance", methods=["POST"])
def take_my_attendance():
    if "username" not in session:
        return redirect(url_for("login"))
        
    username = session["username"]
    role = session["role"]
    hali = request.form.get("hali")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM staff_attendance WHERE username = %s AND tarehe = CURDATE()", (username,))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("UPDATE staff_attendance SET hali = %s WHERE username = %s AND tarehe = CURDATE()", (hali, username))
                flash("Mahudhurio yako ya leo yamesasishwa kwa mafanikio!", "success")
            else:
                cursor.execute("INSERT INTO staff_attendance (username, role, hali, tarehe) VALUES (%s, %s, %s, CURDATE())", (username, role, hali))
                flash("Mahudhurio yako ya leo yamesainiwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kusaini mahudhurio: " + str(e), "danger")
    finally:
        db.close()
        
    if role == "Teacher":
        return redirect(url_for("teacher_dashboard"))
    else:
        return redirect(url_for("admin_dashboard"))

@app.route("/staff/submit_excuse", methods=["POST"])
def submit_excuse():
    if "username" not in session:
        return redirect(url_for("login"))
        
    username = session["username"]
    role = session["role"]
    sababu = request.form.get("sababu")
    
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO staff_excuses (username, role, sababu, hali_ya_ombi) VALUES (%s, %s, %s, 'Inasubiri')", (username, role, sababu))
        flash("Ombi lako la udhuru limetumwa kwa Admin kwa mafanikio.", "success")
    except Exception as e:
        flash("Imeshindikana kutuma ombi la udhuru: " + str(e), "danger")
    finally:
        db.close()
        
    if role == "Teacher":
        return redirect(url_for("teacher_dashboard"))
    else:
        return redirect(url_for("admin_dashboard"))

# ==================== STUDENT DASHBOARD ====================
@app.route("/student")
def student_dashboard():
    if "username" not in session or session["role"] != "Student":
        return redirect(url_for("login"))
        
    username = session["username"]
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT students.*, users.name FROM students JOIN users ON students.username = users.username WHERE students.username = %s", (username,))
        student_info = cursor.fetchone()
        
        darasa_lake = student_info.get("darasa") if student_info else ""

        cursor.execute("SELECT * FROM attendance WHERE username = %s ORDER BY tarehe DESC", (username,))
        mahudhurio = cursor.fetchall()

        try:
            cursor.execute("SELECT * FROM student_marks WHERE username = %s ORDER BY id DESC", (username,))
            student_marks_list = cursor.fetchall()
        except Exception:
            student_marks_list = []

        try:
            cursor.execute("""
                SELECT assignments.*, teachers.somo, users.name as teacher_name 
                FROM assignments 
                JOIN teachers ON assignments.teacher_username = teachers.username 
                JOIN users ON teachers.username = users.username 
                WHERE assignments.darasa = %s ORDER BY id DESC
            """, (darasa_lake,))
            assignments = cursor.fetchall()
        except Exception:
            assignments = []

        try:
            cursor.execute("""
                SELECT teachers.somo, users.name as teacher_name, teachers.darasa_la_kufundisha 
                FROM teachers 
                JOIN users ON teachers.username = users.username 
                WHERE teachers.darasa_la_kufundisha = %s
            """, (darasa_lake,))
            walimu_masomo = cursor.fetchall()
        except Exception:
            walimu_masomo = []

    db.close()
    
    fee_req = float(student_info.get('fee_required', 0)) if student_info else 0
    fee_paid = float(student_info.get('ada_iliyolipwa', 0)) if student_info else 0
    deni = fee_req - fee_paid
    perms = calculate_permissions(fee_paid, fee_req)
    
    return render_template(
        "student_dashboard.html", 
        info=student_info, 
        mahudhurio=mahudhurio, 
        assignments=assignments, 
        walimu_masomo=walimu_masomo, 
        student_marks_list=student_marks_list,
        deni=deni, 
        perms=perms
    )

@app.route("/student/submit_assignment", methods=["POST"])
def submit_assignment():
    if "username" not in session or session["role"] != "Student":
        return redirect(url_for("login"))
        
    username = session["username"]
    title = request.form.get("title")
    
    file = request.files.get("assignment_file")
    filename = ""
    if file and file.filename != '':
        filename = f"sub_{username}_{file.filename}"
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT teacher_username FROM assignments WHERE title = %s", (title,))
            res = cursor.fetchone()
            teacher_username = res.get("teacher_username") if res else ""
            
            cursor.execute("""
                INSERT INTO submitted_assignments (student_username, teacher_username, title, file_path) 
                VALUES (%s, %s, %s, %s)
            """, (username, teacher_username, title, filename))
            
        flash("Assignment yako imewasilishwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kuwasilisha assignment: " + str(e), "danger")
    finally:
        db.close()
        
    return redirect(url_for("student_dashboard"))

@app.route("/student/update_profile", methods=["POST"])
def student_update_profile():
    if "username" not in session or session["role"] != "Student":
        return redirect(url_for("login"))
        
    old_username = session["username"]
    new_username = request.form.get("username").strip()
    new_password = request.form.get("password").strip()
    
    file = request.files.get("profile_pic")
    pic_filename = None
    if file and file.filename != '':
        pic_filename = f"student_{new_username}_{file.filename}"
        file.save(os.path.join(UPLOAD_FOLDER, pic_filename))

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("UPDATE users SET username = %s, password = %s WHERE username = %s", (new_username, new_password, old_username))
            if pic_filename:
                cursor.execute("UPDATE students SET username = %s, profile_pic = %s WHERE username = %s", (new_username, pic_filename, old_username))
            else:
                cursor.execute("UPDATE students SET username = %s WHERE username = %s", (new_username, old_username))
            cursor.execute("UPDATE attendance SET username = %s WHERE username = %s", (new_username, old_username))
            
        session["username"] = new_username
        flash("Taarifa za wasifu wako zimesasishwa kwa mafanikio!", "success")
    except Exception as e:
        flash("Imeshindikana kusasisha profile!", "danger")
    finally:
        db.close()
        
    return redirect(url_for("student_dashboard"))

@app.route("/student/download_hall_ticket")
def download_hall_ticket():
    if "username" not in session or session["role"] != "Student":
        return redirect(url_for("login"))
        
    username = session["username"]
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT students.*, users.name FROM students JOIN users ON students.username = users.username WHERE students.username = %s", (username,))
        student = cursor.fetchone()
    db.close()

    if not student:
        flash("Taarifa hazijapatikana!", "danger")
        return redirect(url_for("student_dashboard"))

    perms = calculate_permissions(student.get('ada_iliyolipwa'), student.get('fee_required'))
    if not perms['can_take_exams']:
        flash("Huna ruhusa ya kupakua Hall Ticket! Unatakiwa kumaliza 100% ya ada.", "danger")
        return redirect(url_for("student_dashboard"))

    profile_pic = student.get('profile_pic') or 'default.png'
    pic_url = url_for('static', filename=f'uploads/{profile_pic}')

    html_content = f"""
    <!DOCTYPE html>
    <html lang="sw">
    <head>
        <meta charset="UTF-8">
        <title>Examination Hall Ticket - {student['name']}</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body {{ font-family: 'Poppins', Arial, sans-serif; background: #f0f3f8; color: #333; padding: 30px; }}
            .ticket-box {{ max-width: 700px; margin: auto; background: #fff; border: 3px solid #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }}
            .header {{ text-align: center; border-bottom: 2px solid #cbd5e1; padding-bottom: 15px; margin-bottom: 20px; }}
            .header h2 {{ margin: 0; color: #1e3c72; }}
            .header p {{ margin: 5px 0; color: #64748b; font-size: 14px; }}
            .content-flex {{ display: flex; gap: 25px; align-items: center; margin-top: 20px; }}
            .student-img {{ width: 115px; height: 150px; border: 2px solid #1e293b; border-radius: 4px; object-fit: cover; background: #e2e8f0; }}
            .details table {{ width: 100%; border-collapse: collapse; }}
            .details th, .details td {{ padding: 8px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #f1f5f9; }}
            .details th {{ color: #475569; width: 40%; }}
            .footer {{ margin-top: 30px; text-align: center; border-top: 2px solid #cbd5e1; padding-top: 15px; font-size: 12px; color: #64748b; }}
            .btn-container {{ text-align: center; margin-top: 25px; display: flex; gap: 15px; justify-content: center; }}
            .action-btn {{ padding: 12px 24px; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; text-decoration: none; color: white; display: inline-flex; align-items: center; gap: 8px; }}
            .btn-download {{ background: #16a34a; }}
            .btn-print {{ background: #2563eb; }}
            @media print {{
                .btn-container {{ display: none; }}
                body {{ background: #fff; padding: 0; }}
                .ticket-box {{ border: 2px solid #000; box-shadow: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="ticket-box" id="ticket-content">
            <div class="header">
                <h2>STUDENT MANAGEMENT SYSTEM</h2>
                <p>OFFICIAL EXAMINATION HALL TICKET</p>
            </div>
            
            <div class="content-flex">
                <div>
                    <img src="{pic_url}" alt="Profile Picture" class="student-img">
                </div>
                <div class="details" style="flex: 1;">
                    <table>
                        <tr>
                            <th>Jina Kamili:</th>
                            <td><strong>{student['name']}</strong></td>
                        </tr>
                        <tr>
                            <th>Username:</th>
                            <td>{student['username']}</td>
                        </tr>
                        <tr>
                            <th>Darasa / Kidato:</th>
                            <td>{student['darasa']}</td>
                        </tr>
                        <tr>
                            <th>Hali ya Ada:</th>
                            <td><span style="color: #16a34a; font-weight: 600;">Imelipwa Kamili ({perms['percentage']}%)</span></td>
                        </tr>
                        <tr>
                            <th>Hali ya Mtihani:</th>
                            <td><span style="background: #dcfce7; color: #16a34a; padding: 4px 10px; border-radius: 6px; font-weight: 600;">ANARUHUSIWA</span></td>
                        </tr>
                    </table>
                </div>
            </div>

            <div class="footer">
                <p>Hati hii ni rasmi kwa ajili ya kuingilia ukumbi wa mtihani tafadhali kuwa nayo wakati wote.</p>
            </div>
        </div>

        <div class="btn-container">
            <button class="action-btn btn-download" onclick="downloadPDF()">
                <i class="fa-solid fa-download"></i> Pakua PDF (Download)
            </button>
            <button class="action-btn btn-print" onclick="window.print()">
                <i class="fa-solid fa-print"></i> Chapisha / Print
            </button>
        </div>

        <script>
            function downloadPDF() {{
                const element = document.getElementById('ticket-content');
                const options = {{
                    margin:       10,
                    filename:     'Hall_Ticket_{student["name"]}.pdf',
                    image:        {{ type: 'jpeg', quality: 0.98 }},
                    html2canvas:  {{ scale: 2, useCORS: true }},
                    jsPDF:        {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                }};
                html2pdf().from(element).set(options).save();
            }}
        </script>
    </body>
    </html>
    """
    return html_content

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)