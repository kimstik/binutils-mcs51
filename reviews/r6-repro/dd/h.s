	.text
_start: lcall __GSINIT_STARTUP
	lcall __INIT_DATA
	sjmp _start
