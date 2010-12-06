#! /opt/antelope/5.0-64/local/bin/python 


# Import statements
#{{{
import sys
import os
import getopt
import re
import numpy as np
import math as math
from datetime import datetime
from collections import defaultdict
from time import gmtime

sys.path.append( os.environ['ANTELOPE'] + '/local/data/python' )
import antelope.stock as stock
from antelope.datascope import *
#}}}
# Set defaults
#{{{
pfname  = 'dbmoment'
chan_to_use = 'LH*'
model_type = 'v'
isoflag = 5
dw = False
trim_value = 0.6
statmax = 20
event_db = ''
green_db = ''
wave_db = ''
resp_db = ''
filters = {}
mag_filters = {}
fstring = None
verbose = False
debug = False
flag = 0
#}}}
def usage():
#{{{
    print 'Usage: dbmoment.py [-vV] [-p pfname] orid'
#}}}
def logmt(flag,message):
#{{{
    from time import time
    curtime = stock.strtime(time())
    if not flag:
        return
    elif flag < 3:
        print curtime,message
    else:
        print curtime,'ERROR:',message,'--> exiting'
        sys.exit(-1)
#}}}
def configure():
#{{{zo
# Check command line options
    try:
        opts,pargs = getopt.getopt(sys.argv[1:],'vVp:')
    except getopt.GetoptError:
        usage()
        sys.exit(-1)
    if(len(pargs) != 1):
        usage()
        sys.exit(-1)
    else:
        orid = pargs[0]
# Get command line options
    for option, value in opts:
        if option in ('-v'):
            globals()['verbose'] = True
        if option in ('-V'):
            globals()['verbose'] = True
            globals()['debug'] = True
        if option in ('-p'):
            globals()['pfname'] = value
# Get parameters from pf-file
    globals()['chan_to_use'] = stock.pfget_string(pfname,'chan_to_use')
    globals()['trim_value']  = stock.pfget_string(pfname,'trim_value')
    if(stock.pfget_string(pfname,'isoflag') == 1): globals()['isoflag'] = 6
    globals()['model_type']  = stock.pfget_string(pfname,'model_type')
    globals()['statmax']     = stock.pfget_int(pfname,'statmax')
    globals()['event_db']    = stock.pfget_string(pfname,'event_db')
    globals()['wave_db']     = stock.pfget_string(pfname,'wave_db')
    globals()['green_db']    = stock.pfget_string(pfname,'green_db')
    globals()['resp_db']     = stock.pfget_string(pfname,'resp_db')
    globals()['filters']     = stock.pfget_arr(pfname,'filters')
    globals()['mag_filters'] = stock.pfget_arr(pfname,'mag_filters')
    if(stock.pfget_string(pfname,'distance_weighting') == 'on'): globals()['dw'] = True
    if not wave_db: globals()['wave_db'] = event_db
    if not resp_db: globals()['resp_db'] = event_db

    return orid
#}}}
def get_view_from_db(orid):
#{{{
    if not os.path.isfile(event_db):
        logmt(3,'Database (%s) does not exist' % event_db)
    evdb = dbopen(event_db,'r')
    evdb = dblookup(evdb,'','origin','','')
    logmt(verbose,'Processing origin %s' %orid)
    evdb = dbsubset(evdb,'orid == %s' % orid)
    if evdb.nrecs() == 0:
        logmt(3,'Origin id (%s) does not exist in origintable'%orid)
    evdb = dbjoin(evdb,'netmag')
    if evdb.nrecs() == 0:
        logmt(3,'Could not join netmag tabel for orid %s' % orid)
    evparams = {}
    evdb[3] = 0
    for field in dbquery(evdb,'dbTABLE_FIELDS'):
        try: 
            evparams[field] = evdb.getv(field)
        except: logmt(3,'Could not find field %s in join of origin and netmag table for orid %s' % (field,orid))

    evdb = dbjoin(evdb,'assoc')
    evdb = dbjoin(evdb,'arrival')
    evdb = dbsort(evdb,'delta')
    evdb = dbsubset(evdb,'iphase=~/.*P.*|.*p.*/')
    if evdb.nrecs() == 0:
        logmt(3,'No arrivals for selected origin')
    for line in mag_filters:
        splitline = line.split()
        if not len(splitline)==3:
            lm,flt=splitline
        else:
            lm,um,flt = splitline
        if (float(evparams['magnitude'][0]) > float(lm) and float(evparams['magnitude'][0]) < float(um)):
            flt = flt.replace('_',' ')
            globals()['fstring'] = flt
    return(evdb,evparams)
