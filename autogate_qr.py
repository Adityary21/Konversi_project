import streamlit as st
import mysql.connector
import time
import qrcode
import random
from PIL import Image
from io import BytesIO
import pandas as pd
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import base64
import requests

# Inisialisasi session_state
if 'qr_code' not in st.session_state:
    st.session_state.qr_code = ""
if 'qr_valid' not in st.session_state:
    st.session_state.qr_valid = False
if 'gate_1_status' not in st.session_state:
    st.session_state.gate_1_status = "locked"
if 'gate_2_status' not in st.session_state:
    st.session_state.gate_2_status = "locked"
if 'gate_3_status' not in st.session_state:
    st.session_state.gate_3_status = "locked"

# Koneksi ke MySQL
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',
    database='autogate_simulation'
)
cursor = conn.cursor(dictionary=True)

# Mengirim perintah ke Raspberry Pi Pico
def send_command_to_pico(command_on, command_off, duration=5):
    pico_ip = "http://192.168.0.106"
    try:
        response_on = requests.get(f"{pico_ip}/{command_on}")
        if response_on.status_code != 200:
            st.write(f"Failed to send command '{command_on}' to turn on relay.")
        time.sleep(duration)
        response_off = requests.get(f"{pico_ip}/{command_off}")
        if response_off.status_code != 200:
            st.write(f"Failed to send command '{command_off}' to turn off relay.")
    except Exception as e:
        st.write(f"Error sending relay command: {e}")

# Membuat QR code
def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()

# Menyimpan data QR ke database
def save_qr_to_db(nama, umur, harga_tiket, qr_code, random_number, tipe_qr, max_scans):
    query = "INSERT INTO qr_codes (nama, umur, harga_tiket, qr_code, random_number, tipe_qr, max_scans) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    cursor.execute(query, (nama, umur, harga_tiket, qr_code, random_number, tipe_qr, max_scans))
    conn.commit()

# Memproses QR code di gerbang
def process_qr_entry(qr_code):
    query = "SELECT * FROM qr_codes WHERE qr_code = %s AND status IN ('ready', 'already')"
    cursor.execute(query, (qr_code,))
    result = cursor.fetchone()
    
    if result:
        if result['tipe_qr'] == 'individu' and result['status'] == 'ready':
            cursor.execute("UPDATE qr_codes SET status = 'already' WHERE qr_code = %s", (qr_code,))
            conn.commit()
            send_command_to_pico('1/on', '1/off')
            cursor.execute("INSERT INTO gate_log (gate_id, action, tag_id, type) VALUES (1, 'entry', %s, 'qr_individu')", (qr_code,))
            conn.commit()
            return True

        elif result['tipe_qr'] == 'group' and result['scans_done'] < result['max_scans']:
            cursor.execute("UPDATE qr_codes SET scans_done = scans_done + 1 WHERE qr_code = %s", (qr_code,))
            conn.commit()
            if result['scans_done'] + 1 >= result['max_scans']:
                cursor.execute("UPDATE qr_codes SET status = 'already' WHERE qr_code = %s", (qr_code,))
                conn.commit()
            send_command_to_pico('1/on', '1/off')
            cursor.execute("INSERT INTO gate_log (gate_id, action, tag_id, type) VALUES (3, 'entry', %s, 'qr_group')", (qr_code,))
            conn.commit()
            return True
    return False
    
def process_gate_action(gate_id, tag_id, action):
    cursor.execute("SELECT status FROM daftar_kartu WHERE tag_id = %s", (tag_id,))
    card = cursor.fetchone()

    if action == 'entry' and card and card['status'] == 'outside':
        cursor.execute("UPDATE daftar_kartu SET status = 'inside' WHERE tag_id = %s", (tag_id,))
        cursor.execute("INSERT INTO gate_log (gate_id, action, tag_id) VALUES (%s, %s, %s)", (gate_id, action, tag_id))
        conn.commit()
        return True

    elif action == 'exit' and card and card['status'] == 'inside':
        cursor.execute("UPDATE daftar_kartu SET status = 'outside' WHERE tag_id = %s", (tag_id,))
        cursor.execute("INSERT INTO gate_log (gate_id, action, tag_id) VALUES (%s, %s, %s)", (gate_id, action, tag_id))
        conn.commit()
        return True

    return False

