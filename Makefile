.PHONY: install test run backfill

install:
	pip install -r requirements.txt

test:
	pytest

# Corre todos los retailers activos en retailers/*.yaml.
run:
	python run.py

# Carga inicial (o re-carga) de un solo retailer. Uso:
#   make backfill RETAILER=chedraui
# (el nombre es el del archivo YAML en retailers/, sin extensión)
#
# No es un comando distinto al run diario — el pipeline ya es idempotente
# y las guardas de calidad se saltan solas cuando no hay histórico
# suficiente (ver core/quality_guards.py, Fase 6). "backfill" es solo un
# nombre más claro para la primera carga de un retailer nuevo.
backfill:
ifndef RETAILER
	$(error Uso: make backfill RETAILER=<nombre-del-yaml-en-retailers-sin-extension>)
endif
	python run.py --retailer $(RETAILER)
