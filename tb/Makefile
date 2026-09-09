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
#   make guard               a crafted r_offset has to be diagnosed, not written through
#   make sim                 execute testall in ucsim, judge by the P1 verdict
#   make defaultlink         link a probe with ld's built-in script, check the layout
#   make commons             memory-space commons keep their address space
#   make script              every *(...) arm of both linker scripts, fed and placed
#   make disasm              disassemble a linked ELF, read the names it prints
#   make doctruth            gas/doc/c-i51.texi against the code it documents:
#                            the lists it gives - directives, operand names,
#                            relocations, mnemonics - and the diagnostics it
#                            quotes. It reads no prose and builds nothing
#   make gate                everything the merge gate runs, in order
#   make mutants             inject single faults into the port, measure what the
#                            gate catches (needs a tree built by make build)
#   make mutants-coverage    the same faults, but every stage is run against every
#                            mutant and the matrix reduced to per-stage coverage:
#                            what each stage catches on its own, what only it
#                            catches, and where two stages overlap. Slow, on
#                            demand, in no gate - it measures, it judges nothing.
#   make check BUILD=<dir>   ... using a toolchain built elsewhere
#   make dist                install the tools, licence and strip them, and
#                            check the result can assemble and link
#   make dist-check          that last check on its own
#   make release-vars        the pins the release workflow publishes
#   make gate-list           the stage names a release may claim
#   make ci-list             the same names in the order gate.yml runs them
#   make refresh             regenerate the patches with current line numbers
#   make upstream            is there a newer binutils release, and do the
#                            patches still apply to it? reports, changes nothing
#   make libk80              rebuild libk80.a with uppercased symbols
#                            (BROKEN, see the note above the recipe)
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
# file is and where it came from: base2001.PROVENANCE. Defects in the 2001 material
# base.7z ships that are known and deliberately not repaired, because repairing one
# would move the reference ROMs: base.DEFECTS.
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

.PHONY: all frozen build check check-frozen gate mutants mutants-coverage dist dist-check release-vars gate-list ci-list upstream print-port refresh libk80 clean

# The merge gate, in one list, and nothing outside this file keeps a copy of it.
# mutation/run.py requires --stages and the `mutants' target below passes
# $(MUTGATE); .github/workflows/gate.yml asks `ci-list' below for the names and
# runs whatever it prints, one log group and one verdict per name. A stage added
# here is therefore gated by CI and hunted by the mutation harness with no second
# edit anywhere - which is the point: gate.yml used to spell the same list out
# again as one hand-written step per stage, and that copy had drifted before.
#
# TOOLGATE is everything that judges the toolchain from its own inputs: no
# project sources, no reference ROM.
#
# doctruth is the one stage there that does not run the toolchain at all: it
# reads the port's own sources out of mcs51/additions.patch and compares
# gas/doc/c-i51.texi against them. It therefore needs no BUILD, and it can
# kill no mutant - mutation/gen.py mutates a built tree, which this stage
# never looks at, so a zero in its column of the coverage matrix is the
# expected reading and not a finding. It is in the gate because the manual
# is normative and nothing else checks it.
#
# GATE adds the two stages that use the ten projects: check, which compares
# every www8051.rom against the reference base.7z ships, and oracle, which
# compares it against the 2001 www8051.hex. gate.yml used to run oracle alone,
# which meant the merge gate never once hashed a produced ROM against the
# reference; check is a step of its own there now.
#
# MUTGATE is what a mutant has to survive: TOOLGATE and check. It does not also
# add oracle - oracle builds the same ten projects with the same tools and judges
# them against a fixed 2001 image, so against a mutated toolchain it can only
# repeat what check already says, at twice the cost.
TOOLGATE := isa roundtrip branch bits reloc guard sim defaultlink commons script disasm \
            doctruth
GATE     := $(TOOLGATE) check oracle
MUTGATE  := $(TOOLGATE) check

