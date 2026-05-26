import cv2
import tkinter as tk
from PIL import Image, ImageTk
from ultralytics import YOLO
import mediapipe as mp
from db import get_conn, tao_database, tra_gia, luu_lich_su
import time

# ─── Khởi tạo model ───────────────────────────────────────────────
model = YOLO("yolov8n.pt")

mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands      = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.5
)

# ─── Hằng số ──────────────────────────────────────────────────────
CAM_W, CAM_H   = 660, 540
WIN_W, WIN_H   = 1000, 540
PANEL_W        = WIN_W - CAM_W          # 340px
CONF_NGUONG    = 0.50                   # chỉ hiển thị khi >= 50%
LUU_COOLDOWN   = 3.0                    # giây giữa 2 lần lưu lịch sử


def hop_giao_nhau(box_a, box_b) -> bool:
    """Trả True nếu 2 bounding box giao nhau (tay đang cầm sản phẩm)."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def dinh_dang_gia(gia_min: int, gia_max: int, don_vi: str) -> str:
    return f"{gia_min:,}đ – {gia_max:,}đ / {don_vi}"


# ─── Giao diện Tkinter ────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        root.title("Nhận diện rau củ quả & Giá chợ")
        root.geometry(f"{WIN_W}x{WIN_H}")
        root.resizable(False, False)
        root.configure(bg="#1a1a1a")

        # ── Khung camera (trái 2/3) ──────────────────────────────
        self.lbl_cam = tk.Label(root, bg="#000000", cursor="none")
        self.lbl_cam.place(x=0, y=0, width=CAM_W, height=CAM_H)

        # ── Panel thông tin (phải 1/3) ───────────────────────────
        panel = tk.Frame(root, bg="#1e1e1e")
        panel.place(x=CAM_W, y=0, width=PANEL_W, height=WIN_H)

        # Tiêu đề panel
        tk.Label(
            panel, text="THÔNG TIN SẢN PHẨM",
            bg="#1e1e1e", fg="#555555",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", padx=20, pady=(20, 0))

        self._duong_ke(panel)

        # Tên sản phẩm
        tk.Label(panel, text="Sản phẩm",
                 bg="#1e1e1e", fg="#777777",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(12,0))
        self.lbl_ten = tk.Label(
            panel, text="—",
            bg="#1e1e1e", fg="#ffffff",
            font=("Segoe UI", 24, "bold"),
            wraplength=PANEL_W - 40, justify="left"
        )
        self.lbl_ten.pack(anchor="w", padx=20)

        # Độ tin cậy
        self.lbl_conf = tk.Label(
            panel, text="",
            bg="#1e1e1e", fg="#555555",
            font=("Segoe UI", 10)
        )
        self.lbl_conf.pack(anchor="w", padx=20)

        self._duong_ke(panel)

        # Giá
        tk.Label(panel, text="Giá tham khảo",
                 bg="#1e1e1e", fg="#777777",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(12,0))
        self.lbl_gia = tk.Label(
            panel, text="—",
            bg="#1e1e1e", fg="#4ade80",
            font=("Segoe UI", 16, "bold")
        )
        self.lbl_gia.pack(anchor="w", padx=20)

        self._duong_ke(panel)

        # Trạng thái tay
        tk.Label(panel, text="Trạng thái",
                 bg="#1e1e1e", fg="#777777",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(12,0))
        self.lbl_tay = tk.Label(
            panel, text="Chưa phát hiện tay",
            bg="#1e1e1e", fg="#888888",
            font=("Segoe UI", 12)
        )
        self.lbl_tay.pack(anchor="w", padx=20)

        self._duong_ke(panel)

        # Lịch sử nhận diện (5 dòng gần nhất)
        tk.Label(panel, text="Gần đây",
                 bg="#1e1e1e", fg="#777777",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(12,0))
        self.frame_history = tk.Frame(panel, bg="#1e1e1e")
        self.frame_history.pack(fill="x", padx=20)
        self.history_labels = []
        for _ in range(5):
            lbl = tk.Label(
                self.frame_history, text="",
                bg="#1e1e1e", fg="#444444",
                font=("Segoe UI", 10), anchor="w"
            )
            lbl.pack(fill="x")
            self.history_labels.append(lbl)

        # Nút thoát
        tk.Button(
            panel, text="✕  Thoát",
            bg="#2d2d2d", fg="#888888",
            font=("Segoe UI", 10),
            relief="flat", cursor="hand2",
            command=self._thoat
        ).pack(side="bottom", fill="x", padx=20, pady=20)

        # ── Biến trạng thái ──────────────────────────────────────
        self.history   = []
        self.last_save = 0.0
        self.cap       = cv2.VideoCapture(0)
        self.running   = True

        root.protocol("WM_DELETE_WINDOW", self._thoat)
        self._update()

    # ── Tiện ích UI ───────────────────────────────────────────────
    def _duong_ke(self, parent):
        tk.Frame(parent, bg="#2a2a2a", height=1).pack(
            fill="x", padx=20, pady=6)

    def _cap_nhat_history(self, ten_vn: str):
        """Thêm tên SP vào đầu danh sách lịch sử."""
        if not self.history or self.history[0] != ten_vn:
            self.history.insert(0, ten_vn)
            self.history = self.history[:5]
        for i, lbl in enumerate(self.history_labels):
            lbl.config(
                text=f"• {self.history[i]}" if i < len(self.history) else "",
                fg="#555555" if i > 0 else "#888888"
            )

    # ── Vòng lặp chính ───────────────────────────────────────────
    def _update(self):
        if not self.running:
            return

        ret, frame = self.cap.read()
        if not ret:
            self.lbl_cam.after(30, self._update)
            return
        
        frame = cv2.flip(frame, 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h_frame, w_frame = frame.shape[:2]

        # ── Nhận diện bàn tay ─────────────────────────────────
        hand_result = hands.process(rgb)
        hand_boxes  = []

        if hand_result.multi_hand_landmarks:
            for lm in hand_result.multi_hand_landmarks:
                xs = [p.x * w_frame for p in lm.landmark]
                ys = [p.y * h_frame for p in lm.landmark]
                hx1, hy1 = int(min(xs)) - 10, int(min(ys)) - 10
                hx2, hy2 = int(max(xs)) + 10, int(max(ys)) + 10
                hand_boxes.append((hx1, hy1, hx2, hy2))
                cv2.rectangle(rgb, (hx1, hy1), (hx2, hy2),
                              (250, 204, 20), 2)
                cv2.putText(rgb, "Tay", (hx1, hy1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (250, 204, 20), 1)

        # ── Nhận diện sản phẩm ────────────────────────────────
        results = model(frame, verbose=False)[0]
        co_cam  = False

        for box in results.boxes:
            conf   = float(box.conf[0])
            if conf < CONF_NGUONG:
                continue

            ten_en = model.names[int(box.cls[0])]
            
            # Bỏ qua các nhãn không phải sản phẩm
            BO_QUA = {"person", "chair", "couch", "bed", "dining table",
                    "laptop", "tv", "cell phone",
                    "vase", "scissors"}
            if ten_en in BO_QUA:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            sp_box = (x1, y1, x2, y2)

            # Kiểm tra tay cầm sản phẩm
            dang_cam = any(hop_giao_nhau(hb, sp_box) for hb in hand_boxes)
            mau_box  = (74, 222, 128) if dang_cam else (120, 120, 120)

            cv2.rectangle(rgb, (x1, y1), (x2, y2), mau_box, 2)
            cv2.putText(rgb,
                        f"{ten_en} {conf*100:.0f}%",
                        (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, mau_box, 2)

            # Chỉ cập nhật panel khi tay đang cầm
            if dang_cam:
                co_cam = True
                info   = tra_gia(ten_en)
                ten_hien = info[0] if info else ten_en.capitalize()

                self.lbl_ten.config(text=ten_hien)
                self.lbl_conf.config(
                    text=f"Độ tin cậy: {conf*100:.0f}%")

                if info:
                    self.lbl_gia.config(
                        text=dinh_dang_gia(info[1], info[2], info[3]))
                else:
                    self.lbl_gia.config(text="Chưa có trong database")

                self.lbl_tay.config(
                    text="✓ Đang cầm sản phẩm", fg="#4ade80")
                self._cap_nhat_history(ten_hien)

                # Lưu lịch sử vào DB (throttle 3 giây)
                now = time.time()
                if now - self.last_save >= LUU_COOLDOWN:
                    luu_lich_su(ten_hien, conf)
                    self.last_save = now

        # Khi không có sản phẩm đang được cầm
        if not co_cam:
            self.lbl_ten.config(text="—")
            self.lbl_conf.config(text="")
            self.lbl_gia.config(text="—")
            if hand_boxes:
                self.lbl_tay.config(
                    text="Tay trống — hãy cầm sản phẩm", fg="#facc15")
            else:
                self.lbl_tay.config(
                    text="Chưa phát hiện tay", fg="#555555")

        # ── Hiển thị frame lên Tkinter ────────────────────────
        img_resized = cv2.resize(rgb, (CAM_W, CAM_H))
        img_pil     = Image.fromarray(img_resized)
        self.imgtk  = ImageTk.PhotoImage(img_pil)
        self.lbl_cam.config(image=self.imgtk)

        self.lbl_cam.after(30, self._update)   # ~33 fps

    def _thoat(self):
        self.running = False
        self.cap.release()
        self.lbl_cam.winfo_toplevel().destroy()
        



# ─── Chạy ứng dụng ────────────────────────────────────────────────
if __name__ == "__main__":
    print("🔧 Đang khởi tạo database...")
    tao_database()
    print("🚀 Khởi động ứng dụng...")
    root = tk.Tk()
    App(root)
    root.mainloop()