# openkobo. Needs Python 3.11+; the libraries also need Docker.
#
#   make ZIP=~/Downloads/kobo-update-4.38.23852.zip   -> out/full/KoboRoot.tgz
#   make revert ZIP=...                                -> out/revert/KoboRoot.tgz
#   make OVERLAYS=overlay ZIP=...                      without the libraries
#
# ZIP defaults to the first kobo-update-*.zip in this directory.

ZIP      ?= $(firstword $(wildcard kobo-update-*.zip))
PROFILE  ?= offline
LIBS     := out/libs/overlay
OVERLAYS ?= overlay $(LIBS)
ZIPFILE  := $(wildcard $(ZIP))
PY       := python3 -I tools/openkobo.py

ifneq ($(filter all image revert inspect,$(or $(MAKECMDGOALS),all)),)
ifeq ($(ZIPFILE),)
$(error set ZIP=<official kobo-update-*.zip for your device>)
endif
endif

.PHONY: all image revert inspect libs clean

all: image

image: out/full/KoboRoot.tgz

out/full/KoboRoot.tgz: $(ZIPFILE) patches/libnickel.toml tools/openkobo.py \
		$(shell find overlay -type f) $(if $(filter $(LIBS),$(OVERLAYS)),$(LIBS)/lib/libz.so.1)
	$(PY) build --zip "$(ZIPFILE)" --profile $(PROFILE) --overlay $(OVERLAYS) --out out/full

revert:
	$(PY) revert --zip "$(ZIPFILE)" --overlay $(OVERLAYS) --out out/revert

inspect:
	$(PY) inspect --zip "$(ZIPFILE)"

libs: $(LIBS)/lib/libz.so.1

# First run builds the cross-toolchain in Docker (slow); later runs are cached.
$(LIBS)/lib/libz.so.1: tools/libs/Dockerfile tools/libs/build-libs.sh
	sh tools/libs/run.sh
	touch $@

clean:
	rm -rf out/full out/revert
