package scheduler

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Store JSON 持久化接口。
type Store interface {
	Save(inst *DAGInstance) error
	LoadAll() ([]*DAGInstance, error)
}

// JSONStore 将 DAG 实例写入 JSON 文件。
type JSONStore struct {
	Dir string
}

func NewJSONStore(dir string) (*JSONStore, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create store dir: %w", err)
	}
	return &JSONStore{Dir: dir}, nil
}

func (st *JSONStore) path(id string) string {
	return filepath.Join(st.Dir, id+".json")
}

func (st *JSONStore) Save(inst *DAGInstance) error {
	b, err := json.MarshalIndent(inst, "", "  ")
	if err != nil {
		return err
	}
	tmp := st.path(inst.ID) + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, st.path(inst.ID))
}

func (st *JSONStore) LoadAll() ([]*DAGInstance, error) {
	entries, err := os.ReadDir(st.Dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var out []*DAGInstance
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		if filepath.Ext(filepath.Base(e.Name())) == ".tmp" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(st.Dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var inst DAGInstance
		if err := json.Unmarshal(b, &inst); err != nil {
			return nil, fmt.Errorf("load %s: %w", e.Name(), err)
		}
		out = append(out, &inst)
	}
	return out, nil
}

// NoopStore 不持久化。
type NoopStore struct{}

func (NoopStore) Save(*DAGInstance) error           { return nil }
func (NoopStore) LoadAll() ([]*DAGInstance, error) { return nil, nil }
