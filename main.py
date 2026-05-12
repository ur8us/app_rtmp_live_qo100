from maix import camera, display, time, app, image, touchscreen, video
import json
import os
import subprocess

font_size = 16
image.load_font("font", "/maixapp/share/font/SourceHanSansCN-Regular.otf", size=font_size)
image.set_default_font("font")

disp = display.Display()
ts = touchscreen.TouchScreen()

STREAM_WIDTH = 640
STREAM_HEIGHT = 480
STREAM_FPS = 15
STREAM_GOP = 15
FFMPEG_LOG = "/tmp/rtmp_live_qo100_ffmpeg.log"
CONFIG_DIR = "/root/.config/rtmp_live_qo100"
CONFIG_PATH = CONFIG_DIR + "/settings.json"
URL_HISTORY_LIMIT = 10

CODECS = [
    ("H.264", video.VideoType.VIDEO_H264_CBR, "h264"),
    ("H.265", video.VideoType.VIDEO_H265_CBR, "hevc"),
]

BITRATES = [
    ("33 kbps", 33 * 1000),
    ("66 kbps", 66 * 1000),
    ("125 kbps", 125 * 1000),
    ("250 kbps", 250 * 1000),
    ("333 kbps", 333 * 1000),
    ("500 kbps", 500 * 1000),
    ("1 Mbps", 1000 * 1000),
    ("1.5 Mbps", 1500 * 1000),
    ("2 Mbps", 2000 * 1000),
]

choice_codec = 0
choice_bitrate = 4
url_history = []

cam = None
encoder = None
ffmpeg_proc = None
ffmpeg_log = None

str_height_2 = image.string_size("font", 2).height()
str_find_not_url = "Click icon to start scan"
str_rtmp_is_running1 = "rtmp live running"
str_rtmp_is_running2 = "rtmp live running ."
str_rtmp_is_running3 = "rtmp live running . ."
str_no_url_tips1 = "Get RTMP server address from live platform"
str_no_url_tips2 = "Scan QRCode with server address"
str_scan_tips1 = "1. Get RTMP server addr from live platform"
str_scan_tips2 = " format like rtmp://host:port/ or /app/stream"
str_scan_tips3 = "2. Generate QRCode with server addr, scan"

img_exit = image.load("./assets/exit.jpg").resize(50, 50)
img_exit_touch = image.load("./assets/exit_touch.jpg").resize(50, 50)
img_scan = image.load("./assets/scan.png")
img_start = image.load("./assets/start.png").resize(120, 120)
img_running = image.load("./assets/running.png")

global_status = 0  # 0 idle, 1 scan qrcode, 2 init stream, 3 run stream, 4 url history
global_url = ""
global_err_msg = ""
base_img = image.Image(disp.width(), disp.height(), bg=image.COLOR_BLACK)

run_last_ms = time.ticks_ms()
run_cnt = 0
last_touch_ms = 0


def in_box(t, box, pad=0):
    return (
        t[2]
        and t[0] >= box[0] - pad
        and t[0] <= box[0] + box[2] + pad
        and t[1] >= box[1] - pad
        and t[1] <= box[1] + box[3] + pad
    )


def touch_ready():
    global last_touch_ms
    now = time.ticks_ms()
    if now - last_touch_ms > 180:
        last_touch_ms = now
        return True
    return False


def current_codec():
    return CODECS[choice_codec]


def current_bitrate():
    return BITRATES[choice_bitrate]


def cycle_codec():
    global choice_codec
    choice_codec = (choice_codec + 1) % len(CODECS)
    save_state()


def cycle_bitrate():
    global choice_bitrate
    choice_bitrate = (choice_bitrate + 1) % len(BITRATES)
    save_state()


