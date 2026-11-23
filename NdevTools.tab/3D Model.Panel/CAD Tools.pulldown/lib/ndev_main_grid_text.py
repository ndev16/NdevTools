# -*- coding: utf-8 -*-
"""Read model-space CAD grid labels with AutoCAD Core Console."""
import glob
import os
import re
import shutil
import tempfile
import io
import math
from System.Diagnostics import Process, ProcessStartInfo

_FEET = {1:1./12, 2:1., 4:1./304.8, 5:1./30.48, 6:1./.3048, 21:1200./3937/.3048}


def read_labels(path):
    programs = os.path.join(os.environ.get('ProgramW6432', os.environ['ProgramFiles']), 'Autodesk')
    engines = sorted(glob.glob(os.path.join(programs, 'AutoCAD *', 'accoreconsole.exe')))
    if not engines:
        raise ValueError('AutoCAD Core Console is unavailable.')
    folder = tempfile.mkdtemp(prefix='ndev_grid_')
    try:
        drawing = os.path.join(folder, 'source.dwg')
        shutil.copyfile(path, drawing)
        output = os.path.join(folder, 'labels.tsv')
        script = os.path.join(folder, 'read.scr')
        # ATTRIB insertion points are already in drawing coordinates.
        commands = [
            '(setq f (open "{}" "w" "utf8"))'.format(output.replace('\\','/')),
            '(write-line (itoa (getvar "INSUNITS")) f)',
            '(setq e (entnext))',
            '(while e (setq d (entget e) typ (cdr (assoc 0 d)) lay (cdr (assoc 8 d))) (if (and (/= (cdr (assoc 67 d)) 1) (member typ (list "ATTRIB" "TEXT" "MTEXT"))) (progn (setq p (cdr (assoc 10 d)) h (cdr (assoc 40 d)) v (cdr (assoc 1 d))) (if (and p h v) (write-line (strcat lay (chr 9) (rtos (car p) 2 8) (chr 9) (rtos (cadr p) 2 8) (chr 9) (rtos h 2 8) (chr 9) v) f)))) (setq e (entnext e)))',
            '(close f)', '_QUIT', '_N', '']
        with open(script, 'w') as stream:
            stream.write('\n'.join(commands))
        info = ProcessStartInfo(engines[-1], '/i "{}" /s "{}"'.format(drawing,script))
        info.WorkingDirectory = folder
        info.UseShellExecute = False
        info.CreateNoWindow = True
        process = Process.Start(info)
        try:
            if not process.WaitForExit(45000):
                process.Kill()
                process.WaitForExit()
                raise ValueError('Reading CAD text timed out.')
            if process.ExitCode or not os.path.isfile(output):
                raise ValueError('AutoCAD could not read this drawing.')
        finally:
            process.Dispose()
        with io.open(output, encoding='utf-8-sig') as stream:
            units = _FEET.get(int(next(stream).strip()))
            if not units:
                raise ValueError('DWG drawing units are unspecified or unsupported.')
            rows=[]
            for line in stream:
                fields=line.strip().split('\t',4)
                if len(fields)!=5:
                    continue
                layer,x,y,height,value=fields
                if not re.match(r'^[\w.-]+$',value) or len(value)>32:
                    continue
                rows.append((layer,float(x)*units,float(y)*units,float(height)*units,value))
            return rows
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def match_label(axis, labels, layers):
    a,b=axis
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=math.hypot(dx,dy)
    choices=[]
    for layer,x,y,h,value in labels:
        if layer not in layers and not any(s in layer.upper() for s in ('GRID','AXIS','AXES')):
            continue
        h=max(h,.01)
        perp=abs((x-a[0])*dy-(y-a[1])*dx)/length
        end=min(math.hypot(x-p[0],y-p[1]) for p in (a,b))
        if perp<=2*h and end<=6*h:
            choices.append(value)
    names=set(choices)
    return choices[0] if len(names)==1 else None


def letters(number):
    result=''
    while number:
        number,remainder=divmod(number-1,26)
        result=chr(65+remainder)+result
    return result


def fill_names(anchors,vertical,used):
    """Fill unnamed intervals from the preceding real label; reserve real labels first."""
    used.update(s.lower() for s in anchors if s)
    result=[]
    prefix=None
    suffix=0
    sequence=0
    for original in anchors:
        if original:
            base,separator,tail=original.rpartition('.')
            if separator and base and tail.isdigit():
                prefix,suffix=base,int(tail)
            else:
                prefix,suffix=original,0
            result.append(original)
            continue
        while True:
            if prefix:
                suffix+=1
                value='{}.{}'.format(prefix,suffix)
            else:
                sequence+=1
                value=str(sequence) if vertical else letters(sequence)
            if value.lower() not in used:
                break
        used.add(value.lower())
        result.append(value)
    return result
