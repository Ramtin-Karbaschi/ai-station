"""AI Station frontend defaults for MiniMax Music3 / H3 and FLUX.2.

No extra generation nodes. The JS extension replaces the stock Flux
default graph (models we do not ship) and blocks Queue when a loader
points at a missing file. Station FLUX.2 and MiniMax graphs may queue.
"""

WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
