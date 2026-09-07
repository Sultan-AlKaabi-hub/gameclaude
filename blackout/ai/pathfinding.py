"""
A* search over the arena grid.

Uses Manhattan distance as the heuristic. On a 4-connected grid with uniform
unit step costs, Manhattan distance is both admissible (never overestimates)
and consistent (satisfies the triangle inequality), so A* is guaranteed to
return an optimal path and never needs to reopen a closed node.

Hunters call this every turn, so results are memoised per (grid, goal) via the
caller's cache to keep the per-turn budget well under the 150ms target.
"""

from __future__ import annotations

import heapq

from engine.grid import Grid, manhattan


def astar(
    grid: Grid,
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """Return the optimal path from start to goal, inclusive of both ends.

    Returns an empty list when no path exists. `blocked` holds dynamic
    obstacles (other hunters) so agents do not walk through one another;
    the goal itself is never treated as blocked.
    """
    if start == goal:
        return [start]
    if not grid.walkable(goal):
        return []

    blocked = blocked or set()
    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (manhattan(start, goal), counter, start))

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start: 0}
    closed: set[tuple[int, int]] = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct(came_from, current)
        closed.add(current)

        for neighbor in grid.neighbors(current):
            if neighbor in blocked and neighbor != goal:
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(neighbor, 1 << 30):
                g_score[neighbor] = tentative
                came_from[neighbor] = current
                counter += 1
                priority = tentative + manhattan(neighbor, goal)
                heapq.heappush(open_heap, (priority, counter, neighbor))

    return []


def _reconstruct(
    came_from: dict[tuple[int, int], tuple[int, int]],
    current: tuple[int, int],
) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def path_cost(
    grid: Grid,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> int:
    """True traversal cost, or a large sentinel when unreachable.

    Auction bidding uses real path cost rather than straight-line distance so
    that a hunter separated from a target by a wall does not outbid one that
    is genuinely closer by foot.
    """
    path = astar(grid, start, goal)
    return len(path) - 1 if path else 10_000
