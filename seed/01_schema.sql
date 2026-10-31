CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(150) NOT NULL UNIQUE,
    city       VARCHAR(60)  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR(120)   NOT NULL,
    category VARCHAR(50)    NOT NULL,
    price    NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    stock    INTEGER        NOT NULL DEFAULT 0
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER     NOT NULL REFERENCES customers (id),
    status      VARCHAR(20) NOT NULL CHECK (status IN ('PLACED', 'SHIPPED', 'DELIVERED', 'CANCELLED')),
    ordered_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_items (
    order_id   INTEGER        NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id INTEGER        NOT NULL REFERENCES products (id),
    quantity   INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

CREATE INDEX idx_orders_customer ON orders (customer_id);
CREATE INDEX idx_orders_ordered_at ON orders (ordered_at);

COMMENT ON TABLE orders IS 'Customer orders and their fulfilment status';
COMMENT ON COLUMN orders.status IS 'PLACED, SHIPPED, DELIVERED or CANCELLED';
