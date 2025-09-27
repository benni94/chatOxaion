# Simple Makefile helpers

.PHONY: setup run crawl query gui

setup:
	python3 install_dependencies.py

run gui:
	./start.sh

crawl:
	./venv/bin/python crawler.py

query:
	./venv/bin/python query.py
