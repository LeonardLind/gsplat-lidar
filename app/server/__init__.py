"""Local job server for the browser studio (web/viewer/studio.html, clean.html).

    python -m app serve [--port 8765]

Runs the pipeline stages as jobs (one at a time: they share one GPU), reports their progress,
estimates times from this PC's history, and applies cleanup edits to splats. Standard library
only. The Vite dev server proxies /studio-api to it.
"""
