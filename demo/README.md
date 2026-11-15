# MA-ZeroPhish clickable prototype (class demo)

`index.html` is a single self-contained page. Open it in any browser (double-click; no server needed).

- Pick an example link and press **Check link**. In **Step by step** mode, **Next step** runs one stage at a time and explains what it does and what happened to that link; **Run all at once** plays the whole pipeline.
- Three prepared example cases show three paths: a fake bank login (phishing), a library website (safe), and a parcel-fee page whose browser capture fails (missing evidence recorded as a gap, partial-evidence model).
- The example cases, their clues and scores are invented for teaching; the page does not visit real websites or call any model. The thresholds 0.59 / 0.55 are the frozen system's real values (rounded), and the "Real results" section reports the sealed test3 results (see `experiments/camera_ready/CAMERA_READY_RESULTS.md`).
