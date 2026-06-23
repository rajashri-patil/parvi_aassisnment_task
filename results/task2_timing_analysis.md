## **Task 2: Timing Analysis** 

## **Platform context:** 

The ICM-42688-P samples at 100Hz, a new reading every 10ms. If the detection function takes longer than that, samples get missed and the real-time guarantee breaks. So per-sample processing time was measured directly on the actual target hardware, not assumed from desktop behavior. 

## **Q1. Per-sample processing time on ARM64 Linux** 

Measured using time.perf_counter() wrapping each sample in the processing loop, run for real on the Oracle Ampere A1 instance. 

|**Run**|**Average (us)**|**Min (us)**|**Max (us)**|
|---|---|---|---|
|1|0.68|0.32|267.44|
|2|0.56|0.32|117.8|
|3|0.49|0.32|112.2|
|4<br>|0.44|0.36|47.72|
|5(fnal)|0.44|0.32|36.56|



The script was rerun 8 times because the first run's numbers (0.68µs avg, 267.44µs max) didn't match an earlier draft, and rather than picking whichever looked better, repeated runs were used to check if that was a fluke, it wasn't. They showed genuine numbers worth documenting. 

Min is effectively stable (0.32–0.36µs across runs), which is the floor cost of the comparison logic with negligible scheduling interference. Avg and max vary meaningfully: avg ranges 0.44– 0.68µs (mean 0.52µs), max ranges 37–267µs, a 7.3× spread on identical, deterministic input (seed=42, imu.csv verified byte-for-byte across runs). Later runs trend toward the lower end, suggesting jitter is sensitive to incidental system state rather than anything in the code. 

Two environmental causes were ruled out directly: ps aux showed no competing processes (load average 0.00–0.03), and vmstat showed 0% hypervisor steal time throughout. The most likely cause is Python interpreter level jitter (GC pauses, OS scheduler quanta) that simply doesn't register as visible load. 

|**Metric**<br>|**Value**|
|---|---|
|Min(efectivelystable)|0.32 – 0.36 us|
|Average(range across 5 complete runs)|0.44 – 0.68 us|
|Max(range across 5 complete runs)|37 – 267 us|
|Budget|10,000 us(10ms at 100Hz)|



## **Q2. Does it fit the 10ms budget?** 

Yes, comfortably. Even the worst sample seen across the 5 measured runs (267.44us) is roughly 37x under the 10,000us budget. The state machine is O(1) per sample, a magnitude comparison, a counter increment, no dynamic allocation inside the loop, so there was never real risk of missing the deadline on this hardware, even accounting for all run variance documented above. 

## **Q3 . If it didn’t fit, what would I do?** 

I’d actually try on this hardware & the option I’d choose is **offload to the Cortex-M7 coprocessor** . The M7 is already present on the NXP iMX95 at zero additional silicon cost. Moving fall detection there means the FSM runs bare-metal with deterministic timing, reads the ICM-42688-P over DMA rather than polling, and raises an interrupt to the A55 only on a confirmed fall, keeping A55 cores fully free for YOLO inference. This is the same partitioning logic as the CNN accelerator project like dedicated hardware for dedicated tasks. 

The other three options are prototype-phase mitigations, not production answers. NumPy vectorisation and a C extension both make the A55 loop faster but leave a safety critical alert competing for OS scheduled cycles on the same core as YOLO. Reducing to 50Hz doubles the budget and remains physiologically adequate (falls develop for 200-500ms), but doesn't solve the determinism problem. The M7 offload addresses all of these at once and the hardware is already there. 

## **Q4. RTL FSM at 100MHz, clock cycle estimate** 

In my CNN accelerator project on a 7nm FinFET PDK, the design ran at 1GHz with a 14mW power profile and 0.874mm² footprint post-APR. The critical path was a 16-bit multiply accumulate chain, pipelined MAC units running in parallel, synthesized in DC Shell and placed and routed in Innovus. 

Fall detection is the opposite kind of design. The CNN accelerator was compute-bound, deep pipelines, high switching activity, hundreds of MACs firing every cycle, which is why minimizing switching activity was the actual lever for hitting 14mW at 1GHz. Fall detection is controlbound, a handful of comparators checking thresholds and a gyro rate check. Near-zero switching activity per cycle by comparison. 

This tells us two things: First, a fall detection FSM would close timing at 1GHz on 7nm without real effort, the critical path is a 16-bit comparator chain, a few gate delays, nothing like the MAC chain’s pipeline balancing. We don’t need 1GHz here though, the sensor only delivers a new sample every 10ms, so 100MHz is more than sufficient. And second, the power would be far below the CNN accelerator’s 14mW, since that number came from hundreds of MACs switching every cycle. This FSM has on the order of 10-15 flip-flops switching per sample, sub-milliwatt easily on 7nm, comfortably under 5mW even on an older 180nm node. 

## **Clock cycles between state transitions at 100MHz:** 

At 100MHz, between two consecutive IMU samples: 

10ms x 100,000,000 Hz = 1,000,000 clock cycles between samples 

FSM logic completes in ~178 cycles. The remaining 999,822 cycles the co-processor sleeps, idle 99.98% of the time. This is where the real power saving comes from, not faster logic, but sleeping for nearly a million cycles between each sample. 

