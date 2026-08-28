# Testbench for the MCS-51 (i51) binutils port.
#
#   make frozen              build the original 2001 port from ref.7z
#   make build               build the current port from mcs51/*.patch
#   make check               build the ten projects and compare against the reference
#   make check-frozen        ... with the 2001 objects, for the 2.11.2 toolchain
#   make oracle              against projekt/*/www8051.hex, the 2001 ROMs base.7z ships
#   make check-canary        prove check reports red when an input is sabotaged
#   make isa                 instruction-level gate against third-party corpora
#   make roundtrip           disassemble the golden bytes and reassemble them
#   make branch              literal-branch encodings against hand-derived bytes
#   make bits                bit addressing at its boundaries, assembler and linker
#   make reloc               every relocation kind end to end, -r and archives
#   make sim                 execute testall in ucsim, judge by the P1 verdict
#   make defaultlink         link a probe with ld's built-in script, check the layout
#   make commons             memory-space commons keep their address space
#   make script              every *(...) arm of both linker scripts, fed and placed
#   make gate                everything the merge gate runs, in order
#   make mutants             inject single faults into the port, measure what the
#                            gate catches (needs a tree built by make build)
#   make check BUILD=<dir>   ... using a toolchain built elsewhere
#   make dist                install the tools, strip them
#   make refresh             regenerate the patches with current line numbers
#   make libk80              rebuild libk80.a with uppercased symbols
#   make clean
#
# The reference is not a golden file kept in sync by hand: base.7z ships the www8051.rom
# every project is supposed to produce. Their hashes are taken straight after extraction
# and the shipped copies are then deleted, so the only www8051.rom the comparison can see
# is one the run itself produced.

BINUTILS_VERSION ?= 2.11.2
TARBALL          := binutils-$(BINUTILS_VERSION).tar.gz
URL              ?= https://ftp.gnu.org/gnu/binutils/$(TARBALL)
EXPECT_SHA256    ?= 5d600829fa397c6be7f3c51cb6ee135da50b39c3628d7f9fa660171ea4700f11

HERE  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
WORK  ?= $(HERE)/../work
BUILD ?= $(WORK)/frozen/build

# An archive unpacked over the extracted base.7z, before anything is built. Empty means
# the projects link exactly what base.7z ships. base2001.7z replaces the precompiled
# lib/ and cgi/ inputs with the 2001 originals - the only object format the 2.11.2
# toolchain reads - and the linker script that names one of their symbols. What each
# file is and where it came from: base2001.PROVENANCE.
DATA_OVERLAY ?=

PORT_VERSION  ?= 2.47
PORT_TARBALL  := binutils-$(PORT_VERSION).tar.xz
PORT_URL      ?= https://ftp.gnu.org/gnu/binutils/$(PORT_TARBALL)
PORT_SHA256   ?= 154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff
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

.PHONY: all frozen build check check-frozen oracle check-canary isa roundtrip branch bits reloc sim defaultlink commons script gate mutants dist refresh libk80 clean

# The merge gate, in one list, so the workflow and the mutation harness cannot
# drift apart from it.
#
# TOOLGATE is everything that judges the toolchain from its own inputs: no
# project sources, no reference ROM.
#
# GATE adds the two stages that use the ten projects: check, which compares
# every www8051.rom against the reference base.7z ships, and oracle, which
# compares it against the 2001 www8051.hex. gate.yml used to run oracle alone,
# which meant the merge gate never once hashed a produced ROM against the
# reference; check is in the list now and gate.yml runs the list.
#
# MUTGATE is what a mutant has to survive: TOOLGATE and check. It does not also
# add oracle - oracle builds the same ten projects with the same tools and,
# unlike check, does not fail a project that will not build, so it can only be
# the weaker of the two.
TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons script
GATE     := $(TOOLGATE) check oracle
MUTGATE  := $(TOOLGATE) check

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

