"""XP Plus apps. `core` is UI-free. `api` serves it to the hackathon web app (`xp_plus_web/`, built
from FlowLab's frontend); a PySide6 desktop front end on the same core is planned after the hackathon."""


def serve(*args, **kwargs):
    from .api import serve as _serve
    return _serve(*args, **kwargs)


__all__ = ["serve"]
