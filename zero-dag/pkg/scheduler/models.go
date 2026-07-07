package scheduler

import "fmt"

// Kahn's algorithm: topological sort of DAG nodes
func TopologicalSort(spec *DAGSpec) ([]string, error) {
	inDegree := make(map[string]int)
	for id := range spec.Nodes {
		inDegree[id] = 0
	}
	for id, node := range spec.Nodes {
		inDegree[id] = len(node.Dependencies)
	}

	var queue []string
	for id, deg := range inDegree {
		if deg == 0 {
			queue = append(queue, id)
		}
	}

	var result []string
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		result = append(result, current)

		for _, child := range spec.Edges[current] {
			inDegree[child]--
			if inDegree[child] == 0 {
				queue = append(queue, child)
			}
		}
	}

	if len(result) != len(spec.Nodes) {
		return nil, fmt.Errorf("cycle detected in DAG: %d nodes sorted, %d total", len(result), len(spec.Nodes))
	}
	return result, nil
}
