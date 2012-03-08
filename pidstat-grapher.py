#!/usr/bin/python

# Copyright (c) 2011 Fabien Boucher <fabien.dot.boucher@gmail.com>
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import shlex
import time
import sys
import os
import re
import psutil
import signal
import Gnuplot, Gnuplot.funcutils
import subprocess
import threading
from optparse import OptionParser

GDEBUG=0
PIDSTAT = "/usr/bin/pidstat"
CMD_TEMPLATE = "%(cmd)s -p %(pid)s -u -d -r -h -l 1 3600"

def find_pid_by_pattern(pattern):
    me = sys.argv[0]
    mepattern = ".*%s.*" % me
    pattern = ".*%s.*" % pattern
    for p in psutil.process_iter():
        cmdline = " ".join(p.cmdline)
        if re.match(pattern, cmdline) and not re.match(mepattern, cmdline):
            return p.pid
    raise OSError

def create_graph(timeseries, dataseries1, dataseries2, gtitle,
                            title1, title2,
                            ylabel1, ylabel2,
                            savepath):
    data1 = zip(timeseries, dataseries1)
    data1 = Gnuplot.Data(data1, title=title1)
    data2 = zip(timeseries, dataseries2)
    data2 = Gnuplot.Data(data2, title=title2, axes='x1y2')
    yrange_max = max(dataseries1)
    yrange_max = yrange_max * 1.2 or 1
    y2range_max = max(dataseries2)
    y2range_max = y2range_max * 1.2 or 1
    g = Gnuplot.Gnuplot(debug=GDEBUG)
    g.xlabel('duration (s)')
    g.ylabel(ylabel1)
    g('set title "LOAD for cmd: %s"' % gtitle)
    g('set style data linespoints')
    g('set y2label "%s"' % ylabel2)
    g('set y2tics border')
    g('set yrange [0:%s]' % str(yrange_max))
    g('set y2range [0:%s]' % str(y2range_max))
    g('set output "%s"' % savepath)
    g('set terminal png size 1000,480')
    g._add_to_queue([data1, data2])
    g.replot()

class PidWatcherTask(threading.Thread):

    def __init__(self, pid, ret, lock):
        threading.Thread.__init__(self)
        self.pid = pid
        self.ret = ret
        self.lock = lock
        self.terminate = False

    def run(self):
        lock.acquire()
        print "[%s] start watching pid or pattern %s" % (self.name, self.pid)
        lock.release()
        notexists = True
        attempts = 0
        # maxattempts timeout looking for a process
        maxattempts = 120
        while notexists:
            if self.terminate:
                break
            if attempts == maxattempts:
                lock.acquire()
                print "[%s] process pid or pattern %s not found" % (self.name, self.pid)
                lock.release()
                break
            try:
                if isinstance(self.pid, int):
                    os.kill(self.pid, 0)
                if isinstance(self.pid, str):
                    self.pid = find_pid_by_pattern(self.pid)
                notexists = False
                lock.acquire()
                print "[%s] found process pid %s" % (self.name, self.pid)
                lock.release()
            except OSError:
                lock.acquire()
                print "[%s] waiting for pid or pattern %s" % (self.name, self.pid)
                lock.release()
                time.sleep(1)
                attempts += 1
        command = shlex.split(CMD_TEMPLATE % {'cmd': PIDSTAT, 'pid': self.pid})
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE)
        out = [outline for outline in self.process.communicate()[0].split('\n') if not outline.startswith('#')][1:]
        out = [out.strip() for out in out if len(out)]
        dataset = []
        cmdline = None
        for line in out:
            splittedline = re.split('\s{1,}', line)
            if cmdline == None:
                cmdline = " ".join(splittedline[15:])
            splittedline = splittedline[:15]
            dataset.append(splittedline)
        
        timeseries = []
        usrseries = []
        systemseries = []
        iorseries = []
        iowseries = []
        rss = []
        for tick in dataset:
            timeseries.append(float(tick[0]))
            usrseries.append(float(tick[2].replace(',', '.')))
            systemseries.append(float(tick[3].replace(',', '.')))
            rss.append(float(tick[10].replace(',', '.')))
            iorseries.append(float(tick[12].replace(',', '.')))
            iowseries.append(float(tick[13].replace(',', '.')))
        if not timeseries:
            return
        origin = timeseries[0]
        timeseries = [v - origin for v in timeseries]

        self.lock.acquire()
        print "[%s] stop watching %s" % (self.name, self.pid)
        self.ret[self.pid] = {'cmdline': cmdline,
                    'timeseries': timeseries,
                    'usrseries': usrseries,
                    'systemseries': systemseries,
                    'iorseries': iorseries,
                    'iowseries': iowseries,
                    'rss': rss}
        self.lock.release()

def stop_pidstat_watchers(threads):
    for thread in threads:
        print "[%s] user requests terminate thread task" % thread.name
        if not hasattr(thread, 'process'):
            thread.terminate = True
        else:
            try:
                thread.process.terminate()
            except OSError:
                pass

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-p", "--pids",
                      action="store",
                      dest="pids", 
                      default=None,
                      help="provide pids list to watch (separate by a comma)")
    parser.add_option("-a", "--patterns",
                      action="store",
                      dest="patterns",
                      default=None,
                      help="provide string patterns list (separate by a comma)" \
                          "useful when programs will start later and pid is unknown")
    parser.add_option("-d", "--directory",
                      action="store",
                      dest="path",
                      default=None,
                      help="write output files to path")

    (o, a) = parser.parse_args()

    if not os.path.isfile(PIDSTAT):
        print "Unable to find %s. exit." % PIDSTAT
        sys.exit(1)

    path = o.path
    if not path or not (o.pids or o.patterns):
        print "Bad usage. Look at command help. exit."
        sys.exit(1)

    if not os.path.exists(path):
        print "%s not found. exit." % path
        sys.exit(1)

    pids_and_patterns = []
    if o.pids:
        pids = o.pids.split(',')
        pids_and_patterns.extend([int(pid) for pid in pids])
    if o.patterns:
        patterns = [p.strip() for p in o.patterns.split(',')]
        pids_and_patterns.extend(patterns)
    
    ret = {}
    lock = threading.RLock()
    print "Press CTRL-c or kill pidstat subprocess to stop watchers and start rendering in %s" % path
    threads = map(lambda pid_or_pattern: PidWatcherTask(pid_or_pattern, ret, lock), pids_and_patterns)
    signal.signal(signal.SIGINT, lambda signal, frame: stop_pidstat_watchers(threads))
    signal.signal(signal.SIGTERM, lambda signal, frame: stop_pidstat_watchers(threads))
    map(lambda t: t.start(), threads)
    while len([t for t in threads if t.isAlive()]) > 0:
        map(lambda t: t.join(0.2), threads)

    for k, v in ret.items():
        print "Creating activity graph for %s (%s)" % (k, v['cmdline'])
        name = v['cmdline'].replace(' ', '-').replace('/', '_')
        create_graph(v['timeseries'], v['usrseries'], v['systemseries'], v['cmdline'],
                       "CPU %usr", "CPU %system", "load (%)", "load (%)", os.path.join(path, "cpu_"+name)+".png")
        create_graph(v['timeseries'], v['iorseries'], v['iowseries'], v['cmdline'],
                        "IO stats reads", "IO stats writes", "reads (kB)", "writes (kB)", os.path.join(path, "io_"+name)+".png")
        create_graph(v['timeseries'], v['rss'], [0], v['cmdline'],
                        "Physical memory use", "", "amount (kB)", "", os.path.join(path, "mem_"+name)+".png")
