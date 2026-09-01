/* Place .text at 0 and nothing else: testall is a single-section image. */
SECTIONS
{
  . = 0;
  .text : { *(.text) }
}