#}}}
def choose_chan(wvstadb):
#{{{
    view = dbsort(wvstadb,'samprate',unique=True)
    for i in range(view.nrecs()):
        view[3]=i
        chan = dbgetv(view,'chan')
        chanview = dbsubset(wvstadb,'chan =~ /%s.*/' % chan[0][:2])
        chanview = dbsort(chanview,'chan',unique=True)
        channels = []
        if chanview.nrecs() == 3:
            for j in range(chanview.nrecs()):
                chanview[3] = j
                chan = dbgetv(chanview,'chan')
                channels.append(chan[0])
        else:
            logmt(verbose,'Did not find 3 components for %s, trying higher sample rate' % chan)
            channels = []
            continue
        if len(channels) == 3:
            break
    return channels
#}}}
def get_chan_data():
#{{{
    wvdb = dbopen(wave_db,'r')
    wvdb = dblookup(wvdb,'','wfdisc','','')
    wvdb = dbsubset(wvdb,'samprate>=0.9')
    try:
        wvdb = dbsubset(wvdb,'chan =~/%s/' % chan_to_use)
    except:
        logmt(3,'No records found in wfdisc table (%s.wfdisc)' %wave_db) 
    numrec = evdb.nrecs()
    if numrec > int(statmax): numrec = int(statmax)
    logmt(verbose,'Processing %s stations for orid %s' % (numrec,orid))
    stachan_traces = {}
    counter = 0
    for i in range(evdb.nrecs()):
        evdb[3] = i
        (sta,at) = dbgetv(evdb,'sta','arrival.time')
        st = at - 12 
        et = at + 12
        wvstadb = dbsubset(wvdb,'sta=~/^%s$/' % sta)
        logmt(debug,'Looking for channels with a sample rate >= 1 Hz for sta = %s' % sta)
        try:
            chans = choose_chan(wvstadb)
        except:
            logmt(verbose,'No channels found with a sample-rate >= 1 Hz for sta = %s' % sta)
        logmt(debug,'Channels found: %s %s %s' % (chans[0],chans[1],chans[2]))
        foundchans = []
        for chan in chans:
            stachan = '%s_%s' % (sta,chan)
            trace = trloadchan(wvstadb,st,et,sta,chan)
            trsplice(trace)
            ns_tra = 0
            ns_req = 0
            for j in range(dbquery(trace,'dbRECORD_COUNT')):
                trace[3] = j
                (ns,sr) = dbgetv(trace,'nsamp','samprate')
                ns_tra += ns
                ns_req += int((et-st)*sr)
            if not ns_tra == ns_req:
                logmt(verbose,'Incorrect number of samples for %s, skipping %s' % (stachan,sta))
                for delchan in foundchans:
                    if stachan_traces[delchan]:
                        del stachan_traces[delchan]
                        logmt(debug,'Deleting channel %s' % delchan)
                        counter -= 1
            trapply_calib(trace)
            trfilter(trace,fstring)
            stachan_traces[stachan] = trace   
            logmt(debug,'Trace extracted for %s' % stachan)
            foundchans.append(stachan)
            counter += 1
        if counter == statmax*3:
            break
    return (stachan_traces)
