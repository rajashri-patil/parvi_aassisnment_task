# Task 4: Hardware Architecture Proposal

## Section A: NPU vs CPU for YOLO26n

Task 1 measured YOLO26n at 416×416 on ARM64 (Oracle Ampere A1): **11.25 FPS at 512.0 mW**, the resolution Task 1 recommended. YOLO dominates Task 3's system power budget. With NPU offload at 4× FPS and 0.3× YOLO power:

- Total MW new = total MW old - (0.7 x YLO MW old)
- Total MW new= 596.5 - (0.7 x 512) = **238.1 MW**
- Battery Life = 7400/238.1 = **31.1 hrs** vs 12.40 hrs

Both methods land on 238.1 mW, which is a useful consistency check.

What the NPU does not eliminate: resize, normalisation, and colour conversion still run on A55 unless the toolchain fuses them, and NMS/box decoding stays on CPU too. More critically, if NPU offload genuinely delivers 4× FPS (45 FPS), input bandwidth scales from **5.8M to 23.4M values/sec**, which is the real number the memory interconnect must sustain. If the AR1+'s bus cannot keep the NPU fed at that rate, the NPU stalls on data rather than its own MACs.

This is exactly the pattern from the CNN accelerator project: once the MAC array was fast and efficient, the constraint shifted to getting operands in and out of SRAM fast enough. The **14mW at 1GHz on 0.874mm²** came from three levers: high operand reuse (avoiding DRAM re-fetches), aggressive clock gating on idle paths, and datapath sizing to the actual model rather than over-provisioning. All three apply directly here:

- **Operand reuse** - specifically whether AR1+'s NPU caches weights and feature maps on-die across the YOLO layer stack or re-reads from external memory each pass.
- **Clock gating** - whether the NPU can sleep between frames. Insight only needs detections every 88–300ms, not continuously.
- **Datapath sizing** - whether part of the claimed 0.3× power reflects headroom Insight is not actually using. Until these are checked against AR1+'s real datasheet, the NPU figure should be treated as a compute driven estimate rather than a guaranteed platform result.

**Architectural takeaway:** CNN inference is the dominant system power consumer; fall detection, sensors, and alerting contribute relatively little. For production, combining an NPU for CNN inference, a Cortex M7 for always-on sensor processing, and event driven interrupts delivers substantially better battery life, keeping the A55 in low power states whenever possible.

---

## Section B: Fall Detection: Python vs RTL FSM

Task 2 timing (5 complete runs on the same ARM64 target): Python detector averaged **0.44–0.68 µs/sample**, worst-case samples **37–267 µs**, against a 10,000 µs budget.

### FSM: Verilog Pseudocode

Two always block pattern, matching hazard/stall control from the RISC pipeline project:


module fall_detector_fsm (
    input  clk, rst_n, new_sample,
    input  magnitude, gx, gy,
    output reg alert_output
);
    localparam IDLE=0, FREE_FALL_DETECT=1, IMPACT_WINDOW=2,
               FALL_CONFIRMED=3, ALERT=4;
    reg [2:0] state, next_state;
    reg [3:0] free_fall_counter;       // counts to 10 (100ms)
    reg [5:0] impact_timeout_counter;  // counts to 50 (500ms)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)          state <= IDLE;
        else if (new_sample) state <= next_state;
    end
    always @(*) begin
        next_state = state; alert_output = 0;
        case (state)
            IDLE:             if (magnitude < 0.5g) next_state = FREE_FALL_DETECT;
            FREE_FALL_DETECT: if (magnitude < 0.5g) begin
                                  if (free_fall_counter == 10) next_state = IMPACT_WINDOW;
                              end else next_state = IDLE;
            IMPACT_WINDOW:    if (magnitude > 3.5g) begin
                                  if (gx >= 20dps || gy >= 20dps) next_state = FALL_CONFIRMED;
                                  else next_state = IDLE;  // arm swing, reject
                              end else if (impact_timeout_counter == 50) next_state = IDLE;
            FALL_CONFIRMED:   next_state = ALERT;
            ALERT: begin      alert_output = 1; next_state = IDLE; end
        endcase
    end
endmodule

Each state transition resolves in 1 cycle (comparator or counter check). Reading 6 IMU channels over ICM-42688-P's 24MHz SPI and computing magnitude takes 178 cycles. The FSM is idle more than 99.98% of the time and can sleep on a clock-gated co-processor.

**Latency floor:** 10 samples (100ms) to confirm free-fall + 1 sample (10ms) minimum for impact = **110ms to ALERT**, regardless of implementation. The FSM adds only ~1.78 µs of compute on top. Python's average (0.44–0.68 µs) is actually faster than the RTL estimate in the typical case. That is the wrong comparison. Python's worst case ranged 37–267 µs across five runs on identical deterministic input, because variance comes from OS scheduler preemption, not the algorithm. This is the same reasoning applied to setup-time margin and metastability on forwarding paths in the RISC project. What breaks a design is the worst case, not the typical one. An FSM on a sleeping co-processor has no such failure mode; its worst case equals its average, always 178 cycles, deterministically.

