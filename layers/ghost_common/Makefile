build-GhostCommonLayer:
	pip3.12 install -r requirements.txt \
		--target $(ARTIFACTS_DIR)/python \
		--platform manylinux2014_x86_64 \
		--implementation cp \
		--only-binary=:all: \
		--python-version 3.12
	cp python/*.py $(ARTIFACTS_DIR)/python/