# CIGATE is $(GATE) in the order gate.yml runs it, with check-canary spliced in
# behind `check' instead of tacked onto the end: the canary sabotages the
# assembler and requires `check' to report red, so it is only worth reading
# beside the stage it judges. It is written out rather than derived by text
# substitution on $(GATE), because a derivation fails silently - a $(subst) that
# stops matching drops the canary, and a gate that has quietly stopped proving
# `check' can fail is exactly the state this testbench was already in once. What
# is asserted instead is the set: `ci-list' refuses to print a list that is not
# $(GATE) plus the canary, so a stage added above either reaches CI or reddens
# it at the first step.
CIGATE := $(TOOLGATE) check check-canary oracle

# Every stage is phony, from the list itself rather than from a second copy of
# the names: a stage cannot be added to the gate and forgotten here, and a file
# that happens to carry a stage's name cannot shadow the recipe.
.PHONY: $(CIGATE)

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
check-frozen:
	@$(MAKE) --no-print-directory -f $(HERE)/Makefile check DATA_OVERLAY=$(HERE)/base2001.7z

# ------------------------------------------------------------------ hex oracle

# The only input in this repository that no run of the current toolchain has ever
# written: projekt/*/www8051.hex, shipped in base.7z next to the www8051.rom that
# has been regenerated several times since. Each .hex decodes byte-for-byte to the
# .rom that first commit shipped, so it records what the 2001 port emitted, and
# nothing here can regenerate it.
#
# The recipe below extracts base.7z and builds it as it stands. It repairs
# nothing, because the one repair that was needed is already inside the archive:
#
#   lib/www51.sc now carries `*(reset_network)` live. It once shipped with that
#   line commented out, which orphaned the section holding `LCALL network_init`
#   (lib/packet.asm) - the only call to it in nine of the ten projects - so the
#   section landed past _etext and `objcopy -j .text` dropped it. Every ROM the
#   testbench then certified was three bytes short and never initialised the
#   RTL8019AS. base.7z was repacked with the line restored, which put eight of
#   the ten projects back on the 2001 ROM's exact length, and tb/reference.md5
#   was re-pinned on that archive.
#
# diag stays 3 bytes longer than its oracle even so: 2001 linked it with ld's
# built-in script rather than www51.sc, so its reset_network was orphaned there
# too, and diag calls network_init from its own main. hexoracle.py records that
# delta as expected.
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

# The bounds check on r_offset at the head of i51_final_link_relocate ().
# Five relocations index the section contents themselves instead of going
# through _bfd_final_link_relocate (), so that one call is the only thing
# between a crafted object and a read or write at an arbitrary distance from
# the contents buffer.  Every other stage stayed green with the check
# deleted.  The malformed objects are built here from good ones by rewriting
# r_offset and nothing else.
guard:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-guard.py --build $(BUILD)

# Link a probe with ld's built-in default script - no -T, no
# --no-check-sections - and verify the addresses it hands out.
defaultlink:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	sh $(HERE)/sim/run-defaultlink.sh $(BUILD)

# One external common per memory space: each keeps its processor-specific
# section index in the object and through a relocatable link, keeps its own
# space at the final link, keeps the space name a linker script places it
# by, and leaves a real section of that name in the same object alone. One
# name declared a common of two different spaces is refused, in either file
# order; the same name in one space, and a plain .comm beside a space
# common, still link.
commons:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	sh $(HERE)/sim/run-commons.sh $(BUILD)

# Every `*(...)' arm of the default script and of base.7z's lib/www51.sc gets
# an input section of its own carrying one identifiable byte, and the run
# asserts the whole .text image and the address of every RAM-space marker. A
# dropped arm leaves its input an orphan: the section still exists and the
# symbol still resolves, but the byte falls out of `objcopy -j .text'. That is
# how `*(reset_network)' stayed commented out in www51.sc, with every gate stage
# green, until base.7z was repacked with the line restored. The archive's copy
# now carries it live and this stage is what keeps it there.
script:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-script.py --build $(BUILD) --base $(HERE)/base.7z

