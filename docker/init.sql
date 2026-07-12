-- docker/init.sql
-- 测试数据库初始化脚本

USE test;

-- 创建测试表
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    city VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10, 2),
    category VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 插入测试数据（用存储过程批量插入）
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS seed_data()
BEGIN
    DECLARE i INT DEFAULT 0;
    WHILE i < 10000 DO
        INSERT INTO users (name, email, city)
        VALUES (CONCAT('user', i), CONCAT('user', i, '@test.com'),
                ELT(FLOOR(RAND() * 5) + 1, '北京', '上海', '广州', '深圳', '杭州'));
        SET i = i + 1;
    END WHILE;

    SET i = 0;
    WHILE i < 100000 DO
        INSERT INTO orders (user_id, amount, status)
        VALUES (FLOOR(RAND() * 10000) + 1,
                ROUND(RAND() * 1000, 2),
                ELT(FLOOR(RAND() * 3) + 1, 'pending', 'paid', 'cancelled'));
        SET i = i + 1;
    END WHILE;

    SET i = 0;
    WHILE i < 1000 DO
        INSERT INTO products (name, price, category)
        VALUES (CONCAT('product', i),
                ROUND(RAND() * 100, 2),
                ELT(FLOOR(RAND() * 4) + 1, '电子', '服装', '食品', '图书'));
        SET i = i + 1;
    END WHILE;
END //
DELIMITER ;

CALL seed_data();

-- 故意不加索引，用于演示全表扫描问题
-- 优化时建议: CREATE INDEX idx_orders_status ON orders(status);
-- 优化时建议: CREATE INDEX idx_orders_user_id ON orders(user_id);
-- 优化时建议: CREATE INDEX idx_users_city ON users(city);
