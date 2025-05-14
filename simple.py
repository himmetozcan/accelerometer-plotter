from flask import Flask, request
import threading
import queue
import json
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import time
from scipy.interpolate import PchipInterpolator
from collections import deque

# Flask sunucusu
app = Flask(__name__)

# Veri tamponları
BUFFER_SIZE = 10000
times_buffer = deque(maxlen=BUFFER_SIZE)
x_buffer = deque(maxlen=BUFFER_SIZE)
y_buffer = deque(maxlen=BUFFER_SIZE)
z_buffer = deque(maxlen=BUFFER_SIZE)

# Animasyon parametreleri
DISPLAY_WINDOW = 8.0  # saniye
ANIMATION_FPS = 60     # animasyon kare hızı
BATCH_INTERVAL = 1.0   # veri gelme aralığı (saniye)

# Dinamik veri yoğunluğu hesaplama
points_per_second = 20  # başlangıç değeri
min_points_allowed = 5  # minimum nokta sayısı (çok seyrek veri için)
density_update_rate = 0.3  # veri yoğunluğu güncelleme hızı

# Veri filtreleme ve eksen parametreleri
ENABLE_FILTERING = False      # Veri filtreleme aktif/pasif
FIXED_Y_SCALE = False         # Y ekseni sabit ölçeklendirme
Y_MIN = -0.15                 # Y ekseni minimum değeri (sabit ölçekle kullanılır)
Y_MAX = 0.15                  # Y ekseni maksimum değeri (sabit ölçekle kullanılır)
AUTO_Y_SCALE_MARGIN = 0.05    # Otomatik Y ölçekleme için marj

# Veri akışı durumu parametreleri
MAX_NO_DATA_TIME = 3.0        # Veri gelmezse bu süre sonra akış durdurulur (saniye)
FLOW_PAUSED = False           # Akış durumu (durduruldu/devam ediyor)
RESET_NEEDED = False          # Veri akışı başladığında sıfırlama gerekiyor mu?
last_no_data_check = 0        # Son veri akış kontrolü zamanı

# Başlangıç zamanı ve global değişkenler
start_time = None
base_time = None
last_data_time = 0
virtual_time_offset = 0
data_received = False
buffer_lock = threading.Lock()
last_density_calc_time = 0  # son veri yoğunluğu hesaplama zamanı
last_data_count = 0  # Son hesaplamadan bu yana alınan veri noktası sayısı
pause_time = 0      # Akışın durdurulduğu zaman

# Y-ekseni sınırları
y_min_value = -0.1
y_max_value = 0.1
y_scale_update_rate = 0.2  # Y ekseni ölçeğinin yumuşak değişim oranı (daha hızlı değişim)

# Veri ve ekran noktaları - başlangıçta varsayılan değerlerle doldur
n_points = 100  # Başlangıç için varsayılan değer
display_times = np.linspace(0, DISPLAY_WINDOW, n_points)
display_x = np.zeros(n_points)
display_y = np.zeros(n_points)
display_z = np.zeros(n_points)

def reset_all_buffers():
    """Tüm tamponları ve zamanlamayı sıfırla"""
    global times_buffer, x_buffer, y_buffer, z_buffer
    global start_time, base_time, virtual_time_offset, last_data_time
    global display_times, display_x, display_y, display_z
    global y_min_value, y_max_value, points_per_second, last_density_calc_time
    global last_data_count, data_received, RESET_NEEDED
    
    # Tamponları temizle
    times_buffer.clear()
    x_buffer.clear()
    y_buffer.clear()
    z_buffer.clear()
    
    # Zaman referanslarını sıfırla
    start_time = None
    base_time = None
    virtual_time_offset = 0
    last_data_time = 0
    last_density_calc_time = 0
    last_data_count = 0
    
    # Ekran verilerini sıfırla
    display_times = np.linspace(0, DISPLAY_WINDOW, n_points)
    display_x = np.zeros(n_points)
    display_y = np.zeros(n_points)
    display_z = np.zeros(n_points)
    
    # Y-ekseni sınırlarını varsayılan değerlere ayarla
    y_min_value = -0.1
    y_max_value = 0.1
    
    # Veri yoğunluğunu varsayılan değere ayarla
    points_per_second = 20
    
    # Sıfırlama tamamlandı
    data_received = False
    RESET_NEEDED = False
    print("Tüm veriler sıfırlandı, yeni veri akışı bekleniyor...")