# The disassembler's symbol filter, i51_symbol_is_valid: which symbols may
# name an address. Every other objdump call above passes `-b binary', a flat
# image with no symbol table, so the hook was never executed at all - and a
# .o would not execute it either, because objdump matches sections itself
# whenever the file carries relocations. Only on a linked executable does
# the hook decide, so this stage links a probe and reads the name objdump
# prints beside a code address.
disasm:
	@test -x "$(BUILD)/gas/as-new" || { echo "no toolchain in $(BUILD)"; exit 2; }
	python3 $(HERE)/sim/run-disasm.py --build $(BUILD)

# ------------------------------------------------------------------ doctruth

# gas/doc/c-i51.texi was made normative and nothing checked it. Three of its
# sentences were found false in one afternoon, and a human reading caught
# every one of them: a pin with no gate, which is the disease a review round
# was spent removing from the rest of this testbench.
#
# This stage is the part of that reading a machine can do. It compares the
# lists the manual gives against the lists the source gives - md_pseudo_table
# against the Directives section, i51_directop against the operand names,
# RELOC_NUMBERS against the relocation names, the I51_INS rows against the
# instruction list - and it requires every diagnostic the manual quotes to be
# an instance of a format string the port really carries, conversions and all.
# Both directions each time: an entry the manual invents and an entry it drops
# are the same failure.
#
# It does not read English, and no amount of green here says a documented
# rule is the rule the code implements. The three false sentences that
# prompted it were all of that shape and all three would still pass; what
# judges those is bits, reloc and branch, which assemble something. The
# header of doctruth.py states what it checks and what it cannot, at length,
# because a check that appears to verify prose is worse than no check.
#
# No toolchain: the port has no source tree, so the files are reconstructed
# from the hunk bodies of mcs51/additions.patch by the same reader that
# patch file's hash check uses.
doctruth:
	python3 $(HERE)/doctruth.py --patch $(HERE)/../mcs51/additions.patch

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

# Which stage earns its place, as a measurement rather than an opinion.
#
# `mutants' above stops at the first stage that goes red, so a stage's kill
# count is a fact about its POSITION in $(MUTGATE): a stage that runs last is
# only ever recorded catching what every stage before it missed. The last
# recorded run read sim 0 and commons 0 for exactly that reason, and no
# argument about removing or merging a stage can rest on a number like that.
#
# This target runs the whole list against every mutant - `run.py --all-stages'
# - and reduces the matrix: per stage the kills it makes on its own and the
# kills only it makes, per mutant how many stages caught it, every pair of
# stages compared, and the wall clock behind each. It costs the full gate per
# mutant instead of stopping at the first red, which is why it is on demand
# and in no gate: .github/workflows/coverage.yml runs it on workflow_dispatch
# alone.
#
# MUTSTAGES defaults to $(MUTGATE) so the measurement matches what a mutant
# actually has to survive. Overriding it is how a claim about a stage outside
# that list gets tested - `MUTSTAGES="$(MUTGATE) oracle"' is the way to find
# out whether oracle ever catches a fault check misses, which the comment
# above $(MUTGATE) asserts on reasoning alone.
#
# MUTTIMEOUT is per stage. It matters more here than in `mutants': a stage
# that overruns is recorded rc 124, which counts as a kill, so on a slow
# runner a generous limit is what keeps the wall clock from inventing
# coverage. coverage.py prints the timeout count per stage beside the kills
# so the reader can see whether that happened.
MUTSTAGES  ?= $(MUTGATE)
MUTONLY    ?=
# COVCAP is this target's own population, deliberately smaller than MUTCAP:
# `mutants' runs one stage per mutant and stops at the first red, this runs
# twelve, so the same cap costs an order of magnitude more wall clock, and
# one hung mutant costs one timeout there and twelve here.  Raise either
# when the matrix is the point and the runner has the hours.
MUTTIMEOUT ?= 300
COVCAP     ?= 4
mutants-coverage:
	@test -d $(WORK)/modern/binutils-$(PORT_VERSION) || { echo "run make build first"; exit 2; }
	mkdir -p $(MUTOUT)
	python3 $(HERE)/mutation/gen.py --tree $(WORK)/modern/binutils-$(PORT_VERSION) \
		--cap $(COVCAP) --out $(MUTOUT)/mutants.json
	python3 $(HERE)/mutation/run.py \
		--tree $(WORK)/modern/binutils-$(PORT_VERSION) \
		--build $(WORK)/modern/build \
		--mutants $(MUTOUT)/mutants.json \
		--work $(MUTOUT)/work \
		--stages $(subst $(space),$(comma),$(MUTSTAGES)) \
		$(if $(MUTONLY),--only $(MUTONLY),) \
		--timeout $(MUTTIMEOUT) \
		--all-stages \
		--out $(MUTOUT)/coverage.json
	python3 $(HERE)/mutation/coverage.py --results $(MUTOUT)/coverage.json \
		> $(MUTOUT)/COVERAGE.md
	@cat $(MUTOUT)/COVERAGE.md

