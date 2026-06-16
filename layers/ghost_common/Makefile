build-GhostCommonLayer:
	/Users/omar/personal/AI-messaging/.venv/bin/python -m pip install -r requirements.txt \
		--target $(ARTIFACTS_DIR)/python \
		--platform manylinux2014_x86_64 \
		--implementation cp \
		--only-binary=:all: \
		--python-version 3.12
	cp python/*.py $(ARTIFACTS_DIR)/python/
