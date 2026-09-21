import sys

from . import __version__


def main():
    if "--version" in sys.argv:
        print(f"comfyui-canvas-mcp {__version__} (official comfy-mcp 0.10.0 + local canvas)")
        return
    from . import canvas, workflows, media, models, nodepacks, runtime, snapshots  # register additions
    from .upstream import serve
    serve()


if __name__ == "__main__":
    main()