comma := ,
space := $(subst ,, )

# ------------------------------------------------------------------------- dist

# What a release ships. Install the tools, drop the docs, put the licence and a
# BUILD-INFO beside them, strip, then check the result is a toolchain somebody
# can actually assemble and link 8051 code with.
#
# The first three of those are all the recipe used to do, and every archive
# published from it was wrong in three ways that nothing could have caught:
#
#   - No licence. binutils is GPLv3 and its `make install' installs no COPYING
#     of any kind, so the archive was a pile of GPL binaries with no licence
#     text - not redistributable. The text is copied out of the tarball that was
#     just built, so it is the licence of the sources these binaries came from
#     rather than a copy kept in this repository and liable to drift.
#   - No provenance. Nothing in the archive said which binutils, which commit or
#     which host it was, so an unpacked copy was unidentifiable a week later.
#   - `strip ... || true'. A missing cross-strip published unstripped binaries
#     under a release note promising stripped ones, silently. It is fatal now;
#     DIST_STRIP overrides the program if a host ever needs it to.
#
# And nothing looked at the result. Every gate stage runs the binaries out of
# the build tree, so `install' could drop a tool or the linker script and the
# whole gate would stay green while the archive shipped broken. dist_check.sh
# is the only thing in the repository that judges the installed tree.
#
# DIST_RUN says whether the installed binaries can be executed here: `native'
# when they are this machine's, `wine' for the mingw hosts, `none' for the
# static checks alone. A cross build defaults to `none' so a caller that says
# nothing gets no false failure; the workflows pass `wine' for the two Windows
# hosts, where the probe is the whole point.
DIST_PREFIX := $(WORK)/modern/toolchain
DIST_LABEL  ?= $(if $(HOST),$(HOST),$(shell uname -s 2>/dev/null)-$(shell uname -m 2>/dev/null))
DIST_RUN    ?= $(if $(HOST),none,native)
DIST_STRIP  ?= $(TOOLPREFIX)strip
DIST_COMMIT ?= $(or $(shell git -C $(HERE)/.. rev-parse HEAD 2>/dev/null),unknown)

dist:
	cd $(WORK)/modern/build && $(MAKE) MAKEINFO=true install-gas install-ld install-binutils
	rm -rf $(DIST_PREFIX)/share