#}}}
def construct_matrix(stachan_traces,evdb):

    numsta = 0
    numchan = 0
    for stachan,trace in sorted(stachan_traces.items()):
        sta,chan = stachan.split('_')
        trace[3] = 0
        tr = trdata(trace)
        test = np.correlate(tr,tr,'full')
        counter = -len(test)/2 +1
        maxcoef = 0
        coef = 0
        for i in test:
            if i > maxcoef:
                maxcoef = i
                coef = counter
            counter += 1 
        if dw == True:
            logmt(debug,'Apply distance weighting')
        
        staevdb = dbsubset(evdb,'sta =~ /^%s$/' % sta)
        staevdb[3] = 0
        azim = dbgetv(evdb,'seaz')
        if chan[2:] == 'E':
            numchan += 1
            for j in range(len(tr)):
                #sse[numsta][j] = tr[j]
                s[chan[2:]][numsta][j] = tr[j]
        if chan[2:] == 'N':
            numchan += 1
            for j in range(len(tr)):
                #ssn[numsta][j] = tr[j]
                s[chan[2:]][numsta][j] = tr[j]
        if chan[2:] == 'Z':
            numchan += 1
            for j in range(len(tr)):
                #ssz[numsta][j] = tr[j]
                s[chan[2:]][numsta][j] = tr[j]
        if numchan == 3:
            numchan = 0
            numsta += 1
    return(s)

def cross_cor(a,b):
    #{{{
    xcor  = np.correlate(a.values(),b.values(),'full')
    pr = len(xcor)/2 
    maxval  = 0
    maxcoef = 0
    for j in range(pr):
        if abs(xcor[j+pr]) > maxval:
            maxval = abs(xcor[j+pr])
            maxcoef = j+1
    return (maxval,maxcoef)
#}}}

orid = configure()
(evdb,evparams) = get_view_from_db(orid)
stachan_traces = get_chan_data()

sse = defaultdict(dict) 
ssn = defaultdict(dict) 
ssz = defaultdict(dict) 
s = defaultdict(lambda: defaultdict(defaultdict))

(s) = construct_matrix(stachan_traces,evdb)

print s

exit()

# Declare matrices (data and Green's functions

sst = defaultdict(dict) 
ssr = defaultdict(dict) 
ssz = defaultdict(dict) 

def get_greens_functions(evdb):
#{{{
    tmp = {}
    green_pf = 'pf/create_green'
    ddist = stock.pfget_string(green_pf,'ddist')
    dazim = stock.pfget_string(green_pf,'dazim')
    ddip = stock.pfget_string(green_pf,'ddip')
    ddepth = stock.pfget_string(green_pf,'ddepth')
    if not os.path.isfile(green_db):
        logmt(3,'Database (%s) does not exist' % green_db)

    gdb = dbopen(green_db,'r')
    gdb = dblookup(gdb,'','moment_tensor_greensfuncs','','')
    for i in range(evdb.nrecs()):

        evdb[3] = i
        (sta,delta,seaz) = evdb.getv('sta','delta','seaz')
        ddist = float(ddist)
        dazim = float(dazim)
        expr = 'delta > %s && delta <= %s ' % (delta-ddist/2,delta+ddist/2)
        expr += '&& azimuth > %s && azimuth <= %s ' % (seaz-dazim/2,seaz+dazim/2)
        print expr
        subgdb = dbsubset(gdb,expr)
        try:
            subgdb = dbsubset(gdb,expr)
            subgdb[3] = 0
            (dir,file) = subgdb.getv('dir','dfile')       
            dir += '/%s' % file 
            tmp[sta] = dir
        except:
            logmt(verbose,'No Green\'s function found for %s' % sta)
    return(tmp)
#}}}

green_funcs  = {}
#greens_funcs = get_greens_functions(evdb)


W = []
for i in range(len(sst)):
    W.append(1.0)

# sse contains east, ssn north and ssz vertical component traces

# read the Green's function from database......based on distance and depth.....

