SELECT setseed(0.42);

INSERT INTO customers (name, email, city, created_at)
SELECT 'Customer ' || g,
       'customer' || g || '@example.com',
       (ARRAY ['Bengaluru', 'Hyderabad', 'Bhubaneswar', 'Pune', 'Chennai', 'Mumbai'])[1 + (g % 6)],
       now() - (g || ' days')::interval
FROM generate_series(1, 200) AS g;

INSERT INTO products (name, category, price, stock)
VALUES ('Wireless Mouse', 'Electronics', 799.00, 120),
       ('Mechanical Keyboard', 'Electronics', 3499.00, 45),
       ('USB-C Hub', 'Electronics', 1899.00, 80),
       ('27" Monitor', 'Electronics', 15999.00, 20),
       ('Laptop Stand', 'Accessories', 1299.00, 150),
       ('Desk Lamp', 'Home Office', 999.00, 90),
       ('Ergonomic Chair', 'Home Office', 12499.00, 15),
       ('Notebook Pack', 'Stationery', 249.00, 500),
       ('Gel Pens (10)', 'Stationery', 199.00, 650),
       ('Noise-Cancelling Headphones', 'Electronics', 8999.00, 35),
       ('Webcam 1080p', 'Electronics', 2799.00, 60),
       ('Standing Desk Mat', 'Home Office', 1599.00, 40);

INSERT INTO orders (customer_id, status, ordered_at)
SELECT 1 + floor(random() * 200)::int,
       (ARRAY ['PLACED', 'SHIPPED', 'DELIVERED', 'DELIVERED', 'DELIVERED', 'CANCELLED'])[1 + floor(random() * 6)::int],
       now() - (floor(random() * 365) || ' days')::interval
FROM generate_series(1, 1500);

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT o.id, p.id, 1 + floor(random() * 3)::int, p.price
FROM orders o
CROSS JOIN LATERAL (
    SELECT id, price FROM products ORDER BY random() + o.id * 0 LIMIT 1 + floor(random() * 3)::int
) p;

ANALYZE;
