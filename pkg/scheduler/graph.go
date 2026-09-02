package scheduler

import "fmt"

// buildGraph 构建入度表与邻接表，并校验边引用。
func buildGraph(spec *DAGSpec) (inDegree map[string]int, children map[string][]string, err error) {
	nodeCount := len(spec.Nodes)
	inDegree = make(map[string]int, nodeCount)
	children = make(map[string][]string, nodeCount)

	for id := range spec.Nodes {
		inDegree[id] = 0
	}
	for _, edge := range spec.Edges {
		if edge == nil {
			return nil, nil, fmt.Errorf("scheduler: nil edge")
		}
		from, to := edge.From, edge.To
		if from == to {
			return nil, nil, fmt.Errorf("scheduler: self-loop on node %s", from)
		}
		if _, ok := spec.Nodes[from]; !ok {
			return nil, nil, fmt.Errorf("scheduler: edge references unknown node %s", from)
		}
		if _, ok := spec.Nodes[to]; !ok {
			return nil, nil, fmt.Errorf("scheduler: edge references unknown node %s", to)
		}
		children[from] = append(children[from], to)
		inDegree[to]++
	}
	return inDegree, children, nil
}

// predecessors 返回节点的所有前驱。
func predecessors(spec *DAGSpec, nodeID string) []string {
	var preds []string
	for _, e := range spec.Edges {
		if e != nil && e.To == nodeID {
			preds = append(preds, e.From)
		}
	}
	return preds
}

// depsSatisfied 检查节点所有前驱是否已完成或跳过。
func depsSatisfied(inst *DAGInstance, nodeID string) bool {
	preds := predecessors(inst.Spec, nodeID)
	if len(preds) == 0 {
		return true
	}
	for _, pred := range preds {
		st := inst.NodeStates[pred].Status
		if st != StatusCompleted && st != StatusSkipped {
			return false
		}
	}
	return true
}
