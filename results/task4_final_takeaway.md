# Task 4: Bottom Line

**Parvai Insight: Wearable AI for Visually Impaired Users**
**Candidate: Rajashri Patil**

---

## Q: What is your biggest takeaway from building this?

The biggest takeaway from building this was how often the real measurement changed the conclusion I expected to write, rather than simply confirming it, and how much more defensible the final answer was as a result. In Task 1, I expected resolution to be the main lever on battery life, and the measurement said otherwise: CPU percentage barely moved across 640, 416, and 320, so the power-based case for a smaller resolution was not actually present in the data. The real differentiator turned out to be FPS, and the recommendation had to be built on that instead, which is a more honest argument even though it is a less dramatic one. Task 2 produced a similar correction. My RTL cycle estimate looked like it should beat Python on raw speed, and the measured average showed the opposite. Python's interpreted loop was genuinely faster on average than the hand-counted hardware cycles. That forced the real case for hardware to rest on worst-case determinism rather than throughput, a distinction the 37–267 µs worst-case range in the data made directly visible rather than theoretical. Task 3 carried the same lesson into the systems level, where it stopped being about numbers and started being about getting the measurement to exist at all: two clean 10-minute runs required tracking down a real espeak driver bug, a missing audio device on a headless instance, a thread that needed a timeout safeguard after it froze mid-run, and a dropped SSH session that taught me to background long jobs with nohup before trusting a result to actually finish. None of that was anticipated going in, and all of it turned out to be necessary to produce numbers worth standing behind in a submission that explicitly asks for measurement rigor over estimates. Taken together, the project's real lesson was not about YOLO, fall detection, or any one architectural decision. It was that hardware-constraint thinking only earns its keep when it is willing to be wrong first. Every section in this proposal that holds up does so because an earlier assumption got checked against a real number and revised, not because the assumption was good to begin with.

---

## Final Recommendation

The current CPU-only implementation is suitable for prototyping and algorithm validation, but a production deployment should partition workloads according to their computational characteristics: **YOLO26n inference on the NPU**, **fall detection on the Cortex-M7**, and **orchestration/TTS on the A55**. Based on the measured results, NPU acceleration provides the largest system-level benefit, reducing total power from **596.5 mW to 238.1 mW** and extending projected battery life from **12.4 hours to 31.1 hours**. This architecture offers the best balance of performance, power efficiency, determinism, and scalability for the ParvAI Insight platform.
