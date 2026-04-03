from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from coding import CodingLabels, CodingNode, CodingTree

class CodingAction(Enum):
    NO = "No"
    BOTH = "Both"
    YES = "Yes"


@dataclass(frozen=True)
class PathEntry:
    node: CodingNode
    action: CodingAction

@dataclass(frozen=True)
class BranchState:
    current: CodingNode
    path: tuple[PathEntry, ...]


@dataclass(frozen=True)
class CompletedPath:
    tag: str
    path: tuple[PathEntry, ...]

@dataclass
class CodingSession:
    current: CodingNode = CodingTree
    path: list[PathEntry] = field(default_factory=list)
    deferred: BranchState | None = None
    completed: list[CompletedPath] = field(default_factory=list)

    def reset(self) -> None:
        self.current = CodingTree
        self.path = []
        self.deferred = None
        self.completed = []

    def can_go_back(self) -> bool:
        return bool(self.path) or self.deferred is not None or bool(self.completed)

    def can_use_both(self) -> bool:
        return (
            not self.current.is_leaf()
            and self.deferred is None
            and not self.completed
        )

    def go_back(self) -> None:
        if self.deferred is not None or bool(self.completed):
            self.reset()
            return
        if not self.path:
            return
        previous = self.path.pop()
        self.current = previous.node

    def answer(self, action: CodingAction) -> None:
        if self.current.is_leaf():
            raise ValueError("Cannot answer from a leaf node")

        if action == CodingAction.YES:
            self.path.append(PathEntry(self.current, action))
            self.current = self.current.yes
        elif action == CodingAction.NO:
            self.path.append(PathEntry(self.current, action))
            self.current = self.current.no
        elif action == CodingAction.BOTH:
            if not self.can_use_both():
                raise ValueError("Both can only be used once per coding session")
            self.path.append(PathEntry(self.current, action))
            self.deferred = BranchState(
                current=self.current.no, path=tuple(self.path)
            )
            self.current = self.current.yes
        else:
            raise ValueError(f"Unsupported action: {action}")

        self._advance_from_leaf()

    def is_complete(self) -> bool:
        return self.current.is_leaf() and self.deferred is None

    def current_tags(self) -> list[str]:
        return [completed_path.tag for completed_path in self.completed]

    def all_decision_paths(self) -> list[CompletedPath]:
        return self.completed

    def _advance_from_leaf(self) -> None:
        while self.current.is_leaf():
            self.completed.append(
                CompletedPath(tag=self.current.label, path=tuple(self.path))
            )
            if self.deferred is None:
                return
            branch = self.deferred
            self.deferred = None
            self.current = branch.current
            self.path = list(branch.path)
