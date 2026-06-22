import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import time
import os

ff_thresh = 0.5
imp_thresh = 3.5
ff_min = 10
imp_win = 50
gyro_min = 20.0

IDLE = 0
FF = 1
IMP = 2
DONE = 3


def gen_data():
    np.random.seed(42)
    t = np.linspace(0, 20, 2000)

    ax = 0.1 * np.sin(2 * np.pi * 1.8 * t) + np.random.normal(0, 0.05, 2000)
    ay = 0.12 * np.sin(2 * np.pi * 1.8 * t) + np.random.normal(0, 0.05, 2000)
    az = 1.0 + 0.08 * np.sin(2 * np.pi * 0.9 * t) + np.random.normal(0, 0.05, 2000)

    # gyro channels — normal low-level rotation noise during walking
    gx = np.random.normal(0, 5, 2000)
    gy = np.random.normal(0, 5, 2000)

    for ft in [5.0, 11.0, 17.0]:
        i = int(ft * 100)
        # freefall phase
        ax[i:i+10] = np.random.normal(0.04, 0.04, 10)
        az[i:i+10] = np.random.normal(0.04, 0.04, 10)
        # impact phase
        ax[i+10:i+16] = np.random.normal(2.8, 0.3, 6)
        az[i+10:i+16] = np.random.normal(3.6, 0.4, 6)
        # body rotates during fall — gx gy spike above 20 deg/s
        gx[i:i+16] = np.random.normal(35, 5, 16)
        gy[i:i+16] = np.random.normal(30, 5, 16)

    mag = np.sqrt(ax**2 + ay**2 + az**2)
    df = pd.DataFrame({
        't': t, 'ax': ax, 'ay': ay, 'az': az,
        'gx': gx, 'gy': gy, 'magnitude': mag
    })
    df.to_csv('imu.csv', index=False)
    print("[IMU] generated imu.csv")
    return df


def run_detector(df):
    t = df['t'].values
    ax = df['ax'].values
    ay = df['ay'].values
    az = df['az'].values
    gx = df['gx'].values
    gy = df['gy'].values
    mag = df['magnitude'].values
    n = len(t)

    ph1 = np.zeros(n, dtype=int)
    confirmed = np.zeros(n, dtype=int)

    state = IDLE
    ff_cnt = 0
    imp_cnt = 0
    falls = []
    timings = []

    print(f"\n[DETECTOR] ff < {ff_thresh}g | imp > {imp_thresh}g | gyro reject < {gyro_min} deg/s\n")

    for i in range(n):
        t0 = time.perf_counter()
        m = mag[i]
        ts = t[i] * 1000

        if state == IDLE:
            if m < ff_thresh:
                state = FF
                ff_cnt = 1

        elif state == FF:
            if m < ff_thresh:
                ff_cnt += 1
                ph1[i] = 1
                if ff_cnt >= ff_min:
                    state = IMP
                    imp_cnt = 0
            else:
                state = IDLE
                ff_cnt = 0

        elif state == IMP:
            ph1[i] = 1
            imp_cnt += 1

            if m > imp_thresh:
                # gx or gy must exceed 20 deg/s — arm swing stays low
                if abs(gx[i]) >= gyro_min or abs(gy[i]) >= gyro_min:
                    state = DONE
                    confirmed[i] = 1
                    falls.append(ts)
                    print(f"  FALL DETECTED at {ts:.0f}ms  (mag={m:.2f}g, gx={gx[i]:.1f}, gy={gy[i]:.1f} deg/s)")
                else:
                    print(f"  rejected at {ts:.0f}ms (arm swing — gx={gx[i]:.1f}, gy={gy[i]:.1f} deg/s)")
                state = IDLE
                ff_cnt = 0
                imp_cnt = 0

            elif imp_cnt >= imp_win:
                state = IDLE
                ff_cnt = 0
                imp_cnt = 0

        timings.append((time.perf_counter() - t0) * 1e6)

    out = df.copy()
    out['phase1_active'] = ph1
    out['fall_confirmed'] = confirmed
    return out, falls, timings


