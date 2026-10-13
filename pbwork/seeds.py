"""Worker-independent operation selection seeds."""

import hashlib
import random


def operation_seed(seed: int, profile_version: int, ordinal: int, operation_id: str) -> int:
    raw = f"{seed}|{profile_version}|{ordinal}|{operation_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def operation_rng(seed: int, profile_version: int, ordinal: int, operation_id: str) -> random.Random:
    return random.Random(operation_seed(seed, profile_version, ordinal, operation_id))


def select_operation(seed: int, profile_version: int, ordinal: int, operations):
    ordered = tuple(operations)
    chooser = random.Random(operation_seed(seed, profile_version, ordinal, "profile-selection"))
    total = sum(op.weight for op in ordered)
    target = chooser.random() * total
    for op in ordered:
        target -= op.weight
        if target < 0:
            return op
    return ordered[-1]
