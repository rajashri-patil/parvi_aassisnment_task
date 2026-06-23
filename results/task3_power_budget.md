## **Task 3: Combined Power Budget** 

## **Component table** 

|**Component table**|||
|---|---|---|
|**Component**|**Est. Power**<br>**(mW)**|**Source**|
|YOLO26n(416x416)|512|Task 1 measurement|
|Fall detector(Python)|0.052|Task 2 measurement|
|TTS(espeak,implied)|13.95|Task 3 measurement(derived,see below)|
|ICM-42688-P sensor|0.55|Datasheet|
|VL53L5CX ToF sensor|40|Datasheet(active)|
|BG96 LTE active|300|Datasheet(peak)|
|BG96 idle/GPS only|30|Datasheet|
|**TOTAL(AI active, BG96 idle)**|**596.5**|Calculation below|
|**TOTAL (AI active, BG96**<br>**peak)**|**866.5**|Calculation below|



## **How each number was derived** 

**YOLO26n (512.0mW):** taken directly from Task 1’s isolated measurement at 416x416 (51.2% avg CPU, see task1_fps.md). This is YOLO running alone, not under Task 3’s combined load. 

**Fall detector (0.052mW):** derived from Task 2’s real measured timing, which showed real runto-run variance across 5 complete repeated runs (0.44-0.68us average, mean 0.52us per sample) rather than a single stable value, see task2_timing_analysis.md. The mean of those 5 measured averages is used here as the representative figure. 

Formula & calculations:

Cpu pct = (time used per sample us / sample budget us) * 100 power mw = (cpu pct / 100) x num cores x core tdp mw 

Fall detector cpu pct = (0.522 / 10,000) x100 = 0.0052% fall detector mw = (0.0052 / 100) x 2 cores x500mW = 0.052 mW 

This is consistent with Task 2’s finding that the fall detector FSM is idle 99.98% of the time, it genuinely costs almost nothing in software. 

**TTS (~13.95mW, derived, not directly measured):** Task 3’s full integrated runs measured combined system CPU at 52.6% average, 1.4 percentage points above YOLO’s isolated 51.2%. Converting that gap to power. 

_pyttsx3 was chosen because it installs cleanly as a standard pip package on ARM64 Ubuntu with no model downloads, keeping the environment straightforwardly reproducible. MeloTTS requires neural TTS weights and heavier dependencies that would have added setup complexity without changing the measurement, since what's being measured (combined CPU% above YOLO baseline) is independent of which TTS engine runs in the voice thread._ 

Formula & calculations:

combined power mw = (combined cpu pct / 100) x num cores x core tdp mw 

combined power mw = (52.6 / 100) x 2 cores x 500 mW = 526.0 mW 

overhead mw = combined power mw - yolo isolated power mw overhead mw = 526.0 - 512.0 = 14.0 mW 

tts implied mw = overhead mw - fall detector power mw tts implied mw = 14.0 - 0.052 = 13.948 mW 

This number should be read as a rough estimate, not a direct measurement, it’s a remainder after subtracting two other known quantities from one combined number, so any error in the other two terms shows up here. 

It also can’t be physically measured on this instance, since there’s no real audio hardware to draw real current, the headless Oracle VM uses a null ALSA device (see task3_run_log.md), so even this CPU-based estimate only captures the cost of running espeak’s synthesis step, not whatever a real DAC/speaker driver circuit would draw on actual Insight hardware. 

**Sensor and radio figures** (ICM-42688-P, VL53L5CX, BG96) are taken directly from the task’s own datasheet-sourced values, not measured, since none of that hardware exists on this cloud instance. 

## **Total power and battery life** 

Two totals are given since BG96’s state varies by use case, idle/GPS-only most of the time, peaking only during active LTE transmission. 

total power mw = yolo mw + fall detector mw + tts mw + imu mw + tof mw + bg96 mw 

TOTAL (AI active, BG96 idle) = 512.0 + 0.052 + 13.948 + 0.55 + 40 + 30 = **596.5 mW** TOTAL (AI active, BG96 peak) = 512.0 + 0.052 + 13.948 + 0.55 + 40 + 300 = **866.5 mW** 

Given the 2000mAh / 3.7V battery (7,400mWh): 

battery life hours = battery capacity mWh / total power mW 

BG96 idle:  7,400 / 596.5 = **12.40 hours** BG96 peak:  7,400 / 866.5 = **8.54 hours** 

With BG96 in its typical idle/GPS state, Insight clears the 12-hour target by a narrow margin. If BG96 is actively transmitting over LTE for any meaningful fraction of runtime, battery life drops to under 9 hours, well short of target. 

## **Biggest power consumer, and what to do about it** 

YOLO26n is the single largest consumer by a wide margin, and it’s also the only component running continuously and unavoidably, the camera-based scene description is the core function of the device. 

pct of budget = (component mw / total mw) × 100 **yolo pct of budget = (512.0 / 596.5) × 100 = 85.8%** 

512.0mW out of 596.5mW total (BG96 idle case) means only YOLO accounts for 85.8% of the whole budget. Even BG96 at full LTE transmission (300mW) is barely over half of YOLO’s draw. 

