## **Task 1: Hardware Constraint Analysis : Battery Life** 

## **Setup:** 

Insight runs on a 2000mAh LiPo battery at 3.7V nominal: 

Formula & calculated with measuments: 

Energy mWh = capacity mAh x voltage V 

Applied with the actual battery spec: 

2000mAh x 3.7V = 7,400mWh = 7.4Wh = 26,640 J 

Power estimates below use the measured average CPU% from task1_fps.md, applied to the task’s formula (0.5W per Cortex-A55 core at full load, 2 cores on this instance). 

## **Q1: At measured 416x416 CPU draw, how many hours does YOLO inference alone drain the battery?** 

Measured avg CPU at 416x416: 51.2%, giving an estimated draw of 512.0 mW (calculation in task1_fps.md). 

Formula & calculated with measuments: 

Battery life hours = battery capacity mWh / power draw mW Battery life hours = 7,400 mWh / 512.0 mW = **14.45 hours** 

YOLO inference alone, running continuously at 416x416, would drain the battery in roughly **14 hours and 27 minutes** . 

## **Q2: If Whisper Small (800mW) runs in parallel, how does battery life change?** 

Whisper Small is given as a fixed 800mW estimate on ARM64. Running it alongside YOLO at 416x416 means both draws are active at once: 

Formula & calculated with measuments: 

Combined power mW = yolo power mW + whisper power mW combined mw = 512.0 (YOLO) + 800 (Whisper Small) = **1,312.0 mW** 

battery life hours = battery capacity mWh / combined power mW battery life hours = 7,400 mWh / 1,312.0 mW = **5.64 hours** 

Battery life drops from 14.45 hours to **5.64 hours** , a 61.0% reduction. Adding Whisper Small costs more battery life on its own than YOLO does, since 800mW is well over 1.5x YOLO’s measured draw. This is the single largest item in the whole power budget by a wide margin, larger than YOLO at any resolution we tested. If a wearable speech feature like this were ever added to Insight, it would need to be triggered on demand (push-to-talk style) rather than running continuously, continuous parallel operation simply isn’t compatible with a multi-hour battery target. 

## **Q3: What resolution would I recommend for a >12 hour target?** 

All three measured resolutions clear 12 hours on YOLO power alone: 

|Resolution|Estimated mW|Battery life (YOLO only)|
|---|---|---|
|640x640|508|14.57 hours|
|416x416|512|14.45 hours|
|320x320|517|14.31 hours|



Because measured CPU% barely moved across resolutions (a 0.9 point spread), the power-only calculation does not meaningfully separate these three options, all three land within 16 minutes of each other on battery life. Selecting a resolution on power grounds alone would imply a precision the underlying measurement doesn’t support. 

**My actual recommendation is 416x416** , and the reasoning comes from FPS, not power. While 320×320 delivers the highest performance (17.27 FPS), it uses the least image detail and may miss smaller or more distant objects. At 640×640, detection quality is likely highest, but performance drops to 5.34 FPS, increasing scene description latency. The 416×416 setting provides the best balance, achieving 11.25 FPS while retaining significantly more spatial detail than 320×320. 

A complete decision would ideally include detection accuracy (mAP) at each resolution, but that was outside the scope of this task. 

**From a hardware perspective** , the benchmark demonstrates that CNN inference dominates platform power consumption. Future silicon revisions should prioritize NPU acceleration and memory access optimization rather than CPU scaling, since CPU only execution becomes the primary battery life limiter. This suggests that architectural improvements in accelerator efficiency will provide significantly greater battery life gains than increasing CPU performance alone. 

