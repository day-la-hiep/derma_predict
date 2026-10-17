from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def read_jsonl(path: Path, model: type[T]) -> list[T]:
    return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, items: Iterable[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(i.model_dump_json() + "\n" for i in items), encoding="utf-8")
