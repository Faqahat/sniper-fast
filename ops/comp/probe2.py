import json,sys,time
sys.path.insert(0,"/root/indep")
from common import rpc
from concurrent.futures import ThreadPoolExecutor
x=rpc("getSignaturesForAddress",["HQRmxtF9"+"",{"limit":10}]) 
