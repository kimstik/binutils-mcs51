# Testbench for the MCS-51 (i51) binutils port.
#
#   make frozen              build the original 2001 port from ref.7z
#   make build               build the current port from mcs51/*.patch
#   make check               build the ten projects and compare against the reference
#   make isa                 instruction-level gate against third-party corpora
#   make check BUILD=<dir>   ... using a toolchain built elsewhere
#   make dist                install the tools, strip them
#   make refresh             regenerate the patches with current line numbers
#   make libk80              rebuild libk80.a with uppercased symbols
#   make clean
#
# The reference is not a golden file kept in sync by hand: base.7z ships the www8051.rom
# every project is supposed to produce. make overwrites those in place, so their hashes
# are taken before anything is built.

BINUTILS_VERSION ?= 2.11.2
TARBALL          := binutils-$(BINUTILS_VERSION).tar.gz
URL              ?= https://ftp.gnu.org/gnu/binutils/$(TARBALL)
EXPECT_SHA256    ?= 5d600829fa397c6be7f3c51cb6ee135da50b39c3628d7f9fa660171ea4700f11

HERE  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
WORK  ?= $(HERE)/../work
BUILD ?= $(WORK)/frozen/build

PORT_VERSION  ?= 2.47
PORT_TARBALL  := binutils-$(PORT_VERSION).tar.xz
PORT_URL      ?= https://ftp.gnu.org/gnu/binutils/$(PORT_TARBALL)
PORT_SHA256   ?=
TARGET        ?= i51-elf

# Release builds are small: size-optimised, LTO, stripped. HOST empty means native.
HOST          ?=
OPTFLAGS      ?= -Os -flto -march=haswell
AR_WRAP       ?= yes
TOOLPREFIX    := $(if $(HOST),$(HOST)-,)

PROJECTS := diag ds1620 ds1822 lcd led1 led2 led3 serial welcome wjava

# gas/ld are built as as-new/ld-new before installation; the rest keep their names.
TOOLS := mcs51-as:gas/as-new \
         mcs51-ld:ld/ld-new \
         mcs51-objcopy:binutils/objcopy \
         mcs51-ar:binutils/ar \
         mcs51-nm:binutils/nm-new \
         mcs51-strip:binutils/strip-new

.PHONY: all frozen build check isa dist refresh libk80 clean

all: frozen check

# ---------------------------------------------------------------- frozen 2.11.2

# Base is the release tarball: that is what the web51 patches were cut against, their
# headers read binutils-2.11.2/... with June 2001 timestamps. They are context diffs,
# so GNU patch is required - git apply reads unified only.
#
# Nothing in the sources or the patches is touched. What makes a 2001 tree build on a
# current host is passed as environment: era compiler flags and an explicit 32-bit
# triplet, because config.sub of that era predates x86_64.
frozen:
	rm -rf $(WORK)/frozen
	mkdir -p $(WORK)/frozen
	7z x -o$(WORK)/frozen $(HERE)/ref.7z > /dev/null
	cd $(WORK)/frozen && curl -fsSL -o $(TARBALL) "$(URL)"
	cd $(WORK)/frozen && sha256sum $(TARBALL) | tee sha256.txt
	@if [ -n "$(EXPECT_SHA256)" ]; then \
		cd $(WORK)/frozen && echo "$(EXPECT_SHA256)  $(TARBALL)" | sha256sum -c -; \
	else \
		echo "note: EXPECT_SHA256 unset, tarball recorded but not verified"; \
	fi
	cd $(WORK)/frozen && tar xzf $(TARBALL)
	cd $(WORK)/frozen && patch --fuzz 5 -p1 -d binutils-$(BINUTILS_VERSION) < i51.patch.112n
	cd $(WORK)/frozen && patch --fuzz 5 -p1 -d binutils-$(BINUTILS_VERSION) < i51.patch.112p
	mkdir -p $(WORK)/frozen/build
	cd $(WORK)/frozen/build && CC="gcc -m32" CFLAGS="-std=gnu89 -fcommon -fpermissive -w" \
		../binutils-$(BINUTILS_VERSION)/configure \
			--build=i686-pc-linux-gnu --host=i686-pc-linux-gnu --target=i51 \
			--prefix=$(WORK)/frozen/toolchain --disable-nls --disable-werror
	# Serial on purpose: bfd/po of this era builds SRC-POTFILES.in and BLD-POTFILES.in
	# through a fixed temporary file called tmp in the same directory, so under -j the
	# two rules race and one loses its tmp before the mv.
	cd $(WORK)/frozen/build && $(MAKE) -j1 MAKEINFO=true \
		all-bfd all-opcodes all-gas all-ld all-binutils
	ls -l $(WORK)/frozen/build/gas/as-new $(WORK)/frozen/build/ld/ld-new

