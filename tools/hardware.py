"""Host hardware information."""
import platform

import psutil


def get_specs() -> str:
    return (
        f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}% "
        f"| OS: {platform.system()}"
    )
