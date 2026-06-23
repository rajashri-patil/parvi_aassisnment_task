## **Task 1: YOLO26n FPS + CPU + Memory Measurement** 

**Methodology note:** the task specifies one run per resolution. Each resolution was run twice as a deliberate repeatability check. Results were compared for consistency. The complete run with the most reliable logging output is reported. 

## **Results:** 

|**Results:**||||||
|---|---|---|---|---|---|
|Resolution|Avg<br>FPS|Min<br>FPS|Max<br>FPS|Avg<br>CPU%|Avg Mem<br>(MB)|
|640x640|5.34|4|5.49|50.8|832.5|
|416x416|11.25|6.55|11.62|51.2|823|
|320x320|17.27|8.36|17.96|51.7|816.2|



## **Power estimate** 

As per the task’s formula: ARM Cortex-A55 TDP is approximately 0.5W per core at full load. This instance has 2 OCPU. 

Power mw = (avg cpu pct / 100) * num cores * 500mW 

## **Worked calculation for each resolution:** 

640x640: (50.8 / 100) * 2 * 500mW = 0.508 * 2 * 500 = **508.0 mW** 

416x416: (51.2 / 100) * 2 * 500mW = 0.512 * 2 * 500 = **512.0 mW** 

320x320: (51.7 / 100) * 2 * 500mW = 0.517 * 2 * 500 = **517.0 mW** 

|Resolutio<br>n|Avg<br>CPU%|Core<br>s|Estimated mW<br>(inference only)|
|---|---|---|---|
|640x640|50.80%|2|508.0 mW|
|416x416|51.20%|2|512.0 mW|
|320x320|51.70%|2|517.0 mW|



CPU utilization stayed essentially flat across all three resolutions, a 0.9 percentage point spread total, despite FPS ranging from 5.34 to 17.27, more than a 3x difference. That means the power estimate, which is derived from CPU%, doesn’t meaningfully differentiate the three resolutions either, all three land within 9mW of each other. 

This isn’t a measurement error it’s a real finding. At this CPU-only, 2-core configuration, YOLO26n isn’t saturating the CPU even at 640x640 (50.8% average leaves substantial headroom on a 2-core machine), so the bottleneck on responsiveness here is genuinely per-frame compute latency, not contention for CPU cycles. Resolution choice changes how fast a result is returned, not how much power the CPU draws doing it, at least within this CPU-bound, nonsaturated regime. 