######################################################################################################
# Reading test data and Green;s functions....from file                                               #
#{{{
az = [10,40,50]
for j in range(3):
    j += 1
    data =  open('data/data%d' % j,'r')
    samples = []
    for line in data:
        tmp = line.split()
        for samp in tmp:
            samples.append(float(samp))
    data.close()
    for i in range(200):
        sst[j-1][i] = samples.pop(0)
    for i in range(200):
        ssr[j-1][i] = samples.pop(0)
    for i in range(200):
        ssz[j-1][i] = samples.pop(0)


greens = []
green = open('data/green','r')
for line in green:
    for j in range(len(line)/12):
        greens.append(line[j*12:j*12+12]) 
green.close()

g = defaultdict(lambda: defaultdict(defaultdict))
for i in range(3):
    for k in range(8):
        for j in range(200):
            g[k][i][j] = float(greens[j + k*200])
            if k in [5,6,7]:
                g[k][i][j] *= -1
    if isoflag == 5:
        for k in [8,9]:
            for j in range(200):
                g[k][i][j] = 0.0
    if isoflag == 6:
        for k in [8,9]:
            for j in range(200):
                g[k][i][j] = float(greens[j + k*200])
#}}}
######################################################################################################


def get_time_shift():
#{{{
    for i in range(len(sst)):
        shift = 0
        xcor  = 0
        if cross_cor(sst[i],g[0][i])[0] > xcor:
            xcor  = cross_cor(sst[i],g[0][i])[0]
            shift = cross_cor(sst[i],g[0][i])[1]
        if cross_cor(sst[i],g[1][i])[0] > xcor:
            xcor = cross_cor(sst[i],g[1][i])[0]
            shift = cross_cor(sst[i],g[1][i])[1]
        if cross_cor(ssr[i],g[2][i])[0] > xcor:
            xcor = cross_cor(ssr[i],g[2][i])[0]
            shift = cross_cor(ssr[i],g[2][i])[1]
        if cross_cor(ssr[i],g[3][i])[0] > xcor:
            xcor = cross_cor(ssr[i],g[3][i])[0]
            shift = cross_cor(ssr[i],g[3][i])[1]
        if cross_cor(ssr[i],g[4][i])[0] > xcor:
            xcor = cross_cor(ssr[i],g[4][i])[0]
            shift = cross_cor(ssr[i],g[4][i])[1]
        if cross_cor(ssz[i],g[5][i])[0] > xcor:
            xcor = cross_cor(ssz[i],g[5][i])[0]
            shift = cross_cor(ssz[i],g[5][i])[1]
        if cross_cor(ssz[i],g[6][i])[0] > xcor:
            xcor = cross_cor(ssz[i],g[6][i])[0]
            shift = cross_cor(ssz[i],g[6][i])[1]
        if cross_cor(ssz[i],g[7][i])[0] > xcor:
            xcor = cross_cor(ssz[i],g[7][i])[0]
            shift = cross_cor(ssz[i],g[7][i])[1]
        timeshift.append(shift)
    return(timeshift)
#}}}

timeshift = []
timeshift = get_time_shift()
trim = 0

