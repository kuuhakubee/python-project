import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_conn():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME"),
        ssl_ca=os.path.join(BASE_DIR, "ca.pem")
    )


def tao_database():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS san_pham (
            id       INT AUTO_INCREMENT PRIMARY KEY,
            ten_en   VARCHAR(100) UNIQUE,
            ten_vn   VARCHAR(100),
            gia_min  INT,
            gia_max  INT,
            don_vi   VARCHAR(20) DEFAULT 'kg'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lich_su (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            ten_sp     VARCHAR(100),
            confidence FLOAT,
            thoi_gian  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cap_nhat_gia (
            id       INT AUTO_INCREMENT PRIMARY KEY,
            sp_id    INT,
            gia_min  INT,
            gia_max  INT,
            ngay     DATE DEFAULT (CURDATE()),
            FOREIGN KEY (sp_id) REFERENCES san_pham(id)
        )
    """)

    # Dữ liệu mẫu
    mau = [
        ("banana",     "Chuối",    15000, 25000, "kg"),
        ("apple",      "Táo",      40000, 70000, "kg"),
        ("orange",     "Cam",      30000, 50000, "kg"),
        ("tomato",     "Cà chua",  20000, 35000, "kg"),
        ("carrot",     "Cà rốt",   15000, 25000, "kg"),
        ("cucumber",   "Dưa leo",  10000, 20000, "kg"),
        ("watermelon", "Dưa hấu",   8000, 15000, "kg"),
        ("mango",      "Xoài",     25000, 60000, "kg"),
        ("pineapple",  "Khóm",     15000, 30000, "trái"),
        ("cabbage",    "Bắp cải",  10000, 18000, "kg"),
        ("broccoli",   "Bông cải", 25000, 45000, "kg"),
        ("lemon",      "Chanh",    20000, 40000, "kg"),
    ]
    cursor.executemany(
        "INSERT IGNORE INTO san_pham (ten_en, ten_vn, gia_min, gia_max, don_vi) VALUES (%s,%s,%s,%s,%s)",
        mau
    )

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database và bảng đã được tạo thành công.")


def tra_gia(ten_en: str):
    """Trả về (ten_vn, gia_min, gia_max, don_vi) hoặc None"""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ten_vn, gia_min, gia_max, don_vi FROM san_pham WHERE ten_en = %s",
            (ten_en.lower(),)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row
    except Exception as e:
        print(f"Lỗi tra_gia: {e}")
        return None


def luu_lich_su(ten_sp: str, confidence: float):
    """Lưu lần nhận diện vào bảng lich_su"""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO lich_su (ten_sp, confidence) VALUES (%s, %s)",
            (ten_sp, round(confidence, 4))
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Lỗi luu_lich_su: {e}")