@app.route('/sensor', methods=['POST'])
def receive_data():
    global data_received, last_data_time, virtual_time_offset, last_data_count, FLOW_PAUSED, RESET_NEEDED
    data = request.data.decode('utf-8')
    try:
        parsed = json.loads(data)
        acc_data = [entry for entry in parsed['payload'] if entry['name'] == 'accelerometer']
        
        with buffer_lock:
            # Eğer önceden akış durdurulduysa ve yeni veri geldiyse, tamamen sıfırla
            if FLOW_PAUSED or RESET_NEEDED:
                FLOW_PAUSED = False
                RESET_NEEDED = False
                reset_all_buffers()
                print("Veri akışı yeniden başladı - Tüm veriler sıfırlandı")
                # Grafik başlığını güncelle (ana thread'de)
                if 'fig' in globals() and 'ax' in globals():
                    ax.set_title("Gerçek Zamanlı İvmeölçer Verisi - Ham Veri")
            
            # Yeni verileri işle
            for entry in acc_data:
                process_data_point(entry)
            
            # Veri yoğunluğu hesaplaması için veri sayısını artır
            last_data_count += len(acc_data)
            
            data_received = True
            last_data_time = time.time()
            
        print(f"Veri alındı: {len(acc_data)} nokta, toplam: {len(times_buffer)}")
    except Exception as e:
        print(f"Hata: {e}")
    return "OK", 200

def process_data_point(entry):
    """Her bir veri noktasını işle ve tampona ekle"""
    global base_time, start_time
    
    current_time = entry['time']
    
    # İlk veri için referans zamanlarını ayarla
    if base_time is None:
        base_time = current_time
        start_time = time.time()
        print(f"İlk veri alındı, referans zamanı: {base_time}")
    
    # Sensör verisinden gerçek zamanı hesapla (saniye)
    real_time = (current_time - base_time) / 1e9
    
    # Verileri tampona ekle
    times_buffer.append(real_time)
    x_buffer.append(entry['values']['x'])
    y_buffer.append(entry['values']['y'])
    z_buffer.append(entry['values']['z'])

def update_data_density():
    """Saniyede gelen veri noktası sayısını hesapla ve güncelle"""
    global points_per_second, last_density_calc_time, last_data_count
    
    current_time = time.time()
    # İlk veri yoksa veya son hesaplamadan bu yana çok az zaman geçtiyse hesaplama yapma
    if last_density_calc_time == 0 or last_data_count == 0:
        last_density_calc_time = current_time
        last_data_count = 0
        return
    
    # En az 3 saniyede bir yoğunluğu hesapla
    elapsed = current_time - last_density_calc_time
    if elapsed >= 3.0:
        # Saniye başına düşen ortalama veri noktası sayısı
        new_density = last_data_count / elapsed
        
        # Aşırı dalgalanmaları önlemek için yumuşak geçiş yap
        if points_per_second == 20:  # İlk defa hesaplanıyorsa
            points_per_second = max(min_points_allowed, int(new_density))
        else:
            points_per_second = max(
                min_points_allowed,
                int(points_per_second * (1 - density_update_rate) + new_density * density_update_rate)
            )
        
        print(f"Veri yoğunluğu güncellendi: {new_density:.1f} nokta/sn → {points_per_second} nokta/sn")
        
        # Sayaçları sıfırla
        last_density_calc_time = current_time
        last_data_count = 0

def check_data_flow():
    """Veri akışını kontrol et, uzun süre veri gelmezse akışı durdur"""
    global FLOW_PAUSED, last_data_time, last_no_data_check, RESET_NEEDED
    
    current_time = time.time()
    
    # İlk veri geldiyse ve belli bir süre kontrol yapılmadıysa
    if last_data_time > 0 and current_time - last_no_data_check >= 1.0:
        last_no_data_check = current_time
        
        # Son veri gelişinden bu yana geçen süre MAX_NO_DATA_TIME'dan fazla mı?
        if current_time - last_data_time > MAX_NO_DATA_TIME and not FLOW_PAUSED:
            FLOW_PAUSED = True
            RESET_NEEDED = True  # Veri tekrar geldiğinde sıfırlama gerektiğini işaretle
            print(f"Veri akışı durdu! {MAX_NO_DATA_TIME} saniyedir veri yok. Yeni veri geldiğinde sıfırlanacak.")
            
            # Grafik başlığını güncelle
            if 'fig' in globals() and 'ax' in globals():
                ax.set_title("Gerçek Zamanlı İvmeölçer Verisi - AKIŞ DURDURULDU (Veri Bekleniyor)")

def get_virtual_time():
    """Sürekli akan bir sanal zaman değeri döndürür"""
    if start_time is None:
        return 0
    
    # Başlangıçtan bu yana geçen süre
    elapsed = time.time() - start_time
    
    # Virtual offset ile düzeltilmiş zaman
    return elapsed - virtual_time_offset