def matrix_AIV_B(g,s):
#{{{
    AJ = defaultdict(dict) 
    cnt1=cnt2=cnt3 = 0
    trim  = int(len(sst[0])*float(trim_value))
    for i in range(len(sst)):
        cnt1=cnt2=cnt3
        cnt2 += len(sst[0])-trim
        cnt3 += 2*len(sst[0])-2*trim
        az[i] *= math.pi/180
        for j in range(len(sst[0])-trim):
            AJ[0][cnt1] =  math.sin(2*az[i])*g[0][i][j]/2
            AJ[1][cnt1] = -math.sin(2*az[i])*g[0][i][j]/2
            AJ[2][cnt1] = -math.cos(2*az[i])*g[0][i][j]
            AJ[2][cnt2] = -math.sin(2*az[i])*g[2][i][j]
            AJ[2][cnt3] = -math.sin(2*az[i])*g[5][i][j]
            AJ[3][cnt1] = -math.sin(az[i])*g[1][i][j]
            AJ[3][cnt2] =  math.cos(az[i])*g[3][i][j]
            AJ[3][cnt3] =  math.cos(az[i])*g[6][i][j]
            AJ[4][cnt1] =  math.cos(az[i])*g[1][i][j]
            AJ[4][cnt2] =  math.sin(az[i])*g[3][i][j]
            AJ[4][cnt3] =  math.sin(az[i])*g[6][i][j]
            if isoflag == 5:
                AJ[0][cnt2] = (g[4][i][j])/2 - (math.cos(2*az[i])*g[2][i][j])/2
                AJ[0][cnt3] = (g[7][i][j])/2 - (math.cos(2*az[i])*g[5][i][j])/2
                AJ[1][cnt2] = (g[4][i][j])/2 + (math.cos(2*az[i])*g[2][i][j])/2
                AJ[1][cnt3] = (g[7][i][j])/2 + (math.cos(2*az[i])*g[5][i][j])/2
            if isoflag == 6:
                AJ[0][cnt2] = (g[4][i][j])/6 - (math.cos(2*az[i])*g[2][i][j])/2 + (g[8][i][j])/3
                AJ[0][cnt3] = (g[7][i][j])/6 - (math.cos(2*az[i])*g[5][i][j])/2 + (g[9][i][j])/3
                AJ[1][cnt2] = (g[4][i][j])/6 + (math.cos(2*az[i])*g[2][i][j])/2 + (g[8][i][j])/3
                AJ[1][cnt3] = (g[7][i][j])/6 + (math.cos(2*az[i])*g[5][i][j])/2 + (g[9][i][j])/3
                AJ[5][cnt1] = 0.0
                AJ[5][cnt2] = (g[8][i][j])/3  - (g[4][i][j])/3
                AJ[5][cnt3] = (g[9][i][j])/3 - (g[7][i][j])/3
            cnt1 += 1
            cnt2 += 1
            cnt3 += 1
    AIV = defaultdict(dict) 
    for i in range(isoflag):
        for j in range(isoflag):
            AIV[i][j] = 0.0
    for i in range(5):
        for j in range(5):
            for k in range(cnt3):
                AIV[i][j] += AJ[i][k]*AJ[j][k]

    B = defaultdict(dict) 
    for i in range(isoflag):
        B[i][0] = 0.0
    cnt1 = cnt2 = cnt3 = 0
    tmp = defaultdict(dict) 
    for i in range(len(sst)):
    
        cnt1 = cnt2 = cnt3
        cnt2 += len(sst[0])-trim
        cnt3 += 2*(len(sst[0])-trim)
        for j in range(len(sst[0])-trim):
            tmp[cnt1] = sst[i][j+timeshift[i]]
            tmp[cnt2] = ssr[i][j+timeshift[i]]
            tmp[cnt3] = ssz[i][j+timeshift[i]]
            cnt1 += 1
            cnt2 += 1
            cnt3 += 1
    
    for i in range(isoflag):
        for j in range(cnt3):
            B[i][0] += AJ[i][j]*tmp[j]
    return(AIV,B)
#}}}

AIV = defaultdict(dict)
B = defaultdict(dict) 
(AIV,B) = matrix_AIV_B()

def swap(a,b):
#{{{
    tmp = a
    a = b
    b = tmp
    return(a,b)

#}}}
def dyadic(v,n1,n2,c):
#{{{
    tmp = np.matrix([[0.,0.,0.],[0.,0.,0.],[0.,0.,0.]])
    for i in range(3):
        for j in range(3):
            tmp[i,j] = v[i,n1]*v[j,n2]*c
    return(tmp)
    #}}}
