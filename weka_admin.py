import mysql.connector
try:
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="student_management"
    )
    cursor = db.cursor()
    # SQL ya kuingiza admin mpya. 
    # KUMBUKA: Kama jedwali lako halina nguzo ya 'role', unaweza kuondoa '%s' ya tatu na neno 'Admin'
    sql = "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)"
    val = ("admin", "admin123", "Admin")
    cursor.execute(sql, val)
    db.commit()
    print("=========================================")
    print(" AKAUNTI YA ADMIN IMETENGENEZWA! ")
    print("=========================================")
    print("Sasa unaweza kutumia credentials hizi kulogin:")
    print("-> Username: admin")
    print("-> Password: admin123")
    print("=========================================")
except mysql.connector.Error as err:
    print(f"Hitilafu ya Database: {err}")
finally:
    if 'db' in locals() and db.is_connected():
        cursor.close()
        db.close()