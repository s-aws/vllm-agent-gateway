package orders

import "sync"

type Order struct {
	ID     string
	Status string
}

type Repository interface {
	SaveOrder(order Order)
	FindOrder(orderID string) (Order, bool)
}

type MemoryRepository struct {
	lock   sync.RWMutex
	orders map[string]Order
}

func NewMemoryRepository() *MemoryRepository {
	return &MemoryRepository{orders: map[string]Order{}}
}

func (repository *MemoryRepository) SaveOrder(order Order) {
	repository.lock.Lock()
	defer repository.lock.Unlock()
	repository.orders[order.ID] = order
}

func (repository *MemoryRepository) FindOrder(orderID string) (Order, bool) {
	repository.lock.RLock()
	defer repository.lock.RUnlock()
	order, found := repository.orders[orderID]
	return order, found
}
