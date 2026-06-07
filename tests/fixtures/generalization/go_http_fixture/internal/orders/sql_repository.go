package orders

const createOrderSQL = `
INSERT INTO orders (order_id, status)
VALUES ($1, $2)
`

const findOrderSQL = `
SELECT order_id, status
FROM orders
WHERE order_id = $1
`

const updateOrderStatusSQL = `
UPDATE orders
SET status = $2
WHERE order_id = $1
`