# Menampilkan status gerbang dan total masuk/keluar di Streamlit
def display_gate_status():
    st.header("Status Gerbang")
    cursor.execute("SELECT COUNT(*) AS total_entry FROM gate_log WHERE action = 'entry'")
    total_entry = cursor.fetchone()['total_entry']
    cursor.execute("SELECT COUNT(*) AS total_exit FROM gate_log WHERE action = 'exit'")
    total_exit = cursor.fetchone()['total_exit']
    st.write(f"Total yang masuk: {total_entry}")
    st.write(f"Total yang keluar: {total_exit}")
    st.write(f"Total yang di dalam: {total_entry - total_exit}")
    return total_entry, total_exit

# Mengonversi gambar ke base64
def image_to_base64(image):
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# Menampilkan status gerbang dengan warna dan ikon
def display_gate(gate_id, status):
    lock_icon = Image.open("lock.png") if status == "locked" else Image.open("unlock.png")
    img_str = image_to_base64(lock_icon)
    color = "green" if status == "open" else "red"
    return f"""
    <div style="display: flex; align-items: center; justify-content: center; flex-direction: column;">
        <img src="data:image/png;base64,{img_str}" style="width:50px;height:50px;" />
        <div style="background-color: {color}; padding: 20px; text-align: center; margin-top: 10px;">
            Gerbang {gate_id}
        </div>
    </div>
    """