def det_solution_vec(AIV,B):
#{{{
    ipiv = defaultdict(dict)
    for i in range(isoflag):
        ipiv[i] = 0
    for i in range(isoflag):
        big = 0.0
        for j in range(isoflag):
            if ipiv[j] != 1:
                for k in range(isoflag):
                    if ipiv[k] == 0:
                        if abs(AIV[j][k]) >= big:
                                big = abs(AIV[j][k])
                                irow = j
                                icol = k
                    elif ipiv[k] > 1:
                        print 'error......1'
        ipiv[icol] += 1
        if not irow == icol:
            for l in range(isoflag):
                (AIV[irow][l],AIV[icol][l]) = swap(AIV[irow][l],AIV[icol][l])
            for l in range(1):
                (B[irow][l],B[icol][l]) = swap(B[irow][l],B[icol][l])
        if AIV[icol][icol] == 0.0:
            print 'error.....2'
        pivinv = 1.0/AIV[icol][icol]
        AIV[icol][icol] = 1.0
        for l in range(isoflag):
            AIV[icol][l] *= pivinv
        for l in range(1):
            B[icol][l] *= pivinv
        for h in range(isoflag):
            if h != icol:
                dum = AIV[h][icol]
                AIV[h][icol] = 0.0
                for l in range(isoflag):
                    AIV[h][l] -= AIV[icol][l]*dum
                for l in range(1):
                    B[h][l] -= B[icol][l]*dum
    gfscale = 1.0e+20
    if isoflag == 6:
        M = -gfscale*np.matrix([[B[0][0],B[2][0],B[3][0]],[B[2][0],B[1][0],B[4][0]],[B[3][0],B[4][0],B[5][0]]])
    if isoflag == 5:
        M = -gfscale*np.matrix([[B[0][0],B[2][0],B[3][0]],[B[2][0],B[1][0],B[4][0]],[B[3][0],B[4][0],-(B[0][0]+B[1][0])]])
    
#    Coded in the original code by Doug Dreger, however, AIV is not used further in the program, so not needed???
#
#    indc = defaultdict(dict)
#    indr = defaultdict(dict)
#    for i in range(isoflag-1,0,-1):
#        if indr[i] != indc[i]:
#            for j in range(isoflag):
#                (AIV[j][indr[i]],AIV[j][indxc[i]]) = swap(AIV[j][indr[i]],AIV[j][indxc[i]])
    return(M)
#}}}

M = det_solution_vec(AIV,B)
    

