.PHONY: up down logs replay live test build ps

up:
	docker compose up --build -d
	@echo "UI  http://localhost:3000"
	@echo "API http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

replay:
	DATA_MODE=replay docker compose up --build -d
	@echo "Replay mode — UI http://localhost:3000"

live:
	DATA_MODE=live docker compose up --build -d
	@echo "Live (Yahoo delayed + OCC) — UI http://localhost:3000"

test:
	docker compose run --rm --no-deps api pytest -q

build:
	docker compose build

ps:
	docker compose ps