class VideoTransformer(VideoTransformerBase):
    def __init__(self):
        self.qr_code_detected = False

    def recv(self, frame):
        image = frame.to_ndarray(format="bgr24")
        for barcode in decode(image):
            qr_data = barcode.data.decode('utf-8')
            qr_polygon = np.array([barcode.polygon], np.int32).reshape((-1, 1, 2))
            cv2.polylines(image, [qr_polygon], True, (0, 255, 0), 2)
            cv2.putText(image, qr_data, (barcode.rect.left, barcode.rect.top), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            if not self.qr_code_detected:
                self.qr_code_detected = True
                st.session_state.qr_code = qr_data
                st.session_state.qr_valid = process_qr_entry(qr_data)
                st.session_state.gate_1_status = "open" if st.session_state.qr_valid else "locked"
        return frame

# Sidebar untuk navigasi halaman
halaman_terpilih = st.sidebar.radio("Pilih Halaman", ["Data Pengunjung", "Simulasi Gerbang", "Tiket QR"])

if halaman_terpilih == "Data Pengunjung":
    st.title("Data Pengunjung")
    query = "SELECT * FROM gate_log ORDER BY timestamp DESC"
    cursor.execute(query)
    data = cursor.fetchall()
    df = pd.DataFrame(data)
    if not df.empty:
        df.index += 1
        df.index.name = "Nomor"
        st.write("Berikut adalah data pengunjung yang tercatat:")
        st.table(df)
        csv = df.to_csv().encode('utf-8')
        st.download_button(label="Unduh data menjadi CSV", data=csv, file_name="data_pengunjung.csv", mime="text/csv")
    query1 = "SELECT * FROM daftar_kartu WHERE status = 'inside'"
    cursor.execute(query1)
    data1 = cursor.fetchall()
    df1 = pd.DataFrame(data1)
    if not df1.empty:
        df1.index += 1
        df1.index.name = "Nomor"
        st.write("Berikut data kartu yang ada di dalam:")
        st.table(df1)

elif halaman_terpilih == "Simulasi Gerbang":
    st.title("Simulasi Gerbang")
    gate_1_placeholder = st.empty()
    gate_2_placeholder = st.empty()
    gate_3_placeholder = st.empty()

    with st.sidebar.expander("Input RFID"):
        rfid_input = st.text_input("Masukkan ID Kartu RFID:")
        if st.button("Simulasikan Masuk"):
            if rfid_input and process_gate_action(1, rfid_input, 'entry'):
                st.session_state.gate_1_status = "open"
                st.success("Gerbang 1 terbuka untuk masuk.")
                gate_1_placeholder.markdown(display_gate(1, st.session_state.gate_1_status), unsafe_allow_html=True)
                time.sleep(5)
                st.session_state.gate_1_status = "locked"
                gate_1_placeholder.markdown(display_gate(1, st.session_state.gate_1_status), unsafe_allow_html=True)
            else:
                st.sidebar.write("Akses Ditolak atau Kartu sudah di dalam.")
        if st.button("Simulasikan Keluar"):
            if rfid_input and process_gate_action(2, rfid_input, 'exit'):
                st.session_state.gate_2_status = "open"
                st.success("Gerbang 2 terbuka untuk keluar.")
                gate_2_placeholder.markdown(display_gate(2, st.session_state.gate_2_status), unsafe_allow_html=True)
                time.sleep(5)
                st.session_state.gate_2_status = "locked"
                gate_2_placeholder.markdown(display_gate(2, st.session_state.gate_2_status), unsafe_allow_html=True)
            else:
                st.sidebar.write("Akses Ditolak atau Kartu tidak ada di dalam.")

    with st.sidebar.expander("Input QR Code"):
        qr_code_input = st.text_input("Masukkan QR Code:")
        if st.button("Simulasikan Masuk dengan QR Code"):
            if qr_code_input and process_qr_entry(qr_code_input):
                if 'group' in qr_code_input:
                    st.session_state.gate_3_status = "open"
                    st.success(f"QR Code Group '{qr_code_input}' valid. Gerbang 3 terbuka!")
                    gate_3_placeholder.markdown(display_gate(3, st.session_state.gate_3_status), unsafe_allow_html=True)
                    time.sleep(5)
                    st.session_state.gate_3_status = "locked"
                    gate_3_placeholder.markdown(display_gate(3, st.session_state.gate_3_status), unsafe_allow_html=True)
                else:
                    st.session_state.gate_1_status = "open"
                    st.success(f"QR Code Individu '{qr_code_input}' valid. Gerbang 1 terbuka!")
                    gate_1_placeholder.markdown(display_gate(1, st.session_state.gate_1_status), unsafe_allow_html=True)
                    time.sleep(5)
                    st.session_state.gate_1_status = "locked"
                    gate_1_placeholder.markdown(display_gate(1, st.session_state.gate_1_status), unsafe_allow_html=True)
            else:
                st.sidebar.write("Akses Ditolak atau QR Code tidak valid.")

    st.header("Scan QR Code Menggunakan Webcam")
    webrtc_ctx = webrtc_streamer(key="example", video_processor_factory=VideoTransformer, media_stream_constraints={"video": True, "audio": False}, async_processing=True)
    gate_1_placeholder.markdown(display_gate(1, st.session_state.gate_1_status), unsafe_allow_html=True)
    gate_2_placeholder.markdown(display_gate(2, st.session_state.gate_2_status), unsafe_allow_html=True)
    gate_3_placeholder.markdown(display_gate(3, st.session_state.gate_3_status), unsafe_allow_html=True)
    display_gate_status()

if halaman_terpilih == "Tiket QR":
    st.title("Formulir Pembelian Tiket dengan QR Code")
    tipe_qr = st.radio("Pilih Tipe Tiket", ["individu", "group"])
    if tipe_qr == "individu":
        st.subheader("Formulir Tiket Individu")
        with st.form("individu_form"):
            nama = st.text_input("Nama")
            umur = st.number_input("Umur", min_value=0, max_value=120, step=1)
            harga_tiket = st.number_input("Harga Tiket", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("Buat QR Code")
            if submitted and nama and umur > 0 and harga_tiket > 0:
                random_number = random.randint(1000, 9999)
                combined_data = f"{nama}_{umur}_{random_number}"
                qr_code = generate_qr(combined_data)
                st.image(qr_code, caption=f"QR Code for {nama}", use_column_width=True)
                save_qr_to_db(nama, umur, harga_tiket, combined_data, random_number, tipe_qr, 1)
                st.success("QR code untuk individu berhasil dibuat dan disimpan ke database!")
            else:
                st.error("Pastikan semua data sudah diisi dengan benar.")
    elif tipe_qr == "group":
        st.subheader("Formulir Tiket Group")
        with st.form("group_form"):
            nama = st.text_input("Nama")
            umur = st.number_input("Umur", min_value=0, max_value=120, step=1)
            harga_tiket = st.number_input("Harga Tiket", min_value=0.0, step=0.01)
            max_scans = st.number_input("Maksimal Scan", min_value=2, step=1)
            submitted = st.form_submit_button("Buat QR Code")
            if submitted and nama and umur > 0 and harga_tiket > 0:
                random_number = random.randint(1000, 9999)
                combined_data = f"{nama}_{umur}_{random_number}"
                qr_code = generate_qr(combined_data)
                st.image(qr_code, caption=f"QR Code for {nama}", use_column_width=True)
                save_qr_to_db(nama, umur, harga_tiket, combined_data, random_number, tipe_qr, max_scans)
                st.success("QR code untuk group berhasil dibuat dan disimpan ke database!")
            else:
                st.error("Pastikan semua data sudah diisi dengan benar.")

conn.close()