def update_display_data():
    """Görüntülenecek verileri günceller"""
    global display_times, display_x, display_y, display_z, y_min_value, y_max_value
    
    # Veri yoğunluğunu güncelle
    update_data_density()
    
    # Veri akışını kontrol et
    check_data_flow()
    
    # Akış durdurulduysa veri güncellemeyi atla
    if FLOW_PAUSED:
        return
    
    with buffer_lock:
        # Mevcut sanal zamanı al
        current_time = max(0.1, get_virtual_time())
        
        # Son DISPLAY_WINDOW saniye içindeki verileri filtrele
        window_start = max(0, current_time - DISPLAY_WINDOW)
        
        # Gösterilecek zaman değerlerini ham verileri kullanarak belirle
        if len(times_buffer) > 0:
            # Gerçek veri noktaları
            real_times = np.array(list(times_buffer))
            real_x = np.array(list(x_buffer))
            real_y = np.array(list(y_buffer))
            real_z = np.array(list(z_buffer))
            
            # Verileri sırala (zaman sırasına göre)
            sort_idx = np.argsort(real_times)
            real_times = real_times[sort_idx]
            real_x = real_x[sort_idx]
            real_y = real_y[sort_idx]
            real_z = real_z[sort_idx]
            
            # Son DISPLAY_WINDOW saniyedeki verileri filtrele
            visible_indices = np.where((real_times >= window_start) & (real_times <= current_time))[0]
            
            if len(visible_indices) > 0:
                # Görünür penceredeki verileri hazırla
                display_times = real_times[visible_indices]
                display_x = real_x[visible_indices]
                display_y = real_y[visible_indices]
                display_z = real_z[visible_indices]
                
                # Y ekseni için sınırları güncelle
                if len(display_x) > 0 and not FIXED_Y_SCALE:
                    all_values = np.concatenate([display_x, display_y, display_z])
                    if len(all_values) > 0:
                        vmin, vmax = np.nanmin(all_values), np.nanmax(all_values)
                        
                        # Extreme değerleri filtrele
                        if not np.isnan(vmin) and not np.isnan(vmax):
                            # Y eksenini kademeli olarak güncelle
                            new_min = vmin - AUTO_Y_SCALE_MARGIN
                            new_max = vmax + AUTO_Y_SCALE_MARGIN
                            
                            # Yeterli genişlik sağla
                            if abs(new_max - new_min) < 0.1:
                                center = (new_max + new_min) / 2
                                new_min = center - 0.05
                                new_max = center + 0.05
                                
                            y_min_value = y_min_value * (1 - y_scale_update_rate) + new_min * y_scale_update_rate
                            y_max_value = y_max_value * (1 - y_scale_update_rate) + new_max * y_scale_update_rate

def display_update_loop():
    """Ekran verilerini sürekli güncelleyen döngü"""
    while True:
        update_display_data()
        time.sleep(1.0 / ANIMATION_FPS)

def run_flask():
    app.run(host="0.0.0.0", port=6000)

# Grafik animasyon fonksiyonu
def animate(i):
    global display_times, display_x, display_y, display_z
    
    # Dizilerin boyutlarını kontrol et
    if len(display_times) < 2:
        return line_x, line_y, line_z
    
    # Verileri grafik çizgilerine uygula
    line_x.set_data(display_times, display_x)
    line_y.set_data(display_times, display_y)
    line_z.set_data(display_times, display_z)
    
    # X ekseni - her zaman son DISPLAY_WINDOW saniyeyi göster
    current_time = get_virtual_time()
    min_time = max(0, current_time - DISPLAY_WINDOW)
    ax.set_xlim(min_time, max(min_time + 1, current_time))
    
    # X ekseni etiketlerini güncelle (dakika:saniye olarak)
    x_ticks = np.linspace(min_time, current_time, 7)
    x_labels = [time.strftime("%M:%S", time.gmtime(t)) for t in x_ticks]
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels)
    
    # Y ekseni sınırlarını ayarla - sabit veya otomatik ölçeklendirme
    if FIXED_Y_SCALE:
        ax.set_ylim(Y_MIN, Y_MAX)
    else:
        ax.set_ylim(y_min_value, y_max_value)
    
    return line_x, line_y, line_z

# Flask sunucusunu başlat
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Veri güncelleme döngüsünü başlat
update_thread = threading.Thread(target=display_update_loop)
update_thread.daemon = True
update_thread.start()

print("Server başlatıldı, veri bekleniyor... (Port: 6000)")
print(f"Ham veri görüntüleniyor, Y-ekseni: {'Sabit' if FIXED_Y_SCALE else 'Otomatik'}")
print("Veri yoğunluğu otomatik hesaplanıyor (başlangıç: 20 nokta/sn)")
print(f"{MAX_NO_DATA_TIME} saniye veri gelmezse akış durdurulacak ve yeni veri geldiğinde baştan başlayacak")

# Grafik arayüzünü hazırla
fig, ax = plt.subplots(figsize=(12, 6))
ax.set_xlabel("Zaman (dakika:saniye)")
ax.set_ylabel("İvme (m/s²)")
ax.set_title("Gerçek Zamanlı İvmeölçer Verisi - Ham Veri")
ax.grid(True)

# Grafik çizgilerini oluştur
line_x, = ax.plot([], [], 'b-', label="X", linewidth=1.5)
line_y, = ax.plot([], [], 'r-', label="Y", linewidth=1.5)
line_z, = ax.plot([], [], 'g-', label="Z", linewidth=1.5)
ax.legend(loc="upper right")

# X ekseni başlangıç ayarı
ax.set_xlim(0, DISPLAY_WINDOW)
ax.set_ylim(-0.1, 0.1)  # Başlangıç için varsayılan değerler

# Animasyonu başlat
ani = animation.FuncAnimation(fig, animate, interval=1000/ANIMATION_FPS, blit=True)
plt.show()