# The port as it stands, from mcs51/additions.patch and mcs51/modifications.patch,
# applied to binutils $(PORT_VERSION). The patches are kept refreshed against exactly
# that release (make refresh), so they must apply with zero fuzz and zero offsets -
# anything else means the patches and PORT_VERSION are out of sync, and a fuzzy apply
# could land hunks in the wrong place silently.  `--fuzz 0' alone does not
# deliver that: it forbids fuzzy context matching, not a hunk sliding onto
# another line, and patch exits 0 on a slide.  The apply below reads its own
# log and refuses an offset.
# and the testbench says whether a step forward broke anything.
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
	@for p in additions modifications; do \
		echo "== applying mcs51/$$p.patch"; \
		if ! ( cd $(WORK)/modern && patch --fuzz 0 --no-backup-if-mismatch -p1 \
				-d binutils-$(PORT_VERSION) < $(HERE)/../mcs51/$$p.patch ) \
				> $(WORK)/modern/$$p.apply.log 2>&1; then \
			cat $(WORK)/modern/$$p.apply.log; \
			echo "mcs51/$$p.patch does not apply to binutils $(PORT_VERSION)"; \
			exit 1; \
		fi; \
		cat $(WORK)/modern/$$p.apply.log; \
		if grep -q 'offset' $(WORK)/modern/$$p.apply.log; then \
			grep 'offset' $(WORK)/modern/$$p.apply.log; \
			echo "mcs51/$$p.patch landed a hunk at a line offset: the patch and"; \
			echo "binutils $(PORT_VERSION) are out of sync.  Run make refresh."; \
			exit 1; \
		fi; \
	done
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
# The archive carries no unix permission bits, so the helpers the project Makefiles run
# through - perl, rm, bin2hex and the .pl generators - come out of it without +x.
	chmod -R +x $(WORK)/tb/bin
# Overlay files land on top of the extracted tree, replacing whatever base.7z put there.
# It carries lib/ and cgi/ inputs only, so the reference ROMs hashed below are still the
# ones base.7z shipped.
	@if [ -n "$(DATA_OVERLAY)" ]; then \
		echo "== overlay $(DATA_OVERLAY)"; \
		7z x -aoa -o$(WORK)/tb "$(DATA_OVERLAY)" > /dev/null; \
	fi
	@echo "== reference ROMs shipped in base.7z"
	@cd $(WORK)/tb/projekt && for p in $(PROJECTS); do \
		printf '%-8s %5d %s\n' $$p $$(stat -c %s $$p/www8051.rom) \
			$$(md5sum $$p/www8051.rom | cut -d' ' -f1); \
	done | tee $(WORK)/tb/reference.md5
# The shipped ROMs must be the pinned ones: a repack of base.7z cannot move the
# reference unless tb/reference.md5 changes in the same commit.
	@grep -v '^#' $(HERE)/reference.md5 > $(WORK)/tb/pinned.md5; \
	if ! diff -u $(WORK)/tb/pinned.md5 $(WORK)/tb/reference.md5; then \
		echo "reference ROMs in base.7z do not match the pinned tb/reference.md5"; exit 1; \
	fi
