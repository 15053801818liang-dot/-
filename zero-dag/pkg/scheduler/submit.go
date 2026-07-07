package scheduler

import (
	"context"
	"fmt"
	"time"
)

type SubmitRequest struct {
	DAGSpec *DAGSpec `json:"dag_spec"`
}

type SubmitResponse struct {
	DAGID     string   `json:"dag_id"`
	NodeOrder []string `json:"node_order"`
	Status    string   `json:"status"`
	CreatedAt string   `json:"created_at"`
}

func (s *DAGSchedulerV0) Submit(ctx context.Context, req *SubmitRequest) (*SubmitResponse, error) {
	if req.DAGSpec == nil || len(req.DAGSpec.Nodes) == 0 {
		return nil, fmt.Errorf("invalid DAG: no nodes")
	}

	inst, err := s.SubmitDAG(ctx, req.DAGSpec)
	if err != nil {
		return nil, err
	}

	return &SubmitResponse{
		DAGID:     inst.ID,
		NodeOrder: inst.ExecutionOrder,
		Status:    string(inst.Status),
		CreatedAt: inst.CreatedAt.Format(time.RFC3339),
	}, nil
}
