package scheduler

import "fmt"

type API struct {
	scheduler *DAGSchedulerV0
}

func NewAPI(scheduler *DAGSchedulerV0) *API {
	return &API{scheduler: scheduler}
}

func (a *API) Query(dagID string) (*DAGInstance, error) {
	inst, ok := a.scheduler.GetDAG(dagID)
	if !ok {
		return nil, fmt.Errorf("DAG %s not found", dagID)
	}
	return inst, nil
}

func (a *API) List() []string {
	a.scheduler.mu.RLock()
	defer a.scheduler.mu.RUnlock()
	var ids []string
	for id := range a.scheduler.instances {
		ids = append(ids, id)
	}
	return ids
}