# Get eigenvalues and eigen vectors of moment tensor
def decompose_moment_tensor(M):
#{{{
    trace = 0
    for i in range(3):
        trace += M[i,i]
    trace /= 3
    
    for i in range(3):
        M[i,i] -= trace
    miso = np.matrix([[trace,0,0],[0,trace,0],[0,0,trace]])
    (eval,evec) = np.linalg.eig(M)
    
    
    
    
    for i in (0,1):
        k = i
        p = eval[i]
        for j in (1,2):
            if abs(eval[j]) < abs(p):
                k = j
                p = eval[j]
        if k != i:
            eval[k] = eval[i]
            eval[i] = p
            for j in range(3):
                p=evec[j,i]
                evec[j,i] = evec[j,k]
                evec[j,k] = p
    
    
    f = -eval[0]/eval[2]
    c = eval[2]*(1-2*f)
    a2a2 = dyadic(evec,2,2,c)
    c *= -1
    a1a1 = dyadic(evec,1,1,c)
    mdc = a2a2+ a1a1
    c = 2*eval[2]*f
    a2a2 = dyadic(evec,2,2,c)
    c = -eval[2]*f
    a1a1 = dyadic(evec,1,1,c)
    a0a0 = dyadic(evec,0,0,c)
    mclvd = a2a2+a1a1+a0a0
    
    
    dd = []
    for i in range(3):
        dd.append(abs(eval[i]))
    for i in range(3):
        for j in range(i,3):
            if dd[j] < dd[i]:
                dd[i],dd[j] = swap(dd[i],dd[j])
    eps = dd[0]/dd[2]
    pcdc = 100*(1-2*eps)
    pcclvd = 200*eps
    
    
    for i in range(3):
        if evec[2,i] < 0:
            for j in range(3):
                evec[j,i] *= -1
    
    azimuth = []
    plunge = [] 
    for i in range(3):
        if evec[1,i] == 0 and evec[0,i] == 0:
            azimuth.append(0.0)
        else:
            tmp = math.degrees(math.atan2(evec[1,i],evec[0,i]))
            if tmp < 0:
                tmp += 360
            azimuth.append(tmp)
        r = math.sqrt(evec[0,i]*evec[0,i] + evec[1,i]*evec[1,i])
        if evec[2,i] == 0 and r == 0:
            plunge.append(0.0)
        else:
            plunge.append(math.atan2(evec[2,i],r))
    
    axis = []
    axis.append('N')
    if eval[1] > eval[2]:
        axis.append('T')
        axis.append('P')
    else:
        axis.append('P')
        axis.append('T')
    
    p = []
    t = []
    for i in range(3):
        if axis[i] == 'P':
            for j in range(3):
                p.append(evec[j,i])
        elif axis[i] == 'T':
            for j in range(3):
                t.append(evec[j,i])
    con = 1/math.sqrt(2)
    tmp1 = []
    tmp2 = []
    for i in range(3):
        tmp1.append(con*(t[i]+p[i]))
        tmp2.append(con*(t[i]-p[i]))
    u  = np.matrix([[tmp1[0],tmp1[1],tmp1[2]],[tmp2[0],tmp2[1],tmp2[2]]])
    nu = np.matrix([[tmp2[0],tmp2[1],tmp2[2]],[tmp1[0],tmp1[1],tmp1[2]]])
    
    dip = []
    slip = []
    strike = []
    for i in range(2):
        dip.append(math.acos(-nu[i,2]))
        if nu[i,0] == 0 and nu[i,1] == 0:
            strike.append(0)
        else:
            strike.append(math.atan2(-nu[i,0],nu[i,1]))
    for i in range(2):
        sstr = math.sin(strike[i])
        cstr = math.cos(strike[i])
        sdip = math.sin(dip[i])
        cdip = math.cos(dip[i])
        if abs(sdip) > 0:
            lamb = math.asin(-u[i,2])/math.sin(dip[i])
        else:
            if u[i,2] > 0:
                arg = 1
            else:
                arg = -1
            if arg < 0:
                lamb = math.pi
            else:
                lamb = 0
        slamb = math.sin(lamb)
        cdsl = cdip*slamb
        if abs(sstr) > abs(cstr):
            clamb = (u[i,1]+cdsl*cstr)/sstr
        else:
            clamb = (u[i,0]-cdsl*sstr)/cstr
        if slamb == 0 and clamb == 0:
            slip.append(0)
        else:
            slip.append(math.atan2(slamb,clamb))
        if dip[i] > math.pi/2:
            dip[i] = math.pi - dip[i]
            strike[i] += math.pi
            slip[i] = 2*math.pi - slip[i]
        if strike[i] < 0:
            strike[i] += 2*math.pi
        if slip[i] > math.pi:
            slip[i] -= 2*math.pi
    

    m0 = abs(miso[0,0]) + abs(eval[2])
    Mw = math.log10(m0)/1.5 - 10.7
    pciso = abs(miso[0,0])/m0
    return (m0,Mw,strike,dip,slip,pcdc,pcclvd,pciso)
#}}}

#def fitcheck()


#fitcheck()


strike = []
dip = []
rake = []
(m0,Mw,strike,dip,rake,pcdc,pcclvd,pciso) = decompose_moment_tensor(M)

print 'M0      =',m0
print 'Mw      =',Mw 
print 'Strike  =',math.degrees(strike[0])
print 'Rake    =',math.degrees(rake[0])
print 'Dip     =',math.degrees(dip[0])
print 'Strike2 =',math.degrees(strike[1])
print 'Rake2   =',math.degrees(rake[1])
print 'Dip2    =',math.degrees(dip[1])
print 'Pdc     =',pcdc
print 'Pclvd   =',pcclvd
print 'Piso    =',pciso

#logmt(verbose,'Data matrix created for %s channels' % len(stachan_traces))