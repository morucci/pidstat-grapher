What is pidstat-grapher
-----------------------

Pidstat-grapher is a tiny python tool to create graphs about process activity.
Pidstat-grapher is based on pidstat from sysstat suite. It handles pidstat tool
in order to follow multiple process activity. Then it plots each process activity
based on pidstat output. Activity graphs reports CPU %usr, %system load and disk IO
read and write.

Install
-------

Pidstat-grapher has been tested on Debian Squeeze and need python-psutil, python-gnuplot, sysstat
packages to work properly.

How to use it
-------------

Specify pids to wait and watch. The tool run "forever" until you press Ctrl-c or
send a kill (-INT) signal to it. Resulting graphs are stored as png in the directory
you passed to -d option. Additionaly you can pass patterns with -a
option then pidstat-grapher will waiting for a process cmdline matching the provided pattern.

pidstat-grapher.py -p 2365,4589 -d /tmp/
pidstat-grapher.py -a apache,lighttpd,sql -d /tmp
pidstat-grapher.py -p 2365,4589 -a apache,lighttpd,sql -d /tmp
