import os


def hr_module_enabled() -> bool:
    return os.getenv("HR_MODULE_ENABLED", "").lower() in {"1", "true", "yes"}