def parse_url(url):
    host = ""
    port = 0
    application = ""
    stream = ""
    url = str(url).strip()
    if not (url.startswith("rtmp://") or url.startswith("rtmps://")):
        print("parse url failed: {}".format(url))
        return (False, host, port, application, stream)

    res1 = url.split("//", 1)
    if len(res1) < 2:
        print("parse url failed: {}".format(url))
        return (False, host, port, application, stream)

    res2 = res1[1].split("/", 1)
    if len(res2) < 1 or len(res2[0]) == 0:
        print("parse url failed: {}".format(url))
        return (False, host, port, application, stream)

    res3 = res2[0].split(":")
    if len(res3) == 1:
        host = res3[0]
        port = 1935
    elif len(res3) == 2:
        host = res3[0]
        try:
            port = int(res3[1])
        except Exception:
            print("parse url failed: {}".format(url))
            return (False, host, port, application, stream)
    else:
        print("parse url failed: {}".format(url))
        return (False, host, port, application, stream)

    if port <= 0 or port > 65535:
        print("parse url failed: {}".format(url))
        return (False, host, port, application, stream)

    if len(res2) > 1:
        path = res2[1]
        if len(path) > 0:
            res4 = path.split("/", 1)
            application = res4[0]
            if len(res4) > 1:
                stream = res4[1]

    return (len(host) > 0, host, port, application, stream)


def load_state():
    global choice_codec, choice_bitrate, global_url, url_history

    if not os.path.exists(CONFIG_PATH):
        return

    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
    except Exception as e:
        print("load config skipped: {}".format(e))
        return

    try:
        value = int(data.get("codec_index", choice_codec))
        if value >= 0 and value < len(CODECS):
            choice_codec = value
    except Exception:
        codec = str(data.get("codec", "")).lower().replace(".", "")
        if codec in ("h265", "hevc", "265"):
            choice_codec = 1
        elif codec in ("h264", "avc", "264"):
            choice_codec = 0

    try:
        value = int(data.get("bitrate_index", choice_bitrate))
        if value >= 0 and value < len(BITRATES):
            choice_bitrate = value
    except Exception:
        try:
            bitrate = int(data.get("bitrate", BITRATES[choice_bitrate][1]))
            for i, item in enumerate(BITRATES):
                if item[1] == bitrate:
                    choice_bitrate = i
                    break
        except Exception:
            pass

    urls = []
    for url in data.get("url_history", []):
        url = str(url).strip()
        ok, _, _, _, _ = parse_url(url)
        if ok and url not in urls:
            urls.append(url)
        if len(urls) >= URL_HISTORY_LIMIT:
            break
    url_history = urls

    last_url = str(data.get("last_url", "")).strip()
    if last_url:
        ok, _, _, _, _ = parse_url(last_url)
        if ok:
            global_url = last_url
            if global_url not in url_history:
                url_history.insert(0, global_url)
                url_history = url_history[:URL_HISTORY_LIMIT]

    if not global_url and len(url_history):
        global_url = url_history[0]


def save_state():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        codec_label, _, _ = current_codec()
        bitrate_label, bitrate_value = current_bitrate()
        data = {
            "codec": codec_label,
            "codec_index": choice_codec,
            "bitrate": bitrate_value,
            "bitrate_label": bitrate_label,
            "bitrate_index": choice_bitrate,
            "last_url": global_url,
            "url_history": url_history[:URL_HISTORY_LIMIT],
        }
        tmp_path = CONFIG_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, CONFIG_PATH)
    except Exception as e:
        print("save config failed: {}".format(e))


def remember_url(url):
    global global_url, url_history

    url = str(url).strip()
    ok, _, _, _, _ = parse_url(url)
    if not ok:
        return False

    global_url = url
    urls = [url]
    for item in url_history:
        if item != url:
            urls.append(item)
        if len(urls) >= URL_HISTORY_LIMIT:
            break
    url_history = urls
    save_state()
    return True


def draw_text_fit(img, box, text, color, max_scale=1.5, min_scale=0.8):
    scale = max_scale
    while scale > min_scale and image.string_size(text, scale=scale).width() > box[2] - 10:
        scale -= 0.1
    size = image.string_size(text, scale=scale)
    x = box[0] + (box[2] - size.width()) // 2
    y = box[1] + (box[3] - size.height()) // 2
    img.draw_string(x, y, text, color, scale)