# The hashes are recorded, so the shipped build products go. A project that fails to build
# then has nothing left in its directory that could be mistaken for its own output.
	@cd $(WORK)/tb/projekt && for p in $(PROJECTS); do \
		rm -f $$p/www8051.rom $$p/www8051.hex $$p/www8051.o; \
	done
	@echo "== wrappers -> $(BUILD)"
	@cd $(WORK)/tb/bin && for pair in $(TOOLS); do \
		name=$${pair%%:*}; target=$${pair##*:}; \
		rm -f $$name; \
		printf '#!/bin/sh\nexec %s/%s "$$@"\n' "$(BUILD)" "$$target" > $$name; \
		chmod +x $$name; \
	done
	@echo "== building"
# Each project gets its own log in $(WORK)/tb. Nothing here hides an exit status: a make
# that fails, and a make that returns without leaving a www8051.rom, both count as
# failures and no hash is taken for them.
	@cd $(WORK)/tb/projekt && : > $(WORK)/tb/results.md5; : > $(WORK)/tb/status; \
	for p in $(PROJECTS); do \
		if ( cd $$p && $(MAKE) clean && $(MAKE) ) > $(WORK)/tb/$$p.log 2>&1; then \
			if [ -f $$p/www8051.rom ]; then \
				echo "$$p ok" >> $(WORK)/tb/status; \
				printf '%-8s %5d %s\n' $$p $$(stat -c %s $$p/www8051.rom) \
					$$(md5sum $$p/www8051.rom | cut -d' ' -f1) >> $(WORK)/tb/results.md5; \
			else \
				echo "$$p no-rom" >> $(WORK)/tb/status; \
				printf '%-8s %5d %s\n' $$p 0 NO-ROM >> $(WORK)/tb/results.md5; \
			fi; \
		else \
			echo "$$p build-failed" >> $(WORK)/tb/status; \
			printf '%-8s %5d %s\n' $$p 0 BUILD-FAILED >> $(WORK)/tb/results.md5; \
		fi; \
	done
	@echo "== comparison"
# One line per project, then the tail of every failing log so a CI run is readable
# without downloading the artifacts. Exits nonzero if anything failed.
	@fail=0; failed=; for p in $(PROJECTS); do \
		st=$$(awk -v p=$$p '$$1 == p { print $$2 }' $(WORK)/tb/status); \
		want=$$(grep "^$$p " $(WORK)/tb/reference.md5 | tr -s ' ' | cut -d' ' -f2,3); \
		got=$$(grep  "^$$p " $(WORK)/tb/results.md5   | tr -s ' ' | cut -d' ' -f2,3); \
		if [ "$$st" != ok ]; then \
			printf 'FAIL %-8s %s\n' $$p "$$st"; \
			fail=$$((fail+1)); failed="$$failed $$p"; \
		elif [ "$$want" = "$$got" ]; then \
			printf 'PASS %-8s %s\n' $$p "$$got"; \
		else \
			printf 'FAIL %-8s reference=%s produced=%s\n' $$p "$$want" "$$got"; \
			fail=$$((fail+1)); failed="$$failed $$p"; \
		fi; \
	done; \
	for p in $$failed; do \
		echo "---- $$p: last 15 lines of $(WORK)/tb/$$p.log"; \
		tail -n 15 $(WORK)/tb/$$p.log; \
	done; \
	if [ $$fail -ne 0 ]; then \
		echo "$$fail of $(words $(PROJECTS)) projects failed"; exit 1; \
	fi; \
	echo "all $(words $(PROJECTS)) projects match the reference"

# ------------------------------------------------------------------ check frozen

# check as the 2.11.2 toolchain needs it: same projects, same reference ROMs, but the
# precompiled inputs come from base2001.7z. BUILD already points at the frozen build.
# What this produces and how it compares: frozen-report.md.
check-frozen:
	@$(MAKE) --no-print-directory -f $(HERE)/Makefile check DATA_OVERLAY=$(HERE)/base2001.7z

# ------------------------------------------------------------------ hex oracle

# The only input in this repository that no run of the current toolchain has ever
# written: projekt/*/www8051.hex, shipped in base.7z next to the www8051.rom that
# has been regenerated several times since. Each .hex decodes byte-for-byte to the
# .rom that first commit shipped, so it records what the 2001 port emitted, and
# nothing here can regenerate it.
#
# Two repairs are made to the extracted tree before building, both of them in
# base.7z's own copy of the 2001 inputs and neither of them in the port:
#
#   1. lib/www51.sc ships with `*(reset_network)` commented out. The section holds
#      `LCALL network_init` (lib/packet.asm), the only call to it in nine of the
#      ten projects, and with the line commented the section is an orphan that
#      lands past _etext and `objcopy -j .text` drops. Every ROM `make check`
#      certifies is therefore three bytes short and never initialises the
#      RTL8019AS. Restoring the line puts eight of the ten projects back on the
#      2001 ROM's exact length.
#
#   2. projekt/diag/Makefile is left alone: 2001 linked diag with ld's built-in
#      script, so its reset_network was orphaned there too, and diag calls
#      network_init from its own main. Its ROM is expected to come out 3 bytes
#      longer than the oracle's - hexoracle.py records that.
#
# ROOTCAUSE-rom-delta.md derives all of this.
oracle:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD) - run make build, or pass BUILD=<dir>"; exit 2; }
	rm -rf $(WORK)/oracle $(WORK)/oracle-hex
	mkdir -p $(WORK)/oracle
	7z x -o$(WORK)/oracle $(HERE)/base.7z > /dev/null
	chmod -R +x $(WORK)/oracle/bin
