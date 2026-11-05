"""Load presend_attempt + presend_attempt_land joined by sig (AMS runs). READ-ONLY on local copies."""
import json, glob, os
RUNS = {'r49':'ams_r49','r50':'ams_r50','r51':'ams_r51','r52':'ams_r52','r53':'ams_r53','r54':'ams_r54','r55':'ams_r55_snap'}
BASE='/home/moiz/sniper-data/runs/'
def main_file(d):
    return [f for f in glob.glob(BASE+d+'/*.jsonl') if not f.endswith('obs.jsonl')][0]
def load(run):
    att={}; out=[]
    for l in open(main_file(RUNS[run])):
        if '"presend_attempt' not in l: continue
        try: e=json.loads(l)
        except: continue
        if e['ev']=='presend_attempt': att[e['sig']]=e
        elif e['ev']=='presend_attempt_land':
            a=att.get(e['sig'],{}); e['_a']=a; e['run']=run; out.append(e)
    return out