# install-exec-tooldir lands as, ld and the rest a second time under
# $(TARGET)/bin, hardlinked to bin/ where the filesystem allows it and copied
# where it does not - and zip has no notion of a hardlink, so on the two Windows
# hosts those copies would be stored whole and roughly double the archive.
# bin/$(TARGET)-* is what a user runs. $(TARGET)/lib/ldscripts stays: that is
# one of the two places the default linker script can reach them from.
	rm -rf $(DIST_PREFIX)/$(TARGET)/bin
	@n=0; for f in COPYING COPYING3 COPYING.LIB COPYING3.LIB; do \
		if [ -f $(WORK)/modern/binutils-$(PORT_VERSION)/$$f ]; then \
			cp $(WORK)/modern/binutils-$(PORT_VERSION)/$$f $(DIST_PREFIX)/$$f; \
			n=$$((n+1)); \
		fi; \
	done; \
	if [ $$n -eq 0 ]; then \
		echo "dist: binutils-$(PORT_VERSION) ships no COPYING* - refusing to package unlicensed GPL binaries"; \
		exit 1; \
	fi; \
	echo "dist: $$n licence file(s) copied out of binutils-$(PORT_VERSION)"
	@{ \
		echo "i51 binutils - GNU binutils for the Intel MCS-51 / 8051"; \
		echo "upstream-binutils: $(PORT_VERSION)"; \
		echo "upstream-tarball:  $(PORT_TARBALL)"; \
		echo "upstream-sha256:   $(PORT_SHA256)"; \
		echo "target:            $(TARGET)"; \
		echo "host:              $(DIST_LABEL)"; \
		echo "port-commit:       $(DIST_COMMIT)"; \
		echo "built:             $$(date -u '+%Y-%m-%dT%H:%M:%SZ')"; \
		echo "patches:           mcs51/additions.patch mcs51/modifications.patch"; \
		echo "source:            https://github.com/kimstik/binutils-mcs51"; \
		echo "licence:           GNU GPL v3 or later - see COPYING3"; \
	} > $(DIST_PREFIX)/BUILD-INFO.txt
	@command -v $(DIST_STRIP) > /dev/null 2>&1 || { \
		echo "dist: $(DIST_STRIP) not found - refusing to publish binaries nothing stripped"; \
		exit 1; \
	}
	@rc=0; for f in $(DIST_PREFIX)/bin/*; do \
		[ -f "$$f" ] || continue; \
		$(DIST_STRIP) "$$f" || { echo "dist: $(DIST_STRIP) failed on $$f"; rc=1; }; \
	done; \
	if [ $$rc -ne 0 ]; then echo "dist: the archive would not be stripped"; exit 1; fi
	du -sh $(DIST_PREFIX)
	ls -l $(DIST_PREFIX)/bin
	sh $(HERE)/dist_check.sh $(DIST_PREFIX) $(TARGET) $(DIST_RUN)

# The same judgement on its own, for a tree dist has already installed.
dist-check:
	sh $(HERE)/dist_check.sh $(DIST_PREFIX) $(TARGET) $(DIST_RUN)

# ------------------------------------------------------------------- release

# Machine-readable pins for .github/workflows/*.yml. `make --no-print-directory
# -s -C tb release-vars >> "$$GITHUB_ENV"' is how a workflow learns which
# binutils it is publishing and what its tarball must hash to, instead of a
# second copy of those values living in the YAML and going stale.
release-vars:
	@echo 'PORT_VERSION=$(PORT_VERSION)'
	@echo 'PORT_TARBALL=$(PORT_TARBALL)'
	@echo 'PORT_SHA256=$(PORT_SHA256)'
	@echo 'PORT_URL=$(PORT_URL)'
	@echo 'TARGET=$(TARGET)'
	@echo 'GATE_STAGES=$(GATE) check-canary'

# The stage list a release is allowed to claim, straight out of $(GATE) plus the
# canary, which is in no list above. release.yml runs `gate' and `check-canary'
# and then requires this list to be exactly the fourteen names it names in the
# release body: adding a stage without saying so in the release note fails the
# publish instead of quietly changing what "fourteen stages" means.
gate-list:
	@echo $(GATE) check-canary

# The same names in the order .github/workflows/gate.yml runs them, printed only
# if they are exactly $(GATE) plus the canary. That workflow runs what this
# prints and nothing else, so a name missing from CIGATE is a stage that would
# not run: it is fatal here rather than green there. gate.yml reads this before
# it runs anything, so the run dies rather than report a verdict on a short list.
ci-list:
	@miss=; extra=; \
	for s in $(GATE) check-canary; do \
		case " $(CIGATE) " in *" $$s "*) ;; *) miss="$$miss $$s";; esac; \
	done; \
	for s in $(CIGATE); do \
		case " $(GATE) check-canary " in *" $$s "*) ;; *) extra="$$extra $$s";; esac; \
	done; \
	if [ -n "$$miss$$extra" ]; then \
		echo 'ci-list: CIGATE is not $$(GATE) plus check-canary' >&2; \
		[ -z "$$miss" ]  || echo "  in the gate, missing from CIGATE:$$miss" >&2; \
		[ -z "$$extra" ] || echo "  in CIGATE, not in the gate:$$extra" >&2; \
		exit 1; \
	fi; \
	echo $(CIGATE)

# ---------------------------------------------------------------------- refresh

# Regenerate the patches against the tree make build just patched, so hunks carry current
# line numbers instead of accumulating offsets. Writes to work/refreshed, never to mcs51/.
#
# It needs a tree `build' has already patched, which is why the upstream watcher never
# calls it: when the patches are rejected by a new release there is no patched tree to
# diff, and when they apply clean there is nothing to regenerate. The one case in
# between - a hunk that slid to another line - is exactly the one a human has to read
# before the patches are rewritten, because rewriting them is what erases the evidence.
refresh:
	@test -d $(WORK)/modern/binutils-$(PORT_VERSION)/.git || { echo "run make build first"; exit 2; }
	mkdir -p $(WORK)/refreshed
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git add -AN
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git diff --diff-filter=A -- . > $(WORK)/refreshed/additions.patch
	cd $(WORK)/modern/binutils-$(PORT_VERSION) && git diff --diff-filter=M -- . > $(WORK)/refreshed/modifications.patch
	wc -l $(WORK)/refreshed/additions.patch $(WORK)/refreshed/modifications.patch

# --------------------------------------------------------------- upstream watch

# Is there a binutils release newer than PORT_VERSION, and do mcs51/*.patch still
# apply to it? Lists the release directory PORT_URL downloads from, and downloads
# nothing at all unless a newer release is there. This is what the scheduled
# .github/workflows/upstream.yml runs, so a report from that workflow can be
# reproduced by hand:
#
#   make -C tb upstream                  against PORT_VERSION
#   make -C tb upstream PRETEND=2.40     force the whole path, comparing against 2.40
#
# It reports and changes nothing: PORT_VERSION and PORT_SHA256 are bumped by a
# human who has read the report, never by the watcher. It does not call `refresh'
# either - see the note there.
PRETEND ?=
upstream:
	python3 $(HERE)/upstream_watch.py --work $(WORK)/upstream \
		$(if $(PRETEND),--pretend-version $(PRETEND),)

# The pin, for upstream_watch.py. Asking make beats scraping this file with a
# regex: `?=', a command-line override and any future computed value all read the
# same. Nothing else uses it.
print-port:
	@printf '%s\n' 'PORT_VERSION=$(PORT_VERSION)' 'PORT_URL=$(PORT_URL)' 'PORT_SHA256=$(PORT_SHA256)'

# ----------------------------------------------------------------- maintenance

# libk80.a has to carry uppercased symbols to link against the rest of the library set.
# Only needed when the library itself is rebuilt, not for an ordinary check run.
#
# BROKEN as it stands. It runs i51elf_sym_uc.py over members extracted from the
# CURRENT libk80.a, and every member of that archive is ELFDATA2MSB - measured:
# all 27 are EI_DATA = 2, e_machine 165. i51elf_sym_uc.py unpacks every header
# field little-endian whatever EI_DATA says, so it aborts with `struct.error:
# unpack requires a buffer of 4 bytes' and writes no output; the `mv' below then
# fails on a file that is not there. Making the script endian-aware is what fixes
# this target; nothing in the Makefile needs to change.
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