# The 2001 .hex files are moved out of reach before anything builds, because each
# project's own build writes www8051.hex over the top of them.
	@for p in $(PROJECTS); do \
		mkdir -p $(WORK)/oracle-hex/projekt/$$p; \
		mv $(WORK)/oracle/projekt/$$p/www8051.hex $(WORK)/oracle-hex/projekt/$$p/www8051.hex; \
		rm -f $(WORK)/oracle/projekt/$$p/www8051.rom $(WORK)/oracle/projekt/$$p/www8051.o; \
	done
	@cd $(WORK)/oracle/bin && for pair in $(TOOLS); do \
		name=$${pair%%:*}; target=$${pair##*:}; \
		rm -f $$name; \
		printf '#!/bin/sh\nexec %s/%s "$$@"\n' "$(BUILD)" "$$target" > $$name; \
		chmod +x $$name; \
	done
	@echo "== building"
	@cd $(WORK)/oracle/projekt && rc=0; for p in $(PROJECTS); do \
		if ( cd $$p && $(MAKE) clean && $(MAKE) ) > $(WORK)/oracle/$$p.log 2>&1; then \
			echo "   $$p"; \
		else \
			echo "FAIL $$p: build failed"; \
			tail -n 20 $(WORK)/oracle/$$p.log; \
			rc=1; \
		fi; \
	done; \
	if [ $$rc -ne 0 ]; then \
		echo "oracle: a project that does not build cannot be compared"; \
		exit 1; \
	fi
	@echo "== against the 2001 .hex"
	python3 $(HERE)/hexoracle.py --tree $(WORK)/oracle --oracle $(WORK)/oracle-hex --verbose

# ------------------------------------------------------------------ check canary

# Runs check against a toolchain that cannot assemble anything, in a work directory of
# its own so a real check run next to it is untouched. Passes only when that check exits
# nonzero, which is what says the harness still reports a broken build as a failure
# instead of re-hashing the reference ROMs shipped in base.7z.
check-canary:
	rm -rf $(WORK)/canary
	mkdir -p $(WORK)/canary/build/gas
	printf '#!/bin/sh\necho "canary: assembler sabotaged" >&2\nexit 1\n' > $(WORK)/canary/build/gas/as-new
	chmod +x $(WORK)/canary/build/gas/as-new
	@echo "== canary: check with a sabotaged assembler"
	@if $(MAKE) --no-print-directory -f $(HERE)/Makefile check \
			WORK=$(WORK)/canary BUILD=$(WORK)/canary/build \
			> $(WORK)/canary/check.log 2>&1; then \
		echo "CANARY FAIL: check reported success against a toolchain that cannot assemble"; \
		tail -n 30 $(WORK)/canary/check.log; \
		exit 1; \
	else \
		n=$$(grep -c '^FAIL ' $(WORK)/canary/check.log); \
		echo "CANARY PASS: check exited nonzero, $$n project(s) reported FAIL"; \
		echo "log in $(WORK)/canary/check.log"; \
		test "$$n" -gt 0; \
	fi

# ---------------------------------------------------------------------- isa

# Merge gate, not part of a release. 8051.txt carries golden bytes from an
# unrelated assembler; testall.asm is a real program covering branches and tables.
isa:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/isa_check.py --build $(BUILD) \
		--table $(HERE)/isa/8051.txt \
		--program $(HERE)/isa/testall.asm --dialect
	python3 $(HERE)/isa_check.py --build $(BUILD) --table $(HERE)/isa/extra.txt

# Disassembler against assembler on the same golden bytes: what `isa' decoded
# is fed straight back to gas and has to produce the bytes it came from, and
# the displacement a branch prints has to agree with the target its comment
# names. --stages roundtrip, so this does not re-run the assemble and decode
# stages `isa' above has already run; zeroops.txt is only reached here, so for
# that table the roundtrip stage decodes for itself.
roundtrip:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/isa_check.py --build $(BUILD) --table $(HERE)/isa/8051.txt --stages roundtrip
	python3 $(HERE)/isa_check.py --build $(BUILD) --table $(HERE)/isa/extra.txt --stages roundtrip
	python3 $(HERE)/isa_check.py --build $(BUILD) --table $(HERE)/isa/zeroops.txt --stages roundtrip

# ---------------------------------------------------------------- branch + sim

# Literal-branch encodings: relative branches to numeric addresses and the
# acall/ajmp 2K-page rule, compared against hand-derived expected bytes.
branch:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-branch.py --build $(BUILD)

# Execute testall in the ucsim 8051 simulator; the program itself reports the
# verdict through P1 (127 = every instruction test passed).
sim:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	sh $(HERE)/sim/run-testall.sh $(BUILD)

# The bit-address fold at its boundaries: RAM 0x20-0x2F onto bits 0x00-0x7F,
# SFRs at a multiple of 8 onto bits 0x80-0xFF, everything else refused - in
# the assembler and in the linker's R_I51_8_B2B alike.
bits:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-bits.py --build $(BUILD)

# Every relocation kind end to end: which one an instruction emits, what the
# linker leaves in the byte, where its range ends, and that a straight link,
# ld -r and an archive member all produce the same image.
reloc:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-reloc.py --build $(BUILD)

# Link a probe with ld's built-in default script - no -T, no
# --no-check-sections - and verify the addresses it hands out.
defaultlink:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	sh $(HERE)/sim/run-defaultlink.sh $(BUILD)

# One external common per memory space: each keeps its processor-specific
# section index in the object and its own space at the link, keeps the
# space name a linker script places it by, and leaves a real section of
# that name in the same object alone.
commons:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	sh $(HERE)/sim/run-commons.sh $(BUILD)

# Every `*(...)' arm of the default script and of base.7z's lib/www51.sc gets
# an input section of its own carrying one identifiable byte, and the run
# asserts the whole .text image and the address of every RAM-space marker. A
# dropped arm leaves its input an orphan: the section still exists and the
# symbol still resolves, but the byte falls out of `objcopy -j .text'. That is
# how `*(reset_network)' stayed commented out in www51.sc for the life of this
# repository with every gate stage green.
script:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-script.py --build $(BUILD) --base $(HERE)/base.7z

# ---------------------------------------------------------------- gate

# Everything the merge gate runs. Each stage prints its own verdict; the first
# failure stops the run.
gate:
	@for t in $(GATE); do \
		echo "== $$t"; \
		$(MAKE) --no-print-directory -f $(HERE)/Makefile $$t BUILD=$(BUILD) WORK=$(WORK) || exit 1; \
	done
	@echo "gate: PASS ($(GATE))"

# ------------------------------------------------------------------- mutants

# Mutation testing: single faults injected into the port's own sources, one at
# a time, each rebuilt and put through $(MUTGATE). A mutant that survives is a
# fault no test can see. Needs the tree make build left behind, and writes
# only inside $(WORK).
MUTCAP ?= 12
MUTOUT ?= $(WORK)/mutants
mutants:
	@test -d $(WORK)/modern/binutils-$(PORT_VERSION) || { echo "run make build first"; exit 2; }
	mkdir -p $(MUTOUT)
	python3 $(HERE)/mutation/gen.py --tree $(WORK)/modern/binutils-$(PORT_VERSION) \
		--cap $(MUTCAP) --out $(MUTOUT)/mutants.json
	python3 $(HERE)/mutation/run.py \
		--tree $(WORK)/modern/binutils-$(PORT_VERSION) \
		--build $(WORK)/modern/build \
		--mutants $(MUTOUT)/mutants.json \
		--work $(MUTOUT)/work \
		--stages $(subst $(space),$(comma),$(MUTGATE)) \
		--out $(MUTOUT)/results.json

comma := ,
space := $(subst ,, )

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
