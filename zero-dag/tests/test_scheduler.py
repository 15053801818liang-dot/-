"""Tests for Go-like scheduler logic (Python rewrite for testing)"""
import pytest
import sys
sys.path.insert(0, ".")

# Inline scheduler core for tests
from collections import deque


def topological_sort(nodes: dict, edges: dict) -> list:
    """Kahn's algorithm — pure Python for testing"""
    in_degree = {nid: 0 for nid in nodes}
    for nid, deps in nodes.items():
        in_degree[nid] = len(deps)
    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    result = []
    while queue:
        current = queue.popleft()
        result.append(current)
        for child in edges.get(current, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    if len(result) != len(nodes):
        raise ValueError(f"Cycle detected: sorted {len(result)}/{len(nodes)}")
    return result


def test_topological_sort_linear():
    nodes = {"A": [], "B": ["A"], "C": ["B"], "D": ["C"]}
    edges = {"A": ["B"], "B": ["C"], "C": ["D"]}
    assert topological_sort(nodes, edges) == ["A", "B", "C", "D"]


def test_topological_sort_diamond():
    nodes = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]}
    edges = {"A": ["B", "C"], "B": ["D"], "C": ["D"]}
    result = topological_sort(nodes, edges)
    assert result[0] == "A"
    assert result[3] == "D"
    assert set(result[1:3]) == {"B", "C"}


def test_topological_sort_cycle_detected():
    nodes = {"A": ["B"], "B": ["A"]}
    edges = {"A": ["B"], "B": ["A"]}
    with pytest.raises(ValueError, match="Cycle"):
        topological_sort(nodes, edges)


def test_topological_sort_empty():
    assert topological_sort({}, {}) == []
