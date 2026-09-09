/* One code section and one RAM section, and nothing else.  The addresses in
   the probe are what the disassembler's symbol filter is judged on, so no
   symbol this script defines may sit between them: it defines none.

   .rdata is (INFO) - not allocated - which is how the port's own default
   script lets a RAM space carry its true on-chip address while the code
   space covers the same numbers.  Two allocated sections at these addresses
   would trip the linker's overlap check instead.  */

ENTRY(_START)

SECTIONS
{
  .text  0x0000 : { *(.text) }
  .rdata 0x0040 (INFO) : { *(.rdata) }
}
