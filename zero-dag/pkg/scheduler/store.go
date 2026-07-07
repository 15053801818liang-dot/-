package scheduler

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type Store struct {
	path string
}

func NewStore(path string) *Store {
	os.MkdirAll(path, 0755)
	return &Store{path: path}
}

func (s *Store) Save(inst *DAGInstance) error {
	data, err := json.MarshalIndent(inst, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal instance: %w", err)
	}
	fp := filepath.Join(s.path, inst.ID+".json")
	return os.WriteFile(fp, data, 0644)
}

func (s *Store) Load(dagID string) (*DAGInstance, error) {
	fp := filepath.Join(s.path, dagID+".json")
	data, err := os.ReadFile(fp)
	if err != nil {
		return nil, err
	}
	var inst DAGInstance
	if err := json.Unmarshal(data, &inst); err != nil {
		return nil, err
	}
	return &inst, nil
}