**Hardware vs software verdict:** Software is right for the prototype. It fits the 10ms budget on A55 and allows fast threshold tuning. For production, move it to the Cortex-M7 already on the iMX95. Same reasoning as the 28nm vs 45nm RISC synthesis comparison: a small, well-verified control FSM is cheap to close timing on at 100MHz, and multi-corner PPA analysis, using the same methodology from the RISC project, confirms how timing margin holds across process and voltage corners before trusting it in a safety-relevant path.

**SVA verification:** On the RISC pipeline, hazard and forwarding correctness was verified with SVA properties against constrained-random sequences, not just hand picked test vectors. The same applies here: properties like IMPACT_WINDOW only entered from FREE_FALL_DETECT after exactly 10 consecutive sub-threshold samples, and ALERT only fires within one cycle of FALL_CONFIRMED, should be checked as SVA assertions against randomised magnitude/gyro input. A fall detector tested only against the falls it was designed to catch has been demonstrated, not verified. Given what this alert is for, that is a higher bar than the pipeline project required.

---

## Section C: System Architecture Recommendation

### Hardware/Software Partition

| Function | Where | Reason |
|---|---|---|
| YOLO26n CNN inference | NPU | Largest power consumer; convolution is embarrassingly parallel; purpose-built MAC arrays are 4–8× more efficient than general CPU |
| Image pre/post-processing, TTS, orchestration | ARM A55 | Sequential, OS-dependent, benefits from being updatable without a hardware respin |
| Fall detection FSM | Cortex-M7 | Fixed control logic; deterministic 178-cycle execution, zero jitter, ~5mW standby, already on-chip on iMX95 |
| IMU SPI polling | Cortex-M7 | Interrupt-driven at 100Hz; too timing-critical for a general OS scheduler; belongs in bare-metal firmware |
| NMS / box decoding | ARM A55 | Irregular memory access; poor fit for NPU SIMD structure; keep on CPU unless toolchain fuses it |
| LTE/BLE alert transmission | BG96 modem | Dedicated RF hardware; offloads A55 entirely, handles protocol stack in silicon |
| Voice waveform output (TTS) | ARM A55 | Inherently sequential, needs Linux audio stack, not parallelisable; no hardware benefit |

### What Belongs in Hardware and Why

A function is a good hardware candidate when it is **repetitive and parallel** (convolution, MAC arrays), has **hard real-time constraints** a general OS scheduler cannot guarantee (fall detection at 100Hz), runs continuously at low duty cycle where a dedicated low-power block beats a full CPU core (IMU polling), or is **safety-relevant** enough that deterministic worst-case timing matters more than average performance. The fall detection FSM is the clearest example. Not because Python is too slow (it fits the budget), but because a hardware FSM on the M7 eliminates the 37–267 µs scheduler jitter from Task 2, replacing it with a fixed 178-cycle deterministic path. Functions that stay in software are those requiring a full OS and network stack, changing frequently during product iteration, or having irregular memory access patterns that do not map well to SIMD structures.

### Biggest Single Change for Battery Life

**NPU offload of YOLO26n**, reducing total draw from 596.5 mW to 238.1 mW, extending battery life from 12.40 to 31.1 hours, provided memory bandwidth does not absorb the gain (Section A). Moving fall detection to the M7 matters for determinism and safety, but its direct power saving is negligible (0.052 mW from Task 3).

### Future Scope

Future platform revisions can focus on three areas:

1. **INT8 quantization on the NPU** - to further improve performance-per-watt beyond the baseline NPU offload gain. YOLOv8n accuracy loss with INT8 is typically under 1–2% mAP, which is acceptable for object awareness.
2. **Fall detection FSM on the Cortex-M7 or dedicated RTL hardware** - enabling always-on operation with deterministic latency, freeing A55 cores for YOLO pre/post-processing.
3. **Memory movement optimization between camera, NPU, and system memory** - including weight-stationary dataflow to keep YOLO weights pinned in NPU on-chip SRAM, and DMA directly from ISP to NPU input buffer bypassing the A55. Accelerator efficiency eventually becomes limited by data bandwidth rather than compute throughput. That is the next bottleneck after NPU offload.

Together, these improvements would further reduce system power while increasing responsiveness and scalability for future wearable AI workloads.

**Scope note:** Insight as built is an awareness system: object detection and fall alerting. Navigation with turn-by-turn directions would require a routing engine and active GPS on BG96, out of scope here.
