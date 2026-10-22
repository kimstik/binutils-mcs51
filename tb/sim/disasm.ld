/* One code section and one RAM section, and nothing else.  The addresses in
   the probe are what the disassembler's symbol filter is judged on, so no
   symbol this script defines may sit between them: it defines none.

   .rdata carries bytes - the probe disassembles them - so it is a loaded
   section, with its load image past the code, for the linker refuses
   initialized RAM that nothing loads.  Its address is the true on-chip
   one, the same numbers the code space covers, so the link is made with
   --no-check-sections.  */

ENTRY(_START)

SECTIONS
{
  .text  0x0000 : { *(.text) }
  .rdata 0x0040 : AT (0x0200) { *(.rdata) }
}
