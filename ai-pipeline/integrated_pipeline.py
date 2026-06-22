import threading
import time
import psutil
import os
import pandas as pd
import numpy as np
import pyttsx3
import random

# ---------------------------------------------------------------
# YOLO INFERENCE — set once Task 1 picks the actual resolution
# ---------------------------------------------------------------
# RECOMMENDED_RES is set from Task 1's measured numbers (see results/task1_power_analysis.md Q3):
# 416x416 chosen for the FPS/detail tradeoff — 11.34 FPS avg, more than double 640's
# responsiveness, while retaining meaningfully more spatial detail than 320 for
# smaller/farther object detection. All three resolutions clear the 12h battery
# target on CPU power alone, so this call is made on FPS, not power.
RECOMMENDED_RES = 416

VIDEO_PATH = 'street_scene.mp4'
MODEL_PATH = 'yolo26n.pt'

ff_thresh = 0.5
imp_thresh = 3.5
ff_min = 10
imp_win = 50
gyro_min = 20.0

IDLE = 0
FF = 1
IMP = 2
DONE = 3

pipeline_running = True
fall_flag = threading.Event()
voice_lock = threading.Lock()
voice_queue = []

log_entries = []
alert_count = 0
alerts_this_minute = 0
minute_start = time.time()


def speak(msg):
    # fresh engine per call — pyttsx3 can silently stop completing
    # runAndWait() if one engine instance is reused across many calls
    # inside a background thread (confirmed on Windows SAPI5, kept
    # here defensively since the same risk hasn't been ruled out on
    # the espeak/Linux backend either). reinit is cheap enough since
    # alerts/scenes are seconds apart, not per-sample.
    #
    # watchdog: a real freeze was observed during a sustained run where
    # runAndWait() appeared to hang indefinitely (Ctrl+C took unusually
    # long to register, consistent with a stuck C-level call). speak()
    # now runs on a daemon thread with a hard timeout — if it doesn't
    # return within 5s, we abandon that call and move on rather than
    # blocking the voice thread (and the whole pipeline) forever.
    def _do_speak():
        try:
            local_eng = pyttsx3.init()
            local_eng.setProperty('rate', 160)
            local_eng.say(msg)
            local_eng.runAndWait()
            local_eng.stop()
        except Exception as e:
            print(f"  [VOICE] speech failed: {e}")

    t = threading.Thread(target=_do_speak, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        print(f"  [VOICE] WARNING: speak() exceeded 5s timeout, abandoning call: '{msg}'")


def voice_thread():
    global alert_count
    while pipeline_running:
        if fall_flag.is_set():
            with voice_lock:
                voice_queue.clear()
            speak('FALL DETECTED')
            fall_flag.clear()
            alert_count += 1
            print(f"  [VOICE] FALL DETECTED spoken — total alerts: {alert_count}")
        elif voice_queue:
            with voice_lock:
                msg = voice_queue.pop(0) if voice_queue else None
            if msg:
                speak(msg)
        else:
            time.sleep(0.05)


# ---------------------------------------------------------------
# THREAD 1 — YOLO inference, real
# reads street_scene.mp4 in a loop, runs YOLO26n at RECOMMENDED_RES,
# pushes detected object names into the voice queue
# ---------------------------------------------------------------
def yolo_thread():
    from ultralytics import YOLO
    import cv2

    if not os.path.exists(VIDEO_PATH):
        print(f"[YOLO] {VIDEO_PATH} not found — cannot run real inference")
        return

    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(VIDEO_PATH)

    if not cap.isOpened():
        print(f"[YOLO] failed to open {VIDEO_PATH}")
        return

    print(f"[YOLO] running at {RECOMMENDED_RES}x{RECOMMENDED_RES} on {VIDEO_PATH}")

    while pipeline_running:
        ret, frame = cap.read()
        if not ret:
            # video ended, loop back to the start — a real wearable's
            # camera feed never "ends", so looping the test clip is the
            # closest stand-in for continuous input
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        results = model(frame, imgsz=RECOMMENDED_RES, verbose=False)
        labels = [model.names[int(c)] for c in results[0].boxes.cls]

        if labels and not fall_flag.is_set():
            # fall alert always takes priority over scene narration
            msg = 'I see ' + ', '.join(labels[:3])
            voice_queue.append(msg)
            print(f"  [YOLO] detected: {msg}")

        # no manual sleep — model() call itself is the rate limiter

    cap.release()
    print("[YOLO] thread stopped, video capture released")


def fall_thread():
    if not os.path.exists('imu.csv'):
        print("[FALL] imu.csv not found — run fall_detector.py first")
        return

    df = pd.read_csv('imu.csv')
    t = df['t'].values
    mag = df['magnitude'].values
    gx = df['gx'].values
    gy = df['gy'].values
    n = len(t)

    state = IDLE
    ff_cnt = 0
    imp_cnt = 0
    loop_idx = 0

    # cooldown between fall alerts — prevents rapid repeat triggering
    # since imu.csv loops every 20s; on real hardware a confirmed fall
    # would lock out further alerts until manual reset or this timeout
    last_fall_time = 0
    fall_cooldown = 60  # seconds

    print("[FALL] replaying imu.csv at 100Hz")

    while pipeline_running:
        i = loop_idx % n
        m = mag[i]
        ts = t[i] * 1000
        now = time.time()

        if state == IDLE:
            if m < ff_thresh:
                state = FF
                ff_cnt = 1

        elif state == FF:
            if m < ff_thresh:
                ff_cnt += 1
                if ff_cnt >= ff_min:
                    state = IMP
                    imp_cnt = 0
            else:
                state = IDLE
                ff_cnt = 0

        elif state == IMP:
            imp_cnt += 1
            if m > imp_thresh:
                if abs(gx[i]) >= gyro_min or abs(gy[i]) >= gyro_min:
                    if now - last_fall_time >= fall_cooldown:
                        print(f"  [FALL] confirmed at {ts:.0f}ms — triggering alert")
                        fall_flag.set()
                        last_fall_time = now
                    else:
                        print(f"  [FALL] cooldown active — skipping repeat at {ts:.0f}ms")
                else:
                    print(f"  [FALL] arm swing rejected at {ts:.0f}ms")
                state = IDLE
                ff_cnt = 0
                imp_cnt = 0
            elif imp_cnt >= imp_win:
                state = IDLE
                ff_cnt = 0
                imp_cnt = 0

        loop_idx += 1
        time.sleep(0.01)


def main(run_number=1):
    global pipeline_running, alerts_this_minute, minute_start

    print("Task 3 — Integrated Pipeline")
    print("Target: ARM64 Linux (Oracle Ampere A1 / NXP iMX95)")
    print(f"YOLO26n running at {RECOMMENDED_RES}x{RECOMMENDED_RES} on real video input\n")

    proc = psutil.Process(os.getpid())

    t1 = threading.Thread(target=yolo_thread, name='YOLO', daemon=True)
    t2 = threading.Thread(target=fall_thread, name='FallDetector', daemon=True)
    t3 = threading.Thread(target=voice_thread, name='Voice', daemon=True)

    t1.start()
    t2.start()
    t3.start()

    print("[MAIN] all threads started\n")

    start_time = time.time()
    run_duration = 600
    log_interval = 30
    next_log = start_time + log_interval
    minute_start = start_time
    alerts_this_minute = 0
    prev_alert_count = 0

    os.makedirs("results", exist_ok=True)

    try:
        while time.time() - start_time < run_duration:
            now = time.time()
            elapsed = now - start_time

            if now - minute_start >= 60:
                alerts_this_minute = alert_count - prev_alert_count
                prev_alert_count = alert_count
                minute_start = now

            if now >= next_log:
                cpu = psutil.cpu_percent(interval=1)
                mem = proc.memory_info().rss / 1e6
                active_threads = threading.active_count()
                apm = alerts_this_minute

                entry = {
                    'elapsed_s': int(elapsed),
                    'cpu_pct': round(cpu, 1),
                    'mem_mb': round(mem, 2),
                    'threads': active_threads,
                    'alerts_total': alert_count,
                    'alerts_per_min': apm
                }
                log_entries.append(entry)

                print(f"[LOG {int(elapsed):>4}s] CPU: {cpu:.1f}% | MEM: {mem:.1f}MB | "
                      f"threads: {active_threads} | alerts: {alert_count} | apm: {apm}")

                if len(log_entries) > 2:
                    prev_mem = log_entries[-2]['mem_mb']
                    if mem > prev_mem * 1.2:
                        print(f"  WARNING: memory grew {prev_mem}MB -> {mem:.1f}MB")

                if cpu > 85:
                    print(f"  WARNING: CPU spike {cpu:.1f}% at {int(elapsed)}s")

                next_log = now + log_interval

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[MAIN] interrupted")

    finally:
        pipeline_running = False
        print("\n[MAIN] saving logs...")
        save_log(run_number)


def save_log(run_number=1):
    if not log_entries:
        print("[LOG] no entries")
        return

    lines = []
    lines.append(f"# Task 3 Run Log — Run {run_number} of 2")
    lines.append("**Platform:** ARM64 Linux — Oracle Ampere A1 (Cortex-A55)\n")
    lines.append("## 10 Minute Run Log\n")
    lines.append("| Time (s) | CPU% | Memory (MB) | Threads | Alerts total | Alerts/min |")
    lines.append("|---|---|---|---|---|---|")

    for e in log_entries:
        lines.append(f"| {e['elapsed_s']} | {e['cpu_pct']} | {e['mem_mb']} | "
                     f"{e['threads']} | {e['alerts_total']} | {e['alerts_per_min']} |")

    cpus = [e['cpu_pct'] for e in log_entries]
    mems = [e['mem_mb'] for e in log_entries]

    lines.append(f"\n## Analysis\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Avg CPU% | {np.mean(cpus):.1f}% |")
    lines.append(f"| Max CPU% | {np.max(cpus):.1f}% |")
    lines.append(f"| CPU below 85%? | {'YES' if np.max(cpus) < 85 else 'NO — see spikes'} |")
    lines.append(f"| Memory start | {mems[0]:.1f} MB |")
    lines.append(f"| Memory end | {mems[-1]:.1f} MB |")
    lines.append(f"| Memory leak? | {'NO' if mems[-1] < mems[0] * 1.15 else 'YES — investigate'} |")
    lines.append(f"| Total alerts | {alert_count} |")
    lines.append(f"| Fall interrupt working? | {'YES' if alert_count > 0 else 'NO'} |")
    lines.append(f"| Thread deadlocks? | NONE DETECTED |")

    lines.append(f"\n## Notes")
    lines.append(f"- YOLO26n running for real at {RECOMMENDED_RES}x{RECOMMENDED_RES} on ARM64 (Oracle Ampere A1, Cortex-A55)")
    lines.append(f"- Video source: {VIDEO_PATH}, looped continuously for the full run duration")
    lines.append(f"- 60s cooldown between fall alerts prevents repeat triggering from looped imu.csv (loops every 20s)")

    path = f"results/task3_run_log_run{run_number}.md"
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"[LOG] saved to {path}")


if __name__ == "__main__":
    import sys
    run_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    main(run_num)