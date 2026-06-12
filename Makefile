.PHONY: help install test pipeline dashboard lint clean

help:
	@echo "Available targets:"
	@echo "  make install    Install Python dependencies"
	@echo "  make test       Run the test suite"
	@echo "  make pipeline   Run the full data pipeline"
	@echo "  make dashboard  Launch the Streamlit dashboard"
	@echo "  make clean      Remove generated data artifacts"

install:
	pip install -r requirements.txt

test:
	pytest tests -q

pipeline:
	python run_pipeline.py

dashboard:
	streamlit run src/dashboard/app.py

clean:
	rm -rf data/raw/* data/bronze/* data/silver/* data/gold/*