def save_csv(out, path):
    res = pd.DataFrame({
        'timestamp_ms': out['t'] * 1000,
        'ax': out['ax'],
        'ay': out['ay'],
        'az': out['az'],
        'gx': out['gx'],
        'gy': out['gy'],
        'magnitude': out['magnitude'],
        'phase1_active': out['phase1_active'],
        'fall_confirmed': out['fall_confirmed']
    })
    res = res.iloc[::50].reset_index(drop=True)
    res.to_csv(path, index=False)
    print(f"[CSV] {len(res)} rows saved to {path}")


def plot_mag(out, falls, path):
    t = out['t'].values
    mag = out['magnitude'].values
    ph1 = out['phase1_active'].values

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor('#0f0f0f')
    ax.set_facecolor('#1a1a2e')

    ax.plot(t, mag, color='#00d4ff', linewidth=1.2, label='Magnitude (g)')
    ax.axhline(y=ff_thresh, color='#ffa500', linewidth=1, linestyle='--',
               alpha=0.8, label=f'Freefall ({ff_thresh}g)')
    ax.axhline(y=imp_thresh, color='#ff4444', linewidth=1, linestyle='--',
               alpha=0.8, label=f'Impact ({imp_thresh}g)')

    in_ff = False
    s = 0
    for i in range(len(ph1)):
        if ph1[i] == 1 and not in_ff:
            in_ff = True
            s = i
        elif ph1[i] == 0 and in_ff:
            in_ff = False
            ax.axvspan(t[s], t[i], alpha=0.3, color='#ffa500')
    if in_ff:
        ax.axvspan(t[s], t[-1], alpha=0.3, color='#ffa500')

    for f in falls:
        fs = f / 1000
        ax.axvline(x=fs, color='#ff0000', linewidth=2.5, alpha=0.9)
        ax.annotate(f'FALL\n{f:.0f}ms', xy=(fs, imp_thresh + 0.3),
                    fontsize=8, color='#ff4444', ha='center', fontweight='bold')

    h, _ = ax.get_legend_handles_labels()
    h += [
        mpatches.Patch(color='#ffa500', alpha=0.4, label='Freefall window'),
        plt.Line2D([0], [0], color='#ff0000', linewidth=2, label='Confirmed fall')
    ]
    ax.legend(handles=h, loc='upper right', facecolor='#1a1a2e',
              edgecolor='#444', labelcolor='white', fontsize=9)

    ax.set_xlabel('Time (s)', color='white')
    ax.set_ylabel('Magnitude (g)', color='white')
    ax.set_title('IMU Fall Detection — Parvai Insight | ICM-42688-P | 100Hz',
                 color='white', fontweight='bold')
    ax.tick_params(colors='white')
    for sp in ax.spines.values():
        sp.set_color('#444')
    ax.set_xlim(0, 20)
    ax.grid(True, alpha=0.15, color='white')
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    print(f"[PLOT] saved to {path}")


def timing_report(timings):
    arr = np.array(timings)
    avg = np.mean(arr)
    mx = np.max(arr)
    mn = np.min(arr)
    budget = 10_000

    print("\nTIMING (ARM64 Cortex-A55 target)")
    print(f"  avg : {avg:.2f} us")
    print(f"  min : {mn:.2f} us")
    print(f"  max : {mx:.2f} us")
    print(f"  budget : {budget} us | fits: {'YES' if mx < budget else 'NO'}")

    af = avg / budget
    print(f"\n  power: {avg:.2f}/{budget} = {af:.5f} x 500mW = {af*500:.4f} mW")

    return avg, mx, mn


if __name__ == "__main__":
    print("Task 2 — Fall Detection\n")
    os.makedirs("results", exist_ok=True)

    df = gen_data()
    out, falls, timings = run_detector(df)
    save_csv(out, "results/task2_output.csv")
    plot_mag(out, falls, "results/task2_fall_plot.png")
    timing_report(timings)

    print(f"\ndetected: {len(falls)}/3 — {[f'{f:.0f}ms' for f in falls]}")