|**Transition**|**Trigger**|**Cycles**|
|---|---|---|
|IDLE to FREE FALL DETECT|magnitude comparator<br>fres|1|
|FREE FALL DETECT to IMPACT WINDOW|counter reaches 10|1|
|IMPACT WINDOW to FALL CONFIRMED|impact +gyro comparators|1|
|FALL CONFIRMED to ALERT|unconditional|1|
|ALERT to IDLE|unconditional|1|
|Between samples|waitingon DMA interrupt|~1,000,000|



## **Per-sample compute breakdown:** 

|**Per-sample compute breakdown:**|||
|---|---|---|
|**Operation**|**Hardware**|**Cycles**|
|SPI read ax, ay, az, gx, gy (16-bit x 5 at<br>24MHz,ICM-42688-P datasheet)|Serial shift register|160|
|ax² + ay² + az²|3 DSP blocksparallel|4|
|Square root(CORDIC)|CORDIC unit|10|
|Magnitude threshold compare|16-bit comparator|1|
|gx/gythreshold check|2 comparators + ORgate|1|
|Counter update|Ripple adder<br>|1|
|State register|D fip-fop|1|
|**Total**||**178 cycles**|



At 100MHz: 178 x 10ns = **1.78 us active per sample** . 

The SPI read dominates the breakdown (~160 of 178 cycles), the FSM logic itself is only 6-7 cycles. Same bottleneck pattern as the CNN accelerator, where memory/data movement limited throughput more than compute did. The SPI clock used here (24MHz) is the ICM-42688P’s real datasheet confirmed maximum, not an assumed value. 

**Setup/hold timing:** at 100MHz, setup time for standard cell comparators is roughly 0.3-0.5ns, well within the 10ns clock period, trivial compared to the real timing closure work the CNN accelerator’s 1GHz path required. 

## **Minimum fall detection latency:** 

Phase 1: 10 samples x 10ms = 100ms Phase 2: 1 impact sample x 10ms = 10ms Total: 110ms from fall start to ALERT 

Sensor limited, not compute-limited, identical in Python or RTL, since both are bound by the same 100Hz sample rate. 

**DMA vs polling:** the ICM-42688-P feeds data via DMA into a buffer (16-bit x 5 channels). The M7 sleeps, DMA fires an interrupt once all channels are ready, the M7 wakes, runs the FSM in ~178 cycles, and sleeps again. Same interrupt driven pattern I used for memory transfers in the CNN accelerator. 

**Python vs RTL, measured:** 


| | Python on A55 (real, measured) | RTL FSM at 100MHz (estimated) |
|---|---|---|
| Compute per sample (average, range across 5 complete runs) | 0.44 – 0.68 us | 1.78 us |
| Compute per sample (worst case, range across 5 complete runs) | 37 – 267 us | 1.78 us |
| Idle per sample | remainder of 10ms | ~999,822 cycles asleep |
| Fall latency | 110ms | 110ms |
| Real-time guarantee | No — subject to OS jitter | Yes — deterministic |
| Core usage | 1x A55 | 0 — dedicated M7 |


Worth being precise about what this comparison shows. Python's average case (0.44–0.68µs across 5 runs) is actually faster than the RTL estimate (1.78µs) in every single run measured, an interpreted language beating a clock counted hardware number on the typical case. That's not RTL losing the argument, it's the wrong comparison to make. 

The real difference is worst case. Across these 5 runs, worst case latency ranged from 37µs to 267µs, a 7.2x spread on identical, deterministic input data. That instability is the actual case for hardware. Both obvious environmental causes (background CPU load, hypervisor steal time) were directly checked and ruled out via ps aux and vmstat, so this variance is coming from inside the software stack itself, exactly the kind of unpredictability that has no equivalent in RTL. 

An FSM on a sleeping coprocessor has the same worst case as its average, every single time: 178 cycles, deterministically, with no dependency on what else the OS scheduler or interpreter happens to be doing at that instant. 

## **CSV output spacing** 

results/task2_output.csv (timestamp_ms, ax, ay, az, gx, gy, magnitude, phase1_active, fall_confirmed) is logged at a fixed 500ms interval, confirmed directly: 40 rows across the 20second dataset, with consistent ~500.25ms spacing between every consecutive timestamp_ms value (checked across the full file, not just the first few rows). gx and gy are included as extra columns beyond the task’s required set: the task’s data generator spec only defines ax, ay, az, and magnitude, but Phase 2 of the detection algorithm requires gyro channels for the arm-swing rejection check (if gx or gy rate change < 20°/s then reject), so the data generator was extended to include gx/gy channels, confirmed acceptable in advance. 

## **Hardware vs software recommendation:** 

For the prototype, Python on the A55 is the right call, it fits the budget with enormous margin and lets thresholds get tuned quickly while the rest of the system is still being built. For production, the FSM belongs on the Cortex-M7 already present on the iMX95, zero additional silicon cost, deterministic real-time behavior with no OS jitter, and the A55 cores stay fully free for YOLO inference. 

The lesson from the CNN accelerator carries over directly: keep compute where it belongs, specialized hardware for specialized tasks, the same principle that got that design to 14mW at 1GHz on a tight footprint. A threshold comparator and a gyro-rate check have no real business sharing a core with a CNN. 

