package scheduler

import "fmt"

// TopoSort 对 DAG 进行拓扑排序（Kahn 算法 + 判环）。
func TopoSort(spec *DAGSpec) ([]string, error) {
	nodeCount := len(spec.Nodes)
	inDegree, children, err := buildGraph(spec)
	if err != nil {
		return nil, err
	}

	queue := make([]string, 0)
	for id, degree := range inDegree {
		if degree == 0 {
			queue = append(queue, id)
		}
	}

	order := make([]string, 0, nodeCount)
	working := inDegree
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		order = append(order, current)
		for _, child := range children[current] {
			working[child]--
			if working[child] == 0 {
				queue = append(queue, child)
			}
		}
	}

	if len(order) != nodeCount {
		return nil, fmt.Errorf("scheduler: dag contains cycle: sorted %d/%d nodes", len(order), nodeCount)
	}
	return order, nil
}
