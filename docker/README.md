# Docker 测试环境

## 启动测试 MySQL

```bash
cd docker
docker-compose up -d
```

## 连接信息

- Host: localhost
- Port: 3306
- User: coach
- Password: coach123
- Database: test

## 测试数据

- users: 10,000 行
- orders: 100,000 行
- products: 1,000 行

orders 表故意没有 status 索引，方便测试慢查询优化。

## 停止

```bash
docker-compose down
```

## 完全清除（含数据）

```bash
docker-compose down -v
```
