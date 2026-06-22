# quick sanity check that pyttsx3 TTS works on this machine
# (SAPI5 on Windows, espeak on Linux/Oracle) before running
# the full integrated_pipeline.py — isolates the TTS dependency
# so a failure here is easy to tell apart from a pipeline bug

import pyttsx3

print("initializing...")
eng = pyttsx3.init()
print("speaking...")
eng.say("test one two three")
eng.runAndWait()
print("done")