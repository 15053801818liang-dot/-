package backtestapi

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// Store in-memory task index with JSON file persistence.
type Store struct {
	mu   sync.RWMutex
	dir  string
	byID map[string]*Task
}

func NewStore(dir string) (*Store, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create task store: %w", err)
	}
	st := &Store{dir: dir, byID: make(map[string]*Task)}
	if err := st.loadAll(); err != nil {
		return nil, err
	}
	return st, nil
}

func (st *Store) path(id string) string {
	return filepath.Join(st.dir, id+".json")
}

func (st *Store) loadAll() error {
	entries, err := os.ReadDir(st.dir)
	if err != nil {
		return err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(st.dir, e.Name()))
		if err != nil {
			return err
		}
		var t Task
		if err := json.Unmarshal(b, &t); err != nil {
			return fmt.Errorf("load task %s: %w", e.Name(), err)
		}
		st.byID[t.ID] = &t
	}
	return nil
}

func (st *Store) Save(task *Task) error {
	st.mu.Lock()
	defer st.mu.Unlock()
	copy := *task
	st.byID[task.ID] = &copy
	b, err := json.MarshalIndent(&copy, "", "  ")
	if err != nil {
		return err
	}
	tmp := st.path(task.ID) + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, st.path(task.ID))
}

func (st *Store) Get(id string) (*Task, bool) {
	st.mu.RLock()
	defer st.mu.RUnlock()
	t, ok := st.byID[id]
	if !ok {
		return nil, false
	}
	copy := *t
	return &copy, true
}