# ---------------------------------------------------------------- current port

# The port as it stands, from mcs51/additions.patch and mcs51/modifications.patch.
#
# Right now those are byte-identical to the 2001 patches in ref.7z and target the same
# binutils release, so this build and the frozen one must agree exactly. That is the point:
# frozen never moves, this one does, and the testbench says whether a step forward broke
# anything.
build:
	rm -rf $(WORK)/modern
	mkdir -p $(WORK)/modern
	cd $(WORK)/modern && curl -fsSL -o $(PORT_TARBALL) "$(PORT_URL)"
	cd $(WORK)/modern && sha256sum $(PORT_TARBALL) | tee sha256.txt
	@if [ -n "$(PORT_SHA256)" ]; then \
		cd $(WORK)/modern && echo "$(PORT_SHA256)  $(PORT_TARBALL)" | sha256sum -c -; \
	fi
	cd $(WORK)/modern && tar xf $(PORT_TARBALL)
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git init -q && git add -A && \
		git -c user.name=tb -c user.email=tb@local commit -qm pristine
	cd $(WORK)/modern && patch --fuzz 3 -p1 -d binutils-$(PORT_VERSION) < $(HERE)/../mcs51/additions.patch
	cd $(WORK)/modern && patch --fuzz 3 -p1 -d binutils-$(PORT_VERSION) < $(HERE)/../mcs51/modifications.patch
	mkdir -p $(WORK)/modern/build
	cd $(WORK)/modern/build && ../binutils-$(PORT_VERSION)/configure \
		--target=$(TARGET) --prefix=$(WORK)/modern/toolchain \
		$(if $(HOST),--host=$(HOST),) \
		--disable-nls --disable-werror --disable-gdb --disable-shared \
		CFLAGS="$(OPTFLAGS)" CXXFLAGS="$(OPTFLAGS)" LDFLAGS="-s" \
		$(if $(AR_WRAP),AR=$(TOOLPREFIX)gcc-ar RANLIB=$(TOOLPREFIX)gcc-ranlib,)
	cd $(WORK)/modern/build && $(MAKE) -j$$(nproc) MAKEINFO=true
	ls -l $(WORK)/modern/build/gas/as-new* $(WORK)/modern/build/ld/ld-new*

# ------------------------------------------------------------------- testbench

check:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD) - run make frozen, or pass BUILD=<dir>"; exit 2; }
	rm -rf $(WORK)/tb
	mkdir -p $(WORK)/tb
	7z x -o$(WORK)/tb $(HERE)/base.7z > /dev/null
	@echo "== reference ROMs shipped in base.7z"
	@cd $(WORK)/tb/projekt && for p in $(PROJECTS); do \
		printf '%-8s %5d %s\n' $$p $$(stat -c %s $$p/www8051.rom) \
			$$(md5sum $$p/www8051.rom | cut -d' ' -f1); \
	done | tee $(WORK)/tb/reference.md5
	@echo "== wrappers -> $(BUILD)"
	@cd $(WORK)/tb/bin && for pair in $(TOOLS); do \
		name=$${pair%%:*}; target=$${pair##*:}; \
		rm -f $$name; \
		printf '#!/bin/sh\nexec %s/%s "$$@"\n' "$(BUILD)" "$$target" > $$name; \
		chmod +x $$name; \
	done
	@echo "== building"
	@cd $(WORK)/tb/projekt && : > $(WORK)/tb/results.md5; for p in $(PROJECTS); do \
		( cd $$p && $(MAKE) clean > /dev/null 2>&1 || true ); \
		( cd $$p && $(MAKE) > $(WORK)/tb/$$p.log 2>&1 ) || true; \
		if [ -f $$p/www8051.rom ]; then \
			printf '%-8s %5d %s\n' $$p $$(stat -c %s $$p/www8051.rom) \
				$$(md5sum $$p/www8051.rom | cut -d' ' -f1) >> $(WORK)/tb/results.md5; \
		else \
			printf '%-8s %5d %s\n' $$p 0 BUILD-FAILED >> $(WORK)/tb/results.md5; \
		fi; \
	done
	@echo "== disassembler"
	@obj=$(WORK)/tb/projekt/diag/www8051.o; \
	$(BUILD)/binutils/readelf -h $$obj | grep -q MCS-51 || { echo "readelf does not recognise the machine"; exit 1; }; \
	$(BUILD)/binutils/objdump -d $$obj | grep -qE '^ *[0-9a-f]+:' || { echo "objdump produced no instructions"; exit 1; }; \
	echo "readelf names the machine, objdump decodes instructions"
	@echo "== comparison"
	@fail=0; for p in $(PROJECTS); do \
		want=$$(grep "^$$p " $(WORK)/tb/reference.md5 | tr -s ' ' | cut -d' ' -f2,3); \
		got=$$(grep  "^$$p " $(WORK)/tb/results.md5   | tr -s ' ' | cut -d' ' -f2,3); \
		if [ "$$want" = "$$got" ]; then printf 'PASS %-8s %s\n' $$p "$$got"; \
		else printf 'FAIL %-8s reference=%s produced=%s\n' $$p "$$want" "$$got"; fail=$$((fail+1)); fi; \
	done; \
	if [ $$fail -ne 0 ]; then echo "$$fail of 10 projects differ from the reference"; exit 1; fi; \
	echo "all 10 projects match the reference"

# ---------------------------------------------------------------------- isa

# Merge gate, not part of a release. 8051.txt carries golden bytes from an
# unrelated assembler; testall.asm is a real program covering branches and tables.
isa:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/isa_check.py --build $(BUILD) \
		--table $(HERE)/isa/8051.txt --program $(HERE)/isa/testall.asm

# ------------------------------------------------------------------------- dist

# Install only the tools, drop the docs, strip what is left.
dist:
	cd $(WORK)/modern/build && $(MAKE) MAKEINFO=true install-gas install-ld install-binutils
	rm -rf $(WORK)/modern/toolchain/share
	$(TOOLPREFIX)strip $(WORK)/modern/toolchain/bin/* || true
	du -sh $(WORK)/modern/toolchain
	ls -l $(WORK)/modern/toolchain/bin

# ---------------------------------------------------------------------- refresh

# Regenerate the patches against the tree make build just patched, so hunks carry current
# line numbers instead of accumulating offsets. Writes to work/refreshed, never to mcs51/.
refresh:
	@test -d $(WORK)/modern/binutils-$(PORT_VERSION)/.git || { echo "run make build first"; exit 2; }
	mkdir -p $(WORK)/refreshed
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git add -AN
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git diff --diff-filter=A -- . > $(WORK)/refreshed/additions.patch
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git diff --diff-filter=M -- . > $(WORK)/refreshed/modifications.patch
	wc -l $(WORK)/refreshed/additions.patch $(WORK)/refreshed/modifications.patch

# ----------------------------------------------------------------- maintenance

# libk80.a has to carry uppercased symbols to link against the rest of the library set.
# Only needed when the library itself is rebuilt, not for an ordinary check run.
LIBK80_OBJS := ptstr2se pr2x pisecz2x pchcksum prx2s tcp arp arppoirq udp icmp psendchr \
               ethdata outtcp closetcp closetcp2 retrytcp connecttcp synrqtcp psearch \
               scanpar pingcfg prx2e telnet ptcpinsum ptcpoutsum copytcp chngstack

libk80:
	@test -d $(WORK)/tb/lib || { echo "run make check first - $(WORK)/tb/lib is missing"; exit 2; }
	cd $(WORK)/tb/lib && $(BUILD)/binutils/ar x libk80.a
	@cd $(WORK)/tb/lib && for f in $(LIBK80_OBJS); do \
		python3 $(HERE)/i51elf_sym_uc.py $$f.obj $$f.upper.obj > /dev/null; \
		mv $$f.upper.obj $$f.obj; \
	done
	cd $(WORK)/tb/lib && $(BUILD)/binutils/ar rcs libk80.a $(addsuffix .obj,$(LIBK80_OBJS))
	$(BUILD)/binutils/ar t $(WORK)/tb/lib/libk80.a | wc -l

clean:
	rm -rf $(WORK)