def draw_center_text(img, y, text, color, scale=2):
    size = image.string_size(text, scale=scale)
    img.draw_string((img.width() - size.width()) // 2, y, text, color, scale)


def ellipsize_middle(text, max_width, scale=1):
    if image.string_size(text, scale=scale).width() <= max_width:
        return text
    left = text[: max(1, len(text) // 2)]
    right = text[max(1, len(text) // 2) :]
    while len(left) + len(right) > 6:
        value = left + "..." + right
        if image.string_size(value, scale=scale).width() <= max_width:
            return value
        if len(left) > len(right):
            left = left[:-1]
        else:
            right = right[1:]
    return text[:3] + "..."


def settings_boxes():
    screen_w = base_img.width()
    x = 85 if screen_w >= 500 else 75
    y = 74
    gap = 14
    total_w = screen_w - x - 20
    w = (total_w - gap) // 2
    return [x, y, w, 68], [x + w + gap, y, w, 68]


def history_button_box(y):
    w = 220 if base_img.width() >= 500 else 180
    h = 54
    return [(base_img.width() - w) // 2, y, w, h]


def draw_setting_button(img, t, box, label, value):
    bg = image.Color.from_rgb(45, 45, 45)
    bg_touch = image.Color.from_rgb(40, 130, 220)
    txt = image.Color.from_rgb(255, 255, 255)
    muted = image.Color.from_rgb(150, 150, 150)
    img.draw_rect(box[0], box[1], box[2], box[3], bg_touch if in_box(t, box) else bg, -1)
    img.draw_string(box[0] + 10, box[1] + 5, label, muted, 1.5)
    value_box = [box[0] + 4, box[1] + 27, box[2] - 8, box[3] - 29]
    draw_text_fit(img, value_box, value, txt, 2.25, 1.2)


def draw_settings(img, t):
    enc_box, bitrate_box = settings_boxes()
    draw_setting_button(img, t, enc_box, "Codec", current_codec()[0])
    draw_setting_button(img, t, bitrate_box, "Bitrate", current_bitrate()[0])
    return enc_box, bitrate_box


def update_settings_from_touch(t):
    global global_err_msg
    enc_box, bitrate_box = settings_boxes()
    if not t[2]:
        return False
    if in_box(t, enc_box):
        if touch_ready():
            cycle_codec()
            global_err_msg = ""
        return True
    if in_box(t, bitrate_box):
        if touch_ready():
            cycle_bitrate()
            global_err_msg = ""
        return True
    return False


def draw_history_button(img, t, y):
    box = history_button_box(y)
    enabled = len(url_history) > 0
    bg = image.Color.from_rgb(45, 45, 45) if enabled else image.Color.from_rgb(30, 30, 30)
    bg_touch = image.Color.from_rgb(40, 130, 220)
    txt = image.Color.from_rgb(255, 255, 255) if enabled else image.Color.from_rgb(100, 100, 100)
    img.draw_rect(box[0], box[1], box[2], box[3], bg_touch if enabled and in_box(t, box) else bg, -1)
    label = "History"
    if enabled:
        label = "History {}".format(len(url_history))
    draw_text_fit(img, box, label, txt, 2.1, 1.2)
    return box


def draw_exit_button(img, t):
    box = [20, 15, img_exit.width(), img_exit.height()]
    if in_box(t, box, 20):
        img.draw_image(box[0], box[1], img_exit_touch)
        return True
    img.draw_image(box[0], box[1], img_exit)
    return False


def draw_history_page(t):
    base_img.draw_rect(0, 0, base_img.width(), base_img.height(), image.COLOR_BLACK, -1)
    draw_center_text(base_img, 24, "URL History", image.Color.from_rgb(255, 220, 0), 2)
    back_touched = draw_exit_button(base_img, t)

    if len(url_history) == 0:
        draw_center_text(base_img, int(base_img.height() * 0.45), "No saved URLs", image.Color.from_rgb(150, 150, 150), 2)
        disp.show(base_img)
        return "back" if back_touched and touch_ready() else None

    top = 88
    bottom_margin = 16
    gap = 4
    row_h = max(24, (base_img.height() - top - bottom_margin - gap * (URL_HISTORY_LIMIT - 1)) // URL_HISTORY_LIMIT)
    row_w = base_img.width() - 28
    x = 14
    text_color = image.Color.from_rgb(245, 245, 245)
    muted = image.Color.from_rgb(150, 150, 150)
    normal_bg = image.Color.from_rgb(35, 35, 35)
    touch_bg = image.Color.from_rgb(40, 130, 220)

    selected = None
    for i, url in enumerate(url_history[:URL_HISTORY_LIMIT]):
        y = top + i * (row_h + gap)
        box = [x, y, row_w, row_h]
        touched = in_box(t, box)
        base_img.draw_rect(box[0], box[1], box[2], box[3], touch_bg if touched else normal_bg, -1)
        num = "{}.".format(i + 1)
        base_img.draw_string(box[0] + 8, box[1] + 4, num, muted, 1.8)
        url_text = ellipsize_middle(url, box[2] - 76, 1.5)
        base_img.draw_string(box[0] + 62, box[1] + 6, url_text, text_color, 1.5)
        if touched:
            selected = url

    disp.show(base_img)

    if back_touched and touch_ready():
        return "back"
    if selected and t[2] and touch_ready():
        remember_url(selected)
        return "selected"
    return None


def stop_stream():
    global cam, encoder, ffmpeg_proc, ffmpeg_log

    proc = ffmpeg_proc
    ffmpeg_proc = None
    if proc is not None:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=4)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    obj = encoder
    encoder = None
    if obj is not None:
        try:
            del obj
        except Exception:
            pass

    obj = cam
    cam = None
    if obj is not None:
        try:
            del obj
        except Exception:
            pass

    log = ffmpeg_log
    ffmpeg_log = None
    if log is not None:
        try:
            log.close()
        except Exception:
            pass


def start_stream():
    global cam, encoder, ffmpeg_proc, ffmpeg_log

    stop_stream()
    codec_label, codec_type, ffmpeg_format = current_codec()
    bitrate_label, bitrate_value = current_bitrate()
    print("start rtmp: {} {} {}bps {}".format(codec_label, bitrate_label, bitrate_value, global_url))

    try:
        os.remove(FFMPEG_LOG)
    except Exception:
        pass

    ffmpeg_log = open(FFMPEG_LOG, "ab", buffering=0)
    cam = camera.Camera(STREAM_WIDTH, STREAM_HEIGHT, image.Format.FMT_YVU420SP, fps=STREAM_FPS)
    encoder = video.Encoder(
        width=STREAM_WIDTH,
        height=STREAM_HEIGHT,
        type=codec_type,
        framerate=STREAM_FPS,
        gop=STREAM_GOP,
        bitrate=bitrate_value,
        block=True,
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        ffmpeg_format,
        "-r",
        str(STREAM_FPS),
        "-i",
        "pipe:0",
        "-c:v",
        "copy",
        "-an",
        "-flvflags",
        "no_duration_filesize",
        "-f",
        "flv",
        global_url,
    ]
    print("ffmpeg cmd: {}".format(" ".join(cmd)))
    ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=ffmpeg_log, stderr=ffmpeg_log, bufsize=0)


def pump_stream_frame():
    if ffmpeg_proc is None or encoder is None or cam is None:
        return False
    if ffmpeg_proc.poll() is not None:
        print("ffmpeg stopped with code {}".format(ffmpeg_proc.returncode))
        return False

    img = cam.read()
    frame = encoder.encode(img)
    if frame and frame.is_valid() and frame.size() > 0:
        try:
            ffmpeg_proc.stdin.write(frame.to_bytes(False))
        except Exception as e:
            print("ffmpeg pipe write failed: {}".format(e))
            return False
    return True


def apply_env_choices():
    global choice_codec, choice_bitrate

    codec = os.environ.get("QO100_CODEC", "").lower().replace(".", "")
    if codec in ("h265", "hevc", "265"):
        choice_codec = 1
    elif codec in ("h264", "avc", "264"):
        choice_codec = 0

    bitrate = os.environ.get("QO100_BITRATE", "")
    if bitrate:
        try:
            value = int(bitrate)
            best = 0
            best_delta = abs(BITRATES[0][1] - value)
            for i, item in enumerate(BITRATES):
                delta = abs(item[1] - value)
                if delta < best_delta:
                    best = i
                    best_delta = delta
            choice_bitrate = best
        except Exception:
            pass


def run_env_stream_if_requested():
    global global_url
    url = os.environ.get("QO100_RTMP_URL", "")
    if not url:
        return False

    apply_env_choices()
    global_url = url
    ok, _, _, _, _ = parse_url(global_url)
    if not ok:
        raise RuntimeError("bad RTMP URL: {}".format(global_url))

    seconds = 6
    try:
        seconds = int(os.environ.get("QO100_TEST_SECONDS", "6"))
    except Exception:
        pass

    start_stream()
    start_ms = time.ticks_ms()
    while time.ticks_ms() - start_ms < seconds * 1000:
        if not pump_stream_frame():
            raise RuntimeError("stream stopped during test")
    stop_stream()
    print("QO100 headless stream test complete")
    return True


load_state()

if run_env_stream_if_requested():
    app.set_exit_flag(True)

while not app.need_exit():
    t = ts.read()

    if global_status == 0:
        base_img.draw_rect(0, 0, base_img.width(), base_img.height(), image.COLOR_BLACK, -1)
        scan_qrcode = False
        need_exit = False
        run_rtmp = False
        open_history = False

        draw_center_text(base_img, 24, "RTMP QO-100", image.Color.from_rgb(255, 220, 0), 2)
        enc_box, bitrate_box = draw_settings(base_img, t)
        settings_touched = update_settings_from_touch(t)
        history_touched = False

        if len(global_err_msg):
            draw_center_text(base_img, 138, global_err_msg, image.COLOR_RED, 1.6)

        if len(global_url) == 0:
            color = image.Color.from_rgb(0x8e, 0x8e, 0x8e)
            draw_center_text(base_img, 148, str_no_url_tips1, color, 1.4)
            draw_center_text(base_img, 175, str_no_url_tips2, color, 1.4)
            box = [base_img.width() // 2 - img_scan.width() // 2, base_img.height() // 2 - 15, 100, 100]
            base_img.draw_image(box[0], box[1], img_scan)
            if in_box(t, box) and not history_touched and not settings_touched:
                scan_qrcode = True
            prompt_y = int(base_img.height() * 0.72)
            draw_center_text(base_img, prompt_y, str_find_not_url, color, 1.7)
            hist_box = draw_history_button(base_img, t, prompt_y + 36)
            if t[2] and in_box(t, hist_box):
                history_touched = True
                scan_qrcode = False
                if len(url_history) and touch_ready():
                    open_history = True
        else:
            color = image.Color.from_rgb(0x8e, 0x8e, 0x8e)
            box = [base_img.width() // 2 - int(img_scan.width() * 1.35), base_img.height() // 2 - 55, 100, 100]
            base_img.draw_image(box[0], box[1], img_scan)
            if in_box(t, box) and not history_touched and not settings_touched:
                scan_qrcode = True
            draw_text_fit(base_img, [box[0] - 10, box[1] + img_scan.height() + 6, 120, 46], "Scan", color, 2.4, 1.2)

            box = [base_img.width() // 2 + int(img_scan.width() * 0.35), base_img.height() // 2 - 55, 100, 100]
            base_img.draw_image(box[0], box[1], img_start)
            if in_box(t, box) and not history_touched and not settings_touched:
                run_rtmp = True
            draw_text_fit(base_img, [box[0] - 10, box[1] + img_scan.height() + 6, 120, 46], "Run", color, 2.4, 1.2)

            url_scale = 1
            url_text = ellipsize_middle(global_url, base_img.width() - 12, url_scale)
            base_img.draw_string(6, int(base_img.height() * 0.72), "URL:", color, 1.4)
            draw_center_text(base_img, int(base_img.height() * 0.72) + str_height_2 + 4, url_text, color, url_scale)
            hist_box = draw_history_button(base_img, t, int(base_img.height() * 0.84))
            if t[2] and in_box(t, hist_box):
                history_touched = True
                scan_qrcode = False
                run_rtmp = False
                if len(url_history) and touch_ready():
                    open_history = True

        if settings_touched or history_touched:
            scan_qrcode = False
            run_rtmp = False

        need_exit = draw_exit_button(base_img, t)
        disp.show(base_img)

        if scan_qrcode:
            global_status = 1
            global_err_msg = ""
        if run_rtmp:
            global_status = 2
            global_err_msg = ""
        if open_history:
            global_status = 4
            global_err_msg = ""
        if need_exit:
            app.set_exit_flag(True)

    elif global_status == 1:
        try:
            if cam is None or cam.format() != image.Format.FMT_RGB888:
                if cam is not None:
                    old_cam = cam
                    cam = None
                    del old_cam
                cam = camera.Camera(640, 480, image.Format.FMT_RGB888)
            img = cam.read()
            qrcodes = img.find_qrcodes()
            for q in qrcodes:
                url = q.payload()
                print("qrcode res:{}".format(url))
                if remember_url(url):
                    global_status = 0
                else:
                    global_status = 0
                    global_err_msg = "bad url"
                old_cam = cam
                cam = None
                del old_cam

            need_exit = False
            box = [20, 20, img_exit.width(), img_exit.height()]
            if in_box(t, box, 20):
                img.draw_image(box[0], box[1], img_exit_touch)
                need_exit = True
            else:
                img.draw_image(box[0], box[1], img_exit)

            scan_color = image.Color.from_rgb(0x6e, 0x6e, 0x6e)
            y = int(img.height() - (str_height_2 * 3 + 3 * 4))
            img.draw_string(0, y, str_scan_tips1, scan_color, 2)
            img.draw_string(0, y + str_height_2 + 4, str_scan_tips2, scan_color, 2)
            img.draw_string(0, y + str_height_2 * 2 + 4 * 2, str_scan_tips3, scan_color, 2)
            disp.show(img)

            if need_exit:
                global_status = 0
        except Exception as e:
            print("scan qrcode failed: {}".format(e))
            global_status = 0
            global_err_msg = "scan qrcode failed"

    elif global_status == 2:
        try:
            ok, host, port, application, stream = parse_url(global_url)
            if ok:
                print("parse out: {} {} {} {}".format(host, port, application, stream))
                start_stream()
                global_status = 3
            else:
                global_status = 0
                global_err_msg = "bad url"
        except Exception as e:
            print("rtmp init failed: {}".format(e))
            stop_stream()
            global_status = 0
            global_err_msg = "rtmp init failed"

    elif global_status == 3:
        if not pump_stream_frame():
            stop_stream()
            global_status = 0
            global_err_msg = "rtmp stopped"
            continue

        base_img.draw_rect(0, 0, base_img.width(), base_img.height(), image.COLOR_BLACK, -1)
        box = [base_img.width() // 2 - img_scan.width() // 2, base_img.height() // 2 - 70, 100, 100]
        base_img.draw_image(box[0], box[1], img_running)

        curr_ms = time.ticks_ms()
        if curr_ms - run_last_ms > 500:
            run_last_ms = curr_ms
            run_cnt = 0 if run_cnt == 2 else run_cnt + 1

        color = image.Color.from_rgb(0x8e, 0x8e, 0x8e)
        if run_cnt == 0:
            running_text = str_rtmp_is_running1
        elif run_cnt == 1:
            running_text = str_rtmp_is_running2
        else:
            running_text = str_rtmp_is_running3
        draw_center_text(base_img, int(base_img.height() * 0.66), running_text, color, 2)
        info = "{}  {}".format(current_codec()[0], current_bitrate()[0])
        draw_center_text(base_img, int(base_img.height() * 0.75), info, color, 1.6)

        need_exit = draw_exit_button(base_img, t)
        disp.show(base_img)

        if need_exit:
            stop_stream()
            global_status = 0
            time.sleep_ms(100)
    elif global_status == 4:
        action = draw_history_page(t)
        if action:
            global_status = 0
            global_err_msg = ""
            time.sleep_ms(120)
    else:
        print("unknown status {}".format(global_status))
        time.sleep_ms(1000)

stop_stream()
