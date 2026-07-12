"""Live 2D viewer + trace replay + GIF export (pygame-ce).

This package IMPORTS core; core never imports it (design principle 6). It
consumes either a live World (read-only) or a recorded Trace — the drawing
code cannot tell the difference, which is what makes GIFs cheap.
"""
