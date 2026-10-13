"""ParkBench database workload runner."""

from importlib.metadata import PackageNotFoundError, version

__version__ = "0.1.0"


def check_runtime() -> dict[str, str]:
    """Return installed dependency versions or raise a useful setup error."""
    versions: dict[str, str] = {}
    for package in ("PyYAML", "Faker"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"{package} is required; install requirements.txt") from exc
    return versions
